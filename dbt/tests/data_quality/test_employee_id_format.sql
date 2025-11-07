{{
  config(
    severity='error',
    tags=['data_quality', 'employee_id', 'format']
  )
}}

/*
  Data Quality Test: Employee ID Format Validation

  Validates employee_id format across all data sources:
  - Baseline employees: EMP_XXXXXX (6 digits)
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
  WHERE event_type = 'hire'

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
      WHEN employee_id LIKE 'EMP_%' AND LENGTH(employee_id) = 10
        AND REGEXP_MATCHES(employee_id, '^EMP_[0-9]{6}$') THEN 'VALID'
      WHEN employee_id LIKE 'NH_%'
        AND REGEXP_MATCHES(employee_id, '^NH_[0-9]{4}_[a-f0-9]{8}_[0-9]{6}$') THEN 'VALID'
      WHEN employee_id LIKE 'NH_%'
        AND REGEXP_MATCHES(employee_id, '^NH_[0-9]{4}_[0-9]{6}$') THEN 'LEGACY_VALID'
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
