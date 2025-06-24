{{ config(materialized='table') }}

-- Workforce Previous Year - Replaces int_previous_year_workforce
-- Uses snapshot to get previous year's workforce without circular dependency

{% set simulation_year = var('simulation_year', 2025) %}

{% if simulation_year == 2025 %}
-- For 2025 (first simulation year), use baseline workforce
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
-- For subsequent years, get previous year's active workforce from snapshot
SELECT
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    employee_gross_compensation,
    current_age + 1 AS current_age,  -- Age by one year
    current_tenure + 1 AS current_tenure,  -- Add one year tenure
    level_id,
    termination_date,
    employment_status
FROM {{ source('snapshots', 'scd_workforce_state') }}
WHERE simulation_year = {{ simulation_year - 1 }}
  AND employment_status = 'active'
  AND dbt_valid_to IS NULL  -- Get current/latest version from snapshot

{% endif %}
