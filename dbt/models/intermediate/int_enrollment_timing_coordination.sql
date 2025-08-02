{{ config(materialized='table') }}

/*
  Enrollment Timing Coordination Model (Epic E023: Auto-Enrollment Orchestration)

  Orchestrates the complex timing between proactive enrollment and auto-enrollment to ensure
  proper sequence of events. This model implements the core logic that ensures proactive
  enrollment occurs BEFORE the auto-enrollment deadline while maintaining compliance with
  business rules and timing constraints.

  4-Phase Enrollment Workflow:
  1. Phase 1: Proactive Enrollment (Days 7-35 of window)
  2. Phase 2: Auto-Enrollment Execution (Day 45 for non-proactive enrollees)
  3. Phase 3: Opt-Out Processing (Within grace period after auto-enrollment)
  4. Phase 4: Voluntary-Only (For plans without auto-enrollment)

  Key Orchestration Logic:
  - Proactive enrollment must complete before auto-enrollment deadline
  - Auto-enrollment only applies to non-proactive enrollees
  - Opt-out timing is constrained by grace period windows
  - Different logic paths for auto-enrollment enabled vs disabled plans
  - Deterministic timing ensures reproducible simulation results

  Performance Optimizations:
  - Vectorized date calculations using DuckDB's columnar processing
  - Hash-based random generation for consistent employee behavior
  - Strategic CTEs to minimize data scanning
  - Efficient conditional logic using CASE statements

  Dependencies:
  - int_auto_enrollment_window_determination.sql (window boundaries and probabilities)
*/

WITH window_boundaries AS (
  -- Get auto-enrollment window information for all eligible employees
  SELECT
    employee_id,
    employee_ssn,
    simulation_year,

    -- Employee demographics for enrollment decisions
    current_age,
    current_compensation,
    age_segment,
    income_segment,
    plan_type,

    -- Window timing boundaries
    entry_date,
    auto_enrollment_window_start,
    auto_enrollment_window_end,
    proactive_window_start,
    proactive_window_end,
    auto_enrollment_execution_date,
    opt_out_grace_period_end,

    -- Configuration and probabilities
    eligible_for_auto_enrollment,
    proactive_enrollment_enabled,
    final_proactive_probability,
    opt_out_probability,
    default_deferral_rate,

    -- Random seeds for deterministic behavior
    proactive_random_seed,
    opt_out_random_seed,
    timing_random_seed,

    -- Window validation
    timing_window_valid,
    sufficient_proactive_window
  FROM {{ ref('int_auto_enrollment_window_determination') }}
  WHERE eligible_for_auto_enrollment = true
),

proactive_enrollment_determination AS (
  -- Phase 1: Determine which employees will enroll proactively
  SELECT
    *,
    -- Proactive enrollment decision (deterministic)
    proactive_random_seed < final_proactive_probability as will_enroll_proactively,

    -- Calculate proactive enrollment timing within the window
    CASE
      WHEN proactive_random_seed < final_proactive_probability THEN
        -- Calculate enrollment date within proactive window using timing seed
        proactive_window_start +
        INTERVAL (FLOOR(timing_random_seed * DATEDIFF('day', proactive_window_start, proactive_window_end))) DAY
      ELSE null
    END as proactive_enrollment_date
  FROM window_boundaries
  WHERE proactive_enrollment_enabled = true
    AND timing_window_valid = true
    AND sufficient_proactive_window = true
),

proactive_enrollment_validation AS (
  -- Validate proactive enrollment timing constraints
  SELECT
    *,
    -- Ensure proactive enrollment occurs before auto-enrollment deadline
    CASE
      WHEN will_enroll_proactively AND proactive_enrollment_date IS NOT NULL THEN
        proactive_enrollment_date < auto_enrollment_execution_date
      ELSE true  -- No constraint if not enrolling proactively
    END as proactive_timing_valid,

    -- Calculate days before auto-enrollment deadline
    CASE
      WHEN will_enroll_proactively AND proactive_enrollment_date IS NOT NULL THEN
        DATEDIFF('day', proactive_enrollment_date, auto_enrollment_execution_date)
      ELSE null
    END as days_before_auto_deadline
  FROM proactive_enrollment_determination
),

