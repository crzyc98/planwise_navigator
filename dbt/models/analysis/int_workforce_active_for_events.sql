{{ config(
    materialized='table',
    tags=['analysis', 'compensation', 'validation']
) }}

-- Opt-in input for analysis/test_compensation_compounding_validation.sql.
-- Production event generation consumes canonical compensation/workforce inputs.
-- Use --select +test_compensation_compounding_validation to build this helper
-- with its diagnostic consumer. Later years read the prior workforce projection.

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set is_first_year = (simulation_year == start_year) %}

{% if is_first_year %}
-- Year 1: Use baseline workforce directly
SELECT
    {{ simulation_year }} AS simulation_year,
    employee_id,
    employee_ssn,
    employee_hire_date AS hire_date,
    current_compensation AS employee_gross_compensation,
    current_age,
    current_tenure,
    level_id AS job_level,
    age_band,
    tenure_band,
    employment_status,
    -- Data quality flags
    current_age BETWEEN 16 AND 100 AS valid_age,
    current_tenure >= 0 AND current_tenure <= 60 AS valid_tenure,
    current_compensation > 0 AS valid_compensation,
    'baseline' AS data_source
FROM {{ ref('int_baseline_workforce') }}
WHERE employment_status = 'active'

{% else %}
-- Subsequent years: Use previous year's completed workforce snapshot
SELECT
    {{ simulation_year }} AS simulation_year,
    employee_id,
    employee_ssn,
    employee_hire_date AS hire_date,
    employee_gross_compensation,
    current_age,
    current_tenure,
    level_id AS job_level,
    age_band,
    tenure_band,
    employment_status,
    -- Data quality flags
    data_quality_valid as valid_age,
    data_quality_valid as valid_tenure,
    data_quality_valid as valid_compensation,
    data_source
FROM {{ ref('int_active_employees_prev_year_snapshot') }}
WHERE simulation_year = {{ simulation_year }}
  AND employment_status = 'active'

{% endif %}
