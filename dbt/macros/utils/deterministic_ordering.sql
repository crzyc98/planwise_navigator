{% macro deterministic_order_by(primary_keys=[], secondary_keys=[]) %}
  {#-
    Generate deterministic ORDER BY clause for reproducible results

    This macro creates consistent ordering clauses that ensure identical
    result sets across multiple runs of the same query. Critical for
    maintaining determinism in simulation outputs.

    Parameters:
    - primary_keys: List of primary sort columns (e.g., ['employee_id', 'simulation_year'])
    - secondary_keys: List of secondary sort columns for tie-breaking (e.g., ['event_type', 'event_date'])

    Example usage:
    {{ deterministic_order_by(['employee_id', 'simulation_year'], ['event_type', 'event_date']) }}

    Returns: Complete ORDER BY clause with deterministic sorting
  #}

  ORDER BY
    {% if primary_keys %}
      {% for key in primary_keys %}
        {{ key }}{{ ',' if not loop.last }}
      {% endfor %}
      {% if secondary_keys %},{% endif %}
    {% endif %}
    {% if secondary_keys %}
      {% for key in secondary_keys %}
        {{ key }}{{ ',' if not loop.last }}
      {% endfor %}
    {% endif %}
    {% if not primary_keys and not secondary_keys %}
      1  -- Fallback to constant ordering when no keys provided
    {% endif %}

{% endmacro %}


{% macro event_standard_ordering() %}
  {#-
    Standard deterministic ordering for event tables

    Provides the canonical ordering for event-based tables to ensure
    consistent results across all event generation models.

    Returns: Standard ORDER BY clause for events
  #}

  {{ deterministic_order_by(
    ['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year'],
    ['event_type', 'event_date', 'created_at']
  ) }}

{% endmacro %}


{% macro workforce_standard_ordering() %}
  {#-
    Standard deterministic ordering for workforce snapshot tables

    Provides the canonical ordering for workforce snapshot tables.

    Returns: Standard ORDER BY clause for workforce snapshots
  #}

  {{ deterministic_order_by(
    ['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year'],
    ['snapshot_date']
  ) }}

{% endmacro %}


{% macro enforce_deterministic_output(model_sql, ordering_keys=[]) %}
  {#-
    Wrap model SQL to enforce deterministic output ordering

    This macro wraps any model SQL with deterministic ordering to ensure
    consistent results. Used in production models where result ordering
    is critical for reproducibility.

    Parameters:
    - model_sql: The SQL query to wrap (string)
    - ordering_keys: Custom ordering keys (optional, uses defaults if not provided)

    Example usage:
    {{ enforce_deterministic_output('SELECT * FROM final_events', ['employee_id', 'event_date']) }}

    Returns: Wrapped SQL with deterministic ordering
  #}

  WITH model_output AS (
    {{ model_sql }}
  )

  SELECT *
  FROM model_output
  {% if ordering_keys %}
    {{ deterministic_order_by(ordering_keys) }}
  {% else %}
    -- Use standard event ordering as default
    {{ event_standard_ordering() }}
  {% endif %}

{% endmacro %}


{% macro validate_deterministic_ordering(table_name, run_count=3) %}
  {#-
    Generate validation query to test ordering determinism

    Creates a test query that can validate whether a table produces
    consistent ordering across multiple query executions.

    Parameters:
    - table_name: Name of table to test (string)
    - run_count: Number of test runs to perform (default: 3)

    Returns: SQL query for determinism validation
  #}

  WITH run_hashes AS (
    SELECT
      run_number,
      hash(string_agg(
        CONCAT(
          COALESCE(employee_id::VARCHAR, 'null'),
          '|',
          COALESCE(event_type::VARCHAR, 'null'),
          '|',
          COALESCE(event_date::VARCHAR, 'null')
        ),
        '||'
        ORDER BY employee_id, event_type, event_date
      )) AS result_hash
    FROM (
      {% for i in range(run_count) %}
        SELECT
          {{ i + 1 }} AS run_number,
          employee_id,
          event_type,
          event_date
        FROM {{ ref(table_name) }}
        {% if not loop.last %} UNION ALL {% endif %}
      {% endfor %}
    ) multiple_runs
    GROUP BY run_number
  )
  SELECT
    COUNT(DISTINCT result_hash) AS unique_hashes,
    COUNT(*) AS total_runs,
    CASE
      WHEN COUNT(DISTINCT result_hash) = 1 THEN 'DETERMINISTIC ✅'
      ELSE 'NON-DETERMINISTIC ❌'
    END AS determinism_status,
    ARRAY_AGG(result_hash) AS hash_list
  FROM run_hashes

{% endmacro %}


{% macro add_row_hash_for_comparison() %}
  {#-
    Add row hash column for deterministic comparison

    Adds a hash column that can be used to compare rows across
    different query executions to detect non-deterministic behavior.

    Returns: SQL expression for row hash
  #}

  hash(
    CONCAT(
      COALESCE(employee_id::VARCHAR, ''),
      '|',
      COALESCE(event_type::VARCHAR, ''),
      '|',
      COALESCE(event_date::VARCHAR, ''),
      '|',
      COALESCE(simulation_year::VARCHAR, ''),
      '|',
      COALESCE(created_at::VARCHAR, '')
    )
  ) AS row_hash

{% endmacro %}


{% macro stable_window_ordering(partition_keys=[], order_keys=[]) %}
  {#-
    Generate deterministic ORDER BY clause for window functions

    Window functions require stable ordering to produce deterministic results.
    This macro provides that stable ordering with proper tie-breaking.

    Parameters:
    - partition_keys: Keys used in PARTITION BY clause
    - order_keys: Keys used in ORDER BY clause within window

    Example usage:
    ROW_NUMBER() OVER (
      PARTITION BY employee_id
      {{ stable_window_ordering(['employee_id'], ['event_date', 'event_type']) }}
    )

    Returns: ORDER BY clause for window functions
  #}

  ORDER BY
    {% for key in order_keys %}
      {{ key }}{{ ',' if not loop.last }}
    {% endfor %}
    {% if order_keys %}
      ,
    {% endif %}
    -- Add tie-breaking with deterministic hash
    hash(
      CONCAT(
        {% for key in partition_keys %}
          COALESCE({{ key }}::VARCHAR, ''),
          '|',
        {% endfor %}
        {% for key in order_keys %}
          COALESCE({{ key }}::VARCHAR, ''),
          {% if not loop.last %}'|',{% endif %}
        {% endfor %}
      )
    )

{% endmacro %}