auto_enrollment_determination AS (
  -- Phase 2: Determine auto-enrollment for non-proactive enrollees
  SELECT
    *,
    -- Auto-enrollment only applies to employees who didn't enroll proactively
    CASE
      WHEN NOT will_enroll_proactively OR NOT proactive_timing_valid THEN true
      ELSE false
    END as will_auto_enroll,

    -- Auto-enrollment occurs exactly at window expiration
    CASE
      WHEN (NOT will_enroll_proactively OR NOT proactive_timing_valid) THEN
        auto_enrollment_execution_date
      ELSE null
    END as auto_enrollment_date
  FROM proactive_enrollment_validation
),

opt_out_determination AS (
  -- Phase 3: Determine opt-out behavior for auto-enrolled employees
  SELECT
    *,
    -- Opt-out decision (only for auto-enrolled employees)
    CASE
      WHEN will_auto_enroll THEN
        opt_out_random_seed < opt_out_probability
      ELSE false
    END as will_opt_out,

    -- Calculate opt-out timing within grace period
    CASE
      WHEN will_auto_enroll AND (opt_out_random_seed < opt_out_probability) THEN
        auto_enrollment_date +
        INTERVAL (FLOOR(timing_random_seed * {{ var('auto_enrollment_opt_out_grace_period', 30) }})) DAY
      ELSE null
    END as opt_out_date
  FROM auto_enrollment_determination
),

deferral_rate_selection AS (
  -- Determine initial deferral rates for enrolled employees
  SELECT
    *,
    -- Select deferral rate based on distribution probabilities
    CASE
      -- For proactive enrollees, use more sophisticated deferral rate selection
      WHEN will_enroll_proactively THEN
        CASE
          WHEN timing_random_seed < {{ var('deferral_rate_3pct_prob', 0.25) }} THEN 0.03
          WHEN timing_random_seed < {{ var('deferral_rate_3pct_prob', 0.25) }} + {{ var('deferral_rate_6pct_prob', 0.35) }} THEN 0.06
          WHEN timing_random_seed < {{ var('deferral_rate_3pct_prob', 0.25) }} + {{ var('deferral_rate_6pct_prob', 0.35) }} + {{ var('deferral_rate_10pct_prob', 0.20) }} THEN 0.10
          WHEN timing_random_seed < {{ var('deferral_rate_3pct_prob', 0.25) }} + {{ var('deferral_rate_6pct_prob', 0.35) }} + {{ var('deferral_rate_10pct_prob', 0.20) }} + {{ var('deferral_rate_15pct_prob', 0.10) }} THEN 0.15
          ELSE 0.20  -- Max contributors
        END
      -- For auto-enrolled employees, use default rate
      WHEN will_auto_enroll AND NOT will_opt_out THEN
        default_deferral_rate
      ELSE 0.0
    END as initial_deferral_rate,

    -- Final deferral rate after opt-out consideration
    CASE
      WHEN will_enroll_proactively THEN
        CASE
          WHEN timing_random_seed < {{ var('deferral_rate_3pct_prob', 0.25) }} THEN 0.03
          WHEN timing_random_seed < {{ var('deferral_rate_3pct_prob', 0.25) }} + {{ var('deferral_rate_6pct_prob', 0.35) }} THEN 0.06
          WHEN timing_random_seed < {{ var('deferral_rate_3pct_prob', 0.25) }} + {{ var('deferral_rate_6pct_prob', 0.35) }} + {{ var('deferral_rate_10pct_prob', 0.20) }} THEN 0.10
          WHEN timing_random_seed < {{ var('deferral_rate_3pct_prob', 0.25) }} + {{ var('deferral_rate_6pct_prob', 0.35) }} + {{ var('deferral_rate_10pct_prob', 0.20) }} + {{ var('deferral_rate_15pct_prob', 0.10) }} THEN 0.15
          ELSE 0.20
        END
      WHEN will_auto_enroll AND NOT will_opt_out THEN
        default_deferral_rate
      ELSE 0.0  -- Not enrolled or opted out
    END as final_deferral_rate
  FROM opt_out_determination
),

