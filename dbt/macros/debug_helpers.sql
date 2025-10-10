-- dbt/macros/debug_helpers.sql
-- SQL Debugging Macros for PlanWise Navigator
-- Story S071-05: Fast in-query debugging utilities

{% macro debug_row_count(model_name) %}
    -- Print row count for a model during execution
    {% set query %}
        SELECT COUNT(*) as row_count FROM {{ ref(model_name) }}
    {% endset %}

    {% set results = run_query(query) %}
    {% if execute %}
        {% set row_count = results.columns[0].values()[0] %}
        {{ log("DEBUG: " ~ model_name ~ " has " ~ row_count ~ " rows", info=True) }}
    {% endif %}
{% endmacro %}

{% macro debug_column_stats(table_name, column_name) %}
    -- Print statistics for a column
    {% set query %}
        SELECT
            COUNT(*) as total_rows,
            COUNT({{ column_name }}) as non_null_count,
            COUNT(*) - COUNT({{ column_name }}) as null_count,
            MIN({{ column_name }}) as min_value,
            MAX({{ column_name }}) as max_value,
            AVG({{ column_name }}) as avg_value
        FROM {{ ref(table_name) }}
    {% endset %}

    {% set results = run_query(query) %}
    {% if execute %}
        {{ log("DEBUG: Column stats for " ~ column_name ~ ":", info=True) }}
        {{ log("  Total rows: " ~ results.columns[0].values()[0], info=True) }}
        {{ log("  Non-null: " ~ results.columns[1].values()[0], info=True) }}
        {{ log("  Null: " ~ results.columns[2].values()[0], info=True) }}
        {{ log("  Min: " ~ results.columns[3].values()[0], info=True) }}
        {{ log("  Max: " ~ results.columns[4].values()[0], info=True) }}
        {{ log("  Avg: " ~ results.columns[5].values()[0], info=True) }}
    {% endif %}
{% endmacro %}

{% macro debug_duplicates(table_name, key_columns) %}
    -- Check for duplicate keys
    {% set key_list = key_columns | join(', ') %}
    {% set query %}
        SELECT COUNT(*) as duplicate_count
        FROM (
            SELECT {{ key_list }}, COUNT(*) as cnt
            FROM {{ ref(table_name) }}
            GROUP BY {{ key_list }}
            HAVING COUNT(*) > 1
        )
    {% endset %}

    {% set results = run_query(query) %}
    {% if execute %}
        {% set dup_count = results.columns[0].values()[0] %}
        {% if dup_count > 0 %}
            {{ log("⚠️  WARNING: Found " ~ dup_count ~ " duplicate keys in " ~ table_name, info=True) }}
        {% else %}
            {{ log("✓ No duplicates found in " ~ table_name, info=True) }}
        {% endif %}
    {% endif %}
{% endmacro %}

{% macro debug_year_coverage(table_name, year_column='simulation_year') %}
    -- Check which years have data
    {% set query %}
        SELECT DISTINCT {{ year_column }}
        FROM {{ ref(table_name) }}
        ORDER BY {{ year_column }}
    {% endset %}

    {% set results = run_query(query) %}
    {% if execute %}
        {% set years = results.columns[0].values() %}
        {{ log("DEBUG: " ~ table_name ~ " has data for years: " ~ years | join(', '), info=True) }}
    {% endif %}
{% endmacro %}

{% macro debug_event_counts(year) %}
    -- Print event counts by type for a specific year
    {% set query %}
        SELECT
            event_type,
            COUNT(*) as event_count
        FROM {{ ref('fct_yearly_events') }}
        WHERE simulation_year = {{ year }}
        GROUP BY event_type
        ORDER BY event_type
    {% endset %}

    {% set results = run_query(query) %}
    {% if execute %}
        {{ log("DEBUG: Event counts for year " ~ year ~ ":", info=True) }}
        {% for i in range(results.columns[0].values() | length) %}
            {{ log("  " ~ results.columns[0].values()[i] ~ ": " ~ results.columns[1].values()[i], info=True) }}
        {% endfor %}
    {% endif %}
{% endmacro %}

