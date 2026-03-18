/*
  Test: Auto-Enrollment Enabled Generates Events

  When auto_enrollment_enabled is true (default), the int_enrollment_events model
  should generate auto-enrollment events. This test asserts at least one
  auto_enrollment event exists, confirming the default behavior is preserved.

  Run with:
    dbt test --select test_auto_enrollment_enabled_generates_events \
      --vars '{simulation_year: 2025}' --threads 1

  Expected: No rows returned (assertion passes when auto-enrollment count > 0)
*/
WITH auto_enrollment_count AS (
  SELECT COUNT(*) AS cnt
  FROM {{ ref('int_enrollment_events') }}
  WHERE event_category = 'auto_enrollment'
    AND simulation_year = {{ var('simulation_year') }}
)
SELECT cnt
FROM auto_enrollment_count
WHERE cnt = 0
