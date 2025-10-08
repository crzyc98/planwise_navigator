{{ config(
    materialized='table',
    contract={
        "enforced": var('enforce_contracts', true)
    },
    tags=['FOUNDATION']
) }}

-- Standardize raw census data column names to PlanWise Navigator's canonical schema.
-- Handles multiple possible raw column names via COALESCE() where necessary.
-- **DEDUPLICATION**: Removes duplicate employee_ids, keeping most recent hire date.
-- See stg_census_duplicates_audit for full duplicate tracking and data quality monitoring.

WITH raw_data AS (
  SELECT
      employee_id,
      employee_ssn,
      TRY_CAST(employee_birth_date AS DATE) AS employee_birth_date,
      TRY_CAST(employee_hire_date AS DATE) AS employee_hire_date,
      TRY_CAST(employee_termination_date AS DATE) AS employee_termination_date,
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
      TRY_CAST(eligibility_entry_date AS DATE) AS eligibility_entry_date,

      -- **FIX**: Add row_number for deduplication - prefer most recent hire_date
      ROW_NUMBER() OVER (
          PARTITION BY employee_id
          ORDER BY TRY_CAST(employee_hire_date AS DATE) DESC, employee_gross_compensation DESC
      ) AS rn

  FROM read_parquet('{{ var("census_parquet_path") }}')
),

-- Annualized compensation calculation
-- IMPORTANT: The source column `employee_gross_compensation` is defined as an annual amount
-- in the contract. To avoid double-annualizing, we only apply calendar-day gross-up when
-- explicitly enabled via var('annualize_partial_year_compensation').
annualized_data AS (
  SELECT
      *,
      -- Define plan year boundaries
      CAST('{{ var("plan_year_start_date", "2024-01-01") }}' AS DATE) AS plan_start,
      CAST('{{ var("plan_year_end_date", "2024-12-31") }}' AS DATE)   AS plan_end,

      -- Compute effective active window within the plan year
      GREATEST(employee_hire_date, CAST('{{ var("plan_year_start_date", "2024-01-01") }}' AS DATE)) AS active_start,
      LEAST(COALESCE(employee_termination_date, CAST('{{ var("plan_year_end_date", "2024-12-31") }}' AS DATE)), CAST('{{ var("plan_year_end_date", "2024-12-31") }}' AS DATE)) AS active_end,

      -- Days active in plan year (0 if no overlap)
      CASE
        WHEN employee_hire_date > CAST('{{ var("plan_year_end_date", "2024-12-31") }}' AS DATE)
          OR (employee_termination_date IS NOT NULL AND employee_termination_date < CAST('{{ var("plan_year_start_date", "2024-01-01") }}' AS DATE))
        THEN 0
        ELSE GREATEST(0, DATE_DIFF('day',
                   GREATEST(employee_hire_date, CAST('{{ var("plan_year_start_date", "2024-01-01") }}' AS DATE)),
                   LEAST(COALESCE(employee_termination_date, CAST('{{ var("plan_year_end_date", "2024-12-31") }}' AS DATE)), CAST('{{ var("plan_year_end_date", "2024-12-31") }}' AS DATE))
               ) + 1)
      END AS days_active_in_year

  FROM raw_data
  WHERE rn = 1
),

-- Compensation calculations using previously derived days_active_in_year
comp_data AS (
  SELECT
    ad.*,
    CASE
      WHEN ad.days_active_in_year = 0 THEN 0.0
      ELSE ad.employee_gross_compensation * (ad.days_active_in_year / 365.0)
    END AS computed_plan_year_compensation,
    CASE
      WHEN ad.days_active_in_year = 0 THEN ad.employee_gross_compensation
      ELSE (ad.employee_gross_compensation * (ad.days_active_in_year / 365.0)) * 365.0 / GREATEST(1, ad.days_active_in_year)
    END AS employee_annualized_compensation
  FROM annualized_data ad
),

-- Calculate eligibility and enrollment fields
eligibility_data AS (
  SELECT
      ad.*,
      {{ var('eligibility_waiting_period_days', 30) }} AS waiting_period_days,
      -- Calculate eligibility date: hire date + waiting period
      -- Use DATE_ADD for DuckDB compatibility
      CAST(DATE_ADD(ad.employee_hire_date, INTERVAL {{ var('eligibility_waiting_period_days', 30) }} DAY) AS DATE) AS employee_eligibility_date,
      -- Determine current eligibility status based on eligibility date vs census year end
      CASE
          WHEN CAST(DATE_ADD(ad.employee_hire_date, INTERVAL {{ var('eligibility_waiting_period_days', 30) }} DAY) AS DATE) <= CAST('{{ var("plan_year_end_date", "2024-12-31") }}' AS DATE)
          THEN 'eligible'
          ELSE 'pending'
      END AS current_eligibility_status,
      -- Set enrollment date to end of census year only if employee has positive deferral rate
      CASE
          WHEN ad.employee_deferral_rate > 0
          THEN CAST('{{ var("plan_year_end_date", "2024-12-31") }}' AS DATE)
          ELSE NULL
      END AS employee_enrollment_date
  FROM comp_data ad
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
    computed_plan_year_compensation AS employee_plan_year_compensation,
    employee_annualized_compensation,
    employee_capped_compensation,
    employee_deferral_rate,
    employee_contribution,
    pre_tax_contribution,
    roth_contribution,
    after_tax_contribution,
    employer_core_contribution,
    employer_match_contribution,
    eligibility_entry_date,
    employee_eligibility_date,
    waiting_period_days,
    current_eligibility_status,
    employee_enrollment_date
FROM eligibility_data
