{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['employee_id', 'simulation_year'],
    tags=['eligibility', 'erisa', 'STATE_ACCUMULATION'],
    on_schema_change='sync_all_columns'
) }}

/*
  Service Credit Accumulator (E063)

  Temporal state accumulator for independent eligibility and vesting service
  credit tracking. Follows the proven pattern from int_enrollment_state_accumulator.

  Key features:
  - Independent eligibility_years_credited and vesting_years_credited counters
  - Eligibility uses IECP/plan-year computation periods (from int_eligibility_computation_period)
  - Vesting uses plan-year-aligned hours (computed independently)
  - is_plan_eligible latches TRUE once met (never reverts)
  - Temporal accumulation: first year from baseline, subsequent from {{ this }}

  Sources:
  - int_baseline_workforce: Census employees for first-year initialization
  - int_eligibility_computation_period: Current year IECP/plan-year computation
  - int_new_hire_termination_events: Employment status
*/

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}

-- Plan year boundaries from existing UI-controlled config (setup.plan_year_start_date)
{% set pysd = var('plan_year_start_date', '2025-01-01') | string %}
{% set plan_year_start_month = pysd[5:7] | int %}
{% set plan_year_start_day = pysd[8:10] | int %}

-- Hours threshold from existing employer match/core eligibility config (UI-controlled)
{% set employer_match_config = var('employer_match', {}) %}
{% set match_eligibility = employer_match_config.get('eligibility', {}) %}
{% set eligibility_threshold_hours = match_eligibility.get('minimum_hours_annual', 1000) | int %}

{% if simulation_year == start_year %}
-- =========================================================================
-- FIRST YEAR: Initialize from baseline workforce + current year computation
-- =========================================================================

WITH baseline AS (
  SELECT
    bw.employee_id,
    bw.employee_hire_date AS hire_date,
    bw.current_tenure,
    'active' AS employment_status,
    '{{ var("scenario_id", "default") }}' AS scenario_id,
    '{{ var("plan_design_id", "default") }}' AS plan_design_id
  FROM {{ ref('int_baseline_workforce') }} bw
  WHERE bw.simulation_year = {{ simulation_year }}
    AND bw.employment_status = 'active'
    AND bw.employee_id IS NOT NULL
),

-- Current year eligibility computation periods
current_ecp AS (
  SELECT
    employee_id,
    eligibility_years_this_period,
    annual_hours_prorated AS eligibility_hours,
    hours_classification AS eligibility_classification,
    is_plan_year_eligible OR iecp_eligible OR overlap_double_credit AS is_eligible_this_year,
    plan_entry_date,
    period_type,
    hire_date,
    scenario_id,
    plan_design_id
  FROM {{ ref('int_eligibility_computation_period') }}
  WHERE simulation_year = {{ simulation_year }}
),

-- Terminated new hires
terminated AS (
  SELECT DISTINCT employee_id
  FROM {{ ref('int_new_hire_termination_events') }}
  WHERE simulation_year = {{ simulation_year }}
),

-- Compute vesting hours independently (plan-year-aligned)
-- For hire year when only IECP records exist, compute vesting hours directly
vesting_hours AS (
  SELECT
    ecp.employee_id,
    CASE
      -- Plan year records: use same hours
      WHEN ecp.period_type = {{ period_plan_year() }} THEN ecp.eligibility_hours
      -- IECP records in hire year: compute plan-year-aligned vesting hours
      WHEN ecp.period_type = {{ period_iecp() }} THEN
        GREATEST(0.0,
          DATEDIFF('day',
            GREATEST(ecp.hire_date::DATE, MAKE_DATE({{ simulation_year }}, {{ plan_year_start_month }}, {{ plan_year_start_day }})),
            MAKE_DATE({{ simulation_year }}, 12, 31)
          ) / 365.0 * 2080.0
        )
      ELSE 0.0
    END AS vesting_hours_this_year
  FROM current_ecp ecp
)

