{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['scenario_id', 'employee_id', 'simulation_year'],
    on_schema_change='sync_all_columns',
    pre_hook=[
      "{% if is_incremental() %}DELETE FROM {{ this }} WHERE scenario_id = '{{ var('scenario_id', 'default') }}' AND simulation_year = {{ var('simulation_year') }}{% endif %}"
    ],
    tags=['EVENT_GENERATION']
) }}

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set scenario_id = var('scenario_id', 'default') %}
{% set legacy_design_id = var('plan_design_id', 'default') %}
{% set assignment = var('plan_design_assignment', none) %}
{% set default_design_id = assignment['default_plan_design_id'] if assignment else legacy_design_id %}
{% set rules = assignment['rules'] if assignment else [] %}

WITH previous_assignments AS (
{% if is_incremental() and simulation_year > start_year %}
  SELECT
    employee_id,
    plan_design_id,
    first_assignment_year,
    assignment_source
  FROM {{ this }}
  WHERE scenario_id = '{{ scenario_id }}'
    AND simulation_year = {{ simulation_year - 1 }}
{% else %}
  SELECT
    CAST(NULL AS VARCHAR) AS employee_id,
    CAST(NULL AS VARCHAR) AS plan_design_id,
    CAST(NULL AS INTEGER) AS first_assignment_year,
    CAST(NULL AS VARCHAR) AS assignment_source
  WHERE FALSE
{% endif %}
),

unassigned_employees AS (
{% if simulation_year == start_year %}
  SELECT
    employee_id,
    CAST(employee_hire_date AS DATE) AS employee_hire_date,
    'census' AS employee_source
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ simulation_year }}
    AND employee_id IS NOT NULL

  UNION ALL
{% endif %}
  SELECT
    employee_id,
    CAST(effective_date AS DATE) AS employee_hire_date,
    'new_hire' AS employee_source
  FROM {{ ref('int_hiring_events') }}
  WHERE simulation_year = {{ simulation_year }}
    AND employee_id IS NOT NULL
),

new_assignments AS (
  SELECT * EXCLUDE (candidate_rank)
  FROM (
    SELECT
      candidate.employee_id,
{% if rules %}
      CASE
{% for rule in rules %}
        WHEN candidate.employee_hire_date >= CAST('{{ rule['cutoff'] }}' AS DATE)
          THEN '{{ rule['plan_design_id'] }}'
{% endfor %}
        ELSE '{{ default_design_id }}'
      END
{% else %}
      '{{ default_design_id }}'
{% endif %}
        AS plan_design_id,
      {{ simulation_year }} AS first_assignment_year,
      candidate.employee_source AS assignment_source,
      ROW_NUMBER() OVER (
        PARTITION BY candidate.employee_id
        ORDER BY CASE candidate.employee_source WHEN 'census' THEN 1 ELSE 2 END
      ) AS candidate_rank
    FROM unassigned_employees candidate
    LEFT JOIN previous_assignments previous
      ON candidate.employee_id = previous.employee_id
    WHERE previous.employee_id IS NULL
  ) ranked
  WHERE candidate_rank = 1
),

current_assignments AS (
  SELECT * FROM previous_assignments
  UNION ALL
  SELECT * FROM new_assignments
)

SELECT
  '{{ scenario_id }}'::VARCHAR AS scenario_id,
  employee_id,
  plan_design_id,
  {{ simulation_year }}::INTEGER AS simulation_year,
  first_assignment_year,
  assignment_source,
  CURRENT_TIMESTAMP AS created_at
FROM current_assignments
WHERE employee_id IS NOT NULL
