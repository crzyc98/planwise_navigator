{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year'],
    on_schema_change='sync_all_columns',
    tags=['STATE_ACCUMULATION', 'SNAPSHOT_PUBLICATION']
) }}

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set scenario_id = var('scenario_id', 'default') %}

-- Public snapshot composition. Workforce events are applied only by the canonical
-- workforce accumulator; this relation joins the authoritative domain outputs.
WITH irs_limits AS (
  SELECT
    base_limit,
    catch_up_limit,
    catch_up_age_threshold,
    super_catch_up_limit,
    super_catch_up_age_min,
    super_catch_up_age_max
  FROM {{ ref('config_irs_limits') }}
  WHERE limit_year = {{ simulation_year }}
  LIMIT 1
),

workforce AS (
  SELECT
    employee_id,
    plan_design_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    current_compensation,
    prorated_annual_compensation,
    full_year_equivalent_compensation,
    current_age,
    current_tenure,
    level_id,
    age_band,
    tenure_band,
    employment_status,
    termination_date,
    termination_reason,
    detailed_status_code,
    simulation_year,
    scheduled_hours_per_week
  FROM {{ ref('int_workforce_state_accumulator') }}
  WHERE scenario_id = '{{ scenario_id }}'
    AND simulation_year = {{ simulation_year }}
),

enrollment AS (
  SELECT * EXCLUDE (state_rank)
  FROM (
    SELECT
      employee_id,
      enrollment_date,
      enrollment_status,
      enrollment_source,
      enrollment_method,
      ever_opted_out,
      ever_unenrolled,
      ROW_NUMBER() OVER (
        PARTITION BY employee_id, simulation_year
        ORDER BY created_at DESC NULLS LAST
      ) AS state_rank
    FROM {{ ref('int_enrollment_state_accumulator') }}
    WHERE scenario_id = '{{ scenario_id }}'
      AND simulation_year = {{ simulation_year }}
  ) ranked
  WHERE state_rank = 1
),

deferral AS (
  SELECT * EXCLUDE (state_rank)
  FROM (
    SELECT
      employee_id,
      current_deferral_rate,
      escalations_received,
      last_escalation_date,
      has_escalations,
      original_deferral_rate,
      total_escalation_amount,
      ROW_NUMBER() OVER (
        PARTITION BY employee_id, simulation_year
        ORDER BY created_at DESC NULLS LAST
      ) AS state_rank
    FROM {{ ref('int_deferral_rate_state_accumulator') }}
    WHERE scenario_id = '{{ scenario_id }}'
      AND simulation_year = {{ simulation_year }}
  ) ranked
  WHERE state_rank = 1
),

baseline AS (
  SELECT * EXCLUDE (baseline_rank)
  FROM (
    SELECT
      employee_id,
      employee_eligibility_date,
      waiting_period_days,
      current_eligibility_status,
      employee_enrollment_date,
      current_compensation AS baseline_compensation,
      ROW_NUMBER() OVER (
        PARTITION BY employee_id ORDER BY employee_id
      ) AS baseline_rank
    FROM {{ ref('int_baseline_workforce') }}
    WHERE simulation_year = {{ simulation_year }}
      AND employment_status = {{ status_active() }}
  ) ranked
  WHERE baseline_rank = 1
),

-- The start-year status is census provenance, evaluated at the census cutoff
-- (before the simulation starts). employee_eligibility_date is instead the
-- computed target date, so a pending start-year employee can have a target
-- date within the first simulation year. Preserve that start-year observation;
-- only an immutable eligibility event transitions pending state.
prior_year_eligibility AS (
{% if is_incremental() and simulation_year > start_year %}
  SELECT
    employee_id,
    employee_eligibility_date,
    waiting_period_days,
    current_eligibility_status
  FROM {{ this }}
  WHERE simulation_year = {{ simulation_year }} - 1
{% else %}
  -- Start year (or a first build): nothing to carry forward.
  SELECT
    CAST(NULL AS VARCHAR) AS employee_id,
    CAST(NULL AS DATE) AS employee_eligibility_date,
    CAST(NULL AS INTEGER) AS waiting_period_days,
    CAST(NULL AS VARCHAR) AS current_eligibility_status
  WHERE FALSE
{% endif %}
),

