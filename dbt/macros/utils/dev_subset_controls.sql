{% macro apply_dev_subset(base_query) %}
  {#-
    Apply development subset controls to limit data processing

    This macro wraps any base query with development subset logic to limit
    the amount of data processed during development and testing. This dramatically
    speeds up development cycles by processing only a subset of employees.

    Parameters:
    - base_query: Base SQL query to apply subset to (string)

    Variables used:
    - dev_employee_limit: Limit to N employees (exact count)
    - dev_subset_pct: Limit to percentage of employees (0.0-1.0)
    - dev_employee_ids: Specific list of employee IDs to include (comma-separated string)
    - debug_employee_id: Single employee ID for focused debugging
    - enable_dev_subset: Master switch to enable/disable subset controls (default: false)

    Example usage:
    {{ apply_dev_subset("SELECT * FROM base_table WHERE active = 1") }}
  #}

  WITH base_data AS (
    {{ base_query }}
  )

  {% if var('enable_dev_subset', false) %}

    {% if var('debug_employee_id', '') %}
    -- Debug mode: single employee
    , subset_data AS (
      SELECT *
      FROM base_data
      WHERE employee_id = '{{ var("debug_employee_id") }}'
    )

    {% elif var('dev_employee_ids', '') %}
    -- Specific employee list mode
    , subset_data AS (
      SELECT *
      FROM base_data
      WHERE employee_id IN (
        {% set employee_list = var('dev_employee_ids').split(',') %}
        {% for emp_id in employee_list %}
          '{{ emp_id.strip() }}'{{ ',' if not loop.last }}
        {% endfor %}
      )
    )

    {% elif var('dev_subset_pct', 0) > 0 %}
    -- Percentage-based subset using deterministic hash
    , subset_data AS (
      SELECT *
      FROM base_data
      WHERE {{ hash_rng('employee_id', 0, 'subset') }} < {{ var('dev_subset_pct') }}
      {% if var('dev_employee_limit', 0) > 0 %}
        LIMIT {{ var('dev_employee_limit') }}
      {% endif %}
    )

    {% elif var('dev_employee_limit', 0) > 0 %}
    -- Simple count limit with deterministic ordering
    , subset_data AS (
      SELECT *
      FROM base_data
      ORDER BY employee_id  -- Deterministic ordering
      LIMIT {{ var('dev_employee_limit') }}
    )

    {% else %}
    -- No subset controls active, return full data
    , subset_data AS (
      SELECT *
      FROM base_data
    )

    {% endif %}

  {% else %}
  -- Development subset disabled, return full data
  , subset_data AS (
    SELECT *
    FROM base_data
  )

  {% endif %}

  SELECT * FROM subset_data

{% endmacro %}


{% macro dev_limit_clause() %}
  {#-
    Generate LIMIT clause for development subset controls

    This is a lighter-weight alternative to apply_dev_subset for cases where
    you just need to add a LIMIT clause to an existing query.

    Returns: SQL LIMIT clause or empty string
  #}

  {% if var('enable_dev_subset', false) %}
    {% if var('dev_employee_limit', 0) > 0 %}
      LIMIT {{ var('dev_employee_limit') }}
    {% endif %}
  {% endif %}

{% endmacro %}


{% macro dev_where_clause() %}
  {#-
    Generate WHERE clause for development subset controls

    This macro generates WHERE conditions for development subset filtering
    that can be added to existing queries.

    Returns: SQL WHERE conditions or empty string
  #}

  {% if var('enable_dev_subset', false) %}
    {% if var('debug_employee_id', '') %}
      AND employee_id = '{{ var("debug_employee_id") }}'
    {% elif var('dev_employee_ids', '') %}
      AND employee_id IN (
        {% set employee_list = var('dev_employee_ids').split(',') %}
        {% for emp_id in employee_list %}
          '{{ emp_id.strip() }}'{{ ',' if not loop.last }}
        {% endfor %}
      )
    {% elif var('dev_subset_pct', 0) > 0 %}
      AND {{ hash_rng('employee_id', 0, 'subset') }} < {{ var('dev_subset_pct') }}
    {% endif %}
  {% endif %}

{% endmacro %}


{% macro dev_employee_sample(sample_size=1000) %}
  {#-
    Generate a deterministic sample of employee IDs for development

    Creates a consistent sample of employee IDs that can be used across
    multiple models for development and testing purposes.

    Parameters:
    - sample_size: Number of employees to include in sample (default: 1000)

    Returns: CTE that provides sampled employee IDs
  #}

  dev_employee_sample AS (
    SELECT employee_id
    FROM {{ ref('int_baseline_workforce') }}
    WHERE {{ hash_rng('employee_id', 0, 'dev_sample') }} < {{ sample_size / 50000.0 }}
    ORDER BY employee_id
    LIMIT {{ sample_size }}
  )

{% endmacro %}


{% macro validate_dev_subset_performance() %}
  {#-
    Generate performance validation query for development subset

    Creates a query to validate that development subset controls are
    effectively reducing processing time and resource usage.

    Returns: SQL query for performance validation
  #}

  WITH full_data_stats AS (
    SELECT
      'full_dataset' AS subset_type,
      COUNT(*) AS record_count,
      COUNT(DISTINCT employee_id) AS employee_count,
      MIN(simulation_year) AS min_year,
      MAX(simulation_year) AS max_year
    FROM {{ ref('int_baseline_workforce') }}
  ),
  subset_data_stats AS (
    SELECT
      'development_subset' AS subset_type,
      COUNT(*) AS record_count,
      COUNT(DISTINCT employee_id) AS employee_count,
      MIN(simulation_year) AS min_year,
      MAX(simulation_year) AS max_year
    FROM (
      {{ apply_dev_subset("SELECT * FROM " ~ ref('int_baseline_workforce')) }}
    ) subset_data
  )
  SELECT
    subset_type,
    record_count,
    employee_count,
    min_year,
    max_year,
    ROUND(100.0 * record_count / LAG(record_count) OVER (ORDER BY subset_type), 2) AS pct_of_full_data
  FROM (
    SELECT * FROM full_data_stats
    UNION ALL
    SELECT * FROM subset_data_stats
  ) combined_stats
  ORDER BY subset_type

{% endmacro %}


{% macro log_dev_subset_status() %}
  {#-
    Log current development subset configuration

    This macro logs the current development subset settings to help
    developers understand what subset controls are active.
  #}

  {% if var('enable_dev_subset', false) %}
    {% if var('debug_employee_id', '') %}
      {{ log('🔍 DEBUG MODE: Processing single employee: ' ~ var('debug_employee_id'), info=true) }}
    {% elif var('dev_employee_ids', '') %}
      {{ log('👥 DEV SUBSET: Processing specific employee list', info=true) }}
    {% elif var('dev_subset_pct', 0) > 0 %}
      {{ log('📊 DEV SUBSET: Processing ' ~ (var('dev_subset_pct') * 100) ~ '% of employees', info=true) }}
    {% elif var('dev_employee_limit', 0) > 0 %}
      {{ log('🔢 DEV SUBSET: Processing first ' ~ var('dev_employee_limit') ~ ' employees', info=true) }}
    {% else %}
      {{ log('⚠️  DEV SUBSET: Enabled but no subset controls configured', info=true) }}
    {% endif %}
  {% else %}
    {{ log('🚀 FULL DATASET: Development subset controls disabled', info=true) }}
  {% endif %}

{% endmacro %}