SELECT
  COALESCE(bl.employee_id, ecp.employee_id) AS employee_id,
  {{ simulation_year }} AS simulation_year,

  -- Eligibility years: seed from census tenure + current year credit
  -- FLOOR(tenure) gives completed prior years only; eligibility_years_this_period
  -- evaluates only the current computation period's hours, so no double-counting.
  -- New hires (not in baseline) fall through to 0 via COALESCE.
  COALESCE(FLOOR(bl.current_tenure)::INT, 0) + COALESCE(ecp.eligibility_years_this_period, 0)
    AS eligibility_years_credited,

  -- Vesting years: same FLOOR(tenure) seed + current year plan-year hours
  -- (see eligibility comment above for rationale on the split)
  COALESCE(FLOOR(bl.current_tenure)::INT, 0) +
    CASE
      WHEN {{ classify_service_hours('COALESCE(vh.vesting_hours_this_year, 0)', eligibility_threshold_hours) }} = 'year_of_service' THEN 1
      ELSE 0
    END AS vesting_years_credited,

  -- Current year hours
  ROUND(COALESCE(ecp.eligibility_hours, 0.0), 2)::DECIMAL(8,2) AS eligibility_hours_this_year,
  ROUND(COALESCE(vh.vesting_hours_this_year, 0.0), 2)::DECIMAL(8,2) AS vesting_hours_this_year,

  -- Classifications
  COALESCE(ecp.eligibility_classification, 'no_credit') AS eligibility_classification_this_year,
  {{ classify_service_hours('COALESCE(vh.vesting_hours_this_year, 0)', eligibility_threshold_hours) }} AS vesting_classification_this_year,

  -- Plan eligibility (latches TRUE) — census employees with tenure are already eligible
  CASE
    WHEN COALESCE(bl.current_tenure, 0) >= 1 THEN TRUE
    ELSE COALESCE(ecp.is_eligible_this_year, FALSE)
  END AS is_plan_eligible,

  -- Plan entry date
  ecp.plan_entry_date,

  -- First eligible date
  CASE
    WHEN ecp.is_eligible_this_year THEN MAKE_DATE({{ simulation_year }}, 12, 31)
    ELSE NULL
  END AS first_eligible_date,

  -- Employment status
  CASE
    WHEN t.employee_id IS NOT NULL THEN 'terminated'
    ELSE COALESCE(bl.employment_status, 'active')
  END AS employment_status,

  'baseline' AS service_credit_source,

  COALESCE(bl.scenario_id, ecp.scenario_id, '{{ var("scenario_id", "default") }}') AS scenario_id,
  COALESCE(bl.plan_design_id, ecp.plan_design_id, '{{ var("plan_design_id", "default") }}') AS plan_design_id

FROM baseline bl
FULL OUTER JOIN current_ecp ecp ON bl.employee_id = ecp.employee_id
LEFT JOIN vesting_hours vh ON COALESCE(bl.employee_id, ecp.employee_id) = vh.employee_id
LEFT JOIN terminated t ON COALESCE(bl.employee_id, ecp.employee_id) = t.employee_id
WHERE COALESCE(bl.employee_id, ecp.employee_id) IS NOT NULL

{% else %}
-- =========================================================================
-- SUBSEQUENT YEARS: Accumulate from prior year state + current year
-- =========================================================================

WITH prior_year AS (
  SELECT
    employee_id,
    eligibility_years_credited AS prior_eligibility_years,
    vesting_years_credited AS prior_vesting_years,
    is_plan_eligible AS prior_is_plan_eligible,
    plan_entry_date AS prior_plan_entry_date,
    first_eligible_date AS prior_first_eligible_date,
    employment_status AS prior_employment_status,
    scenario_id,
    plan_design_id
  FROM {{ this }}
  WHERE simulation_year = {{ simulation_year - 1 }}
    AND employee_id IS NOT NULL
),

-- Current year eligibility computation periods
current_ecp AS (
  SELECT
    employee_id,
    eligibility_years_this_period,
    annual_hours_prorated AS eligibility_hours,
    hours_classification AS eligibility_classification,
    is_plan_year_eligible OR iecp_eligible OR overlap_double_credit AS is_eligible_this_year,
    plan_entry_date,
    period_type,
    hire_date,
    scenario_id,
    plan_design_id
  FROM {{ ref('int_eligibility_computation_period') }}
  WHERE simulation_year = {{ simulation_year }}
),

