{{ config(
    materialized='table',
    contract={
        "enforced": true
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

-- Annualized compensation calculation
-- IMPORTANT: The source column `employee_gross_compensation` is defined as an annual amount
-- in the contract. To avoid double-annualizing, we only apply calendar-day gross-up when
-- explicitly enabled via var('annualize_partial_year_compensation').
annualized_data AS (
  SELECT
      *,
      -- Define plan year boundaries
      '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE AS plan_start,
      '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE   AS plan_end,

      -- Compute effective active window within the plan year
      GREATEST(employee_hire_date, '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE) AS active_start,
      LEAST(COALESCE(employee_termination_date, '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE), '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE) AS active_end,

      -- Days active in plan year (0 if no overlap)
      CASE
        WHEN employee_hire_date > '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE
          OR (employee_termination_date IS NOT NULL AND employee_termination_date < '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE)
        THEN 0
        ELSE GREATEST(0, DATE_DIFF('day',
                   GREATEST(employee_hire_date, '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE),
                   LEAST(COALESCE(employee_termination_date, '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE), '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE)
               ) + 1)
      END AS days_active_in_year,

      -- Plan-year compensation (partial): pro-rate the annual salary by active days
      CASE
        WHEN (
          employee_hire_date > '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE OR
          (employee_termination_date IS NOT NULL AND employee_termination_date < '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE)
        ) THEN 0.0
        WHEN DATE_DIFF('day', '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE, '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE) + 1 <= 0 THEN employee_gross_compensation
        ELSE employee_gross_compensation * ( (
          CASE
            WHEN employee_hire_date > '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE OR (employee_termination_date IS NOT NULL AND employee_termination_date < '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE)
            THEN 0
            ELSE GREATEST(0, DATE_DIFF('day',
                     GREATEST(employee_hire_date, '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE),
                     LEAST(COALESCE(employee_termination_date, '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE), '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE)
                 ) + 1)
          END
        )::DOUBLE / 365.0 )
      END AS computed_plan_year_compensation,

      -- Annualized compensation: convert partial plan-year comp back to full-year equivalent
      CASE
        WHEN (
          employee_hire_date > '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE OR
          (employee_termination_date IS NOT NULL AND employee_termination_date < '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE)
        ) THEN employee_gross_compensation
        WHEN GREATEST(1, (
          CASE
            WHEN employee_hire_date > '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE OR (employee_termination_date IS NOT NULL AND employee_termination_date < '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE)
            THEN 0
            ELSE GREATEST(0, DATE_DIFF('day',
                     GREATEST(employee_hire_date, '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE),
                     LEAST(COALESCE(employee_termination_date, '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE), '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE)
                 ) + 1)
          END
        )) = 0 THEN employee_gross_compensation
        ELSE (
          (CASE
            WHEN (
              employee_hire_date > '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE OR
              (employee_termination_date IS NOT NULL AND employee_termination_date < '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE)
            ) THEN 0.0
            ELSE employee_gross_compensation * ( (
              CASE
                WHEN employee_hire_date > '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE OR (employee_termination_date IS NOT NULL AND employee_termination_date < '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE)
                THEN 0
                ELSE GREATEST(0, DATE_DIFF('day',
                         GREATEST(employee_hire_date, '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE),
                         LEAST(COALESCE(employee_termination_date, '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE), '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE)
                     ) + 1)
              END
            )::DOUBLE / 365.0 )
          END) * 365.0 /
          GREATEST(1, (
            CASE
              WHEN employee_hire_date > '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE OR (employee_termination_date IS NOT NULL AND employee_termination_date < '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE)
              THEN 0
              ELSE GREATEST(0, DATE_DIFF('day',
                       GREATEST(employee_hire_date, '{{ var("plan_year_start_date", "2024-01-01") }}'::DATE),
                       LEAST(COALESCE(employee_termination_date, '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE), '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE)
                   ) + 1)
            END
          ))
        END AS employee_annualized_compensation

  FROM raw_data
  WHERE rn = 1
),

-- Calculate eligibility and enrollment fields
eligibility_data AS (
  SELECT
      ad.*,
      {{ var('eligibility_waiting_period_days', 30) }} AS waiting_period_days,
      -- Calculate eligibility date: hire date + waiting period
      (ad.employee_hire_date + INTERVAL {{ var('eligibility_waiting_period_days', 30) }} DAY)::DATE AS employee_eligibility_date,
      -- Determine current eligibility status based on eligibility date vs census year end
      CASE
          WHEN (ad.employee_hire_date + INTERVAL {{ var('eligibility_waiting_period_days', 30) }} DAY)::DATE <= '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE
          THEN 'eligible'
          ELSE 'pending'
      END AS current_eligibility_status,
      -- Set enrollment date to end of census year only if employee has positive deferral rate
      CASE
          WHEN ad.employee_deferral_rate > 0
          THEN '{{ var("plan_year_end_date", "2024-12-31") }}'::DATE
          ELSE NULL
      END AS employee_enrollment_date
  FROM annualized_data ad
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
    -- **NEW**: Include computed partial-year plan compensation and annualized version
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
    -- **NEW**: Add eligibility and enrollment fields
    employee_eligibility_date,
    waiting_period_days,
    current_eligibility_status,
    employee_enrollment_date

FROM eligibility_data
