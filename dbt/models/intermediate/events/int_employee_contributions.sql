{{
  config(
    materialized='incremental',
    unique_key=['employee_id', 'simulation_year'],
    incremental_strategy='delete+insert',
    on_schema_change='sync_all_columns'
  )
}}

{# tags removed: now configured in dbt_project.yml to override directory-level EVENT_GENERATION tag #}

{% set simulation_year = var('simulation_year', 2025) | int %}

/*
  Employee 401(k) Contributions Calculator - IRS Compliant Version

  Calculates IRS-compliant 401(k) contributions with proper limit enforcement.
  No contributions will exceed IRS 402(g) limits ($23,500 base / $31,000 catch-up).

  Key Features:
  - IRS limit enforcement using LEAST() function for compliance
  - Age-based limit determination (catch-up at age 50+)
  - Full transparency with requested vs. capped amounts
  - Audit trail for all limit applications
  - Configurable limits via irs_contribution_limits seed

  Dependencies:
  - int_employee_compensation_by_year for compensation and age data
  - int_deferral_rate_state_accumulator_v2 for deferral rates (S042-01: Source of Truth Architecture Fix)
  - irs_contribution_limits for IRS limit configuration
*/

WITH simulation_parameters AS (
    SELECT {{ simulation_year }} AS current_year
),

-- Get IRS contribution limits for the simulation year (with fallback to nearest available year)
irs_limits AS (
    SELECT
        limit_year,
        base_limit,
        catch_up_limit,
        catch_up_age_threshold
    FROM {{ ref('irs_contribution_limits') }}
    WHERE limit_year = (SELECT current_year FROM simulation_parameters)
    UNION ALL
    -- Fallback: If no exact match, use the closest year (latest available if simulation year is beyond seed data)
    SELECT
        limit_year,
        base_limit,
        catch_up_limit,
        catch_up_age_threshold
    FROM {{ ref('irs_contribution_limits') }}
    WHERE NOT EXISTS (
        SELECT 1 FROM {{ ref('irs_contribution_limits') }}
        WHERE limit_year = (SELECT current_year FROM simulation_parameters)
    )
    ORDER BY ABS(limit_year - (SELECT current_year FROM simulation_parameters))
    LIMIT 1
),

-- FIX: Get the most recent deferral rate for each employee up to the current simulation year
-- This handles cases where rates are set in a prior year and carry forward.
deferral_rates_ranked AS (
    SELECT
        employee_id,
        current_deferral_rate,
        is_enrolled_flag,
        data_quality_flag,
        ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY simulation_year DESC) as rn
    FROM {{ ref('int_deferral_rate_state_accumulator_v2') }}
    WHERE simulation_year <= (SELECT current_year FROM simulation_parameters)
),

deferral_rates AS (
    SELECT
        employee_id,
        COALESCE(current_deferral_rate, 0.0) AS deferral_rate,
        COALESCE(is_enrolled_flag, false) AS is_enrolled_flag,
        data_quality_flag AS source_quality
    FROM deferral_rates_ranked
    WHERE rn = 1
),

-- Removed legacy CTEs in favor of workforce_proration as the single source

-- Epic E078: Mode-aware query - uses fct_yearly_events in Polars mode, int_hiring_events in SQL mode
hire_events AS (
    {% if var('event_generation_mode', 'sql') == 'polars' %}
    -- Polars mode: fct_yearly_events is populated from Parquet files before EVENT_GENERATION
    SELECT
        employee_id,
        effective_date::DATE AS hire_date,
        compensation_amount AS annual_salary,
        employee_age
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = (SELECT current_year FROM simulation_parameters)
      AND event_type = 'hire'
    {% else %}
    -- SQL mode: Use intermediate event model that exists during EVENT_GENERATION
    SELECT
        employee_id,
        effective_date::DATE AS hire_date,
        compensation_amount AS annual_salary,
        employee_age
    FROM {{ ref('int_hiring_events') }}
    WHERE simulation_year = (SELECT current_year FROM simulation_parameters)
    {% endif %}
),

-- Epic E078: Mode-aware query - uses fct_yearly_events in Polars mode, int_termination_events in SQL mode
termination_events AS (
    {% if var('event_generation_mode', 'sql') == 'polars' %}
    -- Polars mode: fct_yearly_events is populated from Parquet files before EVENT_GENERATION
    SELECT
        employee_id,
        effective_date::DATE AS termination_date
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = (SELECT current_year FROM simulation_parameters)
      AND event_type = 'termination'
    {% else %}
    -- SQL mode: Use intermediate event model that exists during EVENT_GENERATION
    SELECT
        employee_id,
        effective_date::DATE AS termination_date
    FROM {{ ref('int_termination_events') }}
    WHERE simulation_year = (SELECT current_year FROM simulation_parameters)
    {% endif %}
),

