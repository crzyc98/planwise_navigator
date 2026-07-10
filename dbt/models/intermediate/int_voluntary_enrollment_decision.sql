{{ config(
  materialized='table',
  tags=['EVENT_GENERATION']
) }}

{# Match magnet (Feature 102): per-employee ceiling resolved by match mode. #}
{% set employer_match_status = var('employer_match_status', 'deferral_based') %}
{# Always-on deferral_based ceiling: the formula-derived var (exported whenever a #}
{# match is configured); falls back to the configured match_tiers below when unset. #}
{% set precomputed_match_max = var('employer_match_max_deferral_rate', none) %}
{% set match_tiers = var('match_tiers', [
    {'employee_min': 0.00, 'employee_max': 0.03, 'match_rate': 1.00},
    {'employee_min': 0.03, 'employee_max': 0.05, 'match_rate': 0.50}
]) %}
{% set enrollment_match_magnet_enabled = var('enrollment_match_magnet_enabled', true) %}
{% set enrollment_match_magnet_probability = var('enrollment_match_magnet_probability', 0.45) %}
{% set voluntary_max_deferral_rate = var('voluntary_max_deferral_rate', 0.10) %}

{# Scalar ceiling used only for deferral_based mode; other modes resolve per-employee. #}
{% if precomputed_match_max is not none %}
  {% set deferral_scalar = precomputed_match_max %}
{% else %}
  {% set ns = namespace(match_max_rate=0.0) %}
  {% for tier in match_tiers %}
    {% if tier.employee_max is not none and tier.employee_max > ns.match_max_rate %}
      {% set ns.match_max_rate = tier.employee_max %}
    {% endif %}
  {% endfor %}
  {% set deferral_scalar = ns.match_max_rate %}
{% endif %}

/*
  Voluntary Enrollment Decision Engine - Epic E053

  Implements realistic voluntary enrollment behavior based on demographics:
  - Age and job level influence enrollment decisions
  - Match optimization behavior where employees tend toward match-maximizing rates
  - ~60% voluntary enrollment rate for non-auto enrollment plans
  - Deferral rates range between 1%-10% with demographic clustering

  Key Features:
  - Demographic segmentation (age, income, job level)
  - Enrollment probability matrix calculation
  - Deferral rate selection with match optimization
  - Deterministic random decisions for reproducibility
  - Integration with existing enrollment pipeline

  Dependencies:
  - int_employee_compensation_by_year (employee demographics)
  - enrollment_registry (enrollment tracking - no circular dependencies)

  Output:
  - Employee enrollment decisions with selected deferral rates
  - Event-ready data for int_enrollment_events integration
*/

WITH active_workforce_base AS (
  -- Active continuing employees with current demographics
  -- NOTE: int_employee_compensation_by_year does NOT include a new hire in their hire year
  -- (new hires first appear here the following year), so hire-year new hires are added below.
  SELECT DISTINCT
    employee_id,
    employee_ssn,
    employee_hire_date,
    {{ var('simulation_year') }} as simulation_year,
    current_age,
    current_tenure,
    level_id,
    employee_compensation,
    employment_status
  FROM {{ ref('int_employee_compensation_by_year') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND employment_status = 'active'
    AND employee_id IS NOT NULL
),

new_hires_current_year AS (
  -- Feature 096: Include current-year new hires so they can voluntarily enroll in their HIRE year.
  -- Sourced from int_hiring_events (the canonical current-year new-hire source for ALL years,
  -- unlike int_new_hire_compensation_staging which only emits rows in the start year).
  -- Eligibility gate: only include new hires whose eligibility date falls within the current year
  -- (FR-006/FR-007); not-yet-eligible hires are first evaluated the year they become eligible.
  SELECT DISTINCT
    he.employee_id,
    he.employee_ssn,
    he.effective_date::DATE AS employee_hire_date,
    {{ var('simulation_year') }} as simulation_year,
    he.employee_age AS current_age,
    0 AS current_tenure,
    he.level_id,
    he.compensation_amount AS employee_compensation,
    'active' AS employment_status
  FROM {{ ref('int_hiring_events') }} he
  WHERE he.simulation_year = {{ var('simulation_year') }}
    AND he.employee_id IS NOT NULL
    AND EXTRACT(YEAR FROM (he.effective_date::DATE
        + INTERVAL '{{ var("eligibility_waiting_days", 0) }}' DAY)) <= {{ var('simulation_year') }}
),

active_workforce AS (
  -- Continuing employees plus hire-year new hires (deduplicated, continuing row preferred)
  SELECT * FROM active_workforce_base
  UNION
  SELECT * FROM new_hires_current_year nh
  WHERE nh.employee_id NOT IN (SELECT employee_id FROM active_workforce_base)
),

current_enrollment_status AS (
  SELECT
    employee_id,
    is_enrolled AS is_currently_enrolled,
    ever_opted_out
  FROM {{ ref('stg_prior_enrollment_state') }}
  WHERE employee_id IS NOT NULL
),

eligible_employees AS (
  -- Employees eligible for voluntary enrollment (not currently enrolled AND never opted out)
  -- CRITICAL: Exclude employees who have ever opted out - they made an explicit decision to not participate
  SELECT
    aw.*,
    COALESCE(ces.is_currently_enrolled, false) as is_currently_enrolled,
    COALESCE(ces.ever_opted_out, false) as ever_opted_out
  FROM active_workforce aw
  LEFT JOIN current_enrollment_status ces ON aw.employee_id = ces.employee_id
  -- Feature 103: resolved plan-eligibility override gates voluntary enrollment too
  LEFT JOIN {{ ref('int_plan_eligibility_override') }} ov
    ON aw.employee_id = ov.employee_id
    AND aw.simulation_year = ov.simulation_year
  WHERE COALESCE(ces.is_currently_enrolled, false) = false  -- Not currently enrolled
    AND COALESCE(ces.ever_opted_out, false) = false  -- Never opted out
    AND COALESCE(ov.is_plan_ineligible_override, false) = false  -- Feature 103 gate
),

demographic_segmentation AS (
  -- Segment employees by age, income, and job level
  SELECT
    *,
    -- Age segmentation
    CASE
      WHEN current_age < 31 THEN 'young'
      WHEN current_age < 46 THEN 'mid_career'
      WHEN current_age < 56 THEN 'mature'
      ELSE 'senior'
    END as age_segment,

    -- Income segmentation
    CASE
      WHEN employee_compensation < 50000 THEN 'low'
      WHEN employee_compensation < 100000 THEN 'moderate'
      WHEN employee_compensation < 200000 THEN 'high'
      ELSE 'executive'
    END as income_segment,

    -- Job level segmentation
    CASE
      WHEN level_id <= 2 THEN 'individual'
      WHEN level_id <= 4 THEN 'senior'
      WHEN level_id <= 6 THEN 'manager'
      ELSE 'executive'
    END as job_level_segment
  FROM eligible_employees
),

enrollment_probability_calculation AS (
  -- Calculate enrollment probability using demographic matrix
  SELECT
    *,
    -- Base enrollment rate by age
    CASE age_segment
      WHEN 'young' THEN {{ var('voluntary_enrollment_base_rates_by_age_young', 0.30) }}
      WHEN 'mid_career' THEN {{ var('voluntary_enrollment_base_rates_by_age_mid_career', 0.55) }}
      WHEN 'mature' THEN {{ var('voluntary_enrollment_base_rates_by_age_mature', 0.70) }}
      ELSE {{ var('voluntary_enrollment_base_rates_by_age_senior', 0.80) }}
    END as base_enrollment_rate,

    -- Income multiplier
    CASE income_segment
      WHEN 'low' THEN {{ var('voluntary_enrollment_income_multipliers_low', 0.70) }}
      WHEN 'moderate' THEN {{ var('voluntary_enrollment_income_multipliers_moderate', 1.00) }}
      WHEN 'high' THEN {{ var('voluntary_enrollment_income_multipliers_high', 1.15) }}
      ELSE {{ var('voluntary_enrollment_income_multipliers_executive', 1.25) }}
    END as income_multiplier,

    -- Job level multiplier
    CASE job_level_segment
      WHEN 'individual' THEN {{ var('voluntary_enrollment_job_level_multipliers_individual', 0.90) }}
      WHEN 'senior' THEN {{ var('voluntary_enrollment_job_level_multipliers_senior', 1.00) }}
      WHEN 'manager' THEN {{ var('voluntary_enrollment_job_level_multipliers_manager', 1.10) }}
      ELSE {{ var('voluntary_enrollment_job_level_multipliers_executive', 1.20) }}
    END as job_level_multiplier,

    -- Deterministic random value for enrollment decision
    (ABS(HASH(employee_id || '-voluntary-enroll-' || CAST({{ var('simulation_year') }} AS VARCHAR))) % 1000) / 1000.0 as enrollment_random

  FROM demographic_segmentation
),

deferral_rate_selection AS (
  -- Select deferral rates with demographic influences and match optimization
  SELECT
    *,
    (base_enrollment_rate * income_multiplier * job_level_multiplier * COALESCE({{ var('voluntary_enrollment_rate', 1.0) }}, 1.0)) as final_enrollment_probability,

    -- Select deferral rate based on demographics
    CASE
      WHEN age_segment = 'young' THEN
        CASE income_segment
          WHEN 'low' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_young_low', 0.03) }}
          WHEN 'moderate' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_young_moderate', 0.03) }}
          WHEN 'high' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_young_high', 0.04) }}
          ELSE {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_young_executive', 0.06) }}
        END
      WHEN age_segment = 'mid_career' THEN
        CASE income_segment
          WHEN 'low' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_mid_career_low', 0.04) }}
          WHEN 'moderate' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_mid_career_moderate', 0.06) }}
          WHEN 'high' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_mid_career_high', 0.08) }}
          ELSE {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_mid_career_executive', 0.10) }}
        END
      WHEN age_segment = 'mature' THEN
        CASE income_segment
          WHEN 'low' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_mature_low', 0.05) }}
          WHEN 'moderate' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_mature_moderate', 0.08) }}
          WHEN 'high' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_mature_high', 0.10) }}
          ELSE {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_mature_executive', 0.12) }}
        END
      ELSE -- senior
        CASE income_segment
          WHEN 'low' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_senior_low', 0.06) }}
          WHEN 'moderate' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_senior_moderate', 0.10) }}
          WHEN 'high' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_senior_high', 0.12) }}
          ELSE {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_senior_executive', 0.15) }}
        END
    END as selected_deferral_rate,

    -- Deterministic random value for deferral rate variation
    (ABS(HASH(employee_id || '-deferral-rate-' || CAST({{ var('simulation_year') }} AS VARCHAR))) % 1000) / 1000.0 as deferral_random

  FROM enrollment_probability_calculation
),

match_optimization AS (
  -- Resolve the per-employee match ceiling for the active match mode (Feature 102)
  SELECT
    *,
    {{ resolve_match_magnet_ceiling(
        employer_match_status,
        'FLOOR(current_tenure)',
        '(FLOOR(current_age) + FLOOR(current_tenure))',
        deferral_scalar
    ) }} AS match_magnet_ceiling
  FROM deferral_rate_selection
),

match_snapped AS (
  -- Snap a deterministic fraction of below-ceiling enrollees up to the ceiling
  SELECT
    *,
    {{ match_magnet_snap(
        'selected_deferral_rate',
        'match_magnet_ceiling',
        'deferral_random',
        enrollment_match_magnet_enabled,
        enrollment_match_magnet_probability
    ) }} AS optimized_deferral_rate
  FROM match_optimization
),

enrollment_decisions AS (
  -- Final enrollment decisions
  SELECT
    employee_id,
    employee_ssn,
    employee_hire_date,
    simulation_year,
    current_age,
    current_tenure,
    level_id,
    employee_compensation,
    age_segment,
    income_segment,
    job_level_segment,
    final_enrollment_probability,

    -- Enrollment decision
    CASE
      WHEN enrollment_random < final_enrollment_probability THEN true
      ELSE false
    END as will_enroll,

    -- Selected deferral rate (floor 1%; cap = configurable voluntary_max_deferral_rate)
    GREATEST(0.01, LEAST({{ voluntary_max_deferral_rate }}, optimized_deferral_rate)) as selected_deferral_rate,

    -- Event details for integration
    'voluntary_enrollment' as event_category,
    CASE
      WHEN EXTRACT(YEAR FROM employee_hire_date) = simulation_year
        -- Feature 096: hire-year new hires enroll effective their eligibility date
        -- (hire date + waiting period), which drives correct hire-year proration.
        THEN CAST(employee_hire_date + INTERVAL '{{ var("eligibility_waiting_days", 0) }}' DAY AS TIMESTAMP)
      ELSE CAST((simulation_year || '-01-15 10:00:00') AS TIMESTAMP)
    END as proposed_effective_date,

    -- Audit and tracking fields
    base_enrollment_rate,
    income_multiplier,
    job_level_multiplier,
    enrollment_random,
    deferral_random,
    selected_deferral_rate as raw_deferral_rate,
    optimized_deferral_rate as match_optimized_rate,
    match_magnet_ceiling

  FROM match_snapped
),

-- Performance metrics for monitoring
summary_metrics AS (
  SELECT
    COUNT(*) as total_eligible_employees,
    COUNT(CASE WHEN will_enroll THEN 1 END) as voluntary_enrollments,
    ROUND(COUNT(CASE WHEN will_enroll THEN 1 END) * 100.0 / COUNT(*), 1) as enrollment_percentage,
    ROUND(AVG(CASE WHEN will_enroll THEN selected_deferral_rate END), 3) as avg_deferral_rate,
    COUNT(CASE WHEN will_enroll AND selected_deferral_rate = 0.03 THEN 1 END) as enrollments_at_3_percent,
    COUNT(CASE WHEN will_enroll AND selected_deferral_rate = 0.06 THEN 1 END) as enrollments_at_6_percent
  FROM enrollment_decisions
)

-- Return enrollment decisions for integration with enrollment events
SELECT
  employee_id,
  employee_ssn,
  employee_hire_date,
  simulation_year,
  current_age,
  current_tenure,
  level_id,
  employee_compensation,
  age_segment,
  income_segment,
  job_level_segment,
  will_enroll,
  selected_deferral_rate,
  event_category,
  proposed_effective_date,
  final_enrollment_probability,

  -- Audit fields for data quality monitoring
  base_enrollment_rate,
  income_multiplier,
  job_level_multiplier,
  enrollment_random,
  deferral_random,
  raw_deferral_rate,
  match_optimized_rate,
  match_magnet_ceiling

FROM enrollment_decisions
WHERE will_enroll = true  -- Only return employees who will enroll

-- Add summary comment for monitoring
-- Summary metrics available in summary_metrics CTE for data quality validation