timing_conflict_resolution AS (
  -- Resolve any timing conflicts and validate business rules
  SELECT
    *,
    -- Identify timing conflicts
    CASE
      WHEN will_enroll_proactively AND proactive_enrollment_date >= auto_enrollment_execution_date THEN
        'proactive_after_auto_deadline'
      WHEN will_opt_out AND opt_out_date > opt_out_grace_period_end THEN
        'opt_out_beyond_grace_period'
      WHEN will_enroll_proactively AND will_auto_enroll THEN
        'duplicate_enrollment_events'
      ELSE 'no_conflict'
    END as timing_conflict_type,

    -- Resolution actions for conflicts
    CASE
      WHEN will_enroll_proactively AND proactive_enrollment_date >= auto_enrollment_execution_date THEN
        -- Move proactive enrollment to just before auto-enrollment deadline
        auto_enrollment_execution_date - INTERVAL '{{ var("proactive_cutoff_before_auto", 10) }}' DAY
      ELSE proactive_enrollment_date
    END as resolved_proactive_enrollment_date,

    CASE
      WHEN will_opt_out AND opt_out_date > opt_out_grace_period_end THEN
        -- Move opt-out to last day of grace period
        opt_out_grace_period_end
      ELSE opt_out_date
    END as resolved_opt_out_date
  FROM deferral_rate_selection
),

final_enrollment_coordination AS (
  -- Final enrollment status and timing coordination
  SELECT
    -- Employee identification
    employee_id,
    employee_ssn,
    simulation_year,

    -- Employee demographics
    current_age,
    current_compensation,
    age_segment,
    income_segment,
    plan_type,

    -- Window timing reference
    entry_date,
    auto_enrollment_window_start,
    auto_enrollment_window_end,
    auto_enrollment_execution_date,

    -- Enrollment decisions and timing
    will_enroll_proactively,
    will_auto_enroll,
    will_opt_out,

    -- Resolved timing (conflict-free)
    resolved_proactive_enrollment_date as proactive_enrollment_date,
    auto_enrollment_date,
    resolved_opt_out_date as opt_out_date,

    -- Deferral rates
    initial_deferral_rate,
    final_deferral_rate,

    -- Final enrollment status
    CASE
      WHEN will_enroll_proactively THEN true
      WHEN will_auto_enroll AND NOT will_opt_out THEN true
      ELSE false
    END as final_enrolled_status,

    -- Enrollment source classification
    CASE
      WHEN will_enroll_proactively THEN 'proactive'
      WHEN will_auto_enroll AND NOT will_opt_out THEN 'auto'
      ELSE 'none'
    END as enrollment_source,

    -- Final enrollment date
    CASE
      WHEN will_enroll_proactively THEN resolved_proactive_enrollment_date
      WHEN will_auto_enroll AND NOT will_opt_out THEN auto_enrollment_date
      ELSE null
    END as final_enrollment_date,

    -- Timing validation flags
    proactive_timing_valid,
    timing_conflict_type,
    timing_conflict_type = 'no_conflict' as timing_compliant,

    -- Random seeds for audit trail
    proactive_random_seed,
    opt_out_random_seed,
    timing_random_seed,

    -- Metadata
    current_timestamp as coordination_timestamp
  FROM timing_conflict_resolution
)

SELECT *
FROM final_enrollment_coordination
WHERE final_enrolled_status = true  -- Only return employees who will enroll
ORDER BY simulation_year,
         enrollment_source,  -- Group by proactive vs auto enrollment
         final_enrollment_date,
         employee_id
