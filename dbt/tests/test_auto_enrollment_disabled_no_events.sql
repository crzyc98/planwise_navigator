/*
  Test: Auto-Enrollment Disabled Produces No Auto-Enrollment Events

  When auto_enrollment_enabled is set to false, the int_enrollment_events model
  should NOT generate any rows with event_category = 'auto_enrollment'.

  This test only activates when auto_enrollment_enabled is explicitly false.
  When the var is true (default), the test passes trivially.

  Run with:
    dbt test --select test_auto_enrollment_disabled_no_events \
      --vars '{simulation_year: 2025, auto_enrollment_enabled: false}' --threads 1

  Expected: No rows returned (0 auto-enrollment events when disabled)
*/
{% if not var('auto_enrollment_enabled', true) %}
SELECT
  employee_id,
  simulation_year,
  event_category
FROM {{ ref('int_enrollment_events') }}
WHERE event_category = 'auto_enrollment'
  AND simulation_year = {{ var('simulation_year') }}
{% else %}
-- Test is a no-op when auto_enrollment_enabled is true (default)
SELECT 1 WHERE false
{% endif %}