-- An eligibility event is the authoritative signal that plan eligibility was
-- achieved. int_eligibility_events emits one only when every gate passes --
-- minimum age, a waiting period that completes inside the year, and the
-- Feature 103 ineligibility override -- so event presence, not membership in
-- any cohort, is what this model reports eligibility from.
eligibility_event_years AS (
  SELECT DISTINCT
    employee_id,
    simulation_year AS event_year
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = {{ evt_eligibility() }}
    AND scenario_id = '{{ scenario_id }}'
    AND simulation_year <= {{ simulation_year }}
),

-- Transitions an employee with a census/prior-year status out of 'pending'.
--
-- Start year: events are excluded entirely (the bound below collapses to
-- `<= start_year - 1`, which matches nothing). The start-year status is census
-- provenance -- stg_census_data compares hire_date + eligibility_waiting_period_days
-- against plan_year_end_date -- so an employee hired just after that cutoff is
-- legitimately 'pending' even though their eligibility event fires on day one
-- of the simulation. #493 pinned that start-year distribution; rewriting it
-- here would undo it.
--
-- Later years: the current year's events count. This relation is end-of-year
-- state, so an employee whose event fires during year N is eligible at the
-- close of year N -- not year N+1.
achieved_eligibility_events AS (
  SELECT DISTINCT employee_id
  FROM eligibility_event_years
  WHERE event_year <= {{ simulation_year if simulation_year > start_year else simulation_year - 1 }}
),

-- Issue #499: the same signal for employees hired this year, who have neither a
-- census row nor a prior-year row to carry a status forward from.
--
-- The start-year hold above exists to protect census provenance; a new hire has
-- no census observation to protect, so their own hire-year event counts
-- immediately, in the start year as in any other. Without an event they are
-- 'pending' -- they have not yet met the requirements -- which covers a waiting
-- period running past Dec 31, a hire below minimum_age, and a Feature 103
-- new hire held ineligible for the whole horizon.
hire_year_eligibility_events AS (
  SELECT DISTINCT employee_id
  FROM eligibility_event_years
  WHERE event_year = {{ simulation_year }}
),

contributions AS (
  SELECT
    employee_id,
    annual_contribution_amount,
    effective_annual_deferral_rate,
    total_contribution_base_compensation,
    first_contribution_date,
    last_contribution_date,
    contribution_quality_flag
  FROM {{ ref('int_employee_contributions') }}
  WHERE simulation_year = {{ simulation_year }}
),

employer_match AS (
  SELECT employee_id, employer_match_amount
  FROM {{ ref('int_employee_match_calculations') }}
  WHERE simulation_year = {{ simulation_year }}
),

employer_core AS (
  SELECT employee_id, employer_core_amount
  FROM {{ ref('int_employer_core_contributions') }}
  WHERE simulation_year = {{ simulation_year }}
),

eligibility AS (
  SELECT employee_id, annual_hours_worked
  FROM {{ ref('int_employer_eligibility') }}
  WHERE simulation_year = {{ simulation_year }}
),

