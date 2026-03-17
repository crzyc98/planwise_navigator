{{ config(materialized='table') }}

-- Previous Year Workforce Model with Conditional Compilation
-- Uses conditional compilation to avoid circular dependencies
-- For first year: uses baseline workforce
-- For subsequent years: uses previous year's snapshot with age/tenure increments

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set is_first_year = (simulation_year == start_year) %}

-- Debug: {{ simulation_year }}, {{ start_year }}, {{ is_first_year }}
WITH workforce_data AS (
    {% if is_first_year %}
    -- First year: use baseline workforce directly (simulation_year={{ simulation_year }})
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
    -- Subsequent years: use previous year's snapshot with age/tenure increments (simulation_year={{ simulation_year }})
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        current_compensation AS employee_gross_compensation,
        current_age + 1 AS current_age,
        current_tenure + 1 AS current_tenure,
        level_id,
        -- Recalculate age and tenure bands using centralized macros
        {{ assign_age_band('(current_age + 1)') }} AS age_band,
        {{ assign_tenure_band('(current_tenure + 1)') }} AS tenure_band,
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
