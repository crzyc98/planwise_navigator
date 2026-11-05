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

-- Schema scaffold: ensures all optional DC plan columns exist with proper types
-- The WHERE false clause adds columns to schema without adding rows
WITH schema_scaffold AS (
  {{ census_schema_scaffold() }}
),

-- Combine actual parquet data with schema scaffold using UNION ALL BY NAME
-- This ensures missing columns get NULL values instead of binding errors
parquet_with_schema AS (
  SELECT * FROM read_parquet('{{ var("census_parquet_path") }}')
  UNION ALL BY NAME
  SELECT * FROM schema_scaffold
),

raw_data AS (
  SELECT
      employee_id,
      -- Synthesize a deterministic placeholder SSN from employee_id when the
      -- census omits employee_ssn (it's optional in source files — see
      -- census_schema.py — but the contract below requires a non-null value).
      -- Kept below the 900000000 range used by new-hire event SSN generation
      -- (int_hiring_events.sql) so census-derived and simulation-generated
      -- SSNs never collide.
      COALESCE(
          employee_ssn,
          'SSN-' || LPAD(CAST(ABS(PLANALIGN_HASH(employee_id)) % 900000000 AS VARCHAR), 9, '0')
      ) AS employee_ssn,
      TRY_CAST(employee_birth_date AS DATE) AS employee_birth_date,
      TRY_CAST(employee_hire_date AS DATE) AS employee_hire_date,
      TRY_CAST(employee_termination_date AS DATE) AS employee_termination_date,
      CAST(employee_gross_compensation AS DOUBLE) AS employee_gross_compensation,
      active,

      -- Preserve source compensation; comp_data applies the configured pay basis.
      CAST(employee_gross_compensation AS DOUBLE) AS raw_plan_year_compensation,

      -- DC plan fields (now safely available via schema scaffold)
      {{ stable_decimal('employee_capped_compensation', 12, 2) }} AS employee_capped_compensation,
      {{ stable_decimal('employee_deferral_rate', 7, 5) }} AS employee_deferral_rate,
      {{ stable_decimal('employee_contribution', 12, 2) }} AS employee_contribution,
      {{ stable_decimal('pre_tax_contribution', 12, 2) }} AS pre_tax_contribution,
      {{ stable_decimal('roth_contribution', 12, 2) }} AS roth_contribution,
      {{ stable_decimal('after_tax_contribution', 12, 2) }} AS after_tax_contribution,
      {{ stable_decimal('employer_core_contribution', 12, 2) }} AS employer_core_contribution,
      {{ stable_decimal('employer_match_contribution', 12, 2) }} AS employer_match_contribution,
      TRY_CAST(eligibility_entry_date AS DATE) AS eligibility_entry_date,

      -- Scheduled weekly hours: NULL means full-time (40 hrs/wk assumed downstream)
      TRY_CAST(scheduled_hours_per_week AS DECIMAL(5,2)) AS scheduled_hours_per_week,

      -- Per-employee auto-escalation opt-out (issue #316). Defaults to FALSE
      -- (employee participates in auto-escalation) when absent from the census.
      COALESCE(CAST(auto_escalation_opt_out AS BOOLEAN), FALSE) AS auto_escalation_opt_out,

      -- Per-employee plan eligibility override (Feature 103). Lenient coercion:
      -- an unrecognized value → NULL → eligible (non-fatal, clarify 2026-06-29).
      -- NULL is preserved (NOT defaulted to FALSE) so "unspecified" stays distinct
      -- from an explicit eligible/ineligible flag downstream.
      TRY_CAST(eligibility_override AS BOOLEAN) AS eligibility_override,

      -- **FIX**: Add row_number for deduplication - prefer most recent hire_date
      ROW_NUMBER() OVER (
          PARTITION BY employee_id
          ORDER BY TRY_CAST(employee_hire_date AS DATE) DESC, employee_gross_compensation DESC
      ) AS rn

  FROM parquet_with_schema
),

-- Census compensation defaults to earnings; annual_rate is an explicit opt-in.
{% set census_pay_basis = var('census_pay_basis', 'earnings') %}
{% if census_pay_basis not in ['annual_rate', 'earnings'] %}
  {{ exceptions.raise_compiler_error('census_pay_basis must be annual_rate or earnings') }}
{% endif %}
{% if census_pay_basis == 'earnings' %}
-- Preserve census-year earnings and infer annual rates for active census-year hires.
census_hire_years AS (
  SELECT YEAR(employee_hire_date) AS hire_year, COUNT(*) AS hire_count
  FROM raw_data
  GROUP BY YEAR(employee_hire_date)
),
census_calendar AS (
  SELECT MAKE_DATE(MAX(hire_year), 1, 1) AS year_start,
    MAKE_DATE(MAX(hire_year) + 1, 1, 1) AS year_end
  FROM census_hire_years
  WHERE hire_count >= GREATEST(1, (SELECT COUNT(*) FROM raw_data) * 0.01)
),
earnings_days AS (
  SELECT r.*,
    YEAR(r.employee_hire_date) = YEAR(c.year_start) AND r.employee_termination_date IS NULL AS census_year_active_hire,
    DATE_DIFF('day', c.year_start, c.year_end) AS days_in_year,
    GREATEST(0, DATE_DIFF('day', GREATEST(r.employee_hire_date, c.year_start),
      LEAST(COALESCE(r.employee_termination_date, c.year_end - INTERVAL 1 DAY),
        c.year_end - INTERVAL 1 DAY)) + 1) AS days_employed
  FROM raw_data r CROSS JOIN census_calendar c
  WHERE r.rn = 1
),
earnings_rates AS (
  SELECT *, CASE WHEN census_year_active_hire
      AND days_employed >= {{ var('census_pay_min_days', 30) }}
      AND employee_gross_compensation > 0
    THEN employee_gross_compensation * days_in_year / days_employed
    END AS qualifying_rate
  FROM earnings_days
),
comp_data AS (
  SELECT *, employee_gross_compensation AS computed_plan_year_compensation,
    CASE WHEN census_year_active_hire
      THEN COALESCE(qualifying_rate, MEDIAN(qualifying_rate) OVER (), employee_gross_compensation)
      ELSE employee_gross_compensation
    END AS employee_annualized_compensation
  FROM earnings_rates
),
{% else %}
-- Plan year proration and active-days calculation
-- In annual_rate mode, gross compensation is treated as an annual salary rate.
-- This CTE computes the employee's active window within the plan year to derive days_active_in_year,
-- which is used downstream to calculate plan-year compensation (prorated portion of the annual rate).
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

-- Derive two compensation fields from the annual salary rate:
--   1. computed_plan_year_compensation: prorated amount for the active portion of the plan year
--      (annual rate * days_active_in_year / days_in_plan_year). Equals 0 when employee has no plan-year overlap.
--   2. employee_annualized_compensation: full-year equivalent salary rate, equal to
--      employee_gross_compensation in annual_rate mode.
comp_data AS (
  SELECT
    ad.*,
    -- Plan-year compensation: prorated by active days in the plan year
    CASE
      WHEN ad.days_active_in_year = 0 THEN 0.0
      ELSE ad.employee_gross_compensation * (ad.days_active_in_year / DATE_DIFF('day',
        MAKE_DATE(YEAR(ad.plan_start), 1, 1), MAKE_DATE(YEAR(ad.plan_start) + 1, 1, 1)))
    END AS computed_plan_year_compensation,
    -- Annualized compensation: the full-year salary rate (equals gross in annual_rate mode)
    ad.employee_gross_compensation AS employee_annualized_compensation
  FROM annualized_data ad
),

{% endif %}

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
    scheduled_hours_per_week,
    employee_eligibility_date,
    waiting_period_days,
    current_eligibility_status,
    employee_enrollment_date,
    auto_escalation_opt_out,
    eligibility_override
FROM eligibility_data
