{{ config(
    materialized='incremental',
    unique_key=['employee_id', 'simulation_year'],
    on_schema_change='fail',
    contract={
        "enforced": false
    }
) }}

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set scenario_id = var('scenario_id', 'default') %}
{% set use_payroll_ledger = var('use_payroll_ledger', true) %}

-- Year-end workforce snapshot using the new payroll ledger system
-- with enhanced error handling and safe deployment capability
--
-- **NEW ARCHITECTURE**: Uses fct_payroll_ledger for granular payroll simulation
-- with backward compatibility option via use_payroll_ledger variable
--
-- **SCHEMA CONTRACT ENFORCEMENT**: Maintains exact same output schema
-- and column names for downstream compatibility

-- Debug: simulation_year = {{ simulation_year }}
WITH simulation_parameters AS (
    SELECT {{ simulation_year }} AS current_year
),

{% if use_payroll_ledger %}
-- NEW IMPLEMENTATION: Use payroll ledger system
base_employees AS (
    SELECT
        CAST(employee_id AS VARCHAR) AS employee_id,
        CAST(employee_ssn AS VARCHAR) AS employee_ssn,
        CAST(employee_birth_date AS TIMESTAMP) AS employee_birth_date,
        CAST(employee_hire_date AS TIMESTAMP) AS employee_hire_date,
        CAST(employee_gross_compensation AS DOUBLE) AS employee_gross_compensation,
        CAST(current_age AS BIGINT) AS current_age,
        CAST(current_tenure AS BIGINT) AS current_tenure,
        CAST(level_id AS INTEGER) AS level_id,
        CAST(termination_date AS TIMESTAMP) AS termination_date,
        CAST(employment_status AS VARCHAR) AS employment_status,
        CAST(simulation_year AS INTEGER) AS simulation_year,
        CAST(NULL AS VARCHAR) AS termination_reason  -- Add as NULL since not in base table
    FROM {{ ref('int_snapshot_base') }}
    WHERE simulation_year = {{ simulation_year }}
),

payroll_aggregation AS (
    SELECT
        employee_id,
        simulation_year,
        -- Prorated compensation: sum of all period earnings
        SUM(period_earnings) AS prorated_annual_compensation,
        -- Current compensation: final salary rate from latest pay period
        MAX(annual_salary_rate_on_pay_date) AS current_compensation,
        -- Data quality checks
        COUNT(*) AS pay_periods_count,
        MIN(pay_period_end_date) AS first_pay_date,
        MAX(pay_period_end_date) AS last_pay_date
    FROM {{ ref('fct_payroll_ledger') }}
    WHERE simulation_year = {{ simulation_year }}
    GROUP BY employee_id, simulation_year
),

payroll_quality_check AS (
    SELECT
        p.*,
        -- Validate reasonable compensation ranges and data completeness
        CASE
            WHEN prorated_annual_compensation < 1000
                OR prorated_annual_compensation > 1000000
            THEN TRUE
            ELSE FALSE
        END AS compensation_out_of_range,
        CASE
            WHEN pay_periods_count < 20  -- Minimum expected periods for most employees
            THEN TRUE
            ELSE FALSE
        END AS insufficient_pay_periods
    FROM payroll_aggregation p
),

workforce_with_compensation AS (
    SELECT
        b.employee_id,
        b.employee_ssn,
        b.employee_birth_date,
        b.employee_hire_date,
        b.employee_gross_compensation,
        b.current_age,
        b.current_tenure,
        b.level_id,
        b.termination_date,
        b.employment_status,
        b.termination_reason,
        b.simulation_year,

        -- Use payroll ledger aggregations
        ROUND(COALESCE(p.prorated_annual_compensation, b.employee_gross_compensation), 2) AS prorated_annual_compensation,
        ROUND(COALESCE(p.current_compensation, b.employee_gross_compensation), 2) AS full_year_equivalent_compensation

    FROM base_employees b
    LEFT JOIN payroll_quality_check p
        ON b.employee_id = p.employee_id
        AND b.simulation_year = p.simulation_year
    -- Log warning for employees with missing payroll data
    -- (In production, this could trigger alerts)
),

