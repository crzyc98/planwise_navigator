{{ config(
    materialized='table',
    tags=["FOUNDATION", "circular_dependency_resolution"]
) }}

/*
  Helper model for level-specific workforce data from previous year.
  Breaks circular dependency in workforce planning calculations.
*/

{% set simulation_year = var('simulation_year') %}
{% set start_year = var('start_year', 2025) | int %}
{% set previous_year = simulation_year - 1 %}
{% set is_first_simulation_year = (simulation_year == start_year) %}

-- This model should only execute for years after the baseline year
{% if not is_first_simulation_year %}

WITH previous_year_snapshot AS (
  SELECT *
  FROM {{ adapter.get_relation(database=this.database, schema=this.schema, identifier='fct_workforce_snapshot') }}
  WHERE simulation_year = {{ previous_year }}
    AND employment_status = 'active'
),

-- Get all possible levels from configuration to ensure we always have rows
all_levels AS (
  SELECT DISTINCT level_id
  FROM {{ ref('stg_config_job_levels') }}
),

-- Calculate level aggregates with LEFT JOIN to handle zero workforce scenario
level_aggregates AS (
  SELECT
    l.level_id,
    COUNT(p.employee_id) AS level_headcount,
    COALESCE(AVG(p.current_compensation), 0) AS avg_level_compensation,
    COALESCE(SUM(p.current_compensation), 0) AS total_level_compensation
  FROM all_levels l
  LEFT JOIN previous_year_snapshot p ON l.level_id = p.level_id
  GROUP BY l.level_id
)

SELECT
  {{ simulation_year }} AS simulation_year,
  level_id,
  level_headcount,
  avg_level_compensation,
  total_level_compensation,
  'previous_year_snapshot' AS data_source,
  CURRENT_TIMESTAMP AS created_at
FROM level_aggregates

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
