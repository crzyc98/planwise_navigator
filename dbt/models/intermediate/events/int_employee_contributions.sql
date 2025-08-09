{{ config(
    materialized='table'
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
  - int_deferral_rate_state_accumulator for deferral rates (E036 Fix - No circular dependency)
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

-- FIX: Get enrolled employees with deferral rates ONLY from state accumulator (Single Source of Truth)
enrolled_employees AS (
    SELECT DISTINCT
        employee_id,
        current_deferral_rate AS deferral_rate,
        data_quality_flag AS source_quality
    FROM {{ ref('int_deferral_rate_state_accumulator') }}
    WHERE simulation_year = (SELECT current_year FROM simulation_parameters)
      AND current_deferral_rate IS NOT NULL
      AND current_deferral_rate > 0
      AND is_enrolled_flag = true
),

-- Get employee compensation data with age calculation
-- FIX: Handle employees missing from compensation table (e.g., hired during first year)
employee_compensation AS (
    SELECT
        employee_id,
        simulation_year,
        employee_compensation,
        employment_status,
        is_enrolled_flag,
        employee_birth_date,
        -- Calculate current age for IRS limit determination
        DATE_DIFF('year', employee_birth_date, CAST('{{ simulation_year }}-12-31' AS DATE)) AS current_age
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = (SELECT current_year FROM simulation_parameters)
      AND employee_compensation > 0
),


-- Calculate IRS-compliant contributions for enrolled employees
employee_contributions AS (
    SELECT
        ee.employee_id,  -- Use enrolled_employees as primary source
        {{ simulation_year }} AS simulation_year,
        COALESCE(ec.current_age, 30) AS current_age,  -- Default age if missing
        COALESCE(ec.employee_compensation, 240000) AS current_compensation,  -- Use realistic default for missing employees
        COALESCE(ec.employee_compensation, 240000) AS prorated_annual_compensation,
        COALESCE(ec.employment_status, 'active') AS employment_status,
        true AS is_enrolled_flag,  -- All rows from enrolled_employees are enrolled
        ee.deferral_rate AS effective_annual_deferral_rate,
        ee.deferral_rate AS final_deferral_rate,

        -- Calculate requested contribution amount (before IRS limits) - use computed values
        COALESCE(ec.employee_compensation, 240000) * ee.deferral_rate AS requested_contribution_amount,

        -- Determine applicable IRS limit based on age - use computed values
        CASE
            WHEN COALESCE(ec.current_age, 30) >= il.catch_up_age_threshold
            THEN il.catch_up_limit
            ELSE il.base_limit
        END AS applicable_irs_limit,

        -- Calculate IRS-compliant contribution amount using LEAST()
        LEAST(
            COALESCE(ec.employee_compensation, 240000) * ee.deferral_rate,
            CASE
                WHEN COALESCE(ec.current_age, 30) >= il.catch_up_age_threshold
                THEN il.catch_up_limit
                ELSE il.base_limit
            END
        ) AS annual_contribution_amount,

        -- Transparency and audit fields
        CASE
            WHEN (COALESCE(ec.employee_compensation, 240000) * ee.deferral_rate) >
                 CASE WHEN COALESCE(ec.current_age, 30) >= il.catch_up_age_threshold
                      THEN il.catch_up_limit ELSE il.base_limit END
            THEN true ELSE false
        END AS irs_limit_applied,

        -- Amount that was capped off due to IRS limits
        GREATEST(0,
            (COALESCE(ec.employee_compensation, 240000) * ee.deferral_rate) -
            CASE WHEN COALESCE(ec.current_age, 30) >= il.catch_up_age_threshold
                 THEN il.catch_up_limit ELSE il.base_limit END
        ) AS amount_capped_by_irs_limit,

        -- Age-based limit type for reporting
        CASE WHEN COALESCE(ec.current_age, 30) >= il.catch_up_age_threshold THEN 'CATCH_UP' ELSE 'BASE' END AS limit_type,

        -- Set contribution base
        COALESCE(ec.employee_compensation, 240000) AS total_contribution_base_compensation,
        -- Basic contribution metrics (updated to use IRS-compliant amount)
        1 AS number_of_contribution_periods,
        365 AS total_contribution_days,
        LEAST(
            COALESCE(ec.employee_compensation, 240000) * ee.deferral_rate,
            CASE WHEN COALESCE(ec.current_age, 30) >= il.catch_up_age_threshold
                 THEN il.catch_up_limit ELSE il.base_limit END
        ) / 26 AS average_per_paycheck_contribution,  -- Bi-weekly payroll with IRS limits
        26 AS total_pay_periods_with_contributions,  -- 26 pay periods per year
        CAST('{{ simulation_year }}-01-01' AS DATE) AS first_contribution_date,
        CAST('{{ simulation_year }}-12-31' AS DATE) AS last_contribution_date,
        'full_year' AS contribution_duration_category,
        CASE
            WHEN (COALESCE(ec.employee_compensation, 240000) * ee.deferral_rate) >
                 CASE WHEN COALESCE(ec.current_age, 30) >= il.catch_up_age_threshold
                      THEN il.catch_up_limit ELSE il.base_limit END
            THEN 'IRS_LIMITED'
            ELSE 'NORMAL'
        END AS contribution_quality_flag,
        CURRENT_TIMESTAMP AS calculated_at,
        'E036_single_source_deferral_rate_fixed' AS calculation_source,
        ee.source_quality AS deferral_rate_source_quality
    FROM employee_compensation ec
    RIGHT JOIN enrolled_employees ee ON ec.employee_id = ee.employee_id
    CROSS JOIN irs_limits il  -- Cross join since we only have one row of limits
    WHERE COALESCE(ec.employment_status, 'active') = 'active'  -- Handle NULL employment status
)

-- Final output with IRS-compliant contributions and audit trail
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
    average_per_paycheck_contribution,
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
    calculated_at,
    calculation_source,
    deferral_rate_source_quality,
    -- IRS compliance and transparency fields
    requested_contribution_amount,      -- Original amount before IRS limits
    applicable_irs_limit,              -- Age-appropriate IRS limit
    irs_limit_applied,                 -- Boolean flag for limit enforcement
    amount_capped_by_irs_limit,        -- Amount that was reduced
    limit_type                         -- 'BASE' or 'CATCH_UP'
FROM employee_contributions
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
