{{ config(
    materialized='table',
    indexes=[
        {'columns': ['employee_id', 'simulation_year'], 'type': 'btree'},
        {'columns': ['simulation_year'], 'type': 'btree'},
        {'columns': ['irs_limit_applied'], 'type': 'btree'},
        {'columns': ['current_age'], 'type': 'btree'}
    ]
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
  - fct_yearly_events for enrollment events
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
        catch_up_age_threshold,
        limit_description
    FROM {{ ref('irs_contribution_limits') }}
    WHERE limit_year = (SELECT current_year FROM simulation_parameters)
),

-- Get enrolled employees with deferral rates
enrolled_employees_base AS (
    -- First, get employees from enrollment events (if any exist)
    SELECT DISTINCT
        employee_id,
        COALESCE(employee_deferral_rate, 0.05) AS deferral_rate,
        'event' AS source
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = (SELECT current_year FROM simulation_parameters)
      AND event_type IN ('enrollment')
      AND employee_deferral_rate IS NOT NULL
      AND employee_deferral_rate > 0

    UNION ALL

    -- Fallback: get enrolled employees from compensation data
    SELECT DISTINCT
        employee_id,
        0.05 AS deferral_rate,  -- Default 5% deferral rate
        'baseline' AS source
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = (SELECT current_year FROM simulation_parameters)
      AND is_enrolled_flag = true
      AND employee_compensation > 0
),

-- Deduplicate and prioritize enrollment events over baseline
enrolled_employees AS (
    SELECT
        employee_id,
        deferral_rate
    FROM (
        SELECT
            employee_id,
            deferral_rate,
            ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY CASE WHEN source = 'event' THEN 1 ELSE 2 END) AS rn
        FROM enrolled_employees_base
    ) ranked
    WHERE rn = 1
),

-- Get employee compensation data with age calculation
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
        ec.employee_id,
        ec.simulation_year,
        ec.current_age,
        ec.employee_compensation AS current_compensation,
        ec.employee_compensation AS prorated_annual_compensation,
        ec.employment_status,
        COALESCE(ec.is_enrolled_flag, false) AS is_enrolled_flag,
        ee.deferral_rate AS effective_annual_deferral_rate,
        ee.deferral_rate AS final_deferral_rate,

        -- Calculate requested contribution amount (before IRS limits)
        ec.employee_compensation * ee.deferral_rate AS requested_contribution_amount,

        -- Determine applicable IRS limit based on age
        CASE
            WHEN ec.current_age >= il.catch_up_age_threshold
            THEN il.catch_up_limit
            ELSE il.base_limit
        END AS applicable_irs_limit,

        -- Calculate IRS-compliant contribution amount using LEAST()
        LEAST(
            ec.employee_compensation * ee.deferral_rate,
            CASE
                WHEN ec.current_age >= il.catch_up_age_threshold
                THEN il.catch_up_limit
                ELSE il.base_limit
            END
        ) AS annual_contribution_amount,

        -- Transparency and audit fields
        CASE
            WHEN (ec.employee_compensation * ee.deferral_rate) >
                 CASE WHEN ec.current_age >= il.catch_up_age_threshold
                      THEN il.catch_up_limit ELSE il.base_limit END
            THEN true ELSE false
        END AS irs_limit_applied,

        -- Amount that was capped off due to IRS limits
        GREATEST(0,
            (ec.employee_compensation * ee.deferral_rate) -
            CASE WHEN ec.current_age >= il.catch_up_age_threshold
                 THEN il.catch_up_limit ELSE il.base_limit END
        ) AS amount_capped_by_irs_limit,

        -- Age-based limit type for reporting
        CASE WHEN ec.current_age >= il.catch_up_age_threshold THEN 'CATCH_UP' ELSE 'BASE' END AS limit_type,

        -- Set contribution base
        ec.employee_compensation AS total_contribution_base_compensation,
        -- Basic contribution metrics (updated to use IRS-compliant amount)
        1 AS number_of_contribution_periods,
        365 AS total_contribution_days,
        LEAST(
            ec.employee_compensation * ee.deferral_rate,
            CASE WHEN ec.current_age >= il.catch_up_age_threshold
                 THEN il.catch_up_limit ELSE il.base_limit END
        ) / 26 AS average_per_paycheck_contribution,  -- Bi-weekly payroll with IRS limits
        26 AS total_pay_periods_with_contributions,  -- 26 pay periods per year
        CAST('{{ simulation_year }}-01-01' AS DATE) AS first_contribution_date,
        CAST('{{ simulation_year }}-12-31' AS DATE) AS last_contribution_date,
        'full_year' AS contribution_duration_category,
        CASE
            WHEN (ec.employee_compensation * ee.deferral_rate) >
                 CASE WHEN ec.current_age >= il.catch_up_age_threshold
                      THEN il.catch_up_limit ELSE il.base_limit END
            THEN 'IRS_LIMITED'
            ELSE 'NORMAL'
        END AS contribution_quality_flag,
        CURRENT_TIMESTAMP AS calculated_at,
        'E034_contribution_calculator_irs_compliant' AS calculation_source
    FROM employee_compensation ec
    INNER JOIN enrolled_employees ee ON ec.employee_id = ee.employee_id
    CROSS JOIN irs_limits il  -- Cross join since we only have one row of limits
    WHERE ec.employment_status = 'active'
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
    -- IRS compliance and transparency fields
    requested_contribution_amount,      -- Original amount before IRS limits
    applicable_irs_limit,              -- Age-appropriate IRS limit
    irs_limit_applied,                 -- Boolean flag for limit enforcement
    amount_capped_by_irs_limit,        -- Amount that was reduced
    limit_type                         -- 'BASE' or 'CATCH_UP'
FROM employee_contributions
ORDER BY employee_id

/*
  IRS Compliance Notes:
  - All contributions are capped at IRS 402(g) limits
  - Age-based catch-up contributions supported (age 50+)
  - Full transparency with requested vs. capped amounts
  - Configurable limits via irs_contribution_limits seed
  - Zero tolerance for IRS limit violations
  - Complete audit trail for compliance reporting
*/
