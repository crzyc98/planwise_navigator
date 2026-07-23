{{ config(materialized='table', tags=['FOUNDATION', 'temporal_projection']) }}

{% set simulation_year = var('simulation_year') | int %}
{% set scenario_id = var('scenario_id', 'default') %}
{% set plan_design_id = var('plan_design_id', 'default') %}

WITH all_levels AS (
  SELECT DISTINCT level_id FROM {{ ref('stg_config_job_levels') }}
),

prior_active AS (
  SELECT *
  FROM {{ source('orchestrator_state', 'workforce_state_projection') }}
  WHERE decision_year = {{ simulation_year }}
    AND source_simulation_year = {{ simulation_year - 1 }}
    AND scenario_id = '{{ scenario_id }}'
    AND plan_design_id = '{{ plan_design_id }}'
    AND employment_status = 'active'
)

SELECT
  {{ simulation_year }} AS simulation_year,
  levels.level_id,
  COUNT(prior.employee_id) AS level_headcount,
  COALESCE(AVG(prior.current_compensation), 0) AS avg_level_compensation,
  COALESCE(SUM(prior.current_compensation), 0) AS total_level_compensation,
  'workforce_state_projection' AS data_source,
  CURRENT_TIMESTAMP AS created_at
FROM all_levels levels
LEFT JOIN prior_active prior ON levels.level_id = prior.level_id
GROUP BY levels.level_id
