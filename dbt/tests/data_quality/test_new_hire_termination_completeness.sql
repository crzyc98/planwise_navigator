{{
  config(
    severity='error',
    tags=['data_quality', 'status', 'new_hire', 'termination']
  )
}}

/*
  Data Quality Test: New Hire Termination Completeness

  Validates that all employees classified as 'new_hire_termination'
  have complete termination data:
  - termination_date must be populated (not NULL)
  - employment_status must be 'terminated'

  Success Criteria (SC-003, SC-004):
  - 100% of new_hire_termination employees have non-null termination_date
  - 100% of new_hire_termination employees have employment_status='terminated'

  Bug Fix: Addresses the issue where new hire terminations had
  missing termination_date and incorrect employment_status due to
  column name mismatch (termination_type vs event_category).

  Returns rows where new_hire_termination data is incomplete.
*/

SELECT
    ws.employee_id,
    ws.simulation_year,
    ws.detailed_status_code,
    ws.employment_status,
    ws.termination_date,
    ws.employee_hire_date,
    CONCAT(
        'Employee ', ws.employee_id, ' has detailed_status_code=',
        ws.detailed_status_code, ' but ',
        CASE
            WHEN ws.termination_date IS NULL AND ws.employment_status != 'terminated'
            THEN 'termination_date is NULL AND employment_status=' || ws.employment_status
            WHEN ws.termination_date IS NULL
            THEN 'termination_date is NULL'
            WHEN ws.employment_status != 'terminated'
            THEN 'employment_status=' || ws.employment_status || ' (expected terminated)'
            ELSE 'unknown issue'
        END
    ) as issue_description,
    'ERROR' as severity
FROM {{ ref('fct_workforce_snapshot') }} ws
WHERE ws.simulation_year = {{ var('simulation_year') }}
  AND ws.detailed_status_code = 'new_hire_termination'
  AND (
      ws.termination_date IS NULL
      OR ws.employment_status != 'terminated'
  )
ORDER BY ws.employee_id
