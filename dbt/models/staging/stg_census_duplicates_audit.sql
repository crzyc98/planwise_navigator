{{ config(materialized='table') }}

-- Audit table to track duplicate employee_ids in raw census data
-- This helps identify data quality issues in source systems

-- Match staging's optional-column scaffold without deduplicating the raw input.
WITH schema_scaffold AS (
  SELECT
      NULL::VARCHAR AS employee_ssn,
      NULL::DATE AS employee_termination_date
  WHERE FALSE
),
parquet_with_schema AS (
  SELECT * FROM read_parquet('{{ var("census_parquet_path") }}')
  UNION ALL BY NAME
  SELECT * FROM schema_scaffold
),
duplicates AS (
  SELECT
      employee_id,
      employee_ssn,
      employee_birth_date,
      employee_hire_date,
      employee_termination_date,
      employee_gross_compensation,
      active,
      COUNT(*) OVER (PARTITION BY employee_id) AS duplicate_count,
      ROW_NUMBER() OVER (
          PARTITION BY employee_id
          ORDER BY employee_hire_date DESC, employee_gross_compensation DESC
      ) AS occurrence_rank
  FROM parquet_with_schema
)

SELECT
    employee_id,
    employee_ssn,
    employee_hire_date,
    employee_termination_date,
    employee_gross_compensation,
    active,
    duplicate_count,
    occurrence_rank,
    CASE
        WHEN occurrence_rank = 1 THEN 'KEPT'
        ELSE 'DROPPED'
    END AS dedup_status,
    -- Add context for why record was kept/dropped
    CASE
        WHEN occurrence_rank = 1 THEN 'Most recent hire date'
        WHEN occurrence_rank = 2 THEN 'Second most recent'
        ELSE 'Older duplicate'
    END AS dedup_reason,
    CURRENT_TIMESTAMP AS audit_timestamp

FROM duplicates
WHERE duplicate_count > 1
ORDER BY employee_id, occurrence_rank