composed AS (
  SELECT
    workforce.*,
    -- Issue #493: census baseline (start year) -> value carried from the prior
    -- year -> the new-hire default. Precedence preserves start-year behaviour
    -- exactly: prior_year_eligibility is empty in the start year, and baseline
    -- is empty after it, so at most one of the first two ever matches.
    COALESCE(
      baseline.employee_eligibility_date,
      prior_year_eligibility.employee_eligibility_date,
      CASE
        WHEN EXTRACT(YEAR FROM workforce.employee_hire_date) = {{ simulation_year }}
          THEN workforce.employee_hire_date::DATE
      END
    ) AS employee_eligibility_date,
    COALESCE(
      baseline.waiting_period_days,
      prior_year_eligibility.waiting_period_days,
      CASE
        WHEN EXTRACT(YEAR FROM workforce.employee_hire_date) = {{ simulation_year }}
          THEN 0
      END
    ) AS waiting_period_days,
    CASE
      WHEN COALESCE(
        baseline.current_eligibility_status,
        prior_year_eligibility.current_eligibility_status
      ) = 'pending'
        AND achieved_eligibility_events.employee_id IS NOT NULL
        THEN 'eligible'
      ELSE COALESCE(
        baseline.current_eligibility_status,
        prior_year_eligibility.current_eligibility_status,
        CASE
          WHEN EXTRACT(YEAR FROM workforce.employee_hire_date) = {{ simulation_year }}
            THEN CASE
              WHEN hire_year_eligibility_events.employee_id IS NOT NULL
                THEN 'eligible'
              ELSE 'pending'
            END
        END
      )
    END AS current_eligibility_status,
    COALESCE(enrollment.enrollment_date, baseline.employee_enrollment_date)
      AS employee_enrollment_date,
    COALESCE(enrollment.enrollment_status, FALSE) AS is_enrolled_flag,
    COALESCE(deferral.current_deferral_rate, 0.00) AS current_deferral_rate,
    CASE WHEN COALESCE(deferral.current_deferral_rate, 0.00) > 0
      THEN 'participating' ELSE 'not_participating' END AS participation_status,
    CASE
      WHEN COALESCE(deferral.current_deferral_rate, 0.00) > 0 THEN
        CASE
          WHEN enrollment.enrollment_method = 'auto'
            THEN 'participating - auto enrollment'
          WHEN enrollment.enrollment_method = 'voluntary'
            THEN 'participating - voluntary enrollment'
          WHEN enrollment.enrollment_method IS NULL
            AND enrollment.enrollment_source = 'baseline'
            THEN 'participating - census enrollment'
          WHEN enrollment.enrollment_method IS NULL
            AND enrollment.enrollment_source LIKE 'event_%'
            THEN 'participating - voluntary enrollment'
          WHEN enrollment.enrollment_method IS NULL
            THEN 'participating - unknown source'
          ELSE 'participating - voluntary enrollment'
        END
      WHEN COALESCE(enrollment.ever_opted_out, FALSE)
        THEN 'not_participating - opted out of AE'
      WHEN COALESCE(enrollment.ever_unenrolled, FALSE)
        THEN 'not_participating - proactively unenrolled'
      ELSE 'not_participating - not auto enrolled'
    END AS participation_status_detail,
    COALESCE(deferral.escalations_received, 0) AS total_deferral_escalations,
    COALESCE(deferral.has_escalations, FALSE) AS has_deferral_escalations,
    COALESCE(deferral.original_deferral_rate, 0.00) AS original_deferral_rate,
    COALESCE(deferral.total_escalation_amount, 0.00)
      AS total_escalation_amount,
    COALESCE(contributions.annual_contribution_amount, 0.0)
      AS annual_contribution_amount,
    contributions.effective_annual_deferral_rate,
    contributions.total_contribution_base_compensation,
    contributions.first_contribution_date,
    contributions.last_contribution_date,
    contributions.contribution_quality_flag,
    COALESCE(employer_match.employer_match_amount, 0.0)
      AS employer_match_amount,
    COALESCE(employer_core.employer_core_amount, 0.0)
      AS employer_core_amount,
    COALESCE(employer_match.employer_match_amount, 0.0)
      + COALESCE(employer_core.employer_core_amount, 0.0)
      AS total_employer_contributions,
    COALESCE(eligibility.annual_hours_worked, 0) AS annual_hours_worked,
    baseline.baseline_compensation,
    deferral.last_escalation_date
  FROM workforce
  LEFT JOIN enrollment USING (employee_id)
  LEFT JOIN deferral USING (employee_id)
  LEFT JOIN baseline USING (employee_id)
  LEFT JOIN prior_year_eligibility USING (employee_id)
  LEFT JOIN achieved_eligibility_events USING (employee_id)
  LEFT JOIN hire_year_eligibility_events USING (employee_id)
  LEFT JOIN contributions USING (employee_id)
  LEFT JOIN employer_match USING (employee_id)
  LEFT JOIN employer_core USING (employee_id)
  LEFT JOIN eligibility USING (employee_id)
)

