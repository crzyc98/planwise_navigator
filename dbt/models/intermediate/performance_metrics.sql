{{ config(
    materialized='table',
    indexes=[
        {'columns': ['model_name', 'simulation_year'], 'type': 'btree'},
        {'columns': ['created_at'], 'type': 'btree'}
    ],
    tags=['monitoring', 'performance']
) }}

-- Performance metrics tracking table for monitoring query execution times
-- This table captures execution time and row count metrics for critical models
-- to help identify performance regressions as simulation years progress

WITH empty_metrics AS (
    SELECT
        'placeholder'::VARCHAR AS model_name,
        2025::INTEGER AS simulation_year,
        0.0::FLOAT AS execution_time_ms,
        0::BIGINT AS row_count,
        CURRENT_TIMESTAMP AS created_at
    WHERE FALSE  -- This ensures no rows are created initially
)

SELECT
    model_name,
    simulation_year,
    execution_time_ms,
    row_count,
    created_at
FROM empty_metrics