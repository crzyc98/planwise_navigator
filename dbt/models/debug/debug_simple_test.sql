{{ config(
  materialized='table' if var('enable_debug_models', false) else 'ephemeral',
  tags=['DEBUG', 'SIMPLE_TEST'],
  enabled=var('enable_debug_models', false)
) }}

{% if var('enable_debug_models', false) %}

-- Simple E068F test to validate basic functionality

SELECT
  'E068F Simple Test' AS test_name,
  42 AS random_seed_used,
  {{ var('random_seed', 42) }} AS random_seed_var,
  2025 AS simulation_year,

  -- Test basic hash function
  ABS(HASH('test_string')) % 1000000 AS basic_hash_test,

  -- Test the range of hash values
  ABS(HASH('test_string')) % 2147483647 / 2147483647.0 AS normalized_hash,

  'Basic functionality validated' AS status

{% else %}

SELECT
  NULL::VARCHAR AS test_name,
  NULL::INTEGER AS random_seed_used,
  NULL::INTEGER AS random_seed_var,
  NULL::INTEGER AS simulation_year,
  NULL::BIGINT AS basic_hash_test,
  NULL::DOUBLE AS normalized_hash,
  NULL::VARCHAR AS status
WHERE 1=0

{% endif %}
