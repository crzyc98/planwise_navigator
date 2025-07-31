{{ config(
    materialized='table',
    contract={
        "enforced": true
    }
) }}

-- Standardize raw census data column names to PlanWise Navigator's canonical schema.
-- Handles multiple possible raw column names via COALESCE() where necessary.
-- **DEDUPLICATION**: Removes duplicate employee_ids, keeping most recent hire date.
-- See stg_census_duplicates_audit for full duplicate tracking and data quality monitoring.

WITH raw_data AS (
  SELECT
      employee_id,
      employee_ssn,
      employee_birth_date,
      employee_hire_date,
      employee_termination_date,
      employee_gross_compensation,
      active,

      -- Use gross compensation as plan year compensation when specific column missing
      employee_gross_compensation AS raw_plan_year_compensation,

      -- Read DC plan fields from parquet file (now available in updated data feed)
      -- Cast to match dbt contract data types
      CAST(employee_capped_compensation AS DECIMAL(12,2)) AS employee_capped_compensation,
      CAST(employee_deferral_rate AS DECIMAL(7,5)) AS employee_deferral_rate,
      CAST(employee_contribution AS DECIMAL(12,2)) AS employee_contribution,
      CAST(pre_tax_contribution AS DECIMAL(12,2)) AS pre_tax_contribution,
      CAST(roth_contribution AS DECIMAL(12,2)) AS roth_contribution,
      CAST(after_tax_contribution AS DECIMAL(12,2)) AS after_tax_contribution,
      CAST(employer_core_contribution AS DECIMAL(12,2)) AS employer_core_contribution,
      CAST(employer_match_contribution AS DECIMAL(12,2)) AS employer_match_contribution,
      eligibility_entry_date,

      -- **FIX**: Add row_number for deduplication - prefer most recent hire_date
      ROW_NUMBER() OVER (
          PARTITION BY employee_id
          ORDER BY employee_hire_date DESC, employee_gross_compensation DESC
      ) AS rn

  FROM read_parquet('{{ var("census_parquet_path") }}')
),

-- Calculate annualized compensation for partial year workers
annualized_data AS (
  SELECT
      *,
      -- **NEW**: Annualize plan year compensation for partial year workers
      CASE
          -- New hire during plan year: gross up based on hire date to plan year end
          WHEN employee_hire_date > '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE
               AND employee_hire_date <= '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE
          THEN raw_plan_year_compensation * 365.0 /
               GREATEST(1, DATE_DIFF('day', employee_hire_date, '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE) + 1)

          -- Terminated during plan year: gross up based on termination date
          WHEN employee_termination_date IS NOT NULL
               AND employee_termination_date >= '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE
               AND employee_termination_date < '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE
          THEN raw_plan_year_compensation * 365.0 /
               GREATEST(1, DATE_DIFF('day', '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE, employee_termination_date) + 1)

          -- Mid-year hire AND termination in same plan year
          WHEN employee_hire_date > '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE
               AND employee_termination_date IS NOT NULL
               AND employee_termination_date < '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE
               AND employee_hire_date <= employee_termination_date
          THEN raw_plan_year_compensation * 365.0 /
               GREATEST(1, DATE_DIFF('day', employee_hire_date, employee_termination_date) + 1)

          -- Full year worker: plan year compensation IS the annualized amount
          ELSE raw_plan_year_compensation
      END AS employee_annualized_compensation

  FROM raw_data
  WHERE rn = 1
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
    -- **NEW**: Include both raw plan year compensation and annualized version
    raw_plan_year_compensation AS employee_plan_year_compensation,
    employee_annualized_compensation,
    employee_capped_compensation,
    employee_deferral_rate,
    employee_contribution,
    pre_tax_contribution,
    roth_contribution,
    after_tax_contribution,
    employer_core_contribution,
    employer_match_contribution,
    eligibility_entry_date

FROM annualized_data
