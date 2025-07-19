{{ config(materialized='table') }}

-- Previous Year Workforce Model with Conditional Compilation
-- Uses conditional compilation to avoid circular dependencies
-- For first year: uses baseline workforce
-- For subsequent years: uses previous year's snapshot with age/tenure increments

{% set simulation_year = var('simulation_year', 2025) %}
{% set is_first_year = (simulation_year == 2025) %}

WITH workforce_data AS (
    {% if is_first_year %}
    -- First year: use baseline workforce directly
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

    {% else %}
    -- Subsequent years: use previous year's snapshot with age/tenure increments
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        current_compensation AS employee_gross_compensation,
        current_age + 1 AS current_age,
        current_tenure + 1 AS current_tenure,
        level_id,
        -- Recalculate age band
        CASE
            WHEN (current_age + 1) < 25 THEN '< 25'
            WHEN (current_age + 1) < 35 THEN '25-34'
            WHEN (current_age + 1) < 45 THEN '35-44'
            WHEN (current_age + 1) < 55 THEN '45-54'
            WHEN (current_age + 1) < 65 THEN '55-64'
            ELSE '65+'
        END AS age_band,
        -- Recalculate tenure band
        CASE
            WHEN (current_tenure + 1) < 2 THEN '< 2'
            WHEN (current_tenure + 1) < 5 THEN '2-4'
            WHEN (current_tenure + 1) < 10 THEN '5-9'
            WHEN (current_tenure + 1) < 20 THEN '10-19'
            ELSE '20+'
        END AS tenure_band,
        employment_status,
        termination_date,
        termination_reason,
        {{ simulation_year }} AS simulation_year,
        CURRENT_TIMESTAMP AS snapshot_created_at,
        false AS is_from_census,
        false AS is_cold_start,
        {{ simulation_year - 1 }} AS last_completed_year
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ simulation_year - 1 }}
      AND employment_status = 'active'
    {% endif %}
),
workforce_with_counts AS (
    SELECT
        *,
        COUNT(*) OVER () AS total_employees,
        SUM(CASE WHEN employment_status = 'active' THEN 1 ELSE 0 END) OVER () AS active_employees
    FROM workforce_data
)
SELECT * FROM workforce_with_counts
