{{
  config(
    materialized='table',
    tags=['foundation', 'critical', 'snapshot_base']
  )
}}

-- Establish the starting workforce state for each simulation year
-- For year 1: Use baseline workforce from census
-- For subsequent years: Use previous year's active employees with incremented age/tenure

{%- set start_year = var('simulation_start_year') %}
{%- set simulation_year = var('simulation_year') %}

WITH base_workforce AS (
  {% if simulation_year == start_year %}
    -- Year 1: Start with baseline workforce
    SELECT
      employee_id,
      employee_ssn,
      employee_birth_date,
      employee_hire_date,
      current_compensation AS employee_gross_compensation,
      current_age,
      current_tenure,
      level_id,
      NULL::DATE AS termination_date,
      'active' AS employment_status,
      {{ simulation_year }} AS simulation_year,
      CURRENT_TIMESTAMP AS snapshot_created_at
    FROM {{ ref('int_baseline_workforce') }}
  {% else %}
    -- Subsequent years: Use previous year's active employees with incremented age/tenure
    SELECT
      employee_id,
      employee_ssn,
      employee_birth_date,
      employee_hire_date,
      employee_gross_compensation,
      current_age + 1 AS current_age,
      current_tenure + 1 AS current_tenure,
      level_id,
      termination_date,
      employment_status,
      {{ simulation_year }} AS simulation_year,
      CURRENT_TIMESTAMP AS snapshot_created_at
    FROM {{ ref('int_active_employees_prev_year_snapshot') }}
  {% endif %}
)

SELECT * FROM base_workforce
