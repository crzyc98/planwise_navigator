{{ config(materialized='table') }}

/*
  Enrollment Decision Matrix Model (Epic E023: Auto-Enrollment Orchestration)

  Routes enrollment decisions based on plan configuration, combining auto-enrollment
  participants with voluntary-only enrollment for plans without auto-enrollment.
  This model serves as the unified decision engine that handles all enrollment
  scenarios and produces the final enrollment events for event generation.

  Enrollment Routing Logic:
  1. Auto-enrollment enabled plans → Use timing coordination results
  2. Auto-enrollment disabled plans → Use voluntary enrollment logic
  3. Plan-specific overrides → Apply special rules for executive/emergency plans
  4. Multi-year consistency → Maintain enrollment state across simulation years

  Key Features:
  - Unified enrollment decision engine for all plan types
  - Supports both auto-enrollment and voluntary-only enrollment scenarios
  - Plan-specific configuration overrides (executive, emergency plans)
  - Demographic-based voluntary enrollment probabilities
  - Integration with existing eligibility determination (E022)
  - Performance optimized for 100K+ employee processing

  Output:
  - Final enrollment decisions with source attribution
  - Event-ready data structure for fct_yearly_events generation
  - Complete audit trail for regulatory compliance
  - Timing validation and conflict resolution

  Dependencies:
  - int_workforce_pre_enrollment.sql (circular dependency-free workforce data)
  - int_enrollment_timing_coordination.sql (auto-enrollment timing)
*/

WITH eligible_employees AS (
  -- Get all eligible employees using plan eligibility determination
  SELECT
    wpe.employee_id,
    wpe.employee_ssn,
    wpe.employee_hire_date,
    wpe.employment_status,
    wpe.current_age,
    wpe.current_tenure,
    wpe.level_id,
    wpe.current_compensation,
    wpe.simulation_year,
    -- Use plan eligibility determination
    ped.is_plan_eligible as is_eligible,
    -- Use plan eligibility date as entry date
    ped.plan_eligibility_date as entry_date,

    -- Demographic segmentation for voluntary enrollment
    CASE
      WHEN wpe.current_age BETWEEN 18 AND 30 THEN 'young'
      WHEN wpe.current_age BETWEEN 31 AND 45 THEN 'mid_career'
      WHEN wpe.current_age BETWEEN 46 AND 55 THEN 'mature'
      ELSE 'senior'
    END as age_segment,

    CASE
      WHEN wpe.current_compensation < 30000 THEN 'low_income'
      WHEN wpe.current_compensation < 50000 THEN 'moderate'
      WHEN wpe.current_compensation < 100000 THEN 'high'
      ELSE 'executive'
    END as income_segment,

    -- Plan type determination
    CASE
      WHEN wpe.level_id >= 8 THEN 'executive_plan'
      WHEN wpe.employee_hire_date >= CAST(wpe.simulation_year || '-01-01' AS DATE) THEN 'standard_plan'
      ELSE 'standard_plan'
    END as plan_type
  FROM {{ ref('int_workforce_pre_enrollment') }} wpe
  INNER JOIN {{ ref('int_plan_eligibility_determination') }} ped
    ON wpe.employee_id = ped.employee_id
    AND wpe.simulation_year = ped.simulation_year
  WHERE wpe.simulation_year = {{ var('simulation_year') }}
),

eligible_employees_filtered AS (
  SELECT * FROM eligible_employees WHERE is_eligible = true
),

plan_configuration_matrix AS (
  -- Determine plan-specific configuration for each employee
  SELECT
    *,
    -- Auto-enrollment enabled determination
    CASE plan_type
      WHEN 'executive_plan' THEN {{ var('executive_plan_auto_enrollment_enabled', true) }}
      WHEN 'emergency_plan' THEN {{ var('emergency_plan_auto_enrollment_enabled', false) }}
      ELSE {{ var('auto_enrollment_enabled', true) }}
    END as plan_auto_enrollment_enabled,

    -- Window duration by plan type
    CASE plan_type
      WHEN 'executive_plan' THEN {{ var('executive_plan_window_days', 60) }}
      WHEN 'emergency_plan' THEN {{ var('emergency_plan_window_days', 30) }}
      ELSE {{ var('auto_enrollment_window_days', 45) }}
    END as plan_window_days,

    -- Default deferral rate by plan type
    CASE plan_type
      WHEN 'executive_plan' THEN {{ var('executive_plan_default_deferral_rate', 0.10) }}
      ELSE {{ var('auto_enrollment_default_deferral_rate', 0.06) }}
    END as plan_default_deferral_rate,

    -- Scope check (new hires only vs all eligible employees)
    CASE
      WHEN '{{ var("auto_enrollment_scope", "new_hires_only") }}' = 'new_hires_only'
        AND (
          {% if var("auto_enrollment_hire_date_cutoff", null) %}
            employee_hire_date >= '{{ var("auto_enrollment_hire_date_cutoff") }}'::DATE
          {% else %}
            true
          {% endif %}
        )
        THEN employee_hire_date >= CAST(simulation_year || '-01-01' AS DATE)
      WHEN '{{ var("auto_enrollment_scope", "new_hires_only") }}' = 'all_eligible_employees'
        AND (
          {% if var("auto_enrollment_hire_date_cutoff", null) %}
            employee_hire_date >= '{{ var("auto_enrollment_hire_date_cutoff") }}'::DATE
          {% else %}
            true
          {% endif %}
        )
        THEN true
      ELSE false
    END as in_auto_enrollment_scope
  FROM eligible_employees_filtered
),

