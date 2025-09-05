{% macro generate_event_uuid() %}
  {#-
    Generate deterministic UUID for events based on content hash

    This macro creates consistent, deterministic UUIDs for simulation events
    that remain identical across runs when the same data is processed.
    This ensures reproducibility and enables proper event deduplication.

    The UUID is generated using a hash of key event attributes:
    - scenario_id: Scenario identifier
    - plan_design_id: Plan design identifier
    - employee_id: Employee identifier
    - simulation_year: Year of simulation
    - event_type: Type of event (hire, termination, etc.)
    - event_date: Date when event occurs
    - random_seed: Global seed for scenario isolation

    Returns: Deterministic UUID string in format 'evt-{16-char-hash}'

    Note: This macro expects the calling context to have these columns available.
    If columns are missing, the hash will still be generated but may not be unique.
  #}

  CONCAT(
    'evt-',
    SUBSTR(
      ABS(
        HASH(
          CONCAT(
            CAST({{ var('random_seed', 42) }} AS VARCHAR),
            '|',
            CAST(COALESCE(scenario_id, 'default') AS VARCHAR),
            '|',
            CAST(COALESCE(plan_design_id, 'default') AS VARCHAR),
            '|',
            CAST(employee_id AS VARCHAR),
            '|',
            CAST(simulation_year AS VARCHAR),
            '|',
            event_type,
            '|',
            CAST(event_date AS VARCHAR)
          )
        )
      )::VARCHAR,
      1, 16
    )
  )

{% endmacro %}


{% macro generate_sequence_uuid(sequence_number) %}
  {#-
    Generate deterministic UUID with sequence number for ordered events

    This variant includes a sequence number to ensure uniqueness when
    multiple events of the same type occur for the same employee on the
    same date (e.g., multiple contribution events).

    Parameters:
    - sequence_number: Sequence number for ordering (integer)

    Returns: Deterministic UUID string with sequence
  #}

  CONCAT(
    'evt-',
    SUBSTR(
      ABS(
        HASH(
          CONCAT(
            CAST({{ var('random_seed', 42) }} AS VARCHAR),
            '|',
            CAST(COALESCE(scenario_id, 'default') AS VARCHAR),
            '|',
            CAST(COALESCE(plan_design_id, 'default') AS VARCHAR),
            '|',
            CAST(employee_id AS VARCHAR),
            '|',
            CAST(simulation_year AS VARCHAR),
            '|',
            event_type,
            '|',
            CAST(event_date AS VARCHAR),
            '|seq|',
            CAST({{ sequence_number }} AS VARCHAR)
          )
        )
      )::VARCHAR,
      1, 16
    )
  )

{% endmacro %}


{% macro generate_workforce_uuid() %}
  {#-
    Generate deterministic UUID for workforce snapshot records

    Creates consistent UUIDs for workforce snapshots that remain stable
    across simulation runs. Useful for tracking employee state over time.

    Returns: Deterministic UUID for workforce records
  #}

  CONCAT(
    'wf-',
    SUBSTR(
      ABS(
        HASH(
          CONCAT(
            CAST({{ var('random_seed', 42) }} AS VARCHAR),
            '|wf|',
            CAST(COALESCE(scenario_id, 'default') AS VARCHAR),
            '|',
            CAST(COALESCE(plan_design_id, 'default') AS VARCHAR),
            '|',
            CAST(employee_id AS VARCHAR),
            '|',
            CAST(simulation_year AS VARCHAR),
            '|',
            CAST(COALESCE(snapshot_date, CURRENT_DATE) AS VARCHAR)
          )
        )
      )::VARCHAR,
      1, 16
    )
  )

{% endmacro %}


{% macro generate_scenario_uuid() %}
  {#-
    Generate deterministic UUID for scenario identification

    Creates a consistent UUID for each unique simulation scenario based on
    the scenario configuration parameters. Useful for tracking and comparing
    different simulation runs.

    Returns: Deterministic UUID for scenario identification
  #}

  CONCAT(
    'scn-',
    SUBSTR(
      ABS(
        HASH(
          CONCAT(
            CAST({{ var('random_seed', 42) }} AS VARCHAR),
            '|scn|',
            CAST(COALESCE(scenario_id, 'default') AS VARCHAR),
            '|',
            CAST({{ var('simulation_year') }} AS VARCHAR),
            '|',
            CAST({{ var('target_growth_rate', 0.03) }} AS VARCHAR)
          )
        )
      )::VARCHAR,
      1, 16
    )
  )

{% endmacro %}


{% macro validate_uuid_uniqueness(table_name, uuid_column='event_id') %}
  {#-
    Generate validation query to check UUID uniqueness

    Creates a SQL query that can be used to validate that generated UUIDs
    are unique within the specified table. This is critical for ensuring
    event integrity in the simulation.

    Parameters:
    - table_name: Name of table to check (string)
    - uuid_column: Name of UUID column (defaults to 'event_id')

    Returns: SQL query for uniqueness validation
  #}

  WITH uuid_counts AS (
    SELECT
      {{ uuid_column }},
      COUNT(*) AS occurrence_count
    FROM {{ ref(table_name) }}
    GROUP BY {{ uuid_column }}
  ),
  duplicate_uuids AS (
    SELECT
      {{ uuid_column }},
      occurrence_count
    FROM uuid_counts
    WHERE occurrence_count > 1
  )
  SELECT
    COUNT(*) AS total_duplicates,
    COALESCE(SUM(occurrence_count), 0) AS total_duplicate_records,
    ARRAY_AGG({{ uuid_column }}) AS duplicate_uuid_list
  FROM duplicate_uuids

{% endmacro %}
