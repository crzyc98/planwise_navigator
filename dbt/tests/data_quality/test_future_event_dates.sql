{{
  config(
    severity='error',
    tags=['data_quality', 'events', 'temporal']
  )
}}

/*
  Data Quality Test: Future Event Dates

  Validates that no events have effective dates in the future
  beyond the simulation year.

  Returns rows where event dates are invalid or in the future.
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
WHERE effective_date > MAKE_DATE(simulation_year, 12, 31)
   OR effective_date < MAKE_DATE(simulation_year, 1, 1)
ORDER BY simulation_year, effective_date DESC, employee_id