auto_enrollment_participants AS (
  -- Get participants from auto-enrollment timing coordination
  SELECT
    tc.employee_id,
    tc.employee_ssn,
    tc.simulation_year,
    tc.current_age,
    tc.current_compensation,
    tc.age_segment,
    tc.income_segment,
    tc.plan_type,
    tc.entry_date,

    -- Enrollment decision results
    tc.final_enrolled_status as enrolled,
    tc.enrollment_source,
    tc.final_enrollment_date as enrollment_date,
    tc.final_deferral_rate as deferral_rate,

    -- Auto-enrollment specific fields
    tc.will_enroll_proactively,
    tc.will_auto_enroll,
    tc.will_opt_out,
    tc.proactive_enrollment_date,
    tc.auto_enrollment_date,
    tc.opt_out_date,

    -- Window timing
    tc.auto_enrollment_window_start,
    tc.auto_enrollment_window_end,

    -- Validation flags
    tc.timing_compliant,
    tc.timing_conflict_type,

    -- Source attribution
    'auto_enrollment_engine' as decision_source,
    tc.coordination_timestamp as decision_timestamp
  FROM {{ ref('int_enrollment_timing_coordination') }} tc
  WHERE tc.final_enrolled_status = true
),

voluntary_enrollment_candidates AS (
  -- Identify employees eligible for voluntary-only enrollment
  SELECT
    pcm.*,
    -- Generate random seed for voluntary enrollment decisions
    (ABS(HASH(pcm.employee_id || pcm.simulation_year || 'voluntary')) % 1000000) / 1000000.0 as voluntary_random_seed,
    (ABS(HASH(pcm.employee_id || pcm.simulation_year || 'vol_timing')) % 1000000) / 1000000.0 as voluntary_timing_seed
  FROM plan_configuration_matrix pcm
  WHERE NOT (pcm.plan_auto_enrollment_enabled AND pcm.in_auto_enrollment_scope)
    -- Only include employees not already processed by auto-enrollment
    AND pcm.employee_id NOT IN (
      SELECT employee_id
      FROM auto_enrollment_participants
      WHERE simulation_year = pcm.simulation_year
    )
),

voluntary_enrollment_probability_calculation AS (
  -- Calculate voluntary enrollment probabilities for non-auto-enrollment plans
  SELECT
    *,
    -- Base voluntary enrollment probability
    {{ var('voluntary_enrollment_base_probability', 0.60) }} as base_voluntary_probability,

    -- Age-based adjustment
    GREATEST(0, current_age - 25) * {{ var('voluntary_age_factor_per_year', 0.01) }} as age_adjustment,

    -- Tenure-based adjustment
    current_tenure * {{ var('voluntary_tenure_factor_per_year', 0.05) }} as tenure_adjustment,

    -- High earner bonus
    CASE
      WHEN current_compensation > 100000 THEN {{ var('voluntary_high_earner_bonus', 0.15) }}
      ELSE 0.0
    END as high_earner_bonus,

    -- Income-based multiplier
    CASE income_segment
      WHEN 'low_income' THEN {{ var('enrollment_adjustment_low_income', 0.80) }}
      WHEN 'moderate' THEN {{ var('enrollment_adjustment_moderate', 1.00) }}
      WHEN 'high' THEN {{ var('enrollment_adjustment_high', 1.15) }}
      ELSE {{ var('enrollment_adjustment_executive', 1.30) }}
    END as income_multiplier
  FROM voluntary_enrollment_candidates
  WHERE {{ var('voluntary_enrollment_enabled', true) }} = true
),

