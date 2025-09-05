{{ config(
  materialized='table' if var('enable_debug_models', false) else 'ephemeral',
  tags=['DEBUG', 'MACRO_VALIDATION'],
  enabled=var('enable_debug_models', false)
) }}

{% if var('enable_debug_models', false) %}

-- E068F Macro Validation Tests
-- This model tests the core deterministic macros

WITH rng_test AS (
  SELECT
    'EMP001' AS employee_id,
    {{ hash_rng("'EMP001'", 2025, 'test') }} AS rng_value_1,
    {{ hash_rng("'EMP001'", 2025, 'test') }} AS rng_value_2,  -- Should be identical
    {{ hash_rng("'EMP001'", 2025, 'test2') }} AS rng_value_3, -- Should be different (different salt)
    {{ hash_rng("'EMP002'", 2025, 'test') }} AS rng_value_4   -- Should be different (different employee)
),

uuid_test AS (
  SELECT
    'default' AS scenario_id,
    'default' AS plan_design_id,
    'EMP001' AS employee_id,
    'hire' AS event_type,
    2025 AS simulation_year,
    CURRENT_DATE AS event_date,
    {{ generate_event_uuid() }} AS uuid_1,
    {{ generate_event_uuid() }} AS uuid_2  -- Should be identical with same inputs
),

shard_test AS (
  SELECT
    'EMP001' AS employee_id,
    {{ hash_shard("'EMP001'", 10) }} AS shard_10,
    {{ hash_shard("'EMP001'", 5) }} AS shard_5,
    {{ hash_shard("'EMP002'", 10) }} AS shard_10_diff_emp
),

validation_summary AS (
  SELECT
    -- RNG validation
    rt.rng_value_1,
    rt.rng_value_2,
    rt.rng_value_1 = rt.rng_value_2 AS rng_deterministic,
    rt.rng_value_1 != rt.rng_value_3 AS rng_salt_different,
    rt.rng_value_1 != rt.rng_value_4 AS rng_employee_different,

    -- Check RNG is in valid range [0,1)
    rt.rng_value_1 >= 0.0 AND rt.rng_value_1 < 1.0 AS rng_valid_range,

    -- UUID validation
    ut.uuid_1,
    ut.uuid_2,
    ut.uuid_1 = ut.uuid_2 AS uuid_deterministic,
    LENGTH(ut.uuid_1) AS uuid_length,
    SUBSTR(ut.uuid_1, 1, 4) = 'evt-' AS uuid_prefix_correct,

    -- Shard validation
    st.shard_10,
    st.shard_5,
    st.shard_10_diff_emp,
    st.shard_10 >= 0 AND st.shard_10 < 10 AS shard_10_valid_range,
    st.shard_5 >= 0 AND st.shard_5 < 5 AS shard_5_valid_range,
    st.shard_10 != st.shard_10_diff_emp AS shard_employee_different

  FROM rng_test rt
  CROSS JOIN uuid_test ut
  CROSS JOIN shard_test st
)

SELECT
  -- Test Results Summary
  'E068F Macro Validation Results' AS test_name,

  -- RNG Tests
  CASE WHEN rng_deterministic THEN '✅' ELSE '❌' END || ' RNG Deterministic' AS rng_test_1,
  CASE WHEN rng_salt_different THEN '✅' ELSE '❌' END || ' RNG Salt Sensitivity' AS rng_test_2,
  CASE WHEN rng_employee_different THEN '✅' ELSE '❌' END || ' RNG Employee Sensitivity' AS rng_test_3,
  CASE WHEN rng_valid_range THEN '✅' ELSE '❌' END || ' RNG Valid Range' AS rng_test_4,

  -- UUID Tests
  CASE WHEN uuid_deterministic THEN '✅' ELSE '❌' END || ' UUID Deterministic' AS uuid_test_1,
  CASE WHEN uuid_length = 20 THEN '✅' ELSE '❌' END || ' UUID Length (expected 20)' AS uuid_test_2,
  CASE WHEN uuid_prefix_correct THEN '✅' ELSE '❌' END || ' UUID Prefix' AS uuid_test_3,

  -- Shard Tests
  CASE WHEN shard_10_valid_range THEN '✅' ELSE '❌' END || ' Shard 10 Range' AS shard_test_1,
  CASE WHEN shard_5_valid_range THEN '✅' ELSE '❌' END || ' Shard 5 Range' AS shard_test_2,
  CASE WHEN shard_employee_different THEN '✅' ELSE '❌' END || ' Shard Employee Diff' AS shard_test_3,

  -- Sample values for inspection
  ROUND(rng_value_1, 6) AS sample_rng_value,
  uuid_1 AS sample_uuid,
  shard_10 AS sample_shard,

  -- Overall status
  CASE
    WHEN rng_deterministic AND rng_salt_different AND rng_employee_different AND rng_valid_range AND
         uuid_deterministic AND uuid_length = 20 AND uuid_prefix_correct AND
         shard_10_valid_range AND shard_5_valid_range AND shard_employee_different
    THEN '🎉 ALL TESTS PASSED'
    ELSE '❌ SOME TESTS FAILED'
  END AS overall_status

FROM validation_summary

{% else %}

-- Placeholder when debug not enabled
SELECT
  NULL::VARCHAR AS test_name,
  NULL::VARCHAR AS overall_status
WHERE 1=0

{% endif %}
