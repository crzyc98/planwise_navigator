{{ config(
    materialized='table',
    tags=["FOUNDATION", "circular_dependency_resolution"]
) }}

/*
  Helper model for circular dependency resolution in workforce planning.

  Provides summary workforce statistics from previous year's completed snapshot
  to support Year N hiring calculations without creating circular dependencies.

  This model creates a temporal dependency (year N depends on year N-1) instead of
  a circular dependency within the same year.

  V1: Uses dynamic relation reference (`adapter.get_relation`) instead of static
  `ref()` to prevent dbt's parser from detecting a false circular dependency.
  The orchestrator MUST ensure that year N-1 is complete before running year N.
*/

{% set simulation_year = var('simulation_year') %}
{% set start_year = var('start_year', 2025) | int %}
{% set previous_year = simulation_year - 1 %}
{% set is_first_simulation_year = (simulation_year == start_year) %}

-- This model should only execute for years after the baseline year
{% if not is_first_simulation_year %}

WITH previous_year_snapshot AS (
  SELECT *
  -- Dynamic runtime reference to bypass DAG parser
  FROM {{ adapter.get_relation(database=this.database, schema=this.schema, identifier='fct_workforce_snapshot') }}
  WHERE simulation_year = {{ previous_year }}
    AND employment_status = 'active'
),

workforce_summary AS (
  SELECT
    COUNT(*) AS total_active_workforce,
    COUNT(*) AS experienced_workforce,
    0 AS current_year_hires,
    AVG(current_compensation) AS avg_compensation,
    SUM(current_compensation) AS total_compensation
  FROM previous_year_snapshot
),

workforce_by_level AS (
  SELECT
    level_id,
    COUNT(*) AS level_headcount,
    AVG(current_compensation) AS avg_level_compensation,
    SUM(current_compensation) AS total_level_compensation
  FROM previous_year_snapshot
  GROUP BY level_id
)

SELECT
  {{ simulation_year }} AS simulation_year,
  ws.total_active_workforce,
  ws.experienced_workforce,
  ws.current_year_hires,
  ws.avg_compensation,
  ws.total_compensation,
  'previous_year_snapshot' AS data_source,
  CURRENT_TIMESTAMP AS created_at
FROM workforce_summary ws

{% else %}

-- For the first year, return empty set with correct schema
SELECT
    {{ simulation_year }} AS simulation_year,
    NULL::BIGINT AS total_active_workforce,
    NULL::BIGINT AS experienced_workforce,
    NULL::BIGINT AS current_year_hires,
    NULL::DOUBLE AS avg_compensation,
    NULL::DOUBLE AS total_compensation,
    'no_previous_year' AS data_source,
    CURRENT_TIMESTAMP AS created_at
LIMIT 0

{% endif %}
