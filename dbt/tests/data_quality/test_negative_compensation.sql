{{
  config(
    severity='error',
    tags=['data_quality', 'compensation', 'critical']
  )
}}

/*
  Data Quality Test: Negative Compensation Detection

  Validates that no employees have negative compensation values,
  which would indicate a critical data integrity issue.

  Returns rows where compensation is negative or suspiciously low.
*/

SELECT
  employee_id,
  simulation_year,
  current_compensation,
  prorated_annual_compensation,
  full_year_equivalent_compensation,
  employment_status,
  'Negative or zero compensation detected' as issue_description,
  CASE
    WHEN current_compensation < 0 THEN 'CRITICAL'
    WHEN current_compensation = 0 AND employment_status = 'active' THEN 'ERROR'
    WHEN current_compensation < 10000 AND employment_status = 'active' THEN 'WARNING'
    ELSE 'OK'
  END as severity
FROM {{ ref('fct_workforce_snapshot') }}
WHERE current_compensation <= 0
   OR (current_compensation < 10000 AND employment_status = 'active')
ORDER BY current_compensation ASC, employee_id
