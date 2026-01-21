{{
  config(
    severity='error',
    tags=['data_quality', 'status', 'new_hire']
  )
}}

/*
  Data Quality Test: New Hire Status Accuracy

  Validates that employees are only classified as 'new_hire_active'
  if they actually have a hire event in the current simulation year.

  Success Criteria (SC-002):
  - Zero employees with new_hire_active status who lack
    a current-year hire event
  - hire date must match the simulation year

  Bug Fix: Addresses the issue where employees from baseline census
  were incorrectly classified as new_hire_active.

  Returns rows where new_hire_active classification is incorrect.
*/

SELECT
    ws.employee_id,
    ws.simulation_year,
    ws.detailed_status_code,
    ws.employee_hire_date,
    EXTRACT(YEAR FROM ws.employee_hire_date) AS hire_year,
    ws.employment_status,
    CONCAT(
        'Employee ', ws.employee_id, ' has detailed_status_code=',
        ws.detailed_status_code, ' but hire_date=',
        COALESCE(CAST(ws.employee_hire_date AS VARCHAR), 'NULL'),
        ' (year ', COALESCE(CAST(EXTRACT(YEAR FROM ws.employee_hire_date) AS VARCHAR), 'NULL'),
        ') does not match simulation_year=', ws.simulation_year
    ) as issue_description,
    'ERROR' as severity
FROM {{ ref('fct_workforce_snapshot') }} ws
WHERE ws.simulation_year = {{ var('simulation_year') }}
  AND ws.detailed_status_code = 'new_hire_active'
  AND (
      ws.employee_hire_date IS NULL
      OR EXTRACT(YEAR FROM ws.employee_hire_date) != ws.simulation_year
  )
ORDER BY ws.employee_id
