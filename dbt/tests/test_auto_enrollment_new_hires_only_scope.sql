/*
  Test: Auto-Enrollment New Hires Only Scope

  When auto_enrollment_scope is 'new_hires_only', auto-enrollment events
  should only be generated for employees hired in the current simulation year
  (within the enrollment window).

  This test only activates when scope is explicitly 'new_hires_only'.
  When scope is 'all_eligible_employees' (default), the test passes trivially.

  Run with:
    dbt test --select test_auto_enrollment_new_hires_only_scope \
      --vars '{simulation_year: 2025, auto_enrollment_scope: new_hires_only}' --threads 1

  Expected: No rows returned (all auto-enrolled employees are new hires)
*/
{% if var('auto_enrollment_scope', 'all_eligible_employees') == 'new_hires_only' %}
WITH auto_enrolled_employees AS (
  SELECT
    ee.employee_id,
    ee.simulation_year,
    ee.effective_date
  FROM {{ ref('int_enrollment_events') }} ee
  WHERE ee.event_category = 'auto_enrollment'
    AND ee.simulation_year = {{ var('simulation_year') }}
),

new_hires AS (
  SELECT DISTINCT
    he.employee_id,
    he.effective_date::DATE AS hire_date
  FROM {{ ref('int_hiring_events') }} he
  WHERE he.simulation_year = {{ var('simulation_year') }}
)

-- Find auto-enrolled employees who are NOT new hires (violation)
SELECT
  ae.employee_id,
  ae.simulation_year
FROM auto_enrolled_employees ae
LEFT JOIN new_hires nh ON ae.employee_id = nh.employee_id
WHERE nh.employee_id IS NULL
{% else %}
-- Test is a no-op when scope is 'all_eligible_employees' (default)
SELECT 1 WHERE false
{% endif %}
