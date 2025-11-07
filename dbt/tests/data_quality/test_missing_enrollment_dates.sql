{{
  config(
    severity='error',
    tags=['data_quality', 'enrollment', 'dates']
  )
}}

/*
  Data Quality Test: Missing Enrollment Dates

  Validates that all enrolled employees have enrollment dates.
  Missing enrollment dates indicate a critical architecture issue.

  Returns rows where employees are enrolled but missing enrollment dates.
*/

SELECT
  employee_id,
  simulation_year,
  is_enrolled_flag,
  employee_enrollment_date,
  employment_status,
  current_deferral_rate,
  CONCAT(
    'Employee ', employee_id, ' is enrolled (rate: ',
    ROUND(current_deferral_rate * 100, 2), '%) but missing enrollment date'
  ) as issue_description,
  'CRITICAL' as severity
FROM {{ ref('fct_workforce_snapshot') }}
WHERE is_enrolled_flag = true
  AND employee_enrollment_date IS NULL
  AND employment_status = 'active'
ORDER BY simulation_year, employee_id
