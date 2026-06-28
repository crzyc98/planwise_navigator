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
  Proactive Voluntary Enrollment Model - Epic E053 Integration with Auto-Enrollment Windows

  This model integrates voluntary enrollment logic with auto-enrollment window timing
  to ensure new hires can voluntarily enroll with demographic-based deferral rates
  BEFORE their auto-enrollment deadline.

  Key Features:
  - Calculates auto-enrollment windows for new hires
  - Applies voluntary enrollment logic within the proactive window (days 7-35)
  - Uses demographic-based deferral rates (3%-10%) instead of default auto-enrollment rate
  - Prevents duplicate enrollments by tracking timing precedence
  - Integrates with existing enrollment architecture

  Business Logic:
  - Eligibility Date = Hire Date + waiting_period_days (0 days currently)
  - Auto-Enrollment Window = Eligibility Date + auto_enrollment_window_days (45 days)
  - Proactive Window = Days 7-35 of auto-enrollment window
  - Voluntary enrollment within proactive window uses demographic rates
  - Auto-enrollment at deadline (day 45) uses default rate only if no voluntary enrollment

  Dependencies:
  - int_employee_compensation_by_year (employee demographics)
  - enrollment_registry (enrollment tracking)
  - Configuration from simulation_config.yaml
*/

-- Epic E078: Mode-aware query - uses fct_yearly_events in Polars mode, int_hiring_events in SQL mode
WITH new_hire_population AS (
  -- Get current-year new hires eligible for auto-enrollment
  -- IMPORTANT: Use event data for year N new hires since compensation_by_year
  -- is built before hiring in this pipeline phase and will not include them yet.
  {% if var('event_generation_mode', 'sql') == 'polars' %}
  -- Polars mode: Read from fct_yearly_events
  SELECT DISTINCT
    he.employee_id,
    he.employee_ssn,
    he.effective_date::DATE AS employee_hire_date,
    he.simulation_year,
    he.employee_age AS current_age,
    0.0 AS current_tenure,
    he.level_id,
    he.compensation_amount AS employee_compensation,
    'active' AS employment_status
  FROM {{ ref('fct_yearly_events') }} he
  WHERE he.simulation_year = {{ var('simulation_year') }}
    AND he.event_type = 'hire'
    AND he.employee_id IS NOT NULL
    -- Only include employees eligible for auto-enrollment
    AND {{ is_eligible_for_auto_enrollment('he.effective_date::DATE', 'he.simulation_year') }}
    -- Gate on auto_enrollment_enabled (Issue #246: flag was previously ignored)
    AND {{ var('auto_enrollment_enabled', true) }}
  {% else %}
  -- SQL mode: Use intermediate event model
  SELECT DISTINCT
    he.employee_id,
    he.employee_ssn,
    he.effective_date::DATE AS employee_hire_date,
    he.simulation_year,
    he.employee_age AS current_age,
    0.0 AS current_tenure,
    he.level_id,
    he.compensation_amount AS employee_compensation,
    'active' AS employment_status
  FROM {{ ref('int_hiring_events') }} he
  WHERE he.simulation_year = {{ var('simulation_year') }}
    AND he.employee_id IS NOT NULL
    -- Only include employees eligible for auto-enrollment
    AND {{ is_eligible_for_auto_enrollment('he.effective_date::DATE', 'he.simulation_year') }}
    -- Gate on auto_enrollment_enabled (Issue #246: flag was previously ignored)
    AND {{ var('auto_enrollment_enabled', true) }}
  {% endif %}
),

enrollment_status_check AS (
  -- CRITICAL FIX: Use enrollment_state_accumulator from previous year to account for opt-outs
  -- This replaces enrollment_registry which doesn't properly track opt-out events
  {% set start_year = var('start_year', 2025) | int %}
  {% set current_year = var('simulation_year') | int %}

  {% if current_year == start_year %}
    -- Year 1: Check baseline workforce for enrolled employees
    SELECT
      nh.employee_id,
      nh.employee_ssn,
      nh.employee_hire_date,
      nh.simulation_year,
      nh.current_age,
      nh.current_tenure,
      nh.level_id,
      nh.employee_compensation,
      nh.employment_status,
      COALESCE(bl.is_enrolled_at_census, false) as is_already_enrolled,
      false as ever_opted_out  -- Year 1: no one has opted out yet
    FROM new_hire_population nh
    LEFT JOIN {{ ref('int_baseline_workforce') }} bl ON nh.employee_id = bl.employee_id
    WHERE COALESCE(bl.is_enrolled_at_census, false) = false  -- Only non-enrolled employees
      AND false = false  -- Placeholder for opt-out check (always true in year 1)
  {% else %}
    -- Year 2+: Use enrollment_state_accumulator from previous year
    -- Note: Using direct table reference to avoid circular dependency in dbt DAG
    SELECT
      nh.employee_id,
      nh.employee_ssn,
      nh.employee_hire_date,
      nh.simulation_year,
      nh.current_age,
      nh.current_tenure,
      nh.level_id,
      nh.employee_compensation,
      nh.employment_status,
      COALESCE(acc.is_enrolled, false) as is_already_enrolled,
      COALESCE(acc.ever_opted_out, false) as ever_opted_out
    FROM new_hire_population nh
    LEFT JOIN int_enrollment_state_accumulator acc ON nh.employee_id = acc.employee_id
      AND acc.simulation_year = {{ current_year - 1 }}
    WHERE COALESCE(acc.is_enrolled, false) = false  -- Only non-enrolled employees
      AND COALESCE(acc.ever_opted_out, false) = false  -- Never opted out
  {% endif %}
),

auto_enrollment_window_calculation AS (
  -- Calculate auto-enrollment window timing for eligible new hires
  SELECT
    *,
    -- Calculate eligibility date (hire date + waiting period)
    employee_hire_date + INTERVAL '{{ var("eligibility_waiting_days", 0) }}' DAY as eligibility_date,

    -- Calculate auto-enrollment window boundaries
    (employee_hire_date + INTERVAL '{{ var("eligibility_waiting_days", 0) }}' DAY) as auto_enrollment_window_start,
    (employee_hire_date + INTERVAL '{{ var("eligibility_waiting_days", 0) }}' DAY +
     INTERVAL '{{ var("auto_enrollment_window_days", 45) }}' DAY) as auto_enrollment_window_end,

    -- Calculate proactive voluntary enrollment window (days 7-35 of auto-enrollment window)
    (employee_hire_date + INTERVAL '{{ var("eligibility_waiting_days", 0) }}' DAY +
     INTERVAL '{{ var("proactive_enrollment_min_days", 7) }}' DAY) as proactive_window_start,
    (employee_hire_date + INTERVAL '{{ var("eligibility_waiting_days", 0) }}' DAY +
     INTERVAL '{{ var("proactive_enrollment_max_days", 35) }}' DAY) as proactive_window_end,

    -- Auto-enrollment execution date (if no voluntary enrollment)
    (employee_hire_date + INTERVAL '{{ var("eligibility_waiting_days", 0) }}' DAY +
     INTERVAL '{{ var("auto_enrollment_window_days", 45) }}' DAY) as auto_enrollment_deadline
  FROM enrollment_status_check
),

demographic_segmentation AS (
  -- Apply demographic segmentation for voluntary enrollment logic
  SELECT
    *,
    -- Age segmentation for enrollment probability
    CASE
      WHEN current_age < 31 THEN 'young'
      WHEN current_age < 46 THEN 'mid_career'
      WHEN current_age < 56 THEN 'mature'
      ELSE 'senior'
    END as age_segment,

    -- Income segmentation for deferral rate selection
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
  FROM auto_enrollment_window_calculation
),

voluntary_enrollment_probability AS (
  -- Calculate voluntary enrollment probability within proactive window
  SELECT
    *,
    -- Base enrollment rate by age (using Epic E053 configuration)
    CASE age_segment
      WHEN 'young' THEN {{ var('voluntary_enrollment_base_rates_by_age_young', 0.30) }}
      WHEN 'mid_career' THEN {{ var('voluntary_enrollment_base_rates_by_age_mid_career', 0.55) }}
      WHEN 'mature' THEN {{ var('voluntary_enrollment_base_rates_by_age_mature', 0.70) }}
      ELSE {{ var('voluntary_enrollment_base_rates_by_age_senior', 0.80) }}
    END as base_enrollment_rate,

    -- Income multiplier for enrollment probability
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
    (ABS(HASH(employee_id || '-proactive-voluntary-' || CAST(simulation_year AS VARCHAR))) % 1000) / 1000.0 as enrollment_random
  FROM demographic_segmentation
),

deferral_rate_selection AS (
  -- Select demographic-based deferral rates for voluntary enrollees
  SELECT
    *,
    (base_enrollment_rate * income_multiplier * job_level_multiplier * COALESCE({{ var('voluntary_enrollment_rate', 1.0) }}, 1.0)) as final_enrollment_probability,

    -- Demographic-based deferral rates (Epic E053 logic)
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

    -- Timing random value for enrollment date within proactive window
    (ABS(HASH(employee_id || '-proactive-timing-' || CAST(simulation_year AS VARCHAR))) % 1000) / 1000.0 as timing_random
  FROM voluntary_enrollment_probability
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
    ) }} AS match_magnet_ceiling,
    (ABS(HASH(employee_id || '-match-magnet-' || CAST(simulation_year AS VARCHAR))) % 1000) / 1000.0 AS magnet_random
  FROM deferral_rate_selection
),

