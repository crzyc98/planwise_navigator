{{ config(
  materialized='incremental',
  incremental_strategy='replace_simulation_year',
  on_schema_change='sync_all_columns',
  tags=['EVENT_GENERATION']
) }}

{% set simulation_year = var('simulation_year') | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set scenario_id = var('scenario_id', 'default') %}
{% set step = minimum_wage_step(simulation_year) %}

-- One row per minimum wage step (#1229) in this year: who was on staff on the
-- effective date, who was raised, and the annual pay it added on that date.
--   people_without_rate: census staff with no usable hourly rate, not touched
--   people_not_covered:  simulated hires and acquired members, who have no rate
-- No row in a year without a step.

{% if step is none %}
SELECT
  CAST(NULL AS VARCHAR) AS scenario_id,
  CAST(NULL AS INTEGER) AS simulation_year,
  CAST(NULL AS DATE) AS effective_date,
  CAST(NULL AS DOUBLE) AS minimum_hourly_rate,
  CAST(NULL AS BIGINT) AS people_raised,
  CAST(NULL AS BIGINT) AS people_with_rate,
  CAST(NULL AS BIGINT) AS people_without_rate,
  CAST(NULL AS BIGINT) AS people_not_covered,
  CAST(NULL AS DOUBLE) AS added_annual_pay
WHERE FALSE
{% else %}
WITH on_staff AS (
  SELECT employee_id
  FROM {{ ref('int_employee_compensation_by_year') }}
  WHERE simulation_year = {{ simulation_year }}
    AND employment_status = 'active'
    AND employee_hire_date <= DATE '{{ step.effective_date }}'
  UNION
  SELECT employee_id
  FROM {{ ref('int_hiring_events') }}
  WHERE simulation_year = {{ simulation_year }}
    AND effective_date <= DATE '{{ step.effective_date }}'
),

on_date AS (
  SELECT
    s.employee_id,
    b.employee_id IS NOT NULL AS is_census,
    b.census_hourly_rate IS NOT NULL AS has_rate
  FROM on_staff s
  LEFT JOIN {{ ref('int_employee_termination_dates') }} t
    ON s.employee_id = t.employee_id
   AND t.simulation_year = {{ simulation_year }}
  LEFT JOIN {{ ref('int_baseline_workforce') }} b
    ON s.employee_id = b.employee_id
   AND b.simulation_year = {{ start_year }}
  WHERE t.termination_date IS NULL
    OR t.termination_date >= DATE '{{ step.effective_date }}'
),

raised AS (
  SELECT
    COUNT(*) AS people_raised,
    COALESCE(SUM(compensation_amount - previous_compensation), 0) AS added_annual_pay
  FROM {{ ref('int_minimum_wage_events') }}
  WHERE simulation_year = {{ simulation_year }}
)

SELECT
  '{{ scenario_id }}'::VARCHAR AS scenario_id,
  {{ simulation_year }}::INTEGER AS simulation_year,
  DATE '{{ step.effective_date }}' AS effective_date,
  CAST({{ step.hourly_rate }} AS DOUBLE) AS minimum_hourly_rate,
  r.people_raised,
  COUNT(*) FILTER (WHERE d.has_rate) AS people_with_rate,
  COUNT(*) FILTER (WHERE d.is_census AND NOT d.has_rate) AS people_without_rate,
  COUNT(*) FILTER (WHERE NOT d.is_census) AS people_not_covered,
  CAST(r.added_annual_pay AS DOUBLE) AS added_annual_pay
FROM on_date d
CROSS JOIN raised r
GROUP BY r.people_raised, r.added_annual_pay
{% endif %}
