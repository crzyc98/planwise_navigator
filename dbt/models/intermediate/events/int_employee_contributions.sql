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
  No contributions will exceed IRS 402(g) limits ($23,500 base / $31,000 catch-up / $34,750 super catch-up).

  Key Features:
  - IRS limit enforcement using LEAST() function for compliance
  - SECURE 2.0 super catch-up for ages 60-63 ($11,250 vs $7,500)
  - Age-based limit determination (catch-up at age 50+, super catch-up at ages 60-63)
  - Full transparency with requested vs. capped amounts
  - Audit trail for all limit applications
  - Configurable limits via config_irs_limits seed

  Dependencies:
  - int_employee_compensation_by_year for compensation and age data
  - int_deferral_rate_state_accumulator for deferral rates (S042-01: Source of Truth Architecture Fix)
  - config_irs_limits for IRS limit configuration
*/

WITH simulation_parameters AS (
    SELECT {{ simulation_year }} AS current_year
),

-- Get IRS contribution limits for the simulation year (with fallback to nearest available year)
irs_limits_exact AS (
    SELECT
        limit_year,
        base_limit,
        catch_up_limit,
        catch_up_age_threshold,
        super_catch_up_limit,
        super_catch_up_age_min,
        super_catch_up_age_max
    FROM {{ ref('config_irs_limits') }}
    WHERE limit_year = (SELECT current_year FROM simulation_parameters)
),

-- Fallback: If no exact match, use the closest year (latest available if simulation year is beyond seed data)
irs_limits_fallback AS (
    SELECT
        limit_year,
        base_limit,
        catch_up_limit,
        catch_up_age_threshold,
        super_catch_up_limit,
        super_catch_up_age_min,
        super_catch_up_age_max
    FROM {{ ref('config_irs_limits') }}
    WHERE NOT EXISTS (SELECT 1 FROM irs_limits_exact)
    ORDER BY ABS(limit_year - (SELECT current_year FROM simulation_parameters))
    LIMIT 1
),

