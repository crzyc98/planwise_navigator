{{ config(
    materialized='view',
    tags=['monitoring', 'dashboard']
) }}

-- Performance monitoring dashboard view
-- Provides key metrics and trends for monitoring query performance
-- as simulation years progress and datasets grow

WITH performance_trends AS (
    SELECT
        model_name,
        simulation_year,
        execution_time_ms,
        row_count,
        created_at,
        -- Calculate trends
        LAG(execution_time_ms) OVER (
            PARTITION BY model_name 
            ORDER BY simulation_year, created_at
        ) AS prev_execution_time_ms,
        LAG(row_count) OVER (
            PARTITION BY model_name 
            ORDER BY simulation_year, created_at
        ) AS prev_row_count,
        -- Performance efficiency metrics
        CASE 
            WHEN row_count > 0 
            THEN execution_time_ms / row_count 
            ELSE NULL 
        END AS ms_per_row
    FROM {{ ref('performance_metrics') }}
),

performance_analysis AS (
    SELECT
        model_name,
        simulation_year,
        execution_time_ms,
        row_count,
        created_at,
        ms_per_row,
        -- Calculate percentage changes
        CASE 
            WHEN prev_execution_time_ms IS NOT NULL AND prev_execution_time_ms > 0
            THEN ROUND(
                ((execution_time_ms - prev_execution_time_ms) / prev_execution_time_ms) * 100, 
                2
            )
            ELSE NULL
        END AS execution_time_change_pct,
        CASE 
            WHEN prev_row_count IS NOT NULL AND prev_row_count > 0
            THEN ROUND(
                ((row_count - prev_row_count) / CAST(prev_row_count AS FLOAT)) * 100, 
                2
            )
            ELSE NULL
        END AS row_count_change_pct,
        -- Performance classification
        CASE
            WHEN execution_time_ms < 1000 THEN 'Fast'
            WHEN execution_time_ms < 5000 THEN 'Moderate'
            WHEN execution_time_ms < 15000 THEN 'Slow'
            ELSE 'Very Slow'
        END AS performance_category,
        -- Alert flags
        CASE 
            WHEN prev_execution_time_ms IS NOT NULL 
                 AND execution_time_ms > prev_execution_time_ms * 1.5 
            THEN 'PERFORMANCE_REGRESSION'
            WHEN execution_time_ms > 30000  -- 30 seconds
            THEN 'SLOW_QUERY_ALERT'
            ELSE 'OK'
        END AS alert_status
    FROM performance_trends
)

SELECT
    model_name,
    simulation_year,
    ROUND(execution_time_ms, 2) AS execution_time_ms,
    row_count,
    ROUND(ms_per_row, 4) AS ms_per_row,
    execution_time_change_pct,
    row_count_change_pct,
    performance_category,
    alert_status,
    created_at,
    -- Summary statistics
    AVG(execution_time_ms) OVER (
        PARTITION BY model_name 
        ORDER BY simulation_year 
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS avg_execution_time_3_runs,
    STDDEV(execution_time_ms) OVER (
        PARTITION BY model_name 
        ORDER BY simulation_year 
        ROWS BETWEEN 2 PRECEDING AND CURRENT ROW
    ) AS execution_time_volatility
FROM performance_analysis
ORDER BY model_name, simulation_year DESC, created_at DESC