{{ config(materialized='table', tags=['FOUNDATION', 'temporal_projection']) }}

{% set simulation_year = var('simulation_year') | int %}
{% set scenario_id = var('scenario_id', 'default') %}
{% set plan_design_id = var('plan_design_id', 'default') %}

WITH prior_active AS (
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
  COUNT(*) AS total_active_workforce,
  COUNT(*) FILTER (
    WHERE employee_hire_date < DATE '{{ simulation_year - 1 }}-01-01'
  ) AS experienced_workforce,
  COUNT(*) FILTER (
    WHERE employee_hire_date >= DATE '{{ simulation_year - 1 }}-01-01'
      AND employee_hire_date < DATE '{{ simulation_year }}-01-01'
  ) AS current_year_hires,
  COALESCE(AVG(current_compensation), 50000) AS avg_compensation,
  COALESCE(SUM(current_compensation), 0) AS total_compensation,
  'workforce_state_projection' AS data_source,
  CURRENT_TIMESTAMP AS created_at
FROM prior_active
HAVING COUNT(*) > 0
