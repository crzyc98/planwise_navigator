{{
  config(
    severity='error',
    tags=['data_quality', 'employee_id', 'format']
  )
}}

/*
  Data Quality Test: Employee ID Format Validation

  Validates employee_id format across all data sources:
  - Baseline/census employees: EMP_YYYY_NNNNNNN (year-stamped, 7 digits)
  - Legacy baseline employees: EMP_NNNNNN (6 digits, no year)
  - New hires (with UUID): NH_YYYY_XXXXXXXX_NNNNNN
  - New hires (legacy): NH_YYYY_NNNNNN

  Returns rows with invalid employee ID formats.
*/

WITH all_employee_ids AS (
  SELECT DISTINCT
    employee_id,
    'baseline' AS source,
    2024 AS year
  FROM {{ ref('int_baseline_workforce') }}

  UNION ALL

  SELECT DISTINCT
    employee_id,
    'new_hire' AS source,
    simulation_year AS year
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = {{ evt_hire() }}

  UNION ALL

  SELECT DISTINCT
    employee_id,
    'census' AS source,
    2024 AS year
  FROM {{ ref('stg_census_data') }}
),

format_violations AS (
  SELECT
    employee_id,
    source,
    year,
    CASE
      -- Year-stamped format: EMP_YYYY_NNNNNNN
      WHEN REGEXP_MATCHES(employee_id, '^EMP_\d{4}_\d{7}$') THEN 'VALID'
      -- Legacy format: EMP_NNNNNN
      WHEN REGEXP_MATCHES(employee_id, '^EMP_\d{6}$') THEN 'VALID'
      -- New hire with UUID: NH_YYYY_XXXXXXXX_NNNNNN
      WHEN REGEXP_MATCHES(employee_id, '^NH_\d{4}_[a-f0-9]{8}_\d{6}$') THEN 'VALID'
      -- Legacy new hire: NH_YYYY_NNNNNN
      WHEN REGEXP_MATCHES(employee_id, '^NH_\d{4}_\d{6}$') THEN 'VALID'
      ELSE 'INVALID'
    END AS format_status
  FROM all_employee_ids
)

SELECT
  employee_id,
  source,
  year,
  format_status,
  CONCAT('Invalid employee ID format: ', employee_id, ' from ', source) as issue_description
FROM format_violations
WHERE format_status = 'INVALID'
ORDER BY source, employee_id
