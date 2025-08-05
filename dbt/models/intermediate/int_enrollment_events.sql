{{ config(materialized='table') }}

/*
  Enrollment Events Model with Temporal State Accumulator (Phase 2: Architecture Fix)

  Generates enrollment events with historical enrollment tracking to prevent duplicate
  enrollments across multi-year simulations. Uses int_enrollment_state_accumulator
  for temporal state tracking without circular dependencies.

  Event Types Generated:
  - 'enrollment': Auto-enrollment and voluntary enrollment events
  - 'enrollment_change': Opt-out events based on demographics

  Key Features:
  - Prevents duplicate enrollments using int_enrollment_state_accumulator
  - Consumes: int_employee_compensation_by_year, int_enrollment_state_accumulator
  - Produces: Events for fct_yearly_events integration
  - Uses demographic-based enrollment logic with historical awareness
  - Maintains enrollment continuity across multi-year simulations without circular dependencies
  - CRITICAL: Restores restrictive WHERE clauses to prevent duplicate enrollments
*/

WITH active_workforce AS (
  -- Use consistent data source with other event models (terminations, hiring)
  SELECT DISTINCT
    employee_id,
    employee_ssn,
    employee_hire_date,
    {{ var('simulation_year') }} as simulation_year,
    current_age,
    current_tenure,
    level_id,
    employee_compensation AS current_compensation,
    -- Calculate age and tenure bands consistently with other models
    CASE
      WHEN current_age < 25 THEN '< 25'
      WHEN current_age < 35 THEN '25-34'
      WHEN current_age < 45 THEN '35-44'
      WHEN current_age < 55 THEN '45-54'
      WHEN current_age < 65 THEN '55-64'
      ELSE '65+'
    END AS age_band,
    CASE
      WHEN current_tenure < 2 THEN '< 2'
      WHEN current_tenure < 5 THEN '2-4'
      WHEN current_tenure < 10 THEN '5-9'
      WHEN current_tenure < 20 THEN '10-19'
      ELSE '20+'
    END AS tenure_band,
    employment_status
  FROM {{ ref('int_employee_compensation_by_year') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND employment_status = 'active'
),

previous_enrollment_state AS (
  -- ORCHESTRATOR-LEVEL SOLUTION: Use enrollment_registry table maintained by orchestrator
  -- This table is created/updated before event generation to prevent duplicate enrollments
  -- No circular dependencies since registry is maintained outside dbt workflow
  {% set start_year = var('start_year', 2025) | int %}
  {% set current_year = var('simulation_year') | int %}

  SELECT
    employee_id,
    first_enrollment_date AS previous_enrollment_date,
    is_enrolled AS was_enrolled_previously,
    enrollment_source,
    {{ current_year }} - first_enrollment_year as years_since_first_enrollment
  FROM enrollment_registry
  WHERE is_enrolled = true
    AND employee_id IS NOT NULL
),

eligible_for_enrollment AS (
  -- Enhanced eligibility logic with temporal state accumulator integration
  SELECT
    aw.*,
    -- Join previous enrollment state data
    pe.previous_enrollment_date,
    COALESCE(pe.was_enrolled_previously, false) as was_enrolled_previously,
    pe.enrollment_source as previous_enrollment_source,
    pe.years_since_first_enrollment,
    -- Age-based enrollment segments
    CASE
      WHEN aw.current_age < 30 THEN 'young'
      WHEN aw.current_age < 45 THEN 'mid_career'
      WHEN aw.current_age < 60 THEN 'mature'
      ELSE 'senior'
    END as age_segment,

    -- Income-based segments
    CASE
      WHEN aw.current_compensation < 50000 THEN 'low_income'
      WHEN aw.current_compensation < 100000 THEN 'moderate'
      WHEN aw.current_compensation < 200000 THEN 'high'
      ELSE 'executive'
    END as income_segment,

    -- CRITICAL BUSINESS LOGIC: Enhanced eligibility check with ALL restrictive WHERE clauses restored
    CASE
      WHEN aw.current_tenure >= 1
        -- CRITICAL: Use temporal state accumulator to prevent duplicate enrollments
        AND COALESCE(pe.was_enrolled_previously, false) = false
        AND (
          -- CRITICAL: Hire date cutoff filter (if specified) - prevents late hires from enrolling
          {% if var("auto_enrollment_hire_date_cutoff", null) %}
            aw.employee_hire_date >= '{{ var("auto_enrollment_hire_date_cutoff") }}'::DATE
          {% else %}
            true
          {% endif %}
        )
        AND (
          -- CRITICAL: Scope check prevents inappropriate enrollments
          CASE
            WHEN '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' = 'new_hires_only'
              THEN aw.employee_hire_date >= CAST(aw.simulation_year || '-01-01' AS DATE)
            WHEN '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' = 'all_eligible_employees'
              THEN true
            ELSE true  -- Default to eligible if unrecognized scope
          END
        )
        THEN true
      ELSE false
    END as is_eligible,

    -- CRITICAL: Track already enrolled status to prevent duplicates
    COALESCE(pe.was_enrolled_previously, false) as is_already_enrolled,

    -- Generate deterministic "random" values for enrollment decisions
    (ABS(HASH(aw.employee_id || '-enroll-' || CAST(aw.simulation_year AS VARCHAR))) % 1000) / 1000.0 as enrollment_random,
    (ABS(HASH(aw.employee_id || '-optout-' || CAST(aw.simulation_year AS VARCHAR))) % 1000) / 1000.0 as optout_random
  FROM active_workforce aw
  LEFT JOIN previous_enrollment_state pe ON aw.employee_id = pe.employee_id
),

-- Generate enrollment events using simplified demographics-based logic
enrollment_events AS (
  SELECT
    efo.employee_id,
    efo.employee_ssn,
    'enrollment' as event_type,
    efo.simulation_year,
    CAST((efo.simulation_year || '-01-15 08:00:00') AS TIMESTAMP) as effective_date, -- Fixed enrollment date

    -- Event details based on demographics
    CASE efo.age_segment
      WHEN 'young' THEN 'Young employee auto-enrollment - 3% default deferral'
      WHEN 'mid_career' THEN 'Mid-career voluntary enrollment - 6% deferral'
      WHEN 'mature' THEN 'Mature employee enrollment - 8% deferral'
      ELSE 'Senior employee enrollment - 10% deferral'
    END as event_details,

    -- Compensation amount (current compensation at time of enrollment)
    efo.current_compensation as compensation_amount,
    NULL as previous_compensation,

    -- Employee demographics at time of enrollment
    efo.current_age as employee_age,
    efo.current_tenure as employee_tenure,
    efo.level_id,
    efo.age_band,
    efo.tenure_band,

    -- Event probability based on simplified demographics
    CASE efo.age_segment
      WHEN 'young' THEN 0.30        -- 30% enrollment rate for young employees
      WHEN 'mid_career' THEN 0.55   -- 55% enrollment rate for mid-career
      WHEN 'mature' THEN 0.70       -- 70% enrollment rate for mature employees
      ELSE 0.80                     -- 80% enrollment rate for senior employees
    END *
    CASE efo.income_segment
      WHEN 'low_income' THEN 0.70   -- Lower enrollment for low income
      WHEN 'moderate' THEN 1.0      -- Base rate for moderate income
      WHEN 'high' THEN 1.15         -- Higher enrollment for high income
      ELSE 1.25                     -- Highest enrollment for executives
    END as event_probability,

    -- Event category for grouping
    CASE efo.age_segment
      WHEN 'young' THEN 'auto_enrollment'
      WHEN 'mid_career' THEN 'voluntary_enrollment'
      WHEN 'mature' THEN 'proactive_enrollment'
      ELSE 'executive_enrollment'
    END as event_category
  FROM eligible_for_enrollment efo
  WHERE efo.is_eligible = true
    -- CRITICAL FIX: Prevent duplicate enrollments for ALL simulation years
    -- Now that previous_enrollment_state properly checks accumulator for subsequent years,
    -- we can safely enforce this constraint across all years
    AND efo.is_already_enrolled = false
    -- CRITICAL: Apply probabilistic enrollment based on demographics
    AND efo.enrollment_random < (
      CASE efo.age_segment
        WHEN 'young' THEN 0.30
        WHEN 'mid_career' THEN 0.55
        WHEN 'mature' THEN 0.70
        ELSE 0.80
      END *
      CASE efo.income_segment
        WHEN 'low_income' THEN 0.70
        WHEN 'moderate' THEN 1.0
        WHEN 'high' THEN 1.15
        ELSE 1.25
      END
    )
),

-- Generate opt-out events using simplified logic
opt_out_events AS (
  SELECT
    efo.employee_id,
    efo.employee_ssn,
    'enrollment_change' as event_type,
    efo.simulation_year,
    CAST((efo.simulation_year || '-06-15 14:00:00') AS TIMESTAMP) as effective_date, -- Mid-year opt-out

    -- Opt-out event details
    'Auto-enrollment opt-out - reduced deferral from default to 0%' as event_details,

    -- Compensation remains the same, but showing the change impact
    efo.current_compensation as compensation_amount,
    efo.current_compensation as previous_compensation,

    -- Employee demographics
    efo.current_age as employee_age,
    efo.current_tenure as employee_tenure,
    efo.level_id,
    efo.age_band,
    efo.tenure_band,

    -- Opt-out probability based on demographics (simplified)
    CASE efo.age_segment
      WHEN 'young' THEN 0.35  -- Higher opt-out rate for young employees
      WHEN 'mid_career' THEN 0.20
      WHEN 'mature' THEN 0.15
      ELSE 0.10               -- Lower opt-out rate for seniors
    END *
    CASE efo.income_segment
      WHEN 'low_income' THEN 1.60  -- Much higher opt-out for low income
      WHEN 'moderate' THEN 1.0     -- Base rate
      WHEN 'high' THEN 0.60        -- Lower opt-out for high income
      ELSE 0.20                    -- Very low opt-out for executives
    END as event_probability,

    'enrollment_opt_out' as event_category
  FROM eligible_for_enrollment efo
  WHERE efo.is_eligible = true
    -- CRITICAL: Only employees who were enrolled (either this year or previously) can opt out
    AND (efo.is_already_enrolled = true OR efo.employee_id IN (
      SELECT employee_id FROM enrollment_events WHERE event_type = 'enrollment'
    ))
    AND efo.age_segment = 'young'  -- Only young employees get auto-enrolled and can opt out
    -- CRITICAL: Apply probabilistic opt-out based on demographics
    AND efo.optout_random < (
      0.35 *  -- Base young opt-out rate
      CASE efo.income_segment
        WHEN 'low_income' THEN 1.60
        WHEN 'moderate' THEN 1.0
        WHEN 'high' THEN 0.60
        ELSE 0.20
      END
    )
),

-- Combine all enrollment-related events
all_enrollment_events AS (
  SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    event_details,
    compensation_amount,
    previous_compensation,
    employee_age,
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM enrollment_events

  UNION ALL

  SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    event_details,
    compensation_amount,
    previous_compensation,
    employee_age,
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM opt_out_events
)

-- Final selection compatible with fct_yearly_events schema with event sourcing metadata
-- Phase 2 Fix: Restored all critical WHERE clauses to prevent duplicate enrollments
SELECT
  employee_id,
  employee_ssn,
  event_type,
  simulation_year,
  effective_date,
  event_details,
  compensation_amount,
  previous_compensation,
  employee_age,
  employee_tenure,
  level_id,
  age_band,
  tenure_band,
  event_probability,
  event_category,
  -- Event sourcing metadata for audit trail
  ROW_NUMBER() OVER (PARTITION BY employee_id, simulation_year ORDER BY effective_date, event_type) as event_sequence,
  CURRENT_TIMESTAMP as created_at,
  '{{ var("scenario_id", "default") }}' as parameter_scenario_id,
  'enrollment_pipeline_v2_state_accumulator' as parameter_source,  -- Updated to reflect new architecture
  CASE
    WHEN employee_id IS NULL THEN 'INVALID_EMPLOYEE_ID'
    WHEN simulation_year IS NULL THEN 'INVALID_SIMULATION_YEAR'
    WHEN effective_date IS NULL THEN 'INVALID_EFFECTIVE_DATE'
    WHEN compensation_amount IS NULL THEN 'INVALID_COMPENSATION'
    ELSE 'VALID'
  END as data_quality_flag
FROM all_enrollment_events
WHERE employee_id IS NOT NULL
  AND simulation_year IS NOT NULL
  AND effective_date IS NOT NULL
  AND event_type IS NOT NULL
ORDER BY employee_id, effective_date,
  CASE event_type
    WHEN 'enrollment' THEN 1
    WHEN 'enrollment_change' THEN 2
    ELSE 3
  END

/*
  CRITICAL BUG FIX - Duplicate Enrollment Prevention Across Multi-Year Simulations:

  1. ROOT CAUSE IDENTIFIED:
     - previous_enrollment_state CTE only checked int_baseline_workforce
     - New hires (e.g., NH_2026_000787) not in baseline workforce
     - These employees got enrolled in every subsequent year (2027, 2028, 2029)
     - 321 employees affected by this pattern

  2. SOLUTION IMPLEMENTED (Orchestrator-Level Registry):
     - Created enrollment_registry table maintained by run_multi_year.py orchestrator
     - Registry is created/updated BEFORE event generation each year
     - First year: Populated from int_baseline_workforce enrolled employees
     - Subsequent years: Updated with newly enrolled employees from previous year's events
     - No circular dependencies since registry is maintained outside dbt workflow

  3. ENROLLMENT TRACKING ARCHITECTURE:
     - Year 1: enrollment_registry (baseline) → int_enrollment_events → fct_yearly_events
     - Year N: enrollment_registry (baseline + years 1 to N-1) → int_enrollment_events → fct_yearly_events
     - Registry updated after each year: registry += newly enrolled employees from year N events
     - Clean separation: orchestrator manages state, dbt generates events

  4. VALIDATION APPROACH:
     - Employee NH_2026_000787 should only be enrolled once (in 2027)
     - No enrollment events in 2028, 2029 for already-enrolled employees
     - Registry prevents duplicate enrollments across all simulation years
     - Zero employees with enrollment events but no enrollment dates in workforce snapshots
*/
