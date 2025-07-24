{% macro add_performance_monitoring(model_name=None) %}
    {% if model_name is none %}
        {% set model_name = this.name %}
    {% endif %}
    
    {% set pre_hook %}
        SET enable_profiling = 'json'
    {% endset %}
    
    {% set post_hook %}
        CREATE TABLE IF NOT EXISTS {{ this.schema }}.performance_metrics (
            model_name VARCHAR,
            simulation_year INTEGER,
            execution_time_ms FLOAT,
            row_count BIGINT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );
        
        INSERT INTO {{ this.schema }}.performance_metrics (
            model_name, 
            simulation_year, 
            execution_time_ms, 
            row_count, 
            created_at
        ) 
        SELECT 
            '{{ model_name }}' AS model_name,
            {{ var('simulation_year', 2025) }} AS simulation_year,
            COALESCE(
                (SELECT 
                    CAST(json_extract_string(unnest(profiling_output), 'QUERY_TIME') AS FLOAT) * 1000 
                 FROM pragma_profiling_output() 
                 LIMIT 1), 
                0.0
            ) AS execution_time_ms,
            (SELECT COUNT(*) FROM {{ this }}) AS row_count,
            CURRENT_TIMESTAMP AS created_at
    {% endset %}
    
    {{ return({
        'pre_hook': pre_hook,
        'post_hook': post_hook
    }) }}
{% endmacro %}

{% macro get_performance_trends(model_name, days_back=30) %}
    SELECT
        model_name,
        simulation_year,
        execution_time_ms,
        row_count,
        created_at,
        -- Calculate performance trends
        LAG(execution_time_ms) OVER (
            PARTITION BY model_name 
            ORDER BY simulation_year, created_at
        ) AS prev_execution_time_ms,
        CASE 
            WHEN LAG(execution_time_ms) OVER (
                PARTITION BY model_name 
                ORDER BY simulation_year, created_at
            ) IS NOT NULL
            THEN (execution_time_ms - LAG(execution_time_ms) OVER (
                PARTITION BY model_name 
                ORDER BY simulation_year, created_at
            )) / LAG(execution_time_ms) OVER (
                PARTITION BY model_name 
                ORDER BY simulation_year, created_at
            ) * 100
            ELSE NULL
        END AS performance_change_pct,
        -- Row count efficiency
        CASE 
            WHEN row_count > 0 
            THEN execution_time_ms / row_count 
            ELSE NULL 
        END AS ms_per_row
    FROM {{ ref('performance_metrics') }}
    WHERE model_name = '{{ model_name }}'
      AND created_at >= CURRENT_TIMESTAMP - INTERVAL '{{ days_back }} days'
    ORDER BY simulation_year, created_at
{% endmacro %}