irs_limits AS (
    SELECT * FROM irs_limits_exact
    UNION ALL
    SELECT * FROM irs_limits_fallback
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
    FROM {{ ref('int_deferral_rate_state_accumulator') }}
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

-- Feature 101: Same-year enroll → opt-out active-enrollment window.
-- The year-end deferral rate is 0 (post-opt-out), so recover the deferral rate
-- that was in effect during the enrollment window from the enrollment event payload,
-- mirroring int_deferral_rate_state_accumulator's parse.
enroll_optout_window AS (
    SELECT
        employee_id,
        MAX(CASE WHEN event_type = {{ evt_enrollment() }} THEN effective_date::DATE END) AS enroll_date,
        MAX(CASE WHEN event_type = {{ evt_enrollment_change() }}
                  AND LOWER(event_details) LIKE '%opt-out%' THEN effective_date::DATE END) AS opt_out_date,
        MAX(CASE WHEN event_type = {{ evt_enrollment() }}
                  THEN COALESCE(
                      CAST(NULLIF(REGEXP_EXTRACT(event_details, '([0-9]+\.?[0-9]*)%\s*deferral', 1), '') AS DECIMAL(6,4)) / 100.0,
                      0.06)
            END) AS enrollment_window_deferral_rate
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = (SELECT current_year FROM simulation_parameters)
      AND {{ is_enrollment_event('event_type') }}
      AND employee_id IS NOT NULL
    GROUP BY employee_id
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

-- Epic E078: Mode-aware query - uses fct_yearly_events in Polars mode, int_*_events in SQL mode
-- One termination per employee (MIN date) so the LEFT JOINs below stay 1:1.
termination_events AS (
    SELECT
        employee_id,
        MIN(termination_date) AS termination_date
    FROM (
        {% if var('event_generation_mode', 'sql') == 'polars' %}
        -- Polars mode: fct_yearly_events already unions new-hire + experienced terminations
        SELECT
            employee_id,
            effective_date::DATE AS termination_date
        FROM {{ ref('fct_yearly_events') }}
        WHERE simulation_year = (SELECT current_year FROM simulation_parameters)
          AND event_type = 'termination'
        {% else %}
        -- SQL mode: experienced-employee terminations live in int_termination_events;
        -- new-hire terminations are generated separately (issue #334). Both must be
        -- included or terminated new hires get a full-year comp base, over-stating
        -- their contributions and employer match.
        SELECT
            employee_id,
            effective_date::DATE AS termination_date
        FROM {{ ref('int_termination_events') }}
        WHERE simulation_year = (SELECT current_year FROM simulation_parameters)
        UNION ALL
        SELECT
            employee_id,
            effective_date::DATE AS termination_date
        FROM {{ ref('int_new_hire_termination_events') }}
        WHERE simulation_year = (SELECT current_year FROM simulation_parameters)
        {% endif %}
    ) all_terminations
    GROUP BY employee_id
),

-- Workforce proration base: include prior-year actives (snapshot) and current-year new hires
-- FIX: Add LEFT JOIN with termination events to properly handle terminated employees
snapshot_proration AS (
    SELECT
        comp.employee_id,
        {{ simulation_year }} AS simulation_year,
        comp.employee_compensation AS current_compensation,
        -- FIX: Calculate prorated compensation for terminated employees
        -- NOTE: GREATEST(0, ...) handles edge cases where termination_date precedes year start
        -- (e.g., data quality issues, prior-year terminations in snapshot). Negative day counts
        -- are clamped to 0, resulting in $0 prorated compensation for such records.
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

-- Feature 101: join the enrollment window and compute active-enrollment days,
-- the effective deferral rate, and the contribution base. prorated_annual_compensation
-- (employment-window comp) is intentionally left unchanged for all downstream consumers.
workforce_windowed AS (
    SELECT
        wf.*,
        COALESCE(dr.is_enrolled_flag, false) AS is_enrolled_flag,
        COALESCE(dr.deferral_rate, 0.0) AS year_end_deferral_rate,
        COALESCE(dr.source_quality, 'default_zero') AS source_quality,
        (eo.enroll_date IS NOT NULL
            AND eo.opt_out_date IS NOT NULL
            AND eo.opt_out_date >= eo.enroll_date) AS is_same_year_enroll_optout,
        eo.enrollment_window_deferral_rate,
        -- Active-enrollment days, bounded by termination / year-end (FR-003, FR-007)
        CASE
            WHEN eo.enroll_date IS NOT NULL
                 AND eo.opt_out_date IS NOT NULL
                 AND eo.opt_out_date >= eo.enroll_date
            THEN GREATEST(0,
                    DATEDIFF('day', eo.enroll_date,
                        LEAST(eo.opt_out_date,
                              COALESCE(wf.termination_date, ('{{ simulation_year }}-12-31')::DATE))) + 1)
            ELSE 0
        END AS active_enrollment_days
    FROM workforce_proration wf
    LEFT JOIN deferral_rates dr ON wf.employee_id = dr.employee_id
    LEFT JOIN enroll_optout_window eo ON wf.employee_id = eo.employee_id
),

contribution_inputs AS (
    SELECT
        *,
        -- Effective rate: window rate for enroll→opt-out, else the (carried) rate
        CASE WHEN is_same_year_enroll_optout
             THEN enrollment_window_deferral_rate
             ELSE year_end_deferral_rate
        END AS effective_deferral_rate,
        -- Contribution base: active-window comp for enroll→opt-out (= annual comp ×
        -- active_enrollment_days/365), else the employment-prorated comp (unchanged)
        CASE WHEN is_same_year_enroll_optout
             THEN ROUND(current_compensation * active_enrollment_days / 365.0, 2)
             ELSE prorated_annual_compensation
        END AS contribution_base_compensation,
        CASE
            WHEN is_same_year_enroll_optout THEN 'enroll_optout_window'
            WHEN employment_status = 'terminated' OR termination_date IS NOT NULL THEN 'partial_year'
            ELSE 'full_year'
        END AS contribution_window_category
    FROM workforce_windowed
),


-- Calculate IRS-compliant contributions for ALL employees
employee_contributions AS (
    SELECT
        ci.employee_id,  -- Use contribution_inputs as primary source
        {{ simulation_year }} AS simulation_year,
        ci.current_age,
        ci.current_compensation,
        ci.prorated_annual_compensation,
        ci.employment_status,
        ci.is_enrolled_flag,
        ci.effective_deferral_rate AS effective_annual_deferral_rate,
        ci.effective_deferral_rate AS final_deferral_rate,
        ci.active_enrollment_days,
        ci.contribution_window_category,

        -- Calculate requested contribution amount (before IRS limits)
        ci.contribution_base_compensation * ci.effective_deferral_rate AS requested_contribution_amount,

        -- Determine applicable IRS limit based on age (SECURE 2.0: super catch-up for ages 60-63)
        CASE
            WHEN ci.current_age >= il.super_catch_up_age_min AND ci.current_age <= il.super_catch_up_age_max
                THEN il.super_catch_up_limit
            WHEN ci.current_age >= il.catch_up_age_threshold
                THEN il.catch_up_limit
            ELSE il.base_limit
        END AS applicable_irs_limit,

        -- Calculate IRS-compliant contribution amount using LEAST()
        LEAST(
            (ci.contribution_base_compensation * ci.effective_deferral_rate),
            CASE
                WHEN ci.current_age >= il.super_catch_up_age_min AND ci.current_age <= il.super_catch_up_age_max
                    THEN il.super_catch_up_limit
                WHEN ci.current_age >= il.catch_up_age_threshold
                    THEN il.catch_up_limit
                ELSE il.base_limit
            END
        ) AS annual_contribution_amount,

        -- Transparency and audit fields
        CASE
            WHEN (ci.contribution_base_compensation * ci.effective_deferral_rate) >
                 CASE
                     WHEN ci.current_age >= il.super_catch_up_age_min AND ci.current_age <= il.super_catch_up_age_max
                         THEN il.super_catch_up_limit
                     WHEN ci.current_age >= il.catch_up_age_threshold
                         THEN il.catch_up_limit
                     ELSE il.base_limit
                 END
            THEN true ELSE false
        END AS irs_limit_applied,

        -- Amount that was capped off due to IRS limits
        GREATEST(0,
            (ci.contribution_base_compensation * ci.effective_deferral_rate) -
            CASE
                WHEN ci.current_age >= il.super_catch_up_age_min AND ci.current_age <= il.super_catch_up_age_max
                    THEN il.super_catch_up_limit
                WHEN ci.current_age >= il.catch_up_age_threshold
                    THEN il.catch_up_limit
                ELSE il.base_limit
            END
        ) AS amount_capped_by_irs_limit,

        -- Age-based limit type for reporting (SECURE 2.0: super catch-up for ages 60-63)
        CASE
            WHEN ci.current_age >= il.super_catch_up_age_min AND ci.current_age <= il.super_catch_up_age_max
                THEN 'SUPER_CATCH_UP'
            WHEN ci.current_age >= il.catch_up_age_threshold
                THEN 'CATCH_UP'
            ELSE 'BASE'
        END AS limit_type,

        -- Set contribution base (Feature 101: active-enrollment-window base for
        -- same-year enroll→opt-out employees; employment-prorated comp otherwise).
        -- Used for contributions AND employer match (match reads this column).
        ci.contribution_base_compensation AS total_contribution_base_compensation,
        -- Basic contribution metrics (updated to use IRS-compliant amount)
        1 AS number_of_contribution_periods,
        365 AS total_contribution_days,
        -- Average per paycheck computed after deriving total periods
        0.0 AS average_per_paycheck_contribution,
        -- Pay periods prorated by compensation ratio relative to full-year comp
        CAST(ROUND(
            CASE WHEN COALESCE(ci.current_compensation, 0) > 0 THEN
                26 * LEAST(1.0, GREATEST(0.0, COALESCE(ci.prorated_annual_compensation, 0.0) / NULLIF(ci.current_compensation, 0)))
            ELSE 26 END
        ) AS INTEGER) AS total_pay_periods_with_contributions,
        CAST('{{ simulation_year }}-01-01' AS DATE) AS first_contribution_date,
        COALESCE(ci.termination_date, CAST('{{ simulation_year }}-12-31' AS DATE)) AS last_contribution_date,
        -- FIX: Should be 'partial_year' for terminated employees, 'full_year' for active
        CASE
            WHEN ci.employment_status = 'terminated' OR ci.termination_date IS NOT NULL THEN 'partial_year'
            ELSE 'full_year'
        END AS contribution_duration_category,
        CASE
            WHEN (ci.contribution_base_compensation * ci.effective_deferral_rate) >
                 CASE
                     WHEN ci.current_age >= il.super_catch_up_age_min AND ci.current_age <= il.super_catch_up_age_max
                         THEN il.super_catch_up_limit
                     WHEN ci.current_age >= il.catch_up_age_threshold
                         THEN il.catch_up_limit
                     ELSE il.base_limit
                 END
            THEN 'IRS_LIMITED'
            ELSE 'NORMAL'
        END AS contribution_quality_flag,
        CURRENT_TIMESTAMP AS calculated_at,
        'E036_single_source_deferral_rate_fixed' AS calculation_source,
        ci.source_quality AS deferral_rate_source_quality
    FROM contribution_inputs ci
    CROSS JOIN irs_limits il  -- Cross join since we only have one row of limits
    WHERE ci.employee_id IS NOT NULL  -- Include all employees regardless of status
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
        -- Feature 101: active-enrollment-window audit fields
        active_enrollment_days,
        contribution_window_category,
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
  - Configurable limits via config_irs_limits seed
  - Zero tolerance for IRS limit violations
  - Complete audit trail for compliance reporting
*/
