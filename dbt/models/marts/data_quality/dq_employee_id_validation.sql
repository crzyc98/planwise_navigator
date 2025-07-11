{{ config(materialized='table') }}

-- Data quality validation for employee_id integrity across all models
-- Detects duplicates, format violations, and cross-year conflicts

WITH all_employee_ids AS (
  -- Collect all employee_ids from various sources
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

duplicate_check AS (
  SELECT
    employee_id,
    COUNT(*) AS occurrence_count,
    COUNT(DISTINCT source) AS source_count,
    COUNT(DISTINCT year) AS year_count,
    STRING_AGG(DISTINCT source, ', ') AS sources,
    STRING_AGG(DISTINCT CAST(year AS VARCHAR), ', ') AS years
  FROM all_employee_ids
  GROUP BY employee_id
  HAVING COUNT(*) > 1
),

format_check AS (
  SELECT
    employee_id,
    source,
    year,
    CASE
      -- Check baseline employee format
      WHEN employee_id LIKE 'EMP_%' AND LENGTH(employee_id) = 10
        AND REGEXP_MATCHES(employee_id, '^EMP_[0-9]{6}$') THEN 'VALID'
      -- Check new hire format (with UUID)
      WHEN employee_id LIKE 'NH_%'
        AND REGEXP_MATCHES(employee_id, '^NH_[0-9]{4}_[a-f0-9]{8}_[0-9]{6}$') THEN 'VALID'
      -- Legacy new hire format (without UUID)
      WHEN employee_id LIKE 'NH_%'
        AND REGEXP_MATCHES(employee_id, '^NH_[0-9]{4}_[0-9]{6}$') THEN 'LEGACY_VALID'
      ELSE 'INVALID'
    END AS format_status
  FROM all_employee_ids
),

ssn_duplicate_check AS (
  SELECT
    employee_ssn,
    COUNT(DISTINCT employee_id) AS unique_employee_count,
    STRING_AGG(DISTINCT employee_id, ', ') AS employee_ids
  FROM {{ ref('stg_census_data') }}
  GROUP BY employee_ssn
  HAVING COUNT(DISTINCT employee_id) > 1
),

-- Final data quality report
quality_checks AS (
  SELECT
  'DUPLICATE_IDS' AS check_type,
  'ERROR' AS severity,
  COUNT(*) AS issue_count,
  'Employee IDs appearing multiple times across sources' AS description,
  CASE
    WHEN COUNT(*) > 0 THEN STRING_AGG(
      '{"employee_id":"' || employee_id ||
      '","occurrence_count":' || occurrence_count ||
      ',"sources":"' || sources ||
      '","years":"' || years || '"}', ', '
    )
    ELSE NULL
  END AS details
FROM duplicate_check

UNION ALL

SELECT
  'INVALID_FORMAT' AS check_type,
  'WARNING' AS severity,
  COUNT(*) AS issue_count,
  'Employee IDs not matching expected format patterns' AS description,
  CASE
    WHEN COUNT(*) > 0 THEN STRING_AGG(
      '{"employee_id":"' || employee_id ||
      '","source":"' || source ||
      '","year":' || year ||
      ',"format_status":"' || format_status || '"}', ', '
    )
    ELSE NULL
  END AS details
FROM format_check
WHERE format_status = 'INVALID'

UNION ALL

SELECT
  'LEGACY_FORMAT' AS check_type,
  'INFO' AS severity,
  COUNT(*) AS issue_count,
  'New hire IDs using legacy format without UUID' AS description,
  CASE
    WHEN COUNT(*) > 0 THEN STRING_AGG(
      '{"employee_id":"' || employee_id ||
      '","source":"' || source ||
      '","year":' || year || '"}', ', '
    )
    ELSE NULL
  END AS details
FROM format_check
WHERE format_status = 'LEGACY_VALID'

UNION ALL

SELECT
  'SSN_SHARED' AS check_type,
  'ERROR' AS severity,
  COUNT(*) AS issue_count,
  'SSNs associated with multiple employee IDs' AS description,
  CASE
    WHEN COUNT(*) > 0 THEN STRING_AGG(
      '{"employee_ssn":"' || employee_ssn ||
      '","unique_employee_count":' || unique_employee_count ||
      ',"employee_ids":"' || employee_ids || '"}', ', '
    )
    ELSE NULL
  END AS details
FROM ssn_duplicate_check
)

SELECT
  check_type,
  severity,
  issue_count,
  description,
  details
FROM quality_checks
ORDER BY
  CASE severity
    WHEN 'ERROR' THEN 1
    WHEN 'WARNING' THEN 2
    WHEN 'INFO' THEN 3
  END,
  issue_count DESC
