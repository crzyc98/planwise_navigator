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
--   people_with_rate:    census staff with an hourly rate, and acquired members
--                        sampled from them (#1253)
--   people_without_rate: census staff with no usable hourly rate, not touched
--   people_not_covered:  simulated hires, and acquired members sampled from
--                        someone with no rate
-- Acquired members with a rate who join later in the year count too: the step
-- is in force when they join, and they are raised that day.
-- No row in a year without a step. Members raised on joining in such a year,
-- under an earlier year's step, appear only as events.

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
    -- In the start year this table also holds placeholder hires; the real
    -- hires come from int_hiring_events below.
    AND data_source <> 'new_hire_staging_independent'
  UNION
  SELECT employee_id
  FROM {{ ref('int_hiring_events') }}
  WHERE simulation_year = {{ simulation_year }}
    AND (
      effective_date <= DATE '{{ step.effective_date }}'
      -- #1253: a member with a rate who joins later is held to the step that day
      OR employee_id IN (
        SELECT employee_id
        FROM {{ ref('int_acquired_member_hourly_rates') }}
        WHERE simulation_year = {{ simulation_year }}
          AND scenario_id = '{{ scenario_id | replace("'", "''") }}'
      )
    )
),

on_date AS (
  SELECT
    s.employee_id,
    b.employee_id IS NOT NULL AS is_census,
    b.census_hourly_rate IS NOT NULL OR m.employee_id IS NOT NULL AS has_rate
  FROM on_staff s
  LEFT JOIN {{ ref('int_employee_termination_dates') }} t
    ON s.employee_id = t.employee_id
   AND t.simulation_year = {{ simulation_year }}
  LEFT JOIN {{ ref('int_baseline_workforce') }} b
    ON s.employee_id = b.employee_id
   AND b.simulation_year = {{ start_year }}
  LEFT JOIN {{ ref('int_acquired_member_hourly_rates') }} m
    ON s.employee_id = m.employee_id
   AND m.simulation_year <= {{ simulation_year }}
   AND m.scenario_id = '{{ scenario_id | replace("'", "''") }}'
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
  COUNT(*) FILTER (WHERE NOT d.is_census AND NOT d.has_rate) AS people_not_covered,
  CAST(r.added_annual_pay AS DOUBLE) AS added_annual_pay
FROM on_date d
CROSS JOIN raised r
GROUP BY r.people_raised, r.added_annual_pay
{% endif %}