voluntary_enrollment_decisions AS (
  -- Make voluntary enrollment decisions
  SELECT
    *,
    -- Calculate final voluntary enrollment probability
    LEAST(
      (base_voluntary_probability + age_adjustment + tenure_adjustment + high_earner_bonus) * income_multiplier,
      1.0
    ) as final_voluntary_probability,

    -- Voluntary enrollment decision
    voluntary_random_seed < LEAST(
      (base_voluntary_probability + age_adjustment + tenure_adjustment + high_earner_bonus) * income_multiplier,
      1.0
    ) as will_enroll_voluntarily,

    -- Calculate voluntary enrollment timing (distributed throughout year)
    CASE
      WHEN voluntary_random_seed < LEAST(
        (base_voluntary_probability + age_adjustment + tenure_adjustment + high_earner_bonus) * income_multiplier,
        1.0
      ) THEN
        -- Voluntary enrollment can occur throughout the year after eligibility
        entry_date + INTERVAL (FLOOR(voluntary_timing_seed * 300)) DAY  -- Up to 300 days after eligibility
      ELSE null
    END as voluntary_enrollment_date,

    -- Voluntary deferral rate selection (more conservative than auto-enrollment)
    CASE
      WHEN voluntary_timing_seed < {{ var('deferral_rate_3pct_prob', 0.25) }} THEN 0.03
      WHEN voluntary_timing_seed < {{ var('deferral_rate_3pct_prob', 0.25) }} + {{ var('deferral_rate_6pct_prob', 0.35) }} THEN 0.06
      WHEN voluntary_timing_seed < {{ var('deferral_rate_3pct_prob', 0.25) }} + {{ var('deferral_rate_6pct_prob', 0.35) }} + {{ var('deferral_rate_10pct_prob', 0.20) }} THEN 0.10
      ELSE 0.08  -- Higher average for voluntary enrollees
    END as voluntary_deferral_rate
  FROM voluntary_enrollment_probability_calculation
),

voluntary_enrollment_participants AS (
  -- Format voluntary enrollment results to match auto-enrollment structure
  SELECT
    employee_id,
    employee_ssn,
    simulation_year,
    current_age,
    current_compensation,
    age_segment,
    income_segment,
    plan_type,
    entry_date,

    -- Enrollment decision results
    will_enroll_voluntarily as enrolled,
    'voluntary' as enrollment_source,
    voluntary_enrollment_date as enrollment_date,
    voluntary_deferral_rate as deferral_rate,

    -- Auto-enrollment specific fields (null for voluntary)
    false as will_enroll_proactively,
    false as will_auto_enroll,
    false as will_opt_out,
    null::DATE as proactive_enrollment_date,
    null::DATE as auto_enrollment_date,
    null::DATE as opt_out_date,

    -- Window timing (null for voluntary enrollment)
    null::DATE as auto_enrollment_window_start,
    null::DATE as auto_enrollment_window_end,

    -- Validation flags
    true as timing_compliant,  -- No timing constraints for voluntary enrollment
    'no_conflict' as timing_conflict_type,

    -- Source attribution
    'voluntary_enrollment_engine' as decision_source,
    current_timestamp as decision_timestamp
  FROM voluntary_enrollment_decisions
  WHERE will_enroll_voluntarily = true
),

unified_enrollment_decisions AS (
  -- Combine auto-enrollment and voluntary enrollment results
  SELECT * FROM auto_enrollment_participants
  UNION ALL
  SELECT * FROM voluntary_enrollment_participants
),

final_enrollment_matrix AS (
  -- Apply final business rules and validation
  SELECT
    -- Employee identification
    employee_id,
    employee_ssn,
    simulation_year,

    -- Demographics
    current_age,
    current_compensation,
    age_segment,
    income_segment,
    plan_type,

    -- Enrollment decision
    enrolled,
    enrollment_source,
    enrollment_date,
    deferral_rate,

    -- Auto-enrollment details (for audit trail)
    will_enroll_proactively,
    will_auto_enroll,
    will_opt_out,
    proactive_enrollment_date,
    auto_enrollment_date,
    opt_out_date,

    -- Window timing information
    auto_enrollment_window_start,
    auto_enrollment_window_end,

    -- Validation and compliance
    timing_compliant,
    timing_conflict_type,
    timing_compliant AND enrolled as enrollment_valid,

    -- Event generation fields
    entry_date,
    enrollment_date as effective_date,
    deferral_rate as pre_tax_contribution_rate,
    0.0 as roth_contribution_rate,  -- MVP: Focus on pre-tax contributions
    enrollment_source = 'auto' as auto_enrollment_flag,

    -- Opt-out window calculation
    CASE
      WHEN enrollment_source = 'auto' THEN
        enrollment_date + INTERVAL '{{ var("auto_enrollment_opt_out_grace_period", 30) }}' DAY
      ELSE null
    END as opt_out_window_expires,

    -- Audit trail
    decision_source,
    decision_timestamp,

    -- Performance metadata
    current_timestamp as matrix_calculation_timestamp,
    '{{ var("simulation_year") }}' as matrix_simulation_year
  FROM unified_enrollment_decisions
  WHERE enrolled = true
    AND enrollment_date IS NOT NULL
    AND deferral_rate > 0
)

SELECT *
FROM final_enrollment_matrix
WHERE enrollment_valid = true
ORDER BY simulation_year,
         enrollment_source,  -- Group by enrollment type
         enrollment_date,
         employee_id
