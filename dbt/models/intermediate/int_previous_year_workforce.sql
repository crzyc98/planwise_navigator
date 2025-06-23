{{ config(
    materialized='table'
) }}

-- Extract previous year's active workforce for event generation
-- Uses proper dbt incremental patterns instead of external snapshot management

{% set simulation_year = var('simulation_year', 2025) %}

-- For 2025 (first simulation year), use baseline census data exclusively
-- For subsequent years, use previous year's final snapshot from fct_workforce_snapshot
{% if simulation_year == 2025 %}
SELECT
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    current_compensation AS employee_gross_compensation,
    current_age,
    current_tenure,
    level_id,
    termination_date,
    employment_status
FROM {{ ref('int_baseline_workforce') }}
WHERE employment_status = 'active'

{% else %}
-- Break circular dependency by using direct table reference instead of ref()
SELECT
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    current_compensation AS employee_gross_compensation,
    current_age,
    current_tenure,
    level_id,
    termination_date,
    employment_status
FROM {{ this.schema }}.fct_workforce_snapshot
WHERE simulation_year = {{ simulation_year - 1 }}
  AND employment_status = 'active'

{% endif %}
