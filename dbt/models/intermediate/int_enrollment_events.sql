{{ config(
  materialized='incremental',
  incremental_strategy='replace_simulation_year',
  on_schema_change='sync_all_columns',
  tags=['EVENT_GENERATION']
) }}

{# Issue #652: flat new-hire opt-out rate. Unset keeps the demographic model
   for everyone. When set it applies to hire-year new hires only; continuing
   employees stay on opt_out_rates.target and its demographic multipliers. #}
{% set flat_new_hire_opt_out_rate = var('new_hire_opt_out_rate', none) %}

{# Issue #652: upward-only deferral spread. 0 disables it. The year-over-year
   table below is coarser than the voluntary one -- four age bands, no income
   dimension -- so it clusters hardest of the three sites. #}
{% set deferral_spread_max_lift = var('deferral_spread_max_lift', 4) %}

{%- set yoy_spread_random -%}
((ABS(PLANALIGN_HASH(aw.employee_id || '-deferral-spread-' || CAST(aw.simulation_year AS VARCHAR))) % 1000) / 1000.0)
{%- endset -%}

{%- set yoy_base_deferral_rate -%}
CASE
      WHEN aw.current_age < 31 THEN {{ var('year_over_year_conversion_deferral_rates_young', 0.03) }}
      WHEN aw.current_age < 46 THEN {{ var('year_over_year_conversion_deferral_rates_mid_career', 0.04) }}
      WHEN aw.current_age < 56 THEN {{ var('year_over_year_conversion_deferral_rates_mature', 0.05) }}
      ELSE {{ var('year_over_year_conversion_deferral_rates_senior', 0.06) }}
    END
{%- endset -%}

{# YoY has no upward magnet. Resolve its ceiling only for the new downward rule. #}
{% set yoy_ceiling = namespace(rate=var('employer_match_max_deferral_rate', none)) %}
{% if yoy_ceiling.rate is none %}
  {% set yoy_ceiling.rate = 0.0 %}
  {% for tier in var('match_tiers', [
    {'employee_min': 0.00, 'employee_max': 0.03, 'match_rate': 1.00},
    {'employee_min': 0.03, 'employee_max': 0.05, 'match_rate': 0.50}
  ]) %}
    {% if tier.employee_max is not none and tier.employee_max > yoy_ceiling.rate %}
      {% set yoy_ceiling.rate = tier.employee_max %}
    {% endif %}
  {% endfor %}
{% endif %}
{%- set yoy_match_ceiling -%}
  {{ resolve_match_magnet_ceiling(
    var('employer_match_status', 'deferral_based'), 'FLOOR(aw.current_tenure)',
    '(FLOOR(aw.current_age) + FLOOR(aw.current_tenure))',
    yoy_ceiling.rate, 'aw.plan_design_id'
  ) }}
{%- endset -%}
{%- set yoy_magnet_random -%}
  {{ enrollment_behavior_draw('aw.employee_id', 'aw.simulation_year', '-match-magnet-') }}
{%- endset -%}

/*
  Enrollment Events Model with Temporal State Accumulator (Phase 2: Architecture Fix)

  Generates enrollment events with historical enrollment tracking to prevent duplicate
  enrollments across multi-year simulations. Uses the orchestrator-built,
  fact-backed prior enrollment projection for temporal state.

  Event Types Generated:
  - 'enrollment': Auto-enrollment and voluntary enrollment events
  - 'enrollment_change': Opt-out events based on demographics

  Key Features:
  - Prevents duplicate enrollments using prior immutable event facts
  - Consumes: int_employee_compensation_by_year, stg_prior_enrollment_state
  - Produces: Events for fct_yearly_events integration
  - Uses demographic-based enrollment logic with historical awareness
  - Maintains enrollment continuity across multi-year simulations without circular dependencies
  - CRITICAL: Restores restrictive WHERE clauses to prevent duplicate enrollments
*/

WITH {{ reenrollment_sweep_inputs() }},

auto_enrollment_eligible_population AS (
  -- Single source of truth for auto-enrollment eligibility
  SELECT DISTINCT
    aw.employee_id,
    aw.employee_hire_date,
    aw.simulation_year,
    aw.employment_status,
    pe.was_enrolled_previously,
    -- Explicit eligibility with clear semantics using macro
    {{ get_eligibility_reason('aw.employee_hire_date', 'aw.simulation_year', 'aw.employment_status', 'pe.was_enrolled_previously', 'aw.auto_enrollment_scope') }} as eligibility_reason,
    -- Simplified eligibility flag
    ({{ is_ordinary_auto_enrollment_candidate('aw', 'pe') }}
      OR {{ is_reenrollment_sweep_candidate('aw', 'pe') }}) as is_auto_enrollment_eligible
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

    ({{ is_ordinary_auto_enrollment_candidate('aw', 'pe') }}
      OR {{ is_reenrollment_sweep_candidate('aw', 'pe') }}) AS is_eligible,
    {{ is_reenrollment_sweep_candidate('aw', 'pe') }} AS is_reenrollment_sweep,

    -- CRITICAL: Track already enrolled status to prevent duplicates
    COALESCE(pe.was_enrolled_previously, false) as is_already_enrolled,

    -- Explicit auto-enrollment row flag to drive default rate usage and categories
    -- Gate on auto_enrollment_enabled (Issue #246: flag was previously ignored)
    CASE
      WHEN NOT {{ var('auto_enrollment_enabled', true) }} THEN false
      WHEN {{ is_reenrollment_sweep_candidate('aw', 'pe') }} THEN true
      WHEN aw.auto_enrollment_scope = 'all_eligible_employees' THEN true
      WHEN aw.auto_enrollment_scope = 'new_hires_only'
           AND ({{ is_eligible_for_auto_enrollment_scope('aw.employee_hire_date', 'aw.simulation_year', 'aw.auto_enrollment_scope') }})
        THEN true
      ELSE false
    END AS is_auto_enrollment_row,

    -- Generate deterministic "random" values for enrollment decisions
    (ABS(PLANALIGN_HASH(aw.employee_id || '-enroll-' || CAST(aw.simulation_year AS VARCHAR))) % 1000) / 1000.0 as enrollment_random,
    CASE WHEN {{ is_reenrollment_sweep_candidate('aw', 'pe') }}
      THEN {{ enrollment_behavior_draw('aw.employee_id', 'aw.simulation_year', '-reenrollment-optout-') }}
      ELSE (ABS(PLANALIGN_HASH(aw.employee_id || '-optout-' || CAST(aw.simulation_year AS VARCHAR))) % 1000) / 1000.0
    END AS optout_random
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
    CASE
      WHEN efo.is_reenrollment_sweep THEN {{ reenrollment_sweep_date('efo') }}
      WHEN EXTRACT(YEAR FROM efo.employee_hire_date) = efo.simulation_year
        THEN CAST(efo.plan_eligibility_date + efo.auto_enrollment_window_days * INTERVAL '1 day' AS TIMESTAMP)
      ELSE CAST((efo.simulation_year || '-01-15 08:00:00') AS TIMESTAMP)
    END as effective_date,

    -- Event details based on enrollment type (Phase 2: E062 Fix)
    CASE
      WHEN efo.is_reenrollment_sweep THEN (
        CASE WHEN efo.reenrollment_sweep_method = 'into_aip'
          THEN 'Re-enrollment sweep - ' || CAST(ROUND(efo.deferral_escalation_increment * 100, 1) AS VARCHAR) || '% deferral; method=into_aip'
          ELSE 'Re-enrollment sweep - ' || CAST(ROUND(efo.auto_enrollment_default_deferral_rate * 100, 1) AS VARCHAR) || '% default deferral'
        END
      )
      WHEN efo.is_auto_enrollment_row THEN (
        'Auto-enrollment - ' || CAST(ROUND(efo.auto_enrollment_default_deferral_rate * 100, 1) AS VARCHAR) || '% default deferral'
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
      WHEN efo.is_reenrollment_sweep AND efo.reenrollment_sweep_method = 'into_aip'
        THEN efo.deferral_escalation_increment
      WHEN efo.is_auto_enrollment_row THEN efo.auto_enrollment_default_deferral_rate
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

    -- Event category: ONLY auto-enrollment (voluntary enrollments come from separate CTEs)
    'auto_enrollment' as event_category
  FROM eligible_for_enrollment efo
  WHERE efo.is_eligible = true
    -- CRITICAL FIX: Prevent duplicate enrollments for ALL simulation years
    AND (efo.is_already_enrolled = false OR efo.is_reenrollment_sweep)
    -- ONLY generate auto-enrollment events (voluntary enrollments handled by dedicated CTEs)
    AND efo.is_auto_enrollment_row = true
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

    -- Age and tenure bands using centralized macros
    {{ assign_age_band('ved.current_age') }} as age_band,
    {{ assign_tenure_band('ved.current_tenure') }} as tenure_band,

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
    GREATEST(0.01, LEAST({{ var('voluntary_max_deferral_rate', 0.15) }},
    {{ self_directed_enrollment_rate(
      deferral_spread(yoy_base_deferral_rate, yoy_spread_random, deferral_spread_max_lift),
      yoy_match_ceiling, yoy_magnet_random, 'aw.employee_id', 'aw.simulation_year',
      upward_enabled=false, auto_default='aw.auto_enrollment_default_deferral_rate',
      age='aw.current_age', income='aw.current_compensation'
    ) }})) AS employee_deferral_rate,

    0.00 as prev_employee_deferral_rate,
    aw.current_age as employee_age,
    aw.current_tenure as employee_tenure,
    aw.level_id,

    -- Age and tenure bands using centralized macros
    {{ assign_age_band('aw.current_age') }} as age_band,
    {{ assign_tenure_band('aw.current_tenure') }} as tenure_band,

    -- Conversion probability calculation
    (CASE
      WHEN aw.current_age < 31 THEN {{ var('year_over_year_conversion_base_rates_by_age_young', 0.0275848) }}
      WHEN aw.current_age < 46 THEN {{ var('year_over_year_conversion_base_rates_by_age_mid_career', 0.04597466) }}
      WHEN aw.current_age < 56 THEN {{ var('year_over_year_conversion_base_rates_by_age_mature', 0.06436453) }}
      ELSE {{ var('year_over_year_conversion_base_rates_by_age_senior', 0.07355946) }}
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
    -- CRITICAL: Exclude employees who have ever opted out - they made an explicit decision to not participate
    AND COALESCE(pes.ever_opted_out, false) = false
    -- Feature 103: never convert plan-ineligible employees
    AND aw.is_plan_ineligible_override = false
    -- Exclude recent hires (handled by new hire enrollment logic)
    AND aw.employee_hire_date < CAST(aw.simulation_year || '-01-01' AS DATE)
    -- Apply year-over-year conversion probability
    AND {{ var('year_over_year_conversion_enabled', true) }}
    AND (ABS(PLANALIGN_HASH(aw.employee_id || '-yoy-conversion-' || CAST(aw.simulation_year AS VARCHAR))) % 1000) / 1000.0 < (
      CASE
        WHEN aw.current_age < 31 THEN {{ var('year_over_year_conversion_base_rates_by_age_young', 0.0275848) }}
        WHEN aw.current_age < 46 THEN {{ var('year_over_year_conversion_base_rates_by_age_mid_career', 0.04597466) }}
        WHEN aw.current_age < 56 THEN {{ var('year_over_year_conversion_base_rates_by_age_mature', 0.06436453) }}
        ELSE {{ var('year_over_year_conversion_base_rates_by_age_senior', 0.07355946) }}
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

-- Issue #652: the population that CAN opt out, with a deterministic rank
-- inside its own cohort. The specified flat new-hire path selects ROUND(rate * N);
-- the demographic path below uses normalized probabilities and seeded draws.
opt_out_candidates_raw AS (
  SELECT
    efo.*,
    (EXTRACT(YEAR FROM efo.employee_hire_date) = efo.simulation_year)
      AS is_hire_year_new_hire,
    ROW_NUMBER() OVER (
      PARTITION BY efo.simulation_year,
                   (EXTRACT(YEAR FROM efo.employee_hire_date) = efo.simulation_year)
      ORDER BY efo.optout_random, efo.employee_id
    ) AS optout_rank,
    COUNT(*) OVER (
      PARTITION BY efo.simulation_year,
                   (EXTRACT(YEAR FROM efo.employee_hire_date) = efo.simulation_year)
    ) AS optout_cohort_size
  FROM eligible_for_enrollment efo
  WHERE
    -- ONLY employees who were AUTO-ENROLLED can opt out
    efo.employee_id IN (
      SELECT employee_id FROM enrollment_events
      WHERE event_type = 'enrollment'
        AND event_category = 'auto_enrollment'  -- ONLY auto-enrollment events
    )
    -- EXCLUDE employees who enrolled through ANY voluntary method
    AND efo.employee_id NOT IN (
      SELECT employee_id FROM voluntary_enrollment_events
      UNION
      SELECT employee_id FROM proactive_voluntary_enrollment_events
      UNION
      SELECT employee_id FROM year_over_year_enrollment_events
    )
    AND efo.employment_status = 'active'
),

-- Normalize only across eligible auto-enrolled opt-out candidates.
opt_out_candidates_weighted AS (
  SELECT
    efo.*,
    {{ deferral_change_multiplier('efo.current_age', var('opt_out_multipliers_age', [
      {'min': 0, 'multiplier': 1.8}, {'min': 30, 'multiplier': 1.1},
      {'min': 45, 'multiplier': 0.7}, {'min': 60, 'multiplier': 0.4}])) }} *
    {{ deferral_change_multiplier('efo.current_compensation', var('opt_out_multipliers_income', [
      {'min': 0, 'multiplier': 1.3}, {'min': 50000, 'multiplier': 1.0},
      {'min': 100000, 'multiplier': 0.8}, {'min': 200000, 'multiplier': 0.5}])) }} AS optout_weight
  FROM opt_out_candidates_raw efo
),
opt_out_candidates AS (
  SELECT
    efo.*,
    LEAST(1.0, {{ var('opt_out_rate_target', 0.09) }} * COALESCE(
      optout_weight / NULLIF(AVG(optout_weight) OVER (
        PARTITION BY simulation_year, is_hire_year_new_hire
      ), 0), 1.0)) AS optout_probability
  FROM opt_out_candidates_weighted efo
),

-- Generate opt-out events using simplified logic
opt_out_events AS (
  SELECT
    efo.employee_id,
    efo.employee_ssn,
    'enrollment_change' as event_type,
    efo.simulation_year,
    CASE
      WHEN efo.is_reenrollment_sweep AND EXTRACT(YEAR FROM efo.employee_hire_date) < efo.simulation_year
        THEN GREATEST(CAST((efo.simulation_year || '-06-15 14:00:00') AS TIMESTAMP),
          efo.plan_eligibility_date + INTERVAL '{{ var("auto_enrollment_opt_out_grace_period", 30) }}' DAY)
      WHEN EXTRACT(YEAR FROM efo.employee_hire_date) = efo.simulation_year
        THEN CAST(efo.plan_eligibility_date + efo.auto_enrollment_window_days * INTERVAL '1 day' + INTERVAL '{{ var("auto_enrollment_opt_out_grace_period", 30) }}' DAY AS TIMESTAMP)
      ELSE CAST((efo.simulation_year || '-06-15 14:00:00') AS TIMESTAMP)
    END as effective_date,

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

    {% if flat_new_hire_opt_out_rate is not none %}
    CASE WHEN efo.is_hire_year_new_hire THEN {{ flat_new_hire_opt_out_rate }}
      ELSE efo.optout_probability END AS event_probability,
    {% else %}
    efo.optout_probability AS event_probability,
    {% endif %}

    'enrollment_opt_out' as event_category
  FROM opt_out_candidates efo
  WHERE
    {%- if flat_new_hire_opt_out_rate is not none %}
    -- Issue #652 (decision D3, revised): exact-count opt-out for hire-year
    -- new hires -- take the top Q*N of the auto-enrolled cohort by rank.
    -- Continuing employees use the normalized demographic probability.
    CASE
      WHEN efo.is_hire_year_new_hire
        THEN efo.optout_rank
             <= ROUND({{ flat_new_hire_opt_out_rate }} * efo.optout_cohort_size)
      ELSE efo.optout_random < efo.optout_probability
    END
    {%- else %}
    efo.optout_random < efo.optout_probability
    {%- endif %}
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

-- Apply the employment boundary before category priority. If a later,
-- higher-priority voluntary candidate is invalid, an earlier valid auto
-- candidate remains available for deterministic selection.
sequence_eligible_events AS (
  SELECT
    a.employee_id,
    a.employee_ssn,
    a.event_type,
    a.simulation_year,
    a.effective_date,
    a.event_details,
    a.compensation_amount,
    a.previous_compensation,
    a.employee_deferral_rate,
    a.prev_employee_deferral_rate,
    a.employee_age,
    a.employee_tenure,
    a.level_id,
    a.age_band,
    a.tenure_band,
    a.event_probability,
    a.event_category
  FROM all_enrollment_events a
  LEFT JOIN {{ ref('int_employee_termination_dates') }} t
    ON a.employee_id = t.employee_id
    AND a.simulation_year = t.simulation_year
  WHERE t.termination_date IS NULL
    OR a.effective_date <= t.termination_date
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
  FROM sequence_eligible_events
  -- DEFENSIVE: Exclude employees who already enrolled in prior years
  WHERE event_type != 'enrollment'
    OR (event_category = 'auto_enrollment' AND event_details LIKE 'Re-enrollment sweep - %')
    OR employee_id NOT IN (
      SELECT employee_id
      FROM previous_enrollment_state
      WHERE was_enrolled_previously
        AND employee_id IS NOT NULL
    )
)

{% if var('easy_enroll_enabled', true) %}
, easy_enroll_choices AS (
  SELECT
    employee_id,
    simulation_year,
    event_type,
    {{ easy_enroll_package_rate('employee_id', 'simulation_year') }} AS package_rate
  FROM deduplicated_events
  WHERE priority_rank = 1
    AND event_type = 'enrollment'
    AND {{ easy_enroll_selected('event_category', 'employee_id', 'simulation_year') }}
)
{% endif %}

-- Persist the demographic candidate denominator with the run's target.
, opt_out_diagnostics AS (
  SELECT
    COUNT(*) AS optout_candidate_count,
    COUNT(e.employee_id) AS optout_realized_count
  FROM opt_out_candidates c
  LEFT JOIN deduplicated_events e
    ON e.employee_id = c.employee_id
    AND e.simulation_year = c.simulation_year
    AND e.event_category = 'enrollment_opt_out'
    AND e.priority_rank = 1
  {% if flat_new_hire_opt_out_rate is not none %}
  WHERE NOT COALESCE(c.is_hire_year_new_hire, FALSE)
  {% endif %}
)

-- Final selection compatible with fct_yearly_events schema with event sourcing metadata
-- Phase 2 Fix: Restored all critical WHERE clauses to prevent duplicate enrollments
-- Phase 3 Fix: Added deduplication to prevent multiple enrollments per employee per year
SELECT
  '{{ var("scenario_id", "default") }}' AS scenario_id,
  employee_id,
  employee_ssn,
  event_type,
  simulation_year,
  effective_date,
  {% if var('easy_enroll_enabled', true) %}
  CASE WHEN package_rate IS NOT NULL
    THEN 'Easy Enroll: original_channel=' || event_category
      || '; package_rate=' || CAST(package_rate AS VARCHAR)
      || '; escalation_cap={{ var("easy_enroll_escalation_cap", 0.10) }}; ' || event_details
    ELSE event_details
  END AS event_details,
  {% else %}
  event_details,
  {% endif %}
  compensation_amount,
  previous_compensation,
  {% if var('easy_enroll_enabled', true) %}
  COALESCE(package_rate, employee_deferral_rate) AS employee_deferral_rate,
  {% else %}
  employee_deferral_rate,
  {% endif %}
  prev_employee_deferral_rate,
  employee_age,
  employee_tenure,
  level_id,
  age_band,
  tenure_band,
  event_probability,
  {% if var('easy_enroll_enabled', true) %}
  CASE WHEN package_rate IS NOT NULL THEN 'easy_enroll' ELSE event_category END AS event_category,
  {% else %}
  event_category,
  {% endif %}
  diagnostics.optout_candidate_count,
  diagnostics.optout_realized_count,
  {{ var('opt_out_rate_target', 0.09) }}::DOUBLE AS optout_target_rate,
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
CROSS JOIN opt_out_diagnostics diagnostics
{% if var('easy_enroll_enabled', true) %}
LEFT JOIN easy_enroll_choices USING (employee_id, simulation_year, event_type)
{% endif %}
WHERE priority_rank = 1  -- Keep one per event_type per employee-year (enrollment + opt-out can coexist)
  AND employee_id IS NOT NULL
  AND simulation_year IS NOT NULL
  AND effective_date IS NOT NULL
  AND event_type IS NOT NULL
  {% if is_incremental() %}
  -- Incremental mode: only process current simulation year
  AND simulation_year = {{ var('simulation_year') }}
  {% endif %}
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