-- Workforce proration base: include prior-year actives (snapshot) and current-year new hires
-- FIX: Add LEFT JOIN with termination events to properly handle terminated employees
snapshot_proration AS (
    SELECT
        comp.employee_id,
        {{ simulation_year }} AS simulation_year,
        comp.employee_compensation AS current_compensation,
        -- FIX: Calculate prorated compensation for terminated employees
        CASE
            WHEN term.termination_date IS NOT NULL THEN
                ROUND(
                    comp.employee_compensation *
                    LEAST(365, GREATEST(0,
                        DATEDIFF('day', ({{ simulation_year }} || '-01-01')::DATE, term.termination_date) + 1
                    )) / 365.0
                , 2)
            ELSE comp.employee_compensation
        END AS prorated_annual_compensation,
        -- FIX: Update employment status to 'terminated' when termination events exist
        CASE
            WHEN term.termination_date IS NOT NULL THEN 'terminated'
            ELSE comp.employment_status
        END AS employment_status,
        -- FIX: Set termination_date field properly
        term.termination_date,
        comp.employee_birth_date,
        comp.current_age
    FROM {{ ref('int_employee_compensation_by_year') }} comp
    LEFT JOIN termination_events term ON comp.employee_id = term.employee_id
    WHERE comp.simulation_year = (SELECT current_year FROM simulation_parameters)
      -- CRITICAL FIX (E055): Exclude new hires from snapshot to prevent duplication
      -- New hires should only appear in new_hire_proration with correct proration
      AND NOT EXISTS (
          SELECT 1 FROM hire_events h
          WHERE h.employee_id = comp.employee_id
      )
),

new_hire_proration AS (
    SELECT
        h.employee_id,
        {{ simulation_year }} AS simulation_year,
        h.annual_salary AS current_compensation,
        -- Prorate from hire to termination (if any) else year end
        ROUND(
            h.annual_salary *
            LEAST(365, GREATEST(0,
                DATEDIFF('day', h.hire_date, COALESCE(t.termination_date, ({{ simulation_year }} || '-12-31')::DATE)) + 1
            )) / 365.0
        , 2) AS prorated_annual_compensation,
        CASE WHEN t.termination_date IS NULL THEN 'active' ELSE 'terminated' END AS employment_status,
        t.termination_date,
        NULL::DATE AS employee_birth_date,
        h.employee_age AS current_age
    FROM hire_events h
    LEFT JOIN termination_events t USING (employee_id)
),

workforce_proration AS (
    -- Union of snapshot population and current-year new hires
    SELECT * FROM snapshot_proration
    UNION ALL
    SELECT * FROM new_hire_proration
),


