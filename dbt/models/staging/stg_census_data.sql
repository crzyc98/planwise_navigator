{{ config(materialized='table') }}

-- Standardize raw census data column names to PlanWise Navigator's canonical schema.
-- Handles multiple possible raw column names via COALESCE() where necessary.
-- **FIX**: Added deduplication logic to handle duplicate employee_ids

WITH raw_data AS (
  SELECT
      employee_id,
      'SSN-' || LPAD(REPLACE(employee_id, 'NEW_', ''), 9, '0') AS employee_ssn,
      employee_birth_date,
      employee_hire_date,
      employee_termination_date,
      employee_gross_compensation,
      active,

      -- Add missing columns with defaults for simulation compatibility
      CAST(NULL AS DECIMAL(12,2)) AS employee_plan_year_compensation,
      CAST(NULL AS DECIMAL(12,2)) AS employee_capped_compensation,
      0.0 AS employee_deferral_rate,
      0.0 AS employee_contribution,
      0.0 AS employer_core_contribution,
      0.0 AS employer_match_contribution,
      employee_hire_date AS eligibility_entry_date,

      -- **FIX**: Add row_number for deduplication - prefer most recent hire_date
      ROW_NUMBER() OVER (
          PARTITION BY employee_id
          ORDER BY employee_hire_date DESC, employee_gross_compensation DESC
      ) AS rn

  FROM read_parquet('{{ var("census_parquet_path") }}')
)

-- **FIX**: Select only the first occurrence of each employee_id after deduplication
SELECT
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    employee_termination_date,
    employee_gross_compensation,
    active,
    employee_plan_year_compensation,
    employee_capped_compensation,
    employee_deferral_rate,
    employee_contribution,
    employer_core_contribution,
    employer_match_contribution,
    eligibility_entry_date

FROM raw_data
WHERE rn = 1