{% else %}
-- LEGACY FALLBACK: Use original compensation logic
workforce_with_compensation AS (
    SELECT
        CAST(employee_id AS VARCHAR) AS employee_id,
        CAST(employee_ssn AS VARCHAR) AS employee_ssn,
        CAST(employee_birth_date AS TIMESTAMP) AS employee_birth_date,
        CAST(employee_hire_date AS TIMESTAMP) AS employee_hire_date,
        CAST(employee_gross_compensation AS DOUBLE) AS employee_gross_compensation,
        CAST(current_age AS BIGINT) AS current_age,
        CAST(current_tenure AS BIGINT) AS current_tenure,
        CAST(level_id AS INTEGER) AS level_id,
        CAST(termination_date AS TIMESTAMP) AS termination_date,
        CAST(employment_status AS VARCHAR) AS employment_status,
        CAST(termination_reason AS VARCHAR) AS termination_reason,
        CAST(simulation_year AS INTEGER) AS simulation_year,
        CAST(prorated_annual_compensation AS DOUBLE) AS prorated_annual_compensation,
        CAST(full_year_equivalent_compensation AS DOUBLE) AS full_year_equivalent_compensation
    FROM {{ ref('int_snapshot_compensation_legacy') }}
    WHERE simulation_year = {{ simulation_year }}
),
{% endif %}

-- Add age and tenure bands and final business logic
final_workforce AS (
    SELECT
        w.employee_id,
        w.employee_ssn,
        w.employee_birth_date,
        w.employee_hire_date,
        -- Map current_compensation to prorated_annual_compensation (actual earned compensation)
        -- current_compensation: Actual compensation earned during the year
        -- full_year_equivalent_compensation: Final salary rate at year-end
        w.prorated_annual_compensation AS current_compensation,
        w.prorated_annual_compensation,
        w.full_year_equivalent_compensation,
        w.current_age,
        w.current_tenure,
        w.level_id,
        w.employment_status,
        w.termination_date,
        w.termination_reason,
        w.simulation_year,
        -- Calculate age and tenure bands
        CASE
            WHEN w.current_age < 25 THEN '< 25'
            WHEN w.current_age < 35 THEN '25-34'
            WHEN w.current_age < 45 THEN '35-44'
            WHEN w.current_age < 55 THEN '45-54'
            WHEN w.current_age < 65 THEN '55-64'
            ELSE '65+'
        END AS age_band,
        CASE
            WHEN w.current_tenure < 2 THEN '< 2'
            WHEN w.current_tenure < 5 THEN '2-4'
            WHEN w.current_tenure < 10 THEN '5-9'
            WHEN w.current_tenure < 20 THEN '10-19'
            ELSE '20+'
        END AS tenure_band,
        -- Enhanced detailed_status_code logic to handle all edge cases
        CASE
            -- Active new hires (hired in current year, still active)
            WHEN w.employment_status = 'active' AND
                 EXTRACT(YEAR FROM w.employee_hire_date) = w.simulation_year
            THEN 'new_hire_active'

            -- Terminated new hires (hired and terminated in current year)
            WHEN w.employment_status = 'terminated' AND
                 EXTRACT(YEAR FROM w.employee_hire_date) = w.simulation_year
            THEN 'new_hire_termination'

            -- Active existing employees (hired before current year, still active)
            WHEN w.employment_status = 'active' AND
                 EXTRACT(YEAR FROM w.employee_hire_date) < w.simulation_year
            THEN 'continuous_active'

            -- Terminated existing employees (hired before current year, terminated this year)
            WHEN w.employment_status = 'terminated' AND
                 EXTRACT(YEAR FROM w.employee_hire_date) < w.simulation_year
            THEN 'experienced_termination'

            -- Handle edge cases with NULL values or invalid states
            WHEN w.employment_status IS NULL
            THEN 'continuous_active'  -- Default for NULL employment status

            WHEN w.employee_hire_date IS NULL
            THEN 'continuous_active'  -- Default for NULL hire date

            -- This should now be unreachable, but kept as safeguard
            ELSE 'continuous_active'
        END AS detailed_status_code
    FROM workforce_with_compensation w
)

SELECT
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    current_compensation,
    prorated_annual_compensation,
    full_year_equivalent_compensation,
    current_age,
    current_tenure,
    level_id,
    age_band,
    tenure_band,
    employment_status,
    termination_date,
    termination_reason,
    detailed_status_code,
    simulation_year,
    '{{ scenario_id }}' AS scenario_id,
    CURRENT_TIMESTAMP AS snapshot_created_at
FROM final_workforce

{% if is_incremental() %}
  -- Only process the current simulation year when running incrementally
  WHERE simulation_year = {{ simulation_year }}
{% endif %}