-- Terminated new hires
terminated AS (
  SELECT DISTINCT employee_id
  FROM {{ ref('int_new_hire_termination_events') }}
  WHERE simulation_year = {{ simulation_year }}
),

-- Compute vesting hours independently (plan-year-aligned)
vesting_hours AS (
  SELECT
    ecp.employee_id,
    CASE
      WHEN ecp.period_type = {{ period_plan_year() }} THEN ecp.eligibility_hours
      WHEN ecp.period_type = {{ period_iecp() }} THEN
        GREATEST(0.0,
          DATEDIFF('day',
            GREATEST(ecp.hire_date, MAKE_DATE({{ simulation_year }}, {{ plan_year_start_month }}, {{ plan_year_start_day }})),
            MAKE_DATE({{ simulation_year }}, 12, 31)
          ) / 365.0 * 2080.0
        )
      ELSE 0.0
    END AS vesting_hours_this_year
  FROM current_ecp ecp
)

SELECT
  COALESCE(py.employee_id, ecp.employee_id) AS employee_id,
  {{ simulation_year }} AS simulation_year,

  -- Cumulative eligibility years
  COALESCE(py.prior_eligibility_years, 0) + COALESCE(ecp.eligibility_years_this_period, 0)
    AS eligibility_years_credited,

  -- Cumulative vesting years
  COALESCE(py.prior_vesting_years, 0) +
    CASE
      WHEN {{ classify_service_hours('COALESCE(vh.vesting_hours_this_year, 0)', eligibility_threshold_hours) }} = 'year_of_service' THEN 1
      ELSE 0
    END AS vesting_years_credited,

  -- Current year hours (reset)
  ROUND(COALESCE(ecp.eligibility_hours, 0.0), 2)::DECIMAL(8,2) AS eligibility_hours_this_year,
  ROUND(COALESCE(vh.vesting_hours_this_year, 0.0), 2)::DECIMAL(8,2) AS vesting_hours_this_year,

  -- Classifications (reset per year)
  COALESCE(ecp.eligibility_classification, 'no_credit') AS eligibility_classification_this_year,
  {{ classify_service_hours('COALESCE(vh.vesting_hours_this_year, 0)', eligibility_threshold_hours) }} AS vesting_classification_this_year,

  -- Plan eligibility: latch TRUE once met, never revert
  CASE
    WHEN COALESCE(py.prior_is_plan_eligible, FALSE) THEN TRUE
    WHEN COALESCE(ecp.is_eligible_this_year, FALSE) THEN TRUE
    ELSE FALSE
  END AS is_plan_eligible,

  -- Plan entry date: carry forward once set
  COALESCE(py.prior_plan_entry_date, ecp.plan_entry_date) AS plan_entry_date,

  -- First eligible date: carry forward once set
  CASE
    WHEN py.prior_first_eligible_date IS NOT NULL THEN py.prior_first_eligible_date
    WHEN ecp.is_eligible_this_year THEN MAKE_DATE({{ simulation_year }}, 12, 31)
    ELSE NULL
  END AS first_eligible_date,

  -- Employment status
  CASE
    WHEN t.employee_id IS NOT NULL THEN 'terminated'
    WHEN ecp.employee_id IS NOT NULL THEN 'active'
    ELSE COALESCE(py.prior_employment_status, 'active')
  END AS employment_status,

  'accumulated' AS service_credit_source,

  COALESCE(py.scenario_id, ecp.scenario_id, '{{ var("scenario_id", "default") }}') AS scenario_id,
  COALESCE(py.plan_design_id, ecp.plan_design_id, '{{ var("plan_design_id", "default") }}') AS plan_design_id

FROM prior_year py
FULL OUTER JOIN current_ecp ecp ON py.employee_id = ecp.employee_id
LEFT JOIN vesting_hours vh ON COALESCE(py.employee_id, ecp.employee_id) = vh.employee_id
LEFT JOIN terminated t ON COALESCE(py.employee_id, ecp.employee_id) = t.employee_id
WHERE COALESCE(py.employee_id, ecp.employee_id) IS NOT NULL

{% endif %}