match_snapped AS (
  -- Snap a deterministic fraction of below-ceiling enrollees up to the ceiling
  SELECT
    *,
    {{ match_magnet_snap(
        'selected_deferral_rate',
        'match_magnet_ceiling',
        'magnet_random',
        enrollment_match_magnet_enabled,
        enrollment_match_magnet_probability
    ) }} AS optimized_deferral_rate
  FROM match_optimization
),

proactive_enrollment_decisions AS (
  -- Final enrollment decisions for proactive voluntary enrollment
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

    -- Window timing
    eligibility_date,
    auto_enrollment_window_start,
    auto_enrollment_window_end,
    proactive_window_start,
    proactive_window_end,
    auto_enrollment_deadline,

    -- Enrollment decision
    CASE
      WHEN enrollment_random < final_enrollment_probability THEN true
      ELSE false
    END as will_enroll_proactively,

    -- Enrollment effective date (within proactive window)
    CASE
      WHEN enrollment_random < final_enrollment_probability THEN
        proactive_window_start +
        INTERVAL (FLOOR(timing_random * EXTRACT(DAY FROM (proactive_window_end - proactive_window_start)))) DAY
      ELSE null
    END as proactive_enrollment_date,

    -- Deferral rate for voluntary enrollees (floor 1%; cap = configurable voluntary_max_deferral_rate)
    GREATEST(0.01, LEAST({{ voluntary_max_deferral_rate }}, optimized_deferral_rate)) as proactive_deferral_rate,

    -- Event category
    'proactive_voluntary' as event_category,

    -- Audit fields
    final_enrollment_probability,
    enrollment_random,
    timing_random,
    selected_deferral_rate as raw_deferral_rate,
    optimized_deferral_rate as match_optimized_rate,
    match_magnet_ceiling
  FROM match_snapped
)

