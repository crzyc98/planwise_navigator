{% macro optimize_duckdb_for_scd() %}
    -- Optimize DuckDB settings for SCD processing
    -- This macro applies performance optimizations specific to SCD workloads

    {% set optimization_queries = [
        "SET threads = 16",
        "SET memory_limit = '32GB'",
        "SET enable_parallel_join = true",
        "SET enable_parallel_sort = true",
        "SET enable_parallel_aggregate = true",
        "SET enable_optimizer = true",
        "SET enable_profiling = true",
        "SET preserve_insertion_order = false",
        "SET checkpoint_threshold = '1GB'",
        "SET wal_autocheckpoint = 10000",
        "SET enable_object_cache = true"
    ] %}

    {% for query in optimization_queries %}
        {% if execute %}
            {% set result = run_query(query) %}
            {{ log("Applied optimization: " ~ query, info=true) }}
        {% endif %}
    {% endfor %}

{% endmacro %}

{% macro create_scd_indexes(table_name) %}
    -- Create optimized indexes for SCD table performance
    -- Usage: {{ create_scd_indexes('scd_workforce_state_optimized') }}

    {% set index_queries = [
        "CREATE INDEX IF NOT EXISTS idx_" ~ table_name ~ "_employee_id ON " ~ table_name ~ " (employee_id)",
        "CREATE INDEX IF NOT EXISTS idx_" ~ table_name ~ "_valid_from ON " ~ table_name ~ " (dbt_valid_from)",
        "CREATE INDEX IF NOT EXISTS idx_" ~ table_name ~ "_valid_to ON " ~ table_name ~ " (dbt_valid_to)",
        "CREATE INDEX IF NOT EXISTS idx_" ~ table_name ~ "_current_records ON " ~ table_name ~ " (employee_id, dbt_valid_to) WHERE dbt_valid_to IS NULL",
        "CREATE INDEX IF NOT EXISTS idx_" ~ table_name ~ "_composite ON " ~ table_name ~ " (employee_id, dbt_valid_from, dbt_valid_to)",
        "CREATE INDEX IF NOT EXISTS idx_" ~ table_name ~ "_hash ON " ~ table_name ~ " (change_hash)",
        "ANALYZE " ~ table_name
    ] %}

    {% for query in index_queries %}
        {% if execute %}
            {% set result = run_query(query) %}
            {{ log("Created index: " ~ query, info=true) }}
        {% endif %}
    {% endfor %}

{% endmacro %}

{% macro validate_scd_integrity(table_name) %}
    -- Validate SCD Type 2 integrity for the given table
    -- Usage: {{ validate_scd_integrity('scd_workforce_state_optimized') }}

    {% set validation_queries = [
        {
            'name': 'multiple_current_records',
            'query': "SELECT COUNT(*) FROM (SELECT employee_id FROM " ~ table_name ~ " WHERE dbt_valid_to IS NULL GROUP BY employee_id HAVING COUNT(*) > 1)",
            'expected': 0
        },
        {
            'name': 'null_keys',
            'query': "SELECT COUNT(*) FROM " ~ table_name ~ " WHERE employee_id IS NULL OR dbt_valid_from IS NULL",
            'expected': 0
        },
        {
            'name': 'overlapping_periods',
            'query': "SELECT COUNT(*) FROM " ~ table_name ~ " s1 JOIN " ~ table_name ~ " s2 ON s1.employee_id = s2.employee_id WHERE s1.dbt_scd_id != s2.dbt_scd_id AND s1.dbt_valid_from < COALESCE(s2.dbt_valid_to, '9999-12-31') AND COALESCE(s1.dbt_valid_to, '9999-12-31') > s2.dbt_valid_from",
            'expected': 0
        }
    ] %}

    {% for validation in validation_queries %}
        {% if execute %}
            {% set result = run_query(validation['query']) %}
            {% set actual_count = result.columns[0].values()[0] %}
            {% if actual_count != validation['expected'] %}
                {{ log("SCD integrity violation in " ~ validation['name'] ~ ": expected " ~ validation['expected'] ~ ", got " ~ actual_count, info=false) }}
                {% set error_msg = "SCD integrity validation failed for " ~ validation['name'] ~ " in table " ~ table_name %}
                {{ exceptions.raise_compiler_error(error_msg) }}
            {% else %}
                {{ log("SCD integrity check passed for " ~ validation['name'], info=true) }}
            {% endif %}
        {% endif %}
    {% endfor %}

{% endmacro %}

{% macro log_scd_performance_metrics(phase_name, record_count, duration_seconds) %}
    -- Log SCD performance metrics to monitoring table
    -- Usage: {{ log_scd_performance_metrics('snapshot_processing', 10000, 45.2) }}

    {% if execute %}
        {% set insert_query %}
            INSERT INTO mon_scd_phase_metrics (
                phase_name,
                metric_timestamp,
                duration_seconds,
                record_count,
                records_per_second,
                simulation_year
            )
            VALUES (
                '{{ phase_name }}',
                CURRENT_TIMESTAMP,
                {{ duration_seconds }},
                {{ record_count }},
                {{ record_count / duration_seconds if duration_seconds > 0 else 0 }},
                {{ var('simulation_year', 2025) }}
            )
        {% endset %}

        {% set result = run_query(insert_query) %}
        {{ log("Logged performance metrics for " ~ phase_name ~ ": " ~ record_count ~ " records in " ~ duration_seconds ~ "s", info=true) }}
    {% endif %}

{% endmacro %}