{% macro debug_workforce_metrics(year) %}
    -- Print workforce metrics for a specific year
    {% set query %}
        SELECT
            COUNT(*) as workforce_count,
            AVG(current_compensation) as avg_salary,
            SUM(current_compensation) as total_comp
        FROM {{ ref('fct_workforce_snapshot') }}
        WHERE simulation_year = {{ year }}
            AND employment_status = 'active'
    {% endset %}

    {% set results = run_query(query) %}
    {% if execute %}
        {{ log("DEBUG: Workforce metrics for year " ~ year ~ ":", info=True) }}
        {{ log("  Workforce count: " ~ results.columns[0].values()[0], info=True) }}
        {{ log("  Average salary: $" ~ results.columns[1].values()[0], info=True) }}
        {{ log("  Total compensation: $" ~ results.columns[2].values()[0], info=True) }}
    {% endif %}
{% endmacro %}

{% macro debug_enrollment_status(year) %}
    -- Check enrollment data quality for a specific year
    {% set query %}
        SELECT
            COUNT(*) as total_employees,
            COUNT(employee_enrollment_date) as enrolled_count,
            COUNT(*) - COUNT(employee_enrollment_date) as not_enrolled_count
        FROM {{ ref('fct_workforce_snapshot') }}
        WHERE simulation_year = {{ year }}
            AND employment_status = 'active'
    {% endset %}

    {% set results = run_query(query) %}
    {% if execute %}
        {{ log("DEBUG: Enrollment status for year " ~ year ~ ":", info=True) }}
        {{ log("  Total employees: " ~ results.columns[0].values()[0], info=True) }}
        {{ log("  Enrolled: " ~ results.columns[1].values()[0], info=True) }}
        {{ log("  Not enrolled: " ~ results.columns[2].values()[0], info=True) }}
    {% endif %}
{% endmacro %}

{% macro debug_model_dependencies(model_name) %}
    -- Show dependencies for a model (requires dbt graph parsing)
    {{ log("DEBUG: Dependencies for " ~ model_name ~ ":", info=True) }}
    {{ log("  Use DependencyAnalyzer from navigator_orchestrator.debug_utils for full graph analysis", info=True) }}
{% endmacro %}

{% macro debug_assert_not_null(column_name, context="") %}
    -- Assert that a column has no null values
    {% set null_check %}
        SELECT COUNT(*) as null_count
        FROM ({{ caller() }})
        WHERE {{ column_name }} IS NULL
    {% endset %}

    {% set results = run_query(null_check) %}
    {% if execute %}
        {% set null_count = results.columns[0].values()[0] %}
        {% if null_count > 0 %}
            {{ exceptions.raise_compiler_error("ASSERTION FAILED: " ~ null_count ~ " null values found in " ~ column_name ~ " " ~ context) }}
        {% else %}
            {{ log("✓ ASSERTION PASSED: No null values in " ~ column_name ~ " " ~ context, info=True) }}
        {% endif %}
    {% endif %}
{% endmacro %}

{% macro debug_assert_unique(key_columns, context="") %}
    -- Assert that key columns are unique
    {% set key_list = key_columns | join(', ') %}
    {% set dup_check %}
        SELECT COUNT(*) as duplicate_count
        FROM (
            SELECT {{ key_list }}, COUNT(*) as cnt
            FROM ({{ caller() }})
            GROUP BY {{ key_list }}
            HAVING COUNT(*) > 1
        )
    {% endset %}

    {% set results = run_query(dup_check) %}
    {% if execute %}
        {% set dup_count = results.columns[0].values()[0] %}
        {% if dup_count > 0 %}
            {{ exceptions.raise_compiler_error("ASSERTION FAILED: " ~ dup_count ~ " duplicate keys found " ~ context) }}
        {% else %}
            {{ log("✓ ASSERTION PASSED: Keys are unique " ~ context, info=True) }}
        {% endif %}
    {% endif %}
{% endmacro %}

{% macro debug_sample_data(table_name, limit=10) %}
    -- Print sample rows from a table
    {% set query %}
        SELECT *
        FROM {{ ref(table_name) }}
        LIMIT {{ limit }}
    {% endset %}

    {% set results = run_query(query) %}
    {% if execute %}
        {{ log("DEBUG: Sample data from " ~ table_name ~ " (first " ~ limit ~ " rows):", info=True) }}
        {{ log("  Columns: " ~ results.columns | map(attribute='name') | join(', '), info=True) }}
        {{ log("  Row count: " ~ results.rows | length, info=True) }}
    {% endif %}
{% endmacro %}
