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

WITH active_workforce_base AS (
  -- Base active employees with compensation (excludes current-year new hires in first year)
  SELECT DISTINCT
    employee_id,
    employee_ssn,
    employee_hire_date,
    {{ var('simulation_year') }} as simulation_year,
    current_age,
    current_tenure,
    level_id,
    employee_compensation AS current_compensation,
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

new_hires_current_year AS (
  -- Ensure current-year new hires are considered for enrollment attempts in their hire year
  SELECT DISTINCT
    he.employee_id,
    he.employee_ssn,
    he.effective_date::DATE AS employee_hire_date,
    he.simulation_year,
    he.employee_age AS current_age,
    0.0 AS current_tenure,
    he.level_id,
    he.compensation_amount AS current_compensation,
    CASE
      WHEN he.employee_age < 25 THEN '< 25'
      WHEN he.employee_age < 35 THEN '25-34'
      WHEN he.employee_age < 45 THEN '35-44'
      WHEN he.employee_age < 55 THEN '45-54'
      WHEN he.employee_age < 65 THEN '55-64'
      ELSE '65+'
    END AS age_band,
    '< 2' AS tenure_band,
    'active' AS employment_status
  FROM {{ ref('int_hiring_events') }} he
  WHERE he.simulation_year = {{ var('simulation_year') }}
),

active_workforce AS (
  SELECT * FROM active_workforce_base
  UNION ALL
  SELECT * FROM new_hires_current_year
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
    -- Only treat employees as previously enrolled if enrollment occurred
    -- on or before the current simulation year (ignore future-year enrollments)
    AND first_enrollment_year <= {{ current_year }}
),

auto_enrollment_eligible_population AS (
  -- Single source of truth for auto-enrollment eligibility
  SELECT DISTINCT
    aw.employee_id,
    aw.employee_hire_date,
    aw.simulation_year,
    aw.employment_status,
    pe.was_enrolled_previously,
    -- Explicit eligibility with clear semantics using macro
    {{ get_eligibility_reason('aw.employee_hire_date', 'aw.simulation_year', 'aw.employment_status', 'pe.was_enrolled_previously') }} as eligibility_reason,
    -- Simplified eligibility flag
    CASE
      WHEN aw.employment_status = 'active'
        AND COALESCE(pe.was_enrolled_previously, false) = false
        AND {{ is_eligible_for_auto_enrollment('aw.employee_hire_date', 'aw.simulation_year') }}
      THEN true
      ELSE false
    END as is_auto_enrollment_eligible
  FROM active_workforce aw
  LEFT JOIN previous_enrollment_state pe ON aw.employee_id = pe.employee_id
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

    -- SIMPLIFIED: Use macro-based eligibility logic for consistency
    {{ is_eligible_for_auto_enrollment('aw.employee_hire_date', 'aw.simulation_year') }}
      AND aw.employment_status = 'active'
      AND COALESCE(pe.was_enrolled_previously, false) = false
    as is_eligible,

    -- CRITICAL: Track already enrolled status to prevent duplicates
    COALESCE(pe.was_enrolled_previously, false) as is_already_enrolled,

    -- Explicit auto-enrollment row flag to drive default rate usage and categories
    CASE
      WHEN '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' = 'all_eligible_employees' THEN true
      WHEN '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' = 'new_hires_only'
           AND ({{ is_eligible_for_auto_enrollment('aw.employee_hire_date', 'aw.simulation_year') }})
        THEN true
      ELSE false
    END AS is_auto_enrollment_row,

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

    -- Event details based on enrollment type (Phase 2: E062 Fix)
    CASE
      WHEN efo.is_auto_enrollment_row THEN (
        'Auto-enrollment - ' || CAST(ROUND({{ default_deferral_rate() }} * 100, 1) AS VARCHAR) || '% default deferral'
      )
      ELSE (
        'Voluntary enrollment - ' || UPPER(efo.age_segment) || ' ' || UPPER(efo.income_segment) || ' employee - ' || CAST(ROUND(
          CASE efo.age_segment
            WHEN 'young' THEN
              CASE efo.income_segment
                WHEN 'low_income' THEN 0.03
                WHEN 'moderate' THEN 0.03
                WHEN 'high' THEN 0.04
                ELSE 0.06
              END
            WHEN 'mid_career' THEN
              CASE efo.income_segment
                WHEN 'low_income' THEN 0.04
                WHEN 'moderate' THEN 0.06
                WHEN 'high' THEN 0.08
                ELSE 0.10
              END
            WHEN 'mature' THEN
              CASE efo.income_segment
                WHEN 'low_income' THEN 0.05
                WHEN 'moderate' THEN 0.08
                WHEN 'high' THEN 0.10
                ELSE 0.12
              END
            ELSE -- senior
              CASE efo.income_segment
                WHEN 'low_income' THEN 0.06
                WHEN 'moderate' THEN 0.10
                WHEN 'high' THEN 0.12
                ELSE 0.15
              END
          END * 100, 1) AS VARCHAR) || '% deferral rate'
      )
    END as event_details,

    -- Compensation amount (current compensation at time of enrollment)
    efo.current_compensation as compensation_amount,
    NULL as previous_compensation,

    -- NEW: Employee deferral rate
    -- CRITICAL FIX: Apply auto-enrollment default rate ONLY to auto_enrollment events
    -- All other enrollment types (voluntary, proactive, year-over-year) use demographic-based rates
    CASE
      WHEN efo.is_auto_enrollment_row THEN {{ default_deferral_rate() }}
      ELSE
        CASE efo.age_segment
          WHEN 'young' THEN
            CASE efo.income_segment
              WHEN 'low_income' THEN 0.03
              WHEN 'moderate' THEN 0.03
              WHEN 'high' THEN 0.04
              ELSE 0.06
            END
          WHEN 'mid_career' THEN
            CASE efo.income_segment
              WHEN 'low_income' THEN 0.04
              WHEN 'moderate' THEN 0.06
              WHEN 'high' THEN 0.08
              ELSE 0.10
            END
          WHEN 'mature' THEN
            CASE efo.income_segment
              WHEN 'low_income' THEN 0.05
              WHEN 'moderate' THEN 0.08
              WHEN 'high' THEN 0.10
              ELSE 0.12
            END
          ELSE -- senior
            CASE efo.income_segment
              WHEN 'low_income' THEN 0.06
              WHEN 'moderate' THEN 0.10
              WHEN 'high' THEN 0.12
              ELSE 0.15
            END
        END
    END as employee_deferral_rate,

    -- For new enrollments, previous deferral rate is 0
    0.00 as prev_employee_deferral_rate,

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

    -- Event category for grouping (normalized to accepted values)
    CASE
      WHEN efo.is_auto_enrollment_row THEN 'auto_enrollment'
      ELSE (
        CASE efo.age_segment
          WHEN 'mid_career' THEN 'voluntary_enrollment'
          WHEN 'mature' THEN 'proactive_enrollment'
          WHEN 'young' THEN 'voluntary_enrollment'
          ELSE 'voluntary_enrollment'
        END
      )
    END as event_category
  FROM eligible_for_enrollment efo
  WHERE efo.is_eligible = true
    -- CRITICAL FIX: Prevent duplicate enrollments for ALL simulation years
    -- Now that previous_enrollment_state properly checks accumulator for subsequent years,
    -- we can safely enforce this constraint across all years
    AND efo.is_already_enrolled = false
    -- NEW: Exclude employees who have already enrolled proactively within auto-enrollment window
    AND efo.employee_id NOT IN (
      SELECT employee_id FROM {{ ref('int_proactive_voluntary_enrollment') }}
      WHERE will_enroll_proactively = true
        AND simulation_year = {{ var('simulation_year') }}
    )
    -- BUSINESS RULE: auto-eligible rows enroll deterministically; others probabilistic by demographics
    AND (
      CASE WHEN efo.is_auto_enrollment_row THEN true ELSE
        efo.enrollment_random < (
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

    -- NEW: Opt-out means reducing deferral to 0
    0.00 as employee_deferral_rate,

    -- Previous rate was the default based on demographics (for young employees who opt out)
    0.03 as prev_employee_deferral_rate,

    -- Employee demographics
    efo.current_age as employee_age,
    efo.current_tenure as employee_tenure,
    efo.level_id,
    efo.age_band,
    efo.tenure_band,

    -- Opt-out probability based on demographics (using configurable rates)
    CASE efo.age_segment
      WHEN 'young' THEN {{ var('opt_out_rate_young', 0.10) }}
      WHEN 'mid_career' THEN {{ var('opt_out_rate_mid', 0.07) }}
      WHEN 'mature' THEN {{ var('opt_out_rate_mature', 0.05) }}
      ELSE {{ var('opt_out_rate_senior', 0.03) }}
    END *
    CASE efo.income_segment
      WHEN 'low_income' THEN {{ var('opt_out_rate_low_income', 0.12) }} / {{ var('opt_out_rate_moderate', 0.10) }}
      WHEN 'moderate' THEN 1.0  -- Base rate
      WHEN 'high' THEN {{ var('opt_out_rate_high', 0.07) }} / {{ var('opt_out_rate_moderate', 0.10) }}
      ELSE {{ var('opt_out_rate_executive', 0.05) }} / {{ var('opt_out_rate_moderate', 0.10) }}
    END as event_probability,

    'enrollment_opt_out' as event_category
  FROM eligible_for_enrollment efo
  WHERE
    -- Eligible to opt out: previously enrolled OR newly enrolled this year
    (COALESCE(efo.was_enrolled_previously, false) = true OR efo.employee_id IN (
      SELECT employee_id FROM enrollment_events WHERE event_type = 'enrollment'
    ))
    AND efo.employment_status = 'active'
    -- Apply probabilistic opt-out based on demographics (using configurable rates)
    AND efo.optout_random < (
      CASE efo.age_segment
        WHEN 'young' THEN {{ var('opt_out_rate_young', 0.10) }}
        WHEN 'mid_career' THEN {{ var('opt_out_rate_mid', 0.07) }}
        WHEN 'mature' THEN {{ var('opt_out_rate_mature', 0.05) }}
        ELSE {{ var('opt_out_rate_senior', 0.03) }}
      END *
      CASE efo.income_segment
        WHEN 'low_income' THEN {{ var('opt_out_rate_low_income', 0.12) }} / {{ var('opt_out_rate_moderate', 0.10) }}
        WHEN 'moderate' THEN 1.0
        WHEN 'high' THEN {{ var('opt_out_rate_high', 0.07) }} / {{ var('opt_out_rate_moderate', 0.10) }}
        ELSE {{ var('opt_out_rate_executive', 0.05) }} / {{ var('opt_out_rate_moderate', 0.10) }}
      END
    )
),

-- Epic E053: Voluntary Enrollment Events Integration
voluntary_enrollment_events AS (
  SELECT
    ved.employee_id,
    ved.employee_ssn,
    'enrollment' as event_type,
    ved.simulation_year,
    ved.proposed_effective_date as effective_date,

    -- Enhanced event details with demographic context
    'Voluntary enrollment - ' || UPPER(ved.age_segment) || ' ' || UPPER(ved.income_segment) ||
    ' employee - ' || CAST(ROUND(ved.selected_deferral_rate * 100, 1) AS VARCHAR) || '% deferral rate' as event_details,

    ved.employee_compensation as compensation_amount,
    NULL as previous_compensation,  -- First enrollment, no previous rate
    ved.selected_deferral_rate as employee_deferral_rate,
    0.00 as prev_employee_deferral_rate,  -- First enrollment
    ved.current_age as employee_age,
    ved.current_tenure as employee_tenure,
    ved.level_id,

    -- Age band for consistency with existing logic
    CASE
      WHEN ved.current_age < 25 THEN '< 25'
      WHEN ved.current_age < 35 THEN '25-34'
      WHEN ved.current_age < 45 THEN '35-44'
      WHEN ved.current_age < 55 THEN '45-54'
      WHEN ved.current_age < 65 THEN '55-64'
      ELSE '65+'
    END as age_band,

    -- Tenure band for consistency
    CASE
      WHEN ved.current_tenure < 2 THEN '< 2'
      WHEN ved.current_tenure < 5 THEN '2-4'
      WHEN ved.current_tenure < 10 THEN '5-9'
      WHEN ved.current_tenure < 20 THEN '10-19'
      ELSE '20+'
    END as tenure_band,

    ved.final_enrollment_probability as event_probability,
    'voluntary_enrollment' as event_category

  FROM {{ ref('int_voluntary_enrollment_decision') }} ved
  WHERE ved.will_enroll = true
    AND ved.simulation_year = {{ var('simulation_year') }}
),

-- Proactive Voluntary Enrollment Events (New Hires Within Auto-Enrollment Windows)
proactive_voluntary_enrollment_events AS (
  SELECT
    pve.employee_id,
    pve.employee_ssn,
    'enrollment' as event_type,
    pve.simulation_year,
    pve.proactive_enrollment_date as effective_date,

    -- Enhanced event details with proactive context
    'Proactive voluntary enrollment - ' || UPPER(pve.age_segment) || ' ' || UPPER(pve.income_segment) ||
    ' new hire - ' || CAST(ROUND(pve.proactive_deferral_rate * 100, 1) AS VARCHAR) || '% deferral rate' as event_details,

    pve.employee_compensation as compensation_amount,
    NULL as previous_compensation,  -- First enrollment, no previous rate
    pve.proactive_deferral_rate as employee_deferral_rate,
    0.00 as prev_employee_deferral_rate,  -- First enrollment
    pve.current_age as employee_age,
    pve.current_tenure as employee_tenure,
    pve.level_id,
    pve.age_band,
    pve.tenure_band,
    pve.final_enrollment_probability as event_probability,
    pve.event_category

  FROM {{ ref('int_proactive_voluntary_enrollment') }} pve
  WHERE pve.will_enroll_proactively = true
    AND pve.simulation_year = {{ var('simulation_year') }}
),

-- Epic E053: Year-over-Year Voluntary Enrollment for Non-Participants
year_over_year_enrollment_events AS (
  SELECT
    aw.employee_id,
    aw.employee_ssn,
    'enrollment' as event_type,
    aw.simulation_year,
    CAST((aw.simulation_year || '-06-15 12:00:00') AS TIMESTAMP) as effective_date,  -- Mid-year enrollment

    -- Event details for year-over-year conversions
    'Year-over-year voluntary enrollment - ' ||
    CASE
      WHEN aw.current_age < 31 THEN 'Young'
      WHEN aw.current_age < 46 THEN 'Mid-career'
      WHEN aw.current_age < 56 THEN 'Mature'
      ELSE 'Senior'
    END || ' employee conversion - ' ||
    CAST(ROUND(
      CASE
        WHEN aw.current_age < 31 THEN {{ var('year_over_year_conversion_deferral_rates_young', 0.03) }}
        WHEN aw.current_age < 46 THEN {{ var('year_over_year_conversion_deferral_rates_mid_career', 0.04) }}
        WHEN aw.current_age < 56 THEN {{ var('year_over_year_conversion_deferral_rates_mature', 0.05) }}
        ELSE {{ var('year_over_year_conversion_deferral_rates_senior', 0.06) }}
      END * 100, 1) AS VARCHAR) || '% deferral' as event_details,

    aw.current_compensation as compensation_amount,
    NULL as previous_compensation,

    -- Conservative deferral rates for year-over-year conversions
    CASE
      WHEN aw.current_age < 31 THEN {{ var('year_over_year_conversion_deferral_rates_young', 0.03) }}
      WHEN aw.current_age < 46 THEN {{ var('year_over_year_conversion_deferral_rates_mid_career', 0.04) }}
      WHEN aw.current_age < 56 THEN {{ var('year_over_year_conversion_deferral_rates_mature', 0.05) }}
      ELSE {{ var('year_over_year_conversion_deferral_rates_senior', 0.06) }}
    END as employee_deferral_rate,

    0.00 as prev_employee_deferral_rate,
    aw.current_age as employee_age,
    aw.current_tenure as employee_tenure,
    aw.level_id,

    -- Age band
    CASE
      WHEN aw.current_age < 25 THEN '< 25'
      WHEN aw.current_age < 35 THEN '25-34'
      WHEN aw.current_age < 45 THEN '35-44'
      WHEN aw.current_age < 55 THEN '45-54'
      WHEN aw.current_age < 65 THEN '55-64'
      ELSE '65+'
    END as age_band,

    -- Tenure band
    CASE
      WHEN aw.current_tenure < 2 THEN '< 2'
      WHEN aw.current_tenure < 5 THEN '2-4'
      WHEN aw.current_tenure < 10 THEN '5-9'
      WHEN aw.current_tenure < 20 THEN '10-19'
      ELSE '20+'
    END as tenure_band,

    -- Conversion probability calculation
    (CASE
      WHEN aw.current_age < 31 THEN {{ var('year_over_year_conversion_base_rates_by_age_young', 0.03) }}
      WHEN aw.current_age < 46 THEN {{ var('year_over_year_conversion_base_rates_by_age_mid_career', 0.05) }}
      WHEN aw.current_age < 56 THEN {{ var('year_over_year_conversion_base_rates_by_age_mature', 0.07) }}
      ELSE {{ var('year_over_year_conversion_base_rates_by_age_senior', 0.08) }}
    END *
    CASE
      WHEN aw.current_compensation < 50000 THEN {{ var('year_over_year_conversion_income_multipliers_low_income', 0.8) }}
      WHEN aw.current_compensation < 100000 THEN {{ var('year_over_year_conversion_income_multipliers_moderate', 1.0) }}
      WHEN aw.current_compensation < 200000 THEN {{ var('year_over_year_conversion_income_multipliers_high', 1.2) }}
      ELSE {{ var('year_over_year_conversion_income_multipliers_executive', 1.3) }}
    END *
    CASE
      WHEN aw.current_tenure < 2 THEN {{ var('year_over_year_conversion_tenure_multipliers_new_employee', 0.7) }}
      WHEN aw.current_tenure < 5 THEN {{ var('year_over_year_conversion_tenure_multipliers_established', 1.0) }}
      ELSE {{ var('year_over_year_conversion_tenure_multipliers_veteran', 1.1) }}
    END) as event_probability,

    'year_over_year_voluntary' as event_category

  FROM active_workforce aw
  LEFT JOIN previous_enrollment_state pes ON aw.employee_id = pes.employee_id
  WHERE
    -- Only include employees not currently enrolled
    COALESCE(pes.was_enrolled_previously, false) = false
    -- Exclude recent hires (handled by new hire enrollment logic)
    AND aw.employee_hire_date < CAST(aw.simulation_year || '-01-01' AS DATE)
    -- Apply year-over-year conversion probability
    AND {{ var('year_over_year_conversion_enabled', true) }}
    AND (ABS(HASH(aw.employee_id || '-yoy-conversion-' || CAST(aw.simulation_year AS VARCHAR))) % 1000) / 1000.0 < (
      CASE
        WHEN aw.current_age < 31 THEN {{ var('year_over_year_conversion_base_rates_by_age_young', 0.03) }}
        WHEN aw.current_age < 46 THEN {{ var('year_over_year_conversion_base_rates_by_age_mid_career', 0.05) }}
        WHEN aw.current_age < 56 THEN {{ var('year_over_year_conversion_base_rates_by_age_mature', 0.07) }}
        ELSE {{ var('year_over_year_conversion_base_rates_by_age_senior', 0.08) }}
      END *
      CASE
        WHEN aw.current_compensation < 50000 THEN {{ var('year_over_year_conversion_income_multipliers_low_income', 0.8) }}
        WHEN aw.current_compensation < 100000 THEN {{ var('year_over_year_conversion_income_multipliers_moderate', 1.0) }}
        WHEN aw.current_compensation < 200000 THEN {{ var('year_over_year_conversion_income_multipliers_high', 1.2) }}
        ELSE {{ var('year_over_year_conversion_income_multipliers_executive', 1.3) }}
      END *
      CASE
        WHEN aw.current_tenure < 2 THEN {{ var('year_over_year_conversion_tenure_multipliers_new_employee', 0.7) }}
        WHEN aw.current_tenure < 5 THEN {{ var('year_over_year_conversion_tenure_multipliers_established', 1.0) }}
        ELSE {{ var('year_over_year_conversion_tenure_multipliers_veteran', 1.1) }}
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
    employee_deferral_rate,
    prev_employee_deferral_rate,
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
    employee_deferral_rate,
    prev_employee_deferral_rate,
    employee_age,
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM opt_out_events

  UNION ALL

  -- Epic E053: Add voluntary enrollment events
  SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    event_details,
    compensation_amount,
    previous_compensation,
    employee_deferral_rate,
    prev_employee_deferral_rate,
    employee_age,
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM voluntary_enrollment_events

  UNION ALL

  -- Add proactive voluntary enrollment events (new hires within auto-enrollment windows)
  SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    event_details,
    compensation_amount,
    previous_compensation,
    employee_deferral_rate,
    prev_employee_deferral_rate,
    employee_age,
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM proactive_voluntary_enrollment_events

  UNION ALL

  -- Epic E053: Add year-over-year conversion events
  SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    event_details,
    compensation_amount,
    previous_compensation,
    employee_deferral_rate,
    prev_employee_deferral_rate,
    employee_age,
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM year_over_year_enrollment_events
),

-- Deduplication with event category prioritization
-- Prevent duplicate enrollments per employee per year
deduplicated_events AS (
  SELECT *,
    -- Keep one event per type (enrollment vs enrollment_change) per employee-year
    -- Enrollment type prioritization: voluntary > proactive > yoy > auto
    ROW_NUMBER() OVER (
      PARTITION BY employee_id, simulation_year, event_type
      ORDER BY
        CASE
          WHEN event_type = 'enrollment' THEN (
            CASE event_category
              WHEN 'voluntary_enrollment' THEN 1
              WHEN 'proactive_voluntary_enrollment' THEN 2
              WHEN 'proactive_voluntary' THEN 2  -- alias handling
              WHEN 'year_over_year_voluntary' THEN 3
              WHEN 'auto_enrollment' THEN 4
              ELSE 5
            END
          )
          ELSE 1  -- For enrollment_change (opt-out), keep the single generated row
        END,
        effective_date
    ) as priority_rank
  FROM all_enrollment_events
)

-- Final selection compatible with fct_yearly_events schema with event sourcing metadata
-- Phase 2 Fix: Restored all critical WHERE clauses to prevent duplicate enrollments
-- Phase 3 Fix: Added deduplication to prevent multiple enrollments per employee per year
SELECT
  employee_id,
  employee_ssn,
  event_type,
  simulation_year,
  effective_date,
  event_details,
  compensation_amount,
  previous_compensation,
  employee_deferral_rate,
  prev_employee_deferral_rate,
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
  'E023_enrollment_engine' as event_source,  -- Required by schema
  '{{ var("scenario_id", "default") }}' as parameter_scenario_id,
  'enrollment_pipeline_v2_state_accumulator' as parameter_source,  -- Updated to reflect new architecture
  CASE
    WHEN employee_id IS NULL THEN 'INVALID_EMPLOYEE_ID'
    WHEN simulation_year IS NULL THEN 'INVALID_SIMULATION_YEAR'
    WHEN effective_date IS NULL THEN 'INVALID_EFFECTIVE_DATE'
    WHEN compensation_amount IS NULL THEN 'INVALID_COMPENSATION'
    ELSE 'VALID'
  END as data_quality_flag
FROM deduplicated_events
WHERE priority_rank = 1  -- Keep one per event_type per employee-year (enrollment + opt-out can coexist)
  AND employee_id IS NOT NULL
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

  5. NEW HIRE AUTO ENROLLMENT FIX (2025-01-XX):
     - ISSUE: New hires (NH_2025_*) were not getting auto enrollment attempts
     - ROOT CAUSES:
       a) Tenure requirement (current_tenure >= 1) blocked new hires with 0 tenure
       b) Scope logic required hire dates in current simulation year vs respecting hire_date_cutoff
     - CONFIG: auto_enrollment.scope="new_hires_only" with hire_date_cutoff="2020-01-01"
     - SOLUTIONS:
       a) Modified tenure logic to allow new hires (tenure >= 0) when scope is "new_hires_only"
       b) Fixed scope check to use hire_date_cutoff instead of current year requirement
     - RESULT: NH_2025_* employees (hired 2025, after 2020 cutoff) now eligible for auto enrollment
*/