SELECT
  employee_id,
  employee_ssn,
  employee_birth_date,
  employee_hire_date,
  current_compensation,
  prorated_annual_compensation,
  full_year_equivalent_compensation,
  current_age,
  current_tenure,
  level_id,
  age_band,
  tenure_band,
  employment_status,
  termination_date,
  termination_reason,
  detailed_status_code,
  simulation_year,
  employee_eligibility_date,
  waiting_period_days,
  current_eligibility_status,
  employee_enrollment_date,
  is_enrolled_flag,
  current_deferral_rate,
  participation_status,
  participation_status_detail,
  total_deferral_escalations,
  has_deferral_escalations,
  original_deferral_rate,
  total_escalation_amount,
  annual_contribution_amount AS prorated_annual_contributions,
  annual_contribution_amount * 0.85 AS pre_tax_contributions,
  annual_contribution_amount * 0.15 AS roth_contributions,
  annual_contribution_amount AS ytd_contributions,
  CASE
    WHEN annual_contribution_amount >= CASE
      WHEN current_age BETWEEN irs_limits.super_catch_up_age_min
        AND irs_limits.super_catch_up_age_max
        THEN irs_limits.super_catch_up_limit
      WHEN current_age >= irs_limits.catch_up_age_threshold
        THEN irs_limits.catch_up_limit
      ELSE irs_limits.base_limit
    END THEN TRUE
    ELSE FALSE
  END AS irs_limit_reached,
  effective_annual_deferral_rate,
  total_contribution_base_compensation,
  first_contribution_date,
  last_contribution_date,
  contribution_quality_flag,
  CASE
    WHEN current_compensation > 50000000 THEN 'CRITICAL_OVER_50M'
    WHEN current_compensation > 20000000 THEN 'CRITICAL_OVER_20M'
    WHEN current_compensation > 10000000 THEN 'CRITICAL_OVER_10M'
    WHEN current_compensation > 5000000 THEN 'SEVERE_OVER_5M'
    WHEN current_compensation > 2000000 THEN CASE
      WHEN EXTRACT(YEAR FROM employee_hire_date) = simulation_year
        AND employee_hire_date >= (simulation_year || '-11-01')::DATE
        THEN 'WARNING_ANNUALIZED_LATE_HIRE'
      ELSE 'WARNING_OVER_2M'
    END
    WHEN current_compensation < 10000
      AND employment_status = {{ status_active() }} THEN 'WARNING_UNDER_10K'
    WHEN baseline_compensation IS NULL OR baseline_compensation <= 0 THEN 'NORMAL'
    WHEN current_compensation / baseline_compensation > 100.0
      THEN 'CRITICAL_INFLATION_100X'
    WHEN current_compensation / baseline_compensation > 50.0
      THEN 'CRITICAL_INFLATION_50X'
    WHEN current_compensation / baseline_compensation > 10.0
      THEN 'SEVERE_INFLATION_10X'
    WHEN current_compensation / baseline_compensation > 5.0
      THEN 'WARNING_INFLATION_5X'
    ELSE 'NORMAL'
  END AS compensation_quality_flag,
  employer_match_amount,
  employer_core_amount,
  total_employer_contributions,
  annual_hours_worked,
  scheduled_hours_per_week,
  '{{ scenario_id }}'::VARCHAR AS scenario_id,
  plan_design_id,
  CURRENT_TIMESTAMP AS snapshot_created_at,
  last_escalation_date
FROM composed
CROSS JOIN irs_limits