-- Calculate IRS-compliant contributions for ALL employees
employee_contributions AS (
    SELECT
        wf.employee_id,  -- Use workforce_proration as primary source
        {{ simulation_year }} AS simulation_year,
        wf.current_age,
        wf.current_compensation,
        wf.prorated_annual_compensation,
        wf.employment_status,
        COALESCE(dr.is_enrolled_flag, false) AS is_enrolled_flag,
        COALESCE(dr.deferral_rate, 0.0) AS effective_annual_deferral_rate,
        COALESCE(dr.deferral_rate, 0.0) AS final_deferral_rate,

        -- Calculate requested contribution amount (before IRS limits)
        wf.prorated_annual_compensation * COALESCE(dr.deferral_rate, 0.0) AS requested_contribution_amount,

        -- Determine applicable IRS limit based on age
        CASE
            WHEN wf.current_age >= il.catch_up_age_threshold
            THEN il.catch_up_limit
            ELSE il.base_limit
        END AS applicable_irs_limit,

        -- Calculate IRS-compliant contribution amount using LEAST()
        LEAST(
            (wf.prorated_annual_compensation * COALESCE(dr.deferral_rate, 0.0)),
            CASE
                WHEN wf.current_age >= il.catch_up_age_threshold
                THEN il.catch_up_limit
                ELSE il.base_limit
            END
        ) AS annual_contribution_amount,

        -- Transparency and audit fields
        CASE
            WHEN (wf.prorated_annual_compensation * COALESCE(dr.deferral_rate, 0.0)) >
                 CASE WHEN wf.current_age >= il.catch_up_age_threshold
                      THEN il.catch_up_limit ELSE il.base_limit END
            THEN true ELSE false
        END AS irs_limit_applied,

        -- Amount that was capped off due to IRS limits
        GREATEST(0,
            (wf.prorated_annual_compensation * COALESCE(dr.deferral_rate, 0.0)) -
            CASE WHEN wf.current_age >= il.catch_up_age_threshold
                 THEN il.catch_up_limit ELSE il.base_limit END
        ) AS amount_capped_by_irs_limit,

        -- Age-based limit type for reporting
        CASE WHEN wf.current_age >= il.catch_up_age_threshold THEN 'CATCH_UP' ELSE 'BASE' END AS limit_type,

        -- Set contribution base
        -- Base used for contributions and employer match calculations
        wf.prorated_annual_compensation AS total_contribution_base_compensation,
        -- Basic contribution metrics (updated to use IRS-compliant amount)
        1 AS number_of_contribution_periods,
        365 AS total_contribution_days,
        -- Average per paycheck computed after deriving total periods
        0.0 AS average_per_paycheck_contribution,
        -- Pay periods prorated by compensation ratio relative to full-year comp
        CAST(ROUND(
            CASE WHEN COALESCE(wf.current_compensation, 0) > 0 THEN
                26 * LEAST(1.0, GREATEST(0.0, COALESCE(wf.prorated_annual_compensation, 0.0) / NULLIF(wf.current_compensation, 0)))
            ELSE 26 END
        ) AS INTEGER) AS total_pay_periods_with_contributions,
        CAST('{{ simulation_year }}-01-01' AS DATE) AS first_contribution_date,
        COALESCE(wf.termination_date, CAST('{{ simulation_year }}-12-31' AS DATE)) AS last_contribution_date,
        -- FIX: Should be 'partial_year' for terminated employees, 'full_year' for active
        CASE
            WHEN wf.employment_status = 'terminated' OR wf.termination_date IS NOT NULL THEN 'partial_year'
            ELSE 'full_year'
        END AS contribution_duration_category,
        CASE
            WHEN (wf.prorated_annual_compensation * COALESCE(dr.deferral_rate, 0.0)) >
                 CASE WHEN wf.current_age >= il.catch_up_age_threshold
                      THEN il.catch_up_limit ELSE il.base_limit END
            THEN 'IRS_LIMITED'
            ELSE 'NORMAL'
        END AS contribution_quality_flag,
        CURRENT_TIMESTAMP AS calculated_at,
        'E036_single_source_deferral_rate_fixed' AS calculation_source,
        COALESCE(dr.source_quality, 'default_zero') AS deferral_rate_source_quality
    FROM workforce_proration wf
    LEFT JOIN deferral_rates dr ON wf.employee_id = dr.employee_id
    CROSS JOIN irs_limits il  -- Cross join since we only have one row of limits
    WHERE wf.employee_id IS NOT NULL  -- Include all employees regardless of status
),

-- Final output with IRS-compliant contributions and audit trail
final_contributions AS (
    SELECT
        employee_id,
        simulation_year,
        current_age,
        -- IRS-compliant contribution amounts
        annual_contribution_amount,  -- This is now IRS-capped
        effective_annual_deferral_rate,
        total_contribution_base_compensation,
        number_of_contribution_periods,
        total_contribution_days,
        CASE WHEN total_pay_periods_with_contributions > 0
             THEN annual_contribution_amount / total_pay_periods_with_contributions
             ELSE annual_contribution_amount END AS average_per_paycheck_contribution,
        total_pay_periods_with_contributions,
        first_contribution_date,
        last_contribution_date,
        current_compensation,
        prorated_annual_compensation,
        employment_status,
        is_enrolled_flag,
        final_deferral_rate,
        contribution_duration_category,
        contribution_quality_flag,
        -- Temporary compatibility alias for downstream tools/scripts
        -- DEPRECATE after 2025-09-30
        contribution_quality_flag AS data_quality_flag,
        calculated_at,
        calculation_source,
        deferral_rate_source_quality,
        -- IRS compliance and transparency fields
        requested_contribution_amount,      -- Original amount before IRS limits
        applicable_irs_limit,              -- Age-appropriate IRS limit
        irs_limit_applied,                 -- Boolean flag for limit enforcement
        amount_capped_by_irs_limit,        -- Amount that was reduced
        limit_type
    FROM employee_contributions
)

SELECT *
FROM (
  SELECT fc.*, ROW_NUMBER() OVER (PARTITION BY employee_id, simulation_year ORDER BY employee_id) AS rn
  FROM final_contributions fc
)
WHERE rn = 1

{% if is_incremental() %}
    -- Incremental processing - only include current simulation year
    AND simulation_year = {{ simulation_year }}
{% endif %}
-- ORDER BY removed to avoid CTAS ordering issues on some adapters

/*
  IRS Compliance Notes:
  - All contributions are capped at IRS 402(g) limits
  - Age-based catch-up contributions supported (age 50+)
  - Full transparency with requested vs. capped amounts
  - Configurable limits via irs_contribution_limits seed
  - Zero tolerance for IRS limit violations
  - Complete audit trail for compliance reporting
*/
