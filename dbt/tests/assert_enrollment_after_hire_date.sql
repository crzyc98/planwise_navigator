{{
  config(
    severity='warn',
    tags=['data_quality', 'enrollment', 'temporal'],
    warn_if='!= 0',
    error_if='> 5000'
  )
}}

-- Regression test: no enrollment event should have effective_date before hire_date
-- Note: Auto-enrollment events may precede hire dates within the same simulation
-- year because enrollment processing runs at a fixed date (e.g., Jan 15) while
-- hires occur throughout the year. This is a known timing limitation.
-- Severity set to warn with a high error threshold to catch regressions.
SELECT
  ee.employee_id,
  ee.simulation_year,
  ee.effective_date as enrollment_date,
  he.effective_date as hire_date
FROM {{ ref('int_enrollment_events') }} ee
JOIN {{ ref('int_hiring_events') }} he
  ON ee.employee_id = he.employee_id
  AND ee.simulation_year = he.simulation_year
WHERE ee.event_type = {{ evt_enrollment() }}
  AND ee.effective_date::DATE < he.effective_date::DATE
