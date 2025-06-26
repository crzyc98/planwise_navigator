{{ config(materialized='table') }}

-- Audit table to track duplicate employee_ids in raw census data
-- This helps identify data quality issues in source systems

WITH duplicates AS (
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
  FROM read_parquet('{{ var("census_parquet_path") }}')
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
