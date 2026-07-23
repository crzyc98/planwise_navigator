{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key="employee_id || '_' || simulation_year",
    on_schema_change='sync_all_columns',
    tags=['STATE_ACCUMULATION', 'SNAPSHOT_PUBLICATION']
) }}

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set scenario_id = var('scenario_id', 'default') %}
{% set plan_design_id = var('plan_design_id', 'default') %}

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
    AND plan_design_id = '{{ plan_design_id }}'
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
    CASE
      WHEN {{ simulation_year }} = {{ start_year }}
        AND baseline.employee_id IS NULL
        AND EXTRACT(YEAR FROM workforce.employee_hire_date) = {{ simulation_year }}
        THEN workforce.employee_hire_date::DATE
      ELSE baseline.employee_eligibility_date
    END AS employee_eligibility_date,
    CASE
      WHEN {{ simulation_year }} = {{ start_year }}
        AND baseline.employee_id IS NULL
        AND EXTRACT(YEAR FROM workforce.employee_hire_date) = {{ simulation_year }}
        THEN 0
      ELSE baseline.waiting_period_days
    END AS waiting_period_days,
    CASE
      WHEN {{ simulation_year }} = {{ start_year }}
        AND baseline.employee_id IS NULL
        AND EXTRACT(YEAR FROM workforce.employee_hire_date) = {{ simulation_year }}
        THEN 'eligible'
      ELSE baseline.current_eligibility_status
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
  CURRENT_TIMESTAMP AS snapshot_created_at,
  last_escalation_date
FROM composed
CROSS JOIN irs_limits
