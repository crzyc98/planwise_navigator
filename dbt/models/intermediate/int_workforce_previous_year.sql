{{ config(materialized='table') }}

-- Enhanced Previous Year Workforce Model with Fallback Handling
-- Gracefully handles missing prior year data without errors

WITH baseline_workforce AS (
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        current_compensation AS employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        age_band,
        tenure_band,
        employment_status,
        termination_date,
        termination_reason,
        simulation_year,
        snapshot_created_at,
        is_from_census,
        is_cold_start,
        last_completed_year
    FROM {{ ref('int_baseline_workforce') }}
    WHERE employment_status = 'active'
),
workforce_with_validation AS (
    SELECT
        *,
        COUNT(*) OVER () as total_employees,
        SUM(CASE WHEN employment_status = 'active' THEN 1 ELSE 0 END) OVER () as active_employees
    FROM baseline_workforce
)
SELECT
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    employee_gross_compensation,
    current_age,
    current_tenure,
    level_id,
    age_band,
    tenure_band,
    employment_status,
    termination_date,
    termination_reason,
    simulation_year,
    snapshot_created_at,
    is_from_census,
    is_cold_start,
    last_completed_year,
    total_employees,
    active_employees
FROM workforce_with_validation
