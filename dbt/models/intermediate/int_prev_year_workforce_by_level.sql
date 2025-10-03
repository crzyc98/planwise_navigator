{{ config(
    materialized='table',
    tags=["FOUNDATION", "circular_dependency_resolution"]
) }}

/*
  Helper model for level-specific workforce data from previous year.
  Breaks circular dependency in workforce planning calculations.
*/

{% set simulation_year = var('simulation_year') %}
{% set previous_year = simulation_year - 1 %}
{% set is_first_simulation_year = (simulation_year == 2025) %}

-- This model should only execute for years after the baseline year
{% if not is_first_simulation_year %}

WITH previous_year_snapshot AS (
  SELECT *
  FROM {{ adapter.get_relation(database=this.database, schema=this.schema, identifier='fct_workforce_snapshot') }}
  WHERE simulation_year = {{ previous_year }}
    AND employment_status = 'active'
)

SELECT
  {{ simulation_year }} AS simulation_year,
  level_id,
  COUNT(*) AS level_headcount,
  AVG(current_compensation) AS avg_level_compensation,
  SUM(current_compensation) AS total_level_compensation,
  'previous_year_snapshot' AS data_source,
  CURRENT_TIMESTAMP AS created_at
FROM previous_year_snapshot
GROUP BY level_id

{% else %}

-- For the first year, return empty set with correct schema
SELECT
    {{ simulation_year }} AS simulation_year,
    NULL::INTEGER AS level_id,
    NULL::BIGINT AS level_headcount,
    NULL::DOUBLE AS avg_level_compensation,
    NULL::DOUBLE AS total_level_compensation,
    'no_previous_year' AS data_source,
    CURRENT_TIMESTAMP AS created_at
LIMIT 0

{% endif %}
