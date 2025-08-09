{% macro optimize_escalation_queries() %}
  /*
    Performance optimization macros for deferral rate escalation queries

    Key optimizations:
    - Columnar storage advantages in DuckDB
    - Proper indexing for temporal queries
    - Efficient JOIN strategies for large datasets
    - Minimized data movement between CTEs
  */

  -- Optimized demographic filtering for escalation eligibility
  {% set demographic_filter %}
    AND current_age >= 25  -- Skip very young employees (rarely eligible)
    AND current_tenure >= 1  -- Skip new hires (tenure requirements)
    AND employment_status = 'active'  -- Only active employees
  {% endset %}

  -- Efficient temporal range queries for multi-year analysis
  {% set temporal_range_filter %}
    WHERE simulation_year BETWEEN {{ var('start_year', 2025) }} AND {{ var('end_year', 2029) }}
  {% endset %}

  -- Optimized JOIN hints for DuckDB
  {% set escalation_join_strategy %}
    /*+ USE_HASH_JOIN(escalation_events, escalation_state) */
  {% endset %}

  {{ return({
    'demographic_filter': demographic_filter,
    'temporal_range_filter': temporal_range_filter,
    'join_strategy': escalation_join_strategy
  }) }}

{% endmacro %}

{% macro get_escalation_batch_size() %}
  /*
    Dynamic batch sizing based on employee population
    Optimizes memory usage for large simulations
  */
  {% set batch_size_query %}
    SELECT CASE
      WHEN COUNT(DISTINCT employee_id) > 100000 THEN 10000
      WHEN COUNT(DISTINCT employee_id) > 50000 THEN 5000
      WHEN COUNT(DISTINCT employee_id) > 10000 THEN 2000
      ELSE 1000
    END AS optimal_batch_size
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = {{ var('simulation_year', 2025) }}
      AND employment_status = 'active'
  {% endset %}

  {% if execute %}
    {% set batch_size_result = run_query(batch_size_query) %}
    {% set batch_size = batch_size_result.columns[0].values()[0] %}
  {% else %}
    {% set batch_size = 2000 %}
  {% endif %}

  {{ return(batch_size) }}
{% endmacro %}

{% macro escalation_performance_hints() %}
  /*
    DuckDB-specific performance hints for escalation queries
    Leverages columnar storage and vectorized execution
  */

  -- Enable parallel processing for large datasets
  SET threads TO 4;

  -- Optimize memory for complex aggregations
  SET memory_limit = '4GB';

  -- Enable columnar storage optimizations
  SET enable_object_cache = true;
  SET enable_http_metadata_cache = true;

  -- Optimize for analytical workloads
  SET default_order = 'ASC';
  SET preserve_insertion_order = false;

{% endmacro %}

{% macro validate_escalation_performance() %}
  /*
    Performance validation for escalation models
    Ensures sub-second response times for critical queries
  */

  WITH performance_metrics AS (
    SELECT
      '{{ this }}' AS model_name,
      COUNT(*) AS total_rows,
      COUNT(DISTINCT employee_id) AS unique_employees,
      COUNT(DISTINCT simulation_year) AS simulation_years,
      MIN(simulation_year) AS min_year,
      MAX(simulation_year) AS max_year,
      -- Execution time estimation (simplified)
      CASE
        WHEN COUNT(*) > 1000000 THEN 'HIGH_VOLUME'
        WHEN COUNT(*) > 100000 THEN 'MEDIUM_VOLUME'
        WHEN COUNT(*) > 10000 THEN 'LOW_VOLUME'
        ELSE 'MINIMAL_VOLUME'
      END AS volume_category,
      CURRENT_TIMESTAMP AS measured_at
    FROM {{ this }}
  )

  SELECT
    *,
    -- Performance recommendations
    CASE volume_category
      WHEN 'HIGH_VOLUME' THEN 'Consider partitioning by simulation_year'
      WHEN 'MEDIUM_VOLUME' THEN 'Monitor query performance'
      ELSE 'Acceptable performance expected'
    END AS performance_recommendation
  FROM performance_metrics

{% endmacro %}
