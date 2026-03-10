{{
  config(
    severity='error',
    tags=['data_quality', 'events', 'temporal']
  )
}}

/*
  Data Quality Test: Future Event Dates

  Validates that no events have effective dates outside the simulation year,
  with an allowance for enrollment events which legitimately cross year
  boundaries (e.g., late-year hires enrolled in early next year).

  Returns rows where event dates are invalid or unexpectedly out of range.
*/

SELECT
  employee_id,
  simulation_year,
  event_type,
  effective_date,
  CONCAT(
    'Event ', event_type, ' has invalid date: ', effective_date,
    ' for simulation year ', simulation_year
  ) as issue_description,
  CASE
    WHEN effective_date > MAKE_DATE(simulation_year, 12, 31) THEN 'CRITICAL'
    WHEN effective_date < MAKE_DATE(simulation_year, 1, 1) THEN 'ERROR'
    ELSE 'WARNING'
  END as severity
FROM {{ ref('fct_yearly_events') }}
WHERE (
    -- Events dated after the simulation year end
    effective_date > MAKE_DATE(simulation_year, 12, 31)
    -- Events dated before the simulation year start
    OR effective_date < MAKE_DATE(simulation_year, 1, 1)
  )
  -- Enrollment events may legitimately cross year boundaries for late-year hires
  -- (e.g., hired in Dec, enrolled in Jan of next year with a waiting period)
  AND event_type NOT IN ({{ evt_enrollment() }}, {{ evt_enrollment_change() }})
ORDER BY simulation_year, effective_date DESC, employee_id
