{% macro hash_rng(employee_id, simulation_year, event_type, salt='') %}
  {#-
    Generate deterministic random number between 0 and 1 using hash function

    This macro provides deterministic randomness for workforce simulation events,
    ensuring reproducible results across runs while maintaining proper random
    distribution properties.

    Parameters:
    - employee_id: Employee identifier (string or numeric)
    - simulation_year: Year of simulation (integer)
    - event_type: Type of event (hire, termination, promotion, etc.)
    - salt: Additional randomization salt (optional string)

    Returns: Uniform random number between 0.0 and 1.0

    The hash key ensures deterministic results across runs while providing
    independent random numbers for each employee/year/event combination.
    Incorporates the global random_seed variable for scenario isolation.
  #}

  (
    -- Use DuckDB's hash function for deterministic random generation
    -- Combine all input parameters with global random seed into a single hash key
    ABS(
      HASH(
        CONCAT(
          CAST({{ var('random_seed', 42) }} AS VARCHAR),
          '|',
          CAST({{ employee_id }} AS VARCHAR),
          '|',
          CAST({{ simulation_year }} AS VARCHAR),
          '|',
          '{{ event_type }}',
          {% if salt %}
          '|',
          '{{ salt }}'
          {% endif %}
        )
      )
    ) % 2147483647  -- Use large prime to avoid modulo bias
  ) / 2147483647.0  -- Normalize to [0, 1)

{% endmacro %}


{% macro hash_shard(employee_id, total_shards) %}
  {#-
    Assign employee to shard using consistent hash function

    Useful for distributing workload across parallel processing shards
    while maintaining deterministic assignment.

    Parameters:
    - employee_id: Employee identifier
    - total_shards: Total number of shards (must be > 0)

    Returns: Shard number (0 to total_shards-1)
  #}

  ABS(
    HASH(
      CONCAT(
        CAST({{ var('random_seed', 42) }} AS VARCHAR),
        '|shard|',
        CAST({{ employee_id }} AS VARCHAR)
      )
    )
  ) % {{ total_shards }}

{% endmacro %}


{% macro rand_uniform_legacy() %}
  {#-
    Legacy random number generation for backwards compatibility

    This macro maintains compatibility with existing models that use
    the old HASH(employee_id) % 1000 / 1000.0 pattern.

    Note: Use hash_rng() for new models as it provides better
    determinism and event-specific randomness.
  #}

  (ABS(HASH(employee_id)) % 1000) / 1000.0

{% endmacro %}


{% macro validate_rng_distribution(sample_size=10000) %}
  {#-
    Generate validation query to test RNG distribution properties

    This macro creates a SQL query that can be used to validate
    that the hash-based RNG produces uniform distribution.

    Parameters:
    - sample_size: Number of samples to generate for testing

    Returns: SQL query for distribution validation
  #}

  WITH rng_samples AS (
    SELECT
      seq_num,
      {{ hash_rng('seq_num', 2025, 'test') }} AS random_value
    FROM (
      SELECT ROW_NUMBER() OVER () AS seq_num
      FROM (VALUES (1)) AS t
      CROSS JOIN GENERATE_SERIES(1, {{ sample_size }}) AS g(i)
    ) samples
  ),
  distribution_stats AS (
    SELECT
      COUNT(*) AS total_samples,
      AVG(random_value) AS mean,
      STDDEV(random_value) AS stddev,
      MIN(random_value) AS min_value,
      MAX(random_value) AS max_value,
      -- Check uniformity by dividing into 10 buckets
      COUNT(CASE WHEN random_value < 0.1 THEN 1 END) AS bucket_0_1,
      COUNT(CASE WHEN random_value >= 0.1 AND random_value < 0.2 THEN 1 END) AS bucket_1_2,
      COUNT(CASE WHEN random_value >= 0.2 AND random_value < 0.3 THEN 1 END) AS bucket_2_3,
      COUNT(CASE WHEN random_value >= 0.3 AND random_value < 0.4 THEN 1 END) AS bucket_3_4,
      COUNT(CASE WHEN random_value >= 0.4 AND random_value < 0.5 THEN 1 END) AS bucket_4_5,
      COUNT(CASE WHEN random_value >= 0.5 AND random_value < 0.6 THEN 1 END) AS bucket_5_6,
      COUNT(CASE WHEN random_value >= 0.6 AND random_value < 0.7 THEN 1 END) AS bucket_6_7,
      COUNT(CASE WHEN random_value >= 0.7 AND random_value < 0.8 THEN 1 END) AS bucket_7_8,
      COUNT(CASE WHEN random_value >= 0.8 AND random_value < 0.9 THEN 1 END) AS bucket_8_9,
      COUNT(CASE WHEN random_value >= 0.9 THEN 1 END) AS bucket_9_10
    FROM rng_samples
  )
  SELECT
    *,
    -- Expected bucket size for uniform distribution
    total_samples / 10.0 AS expected_bucket_size,
    -- Chi-square test statistic for uniformity
    (
      POWER(bucket_0_1 - total_samples/10.0, 2) +
      POWER(bucket_1_2 - total_samples/10.0, 2) +
      POWER(bucket_2_3 - total_samples/10.0, 2) +
      POWER(bucket_3_4 - total_samples/10.0, 2) +
      POWER(bucket_4_5 - total_samples/10.0, 2) +
      POWER(bucket_5_6 - total_samples/10.0, 2) +
      POWER(bucket_6_7 - total_samples/10.0, 2) +
      POWER(bucket_7_8 - total_samples/10.0, 2) +
      POWER(bucket_8_9 - total_samples/10.0, 2) +
      POWER(bucket_9_10 - total_samples/10.0, 2)
    ) / (total_samples/10.0) AS chi_square_statistic
  FROM distribution_stats

{% endmacro %}
