-- Regression test: no enrollment event should have effective_date before hire_date
SELECT
  ee.employee_id,
  ee.simulation_year,
  ee.effective_date as enrollment_date,
  he.effective_date as hire_date
FROM {{ ref('int_enrollment_events') }} ee
JOIN {{ ref('int_hiring_events') }} he
  ON ee.employee_id = he.employee_id
  AND ee.simulation_year = he.simulation_year
WHERE ee.event_type = 'enrollment'
  AND ee.effective_date::DATE < he.effective_date::DATE