-- Return proactive voluntary enrollment decisions
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
  eligibility_date,
  auto_enrollment_window_start,
  auto_enrollment_window_end,
  proactive_window_start,
  proactive_window_end,
  auto_enrollment_deadline,
  will_enroll_proactively,
  proactive_enrollment_date,
  proactive_deferral_rate,
  event_category,
  final_enrollment_probability,
  raw_deferral_rate,
  match_optimized_rate,
  match_magnet_ceiling,

  -- Age and tenure bands using centralized macros
  {{ assign_age_band('current_age') }} as age_band,
  {{ assign_tenure_band('current_tenure') }} as tenure_band,

  -- Event sourcing metadata
  current_timestamp as created_at,
  'proactive_voluntary_enrollment_engine' as event_source
FROM proactive_enrollment_decisions
WHERE will_enroll_proactively = true  -- Only return employees who will enroll proactively
ORDER BY employee_id

/*
  ARCHITECTURE NOTES:

  1. TIMING PRECEDENCE:
     - This model identifies new hires who will voluntarily enroll within their auto-enrollment window
     - These employees get demographic-based deferral rates (3%-10%)
     - Remaining new hires will get auto-enrollment with default rate (2%) at deadline

  2. INTEGRATION POINTS:
     - int_enrollment_events.sql should check this model first
     - Only apply auto-enrollment logic if employee is not in this model
     - Prevents duplicate enrollments through proper precedence

  3. PERFORMANCE:
     - Processes only new hires eligible for auto-enrollment
     - Uses deterministic random values for reproducible results
     - Efficient date calculations using DuckDB intervals
*/
