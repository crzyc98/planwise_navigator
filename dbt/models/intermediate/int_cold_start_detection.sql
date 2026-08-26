{{ config(materialized='table') }}

-- Cold Start Detection Logic with Table Existence Check
-- Determines if this is a cold start or continuation of existing simulation
-- Uses table existence check to safely handle empty databases

-- Keep the existence checks for compatibility with partially initialized databases,
-- but declare both relations with ref() so dbt can track the dependencies.
{% set workforce_snapshot_relation = ref('fct_workforce_snapshot') %}
{% set simulation_run_log_relation = ref('int_simulation_run_log') %}

{% set workforce_snapshot_exists = adapter.get_relation(
    database=workforce_snapshot_relation.database,
    schema=workforce_snapshot_relation.schema,
    identifier=workforce_snapshot_relation.identifier
) is not none %}

{% set simulation_run_log_exists = adapter.get_relation(
    database=simulation_run_log_relation.database,
    schema=simulation_run_log_relation.schema,
    identifier=simulation_run_log_relation.identifier
) is not none %}

{% if simulation_run_log_exists %}
-- Use simulation run log to determine cold start status
WITH simulation_state AS (
    SELECT
        COUNT(*) as prior_year_count,
        MAX(simulation_year) as max_year
    FROM {{ ref('int_simulation_run_log') }}
    WHERE simulation_year < {{ var('simulation_year') }}
),
cold_start_flag AS (
    SELECT
        CASE
            WHEN prior_year_count = 0 OR max_year IS NULL THEN true
            ELSE false
        END as is_cold_start,
        COALESCE(max_year, 0) as last_completed_year
    FROM simulation_state
)
SELECT * FROM cold_start_flag
{% else %}
-- Neither table exists, this is definitely a cold start
SELECT
    true as is_cold_start,
    0 as last_completed_year
{% endif %}
