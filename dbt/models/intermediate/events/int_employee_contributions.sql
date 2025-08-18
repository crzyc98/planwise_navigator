{{ config(
    materialized='incremental',
    unique_key=['employee_id', 'simulation_year'],
    incremental_strategy='delete+insert',
    on_schema_change='sync_all_columns'
) }}

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

-- Get IRS contribution limits for the simulation year
irs_limits AS (
    SELECT
        limit_year,
        base_limit,
        catch_up_limit,
        catch_up_age_threshold
    FROM {{ ref('irs_contribution_limits') }}
    WHERE limit_year = (SELECT current_year FROM simulation_parameters)
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

-- EMERGENCY FIX: Use int_employee_compensation_by_year directly since int_workforce_snapshot_optimized is broken
workforce_proration AS (
    SELECT
        employee_id,
        {{ simulation_year }} AS simulation_year,
        employee_compensation AS current_compensation,
        employee_compensation AS prorated_annual_compensation,
        employment_status,
        NULL AS termination_date,
        employee_birth_date,
        current_age
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = (SELECT current_year FROM simulation_parameters)
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
        CASE WHEN wf.termination_date IS NOT NULL THEN 'partial_year' ELSE 'full_year' END AS contribution_duration_category,
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
