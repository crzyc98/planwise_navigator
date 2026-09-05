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
{% set voluntary_max_deferral_rate = var('voluntary_max_deferral_rate', 0.15) %}

{# Issue #652: flat new-hire voluntary enrollment rate.
   Unset (none) keeps the demographic model for everyone -- this is what makes
   pre-existing scenarios reproduce exactly. When the analyst sets a value it
   becomes the exact fraction of eligible NEW HIRES who enroll; continuing
   employees stay on the demographic model either way. #}
{% set flat_new_hire_voluntary_rate = var('voluntary_enrollment_rate', none) %}

{# Issue #652: upward-only deferral spread. 0 disables it. #}
{% set deferral_spread_max_lift = var('deferral_spread_max_lift', 0) %}

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
    assignment.plan_design_id,
    eligibility.plan_eligibility_date,
    COALESCE(ces.is_currently_enrolled, false) as is_currently_enrolled,
    COALESCE(ces.ever_opted_out, false) as ever_opted_out
  FROM active_workforce aw
  LEFT JOIN current_enrollment_status ces ON aw.employee_id = ces.employee_id
  INNER JOIN {{ ref('int_plan_design_assignment_accumulator') }} assignment
    ON aw.employee_id = assignment.employee_id
   AND aw.simulation_year = assignment.simulation_year
   AND assignment.scenario_id = '{{ var('scenario_id', 'default') }}'
  INNER JOIN {{ ref('int_plan_eligibility_determination') }} eligibility
    ON aw.employee_id = eligibility.employee_id
   AND aw.simulation_year = eligibility.simulation_year
   AND assignment.plan_design_id = eligibility.plan_design_id
   AND eligibility.scenario_id = '{{ var('scenario_id', 'default') }}'
  -- Feature 103: resolved plan-eligibility override gates voluntary enrollment too
  LEFT JOIN {{ ref('int_plan_eligibility_override') }} ov
    ON aw.employee_id = ov.employee_id
    AND aw.simulation_year = ov.simulation_year
  WHERE COALESCE(ces.is_currently_enrolled, false) = false  -- Not currently enrolled
    AND COALESCE(ces.ever_opted_out, false) = false  -- Never opted out
    AND COALESCE(ov.is_plan_ineligible_override, false) = false  -- Feature 103 gate
    AND eligibility.is_plan_eligible
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
    {%- if flat_new_hire_voluntary_rate is not none %}
    -- Issue #652: hire-year new hires use the analyst's flat rate directly.
    -- Continuing employees keep the demographic product.
    CASE
      WHEN EXTRACT(YEAR FROM employee_hire_date) = simulation_year
        THEN {{ flat_new_hire_voluntary_rate }}
      ELSE (base_enrollment_rate * income_multiplier * job_level_multiplier)
    END as final_enrollment_probability,
    {%- else %}
    (base_enrollment_rate * income_multiplier * job_level_multiplier) as final_enrollment_probability,
    {%- endif %}

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
    (ABS(HASH(employee_id || '-deferral-rate-' || CAST({{ var('simulation_year') }} AS VARCHAR))) % 1000) / 1000.0 as deferral_random,

    -- Issue #652: SEPARATE seed from deferral_random, which is already spent on
    -- the match-magnet snap. Sharing it would correlate "spread upward" with
    -- "snapped to the match ceiling".
    (ABS(HASH(employee_id || '-deferral-spread-' || CAST({{ var('simulation_year') }} AS VARCHAR))) % 1000) / 1000.0 as spread_random

  FROM enrollment_probability_calculation
),

spread_applied AS (
  -- Issue #652: lift the demographic table value upward before the match
  -- magnet runs, so match-maximising behaviour still operates on the spread
  -- rate rather than the bare floor.
  SELECT
    *,
    {{ deferral_spread('selected_deferral_rate', 'spread_random', deferral_spread_max_lift) }} AS spread_deferral_rate
  FROM deferral_rate_selection
),

match_optimization AS (
  -- Resolve the per-employee match ceiling for the active match mode (Feature 102)
  SELECT
    *,
    {{ resolve_match_magnet_ceiling(
        employer_match_status,
        'FLOOR(source.current_tenure)',
        '(FLOOR(source.current_age) + FLOOR(source.current_tenure))',
        deferral_scalar,
        'source.plan_design_id'
    ) }} AS match_magnet_ceiling
  FROM spread_applied source
),

match_snapped AS (
  -- Snap a deterministic fraction of below-ceiling enrollees up to the ceiling
  SELECT
    *,
    {{ match_magnet_snap(
        'spread_deferral_rate',
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
    plan_design_id,
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
    {%- if flat_new_hire_voluntary_rate is not none %}
    -- Issue #652 (decision D3, revised after measurement): EXACT-COUNT
    -- selection for the flat new-hire rate. Rank the hire-year cohort by its
    -- deterministic draw and take the top P*N.
    --
    -- A raw threshold (enrollment_random < P) was tried first and rejected:
    -- the draw hashes structured ids like NH_2029_000123 and takes a modulo,
    -- which does not distribute evenly across ids sharing long prefixes. In a
    -- 2026-2030 run the realised opt-out share drifted to 14.9% against a
    -- configured 10% (3.6 sigma). Ranking makes the share exact to within one
    -- employee regardless of hash quality, which is what an analyst expects
    -- from typing a percentage into a box.
    CASE
      WHEN EXTRACT(YEAR FROM employee_hire_date) = simulation_year THEN
        ROW_NUMBER() OVER (
          PARTITION BY simulation_year,
                       (EXTRACT(YEAR FROM employee_hire_date) = simulation_year)
          ORDER BY enrollment_random, employee_id
        ) <= ROUND({{ flat_new_hire_voluntary_rate }} * COUNT(*) OVER (
          PARTITION BY simulation_year,
                       (EXTRACT(YEAR FROM employee_hire_date) = simulation_year)
        ))
      ELSE enrollment_random < final_enrollment_probability
    END as will_enroll,
    {%- else %}
    CASE
      WHEN enrollment_random < final_enrollment_probability THEN true
      ELSE false
    END as will_enroll,
    {%- endif %}

    -- Selected deferral rate (floor 1%; cap = configurable voluntary_max_deferral_rate)
    GREATEST(0.01, LEAST({{ voluntary_max_deferral_rate }}, optimized_deferral_rate)) as selected_deferral_rate,

    -- Event details for integration
    'voluntary_enrollment' as event_category,
    CASE
      WHEN EXTRACT(YEAR FROM employee_hire_date) = simulation_year
        -- Feature 096: hire-year new hires enroll effective their eligibility date
        -- (hire date + waiting period), which drives correct hire-year proration.
        THEN CAST(plan_eligibility_date AS TIMESTAMP)
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
  plan_design_id,
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
