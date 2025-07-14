{{ config(materialized='table') }}

-- Enhanced Previous Year Workforce Model with Fallback Handling
-- Gracefully handles missing prior year data without errors
-- Uses baseline workforce for first year, previous year snapshot for subsequent years

{% set simulation_year = var('simulation_year', 2025) %}

WITH cold_start_check AS (
    SELECT is_cold_start, last_completed_year
    FROM {{ ref('int_cold_start_detection') }}
),
baseline_workforce AS (
    -- For first year or cold start: use baseline workforce from census
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
previous_year_snapshot AS (
    -- For subsequent years: use actual previous year's workforce snapshot
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        current_compensation AS employee_gross_compensation,
        current_age + 1 AS current_age,  -- Age by one year
        current_tenure + 1 AS current_tenure,  -- Add one year tenure
        level_id,
        age_band,
        tenure_band,
        employment_status,
        termination_date,
        termination_reason,
        simulation_year,
        snapshot_created_at,
        false as is_from_census,
        false as is_cold_start,
        {{ simulation_year - 1 }} as last_completed_year
    FROM fct_workforce_snapshot
    WHERE simulation_year = {{ simulation_year - 1 }}
      AND employment_status = 'active'
),
workforce_selection AS (
    -- Use baseline for first year (2025) or when cold start is detected
    SELECT
        bw.employee_id,
        bw.employee_ssn,
        bw.employee_birth_date,
        bw.employee_hire_date,
        bw.employee_gross_compensation,
        bw.current_age,
        bw.current_tenure,
        bw.level_id,
        bw.age_band,
        bw.tenure_band,
        bw.employment_status,
        bw.termination_date,
        bw.termination_reason,
        bw.simulation_year,
        bw.snapshot_created_at,
        bw.is_from_census,
        c.is_cold_start,
        c.last_completed_year
    FROM baseline_workforce bw
    CROSS JOIN cold_start_check c
    WHERE {{ simulation_year }} = 2025 OR c.is_cold_start = true

    UNION ALL

    -- Use previous year snapshot for subsequent years when not cold start
    SELECT
        pys.employee_id,
        pys.employee_ssn,
        pys.employee_birth_date,
        pys.employee_hire_date,
        pys.employee_gross_compensation,
        pys.current_age,
        pys.current_tenure,
        pys.level_id,
        pys.age_band,
        pys.tenure_band,
        pys.employment_status,
        pys.termination_date,
        pys.termination_reason,
        pys.simulation_year,
        pys.snapshot_created_at,
        pys.is_from_census,
        c.is_cold_start,
        c.last_completed_year
    FROM previous_year_snapshot pys
    CROSS JOIN cold_start_check c
    WHERE {{ simulation_year }} > 2025 AND c.is_cold_start = false
),
workforce_with_validation AS (
    SELECT
        *,
        COUNT(*) OVER () as total_employees,
        SUM(CASE WHEN employment_status = 'active' THEN 1 ELSE 0 END) OVER () as active_employees
    FROM workforce_selection
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
