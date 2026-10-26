{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['scenario_id', 'plan_design_id', 'employee_id', 'simulation_year'],
    on_schema_change='sync_all_columns',
    tags=['STATE_ACCUMULATION', 'DOMAIN_STATE']
) }}

/*
  Deferral Rate State Accumulator V2 - TEMPORAL ACCUMULATION IMPLEMENTATION

  Story S042-02: Implement Proper Temporal Accumulation

  CRITICAL ARCHITECTURE FIX:
  - IMPLEMENTS: Year N-1 → Year N state accumulation pattern (Epic E023)
  - PRIMARY SOURCE: int_enrollment_events for initial deferral rates
  - TEMPORAL LOGIC: Previous year state + current year escalations
  - MAINTAINS: Same output schema for backward compatibility

  BUSINESS PROCESS FLOW (Real-world):
  1. Year N: Read Year N-1 deferral state from this same model
  2. Apply Year N escalation events to carried-forward rates
  3. Handle new enrollments in Year N with fresh rates
  4. Accumulate state across simulation years

  TEMPORAL BUG FIXED:
  - Before: Employee NH_2025_000007 disappears in 2026+ (no state continuity)
  - After: Employee NH_2025_000007 carries 6% → 7% → 8% across years

  PERFORMANCE: Optimized for DuckDB with early filtering and vectorized processing
*/

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set scenario_id = var('scenario_id', 'default') %}

{% set initial_rate_change %}
  (ce.new_deferral_rate - COALESCE(he.initial_deferral_rate, br.fallback_rate, 0.03))
  / COALESCE(he.initial_deferral_rate, br.fallback_rate, 0.03)
{% endset %}
{% set carried_rate_change %}
  (COALESCE(ce.new_deferral_rate, mr.match_responsive_rate, ne.initial_deferral_rate,
            ps.previous_deferral_rate, br.fallback_rate, 0.03)
    - COALESCE(ps.original_deferral_rate, ne.initial_deferral_rate, br.fallback_rate, 0.03))
  / COALESCE(ps.original_deferral_rate, ne.initial_deferral_rate, br.fallback_rate, 0.03)
{% endset %}

WITH
irs_limits AS (
    SELECT
        base_limit,
        catch_up_limit,
        catch_up_age_threshold,
        super_catch_up_limit,
        super_catch_up_age_min,
        super_catch_up_age_max
    FROM {{ ref('config_irs_limits') }}
    ORDER BY CASE WHEN limit_year = {{ simulation_year }} THEN 0 ELSE 1 END,
        ABS(limit_year - {{ simulation_year }})
    LIMIT 1
),
-- Get current year's new enrollment events from fct_yearly_events
-- (supports both SQL and Polars event generation modes)
current_year_new_enrollments AS (
    SELECT
        employee_id,
        effective_date as enrollment_date,
        -- Use employee_deferral_rate if available, otherwise extract from event_details
        {{ enrollment_payload_deferral_rate() }} as initial_deferral_rate,
        simulation_year,
        'fct_yearly_events' as source,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date
        ) as rn
    FROM {{ ref('fct_yearly_events') }}
    -- E096 FIX: Match both 'enrollment' (from int_enrollment_events) and 'benefit_enrollment' (legacy)
    WHERE LOWER(event_type) IN ('enrollment', 'benefit_enrollment')
      AND employee_id IS NOT NULL
      AND simulation_year = {{ simulation_year }}
),

-- Get current year's escalation events
-- Epic E078: Mode-aware query - uses fct_yearly_events in Polars mode, int_deferral_rate_escalation_events in SQL mode
current_year_escalations AS (
    {% if var('event_generation_mode', 'sql') == 'polars' %}
    -- Polars mode: Read from fct_yearly_events
    SELECT
        employee_id,
        effective_date,
        employee_deferral_rate as new_deferral_rate,
        prev_employee_deferral_rate as previous_deferral_rate,
        CAST(NULL AS DECIMAL(5,4)) as escalation_rate,
        CAST(NULL AS DECIMAL(5,4)) as max_escalation_rate,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date DESC
        ) as rn
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ simulation_year }}
        AND event_type IN ('enrollment_change', 'deferral_escalation')
        AND employee_id IS NOT NULL
        AND employee_deferral_rate IS NOT NULL
    {% else %}
    -- SQL mode: Use intermediate event model
    SELECT
        employee_id,
        effective_date,
        new_deferral_rate,
        previous_deferral_rate,
        escalation_rate,
        max_escalation_rate,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date DESC
        ) as rn
    FROM {{ ref('int_deferral_rate_escalation_events') }}
    WHERE simulation_year = {{ simulation_year }}
        AND employee_id IS NOT NULL
        AND new_deferral_rate IS NOT NULL
    {% endif %}
),

-- E058: Get current year's match-response events
current_year_match_response AS (
    SELECT
        employee_id,
        effective_date,
        employee_deferral_rate AS match_responsive_rate,
        prev_employee_deferral_rate,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date DESC
        ) AS rn
    FROM {{ ref('int_deferral_match_response_events') }}
    WHERE simulation_year = {{ simulation_year }}
        AND employee_id IS NOT NULL
        AND employee_deferral_rate IS NOT NULL
),

-- Capture current year's opt-out events (set deferral to 0 and unenroll)
-- (supports both SQL and Polars event generation modes)
current_year_opt_outs AS (
    SELECT DISTINCT
        employee_id,
        effective_date
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ simulation_year }}
      AND LOWER(event_type) = 'enrollment_change'
      AND COALESCE(employee_deferral_rate, 0) = 0
      AND employee_id IS NOT NULL
),

{% if simulation_year == start_year %}
-- BASE CASE: First simulation year - get enrollments from fct_yearly_events
-- (supports both SQL and Polars event generation modes)
historical_enrollments AS (
    SELECT
        employee_id,
        effective_date as enrollment_date,
        -- Use employee_deferral_rate if available, otherwise extract from event_details
        {{ enrollment_payload_deferral_rate() }} as initial_deferral_rate,
        simulation_year as enrollment_year,
        'fct_yearly_events' as source,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY simulation_year, effective_date
        ) as rn
    FROM {{ ref('fct_yearly_events') }}
    -- E096 FIX: Match both 'enrollment' (from int_enrollment_events) and 'benefit_enrollment' (legacy)
    WHERE LOWER(event_type) IN ('enrollment', 'benefit_enrollment')
      AND employee_id IS NOT NULL
      AND simulation_year <= {{ simulation_year }}
),

-- EPIC E049: Get pre-enrolled employees directly from baseline workforce
-- Pull baseline enrollment data from int_baseline_workforce (census data)
-- (supports both SQL and Polars event generation modes)
synthetic_baseline_enrollments AS (
    SELECT
        employee_id,
        employee_enrollment_date as enrollment_date,
        employee_deferral_rate as initial_deferral_rate,  -- Use actual census rates
        EXTRACT(YEAR FROM COALESCE(employee_enrollment_date, '{{ simulation_year }}-01-01'::DATE)) as enrollment_year,
        'synthetic_baseline' as source,
        1 as rn  -- Baseline data is primary source for existing employees
    FROM {{ ref('int_baseline_workforce') }}
    WHERE employee_id IS NOT NULL
        AND employee_deferral_rate > 0
        AND employee_enrollment_date IS NOT NULL
        -- Only include if not already in event-based enrollments
        AND employee_id NOT IN (
            SELECT employee_id
            FROM historical_enrollments
            WHERE rn = 1
        )
),

-- Combine event-based and baseline pre-enrolled employees
first_year_enrolled_employees AS (
    SELECT
        employee_id,
        enrollment_date,
        initial_deferral_rate,
        enrollment_year,
        source
    FROM historical_enrollments
    WHERE rn = 1  -- First enrollment event per employee

    UNION ALL

    SELECT
        employee_id,
        enrollment_date,
        initial_deferral_rate,
        enrollment_year,
        source
    FROM synthetic_baseline_enrollments
),

{% else %}
-- TEMPORAL CASE: Subsequent years - get previous year's state
previous_year_state AS (
    SELECT
        employee_id,
        plan_design_id,
        current_deferral_rate as previous_deferral_rate,
        escalations_received as previous_escalations_received,
        total_escalation_amount as previous_total_escalation_amount,
        original_deferral_rate,
        employee_enrollment_date,
        is_enrolled_flag,
        aip_participant,
        last_nonzero_deferral_rate
    FROM {{ this }}
    WHERE simulation_year = {{ simulation_year - 1 }}
        AND employee_id IS NOT NULL
),

{% endif %}

-- Get employee demographics for current year (fallback to events data if workforce tables empty)
current_year_workforce AS (
    SELECT DISTINCT
        employee_id::VARCHAR as employee_id,
        employee_ssn::VARCHAR as employee_ssn,
        employee_birth_date::TIMESTAMP as employee_birth_date,
        employee_compensation::DECIMAL(12,2) as employee_compensation,
        current_age::SMALLINT as current_age,
        level_id::SMALLINT as level_id
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = {{ simulation_year }}
      AND employment_status = 'active'
      AND employee_id IS NOT NULL

    UNION

    -- FALLBACK: Extract new hire employee list from fct_yearly_events
    -- (supports both SQL and Polars event generation modes)
    SELECT DISTINCT
        employee_id::VARCHAR as employee_id,
        employee_ssn::VARCHAR as employee_ssn,
        NULL::TIMESTAMP as employee_birth_date,
        COALESCE(compensation_amount, 50000.00)::DECIMAL(12,2) as employee_compensation,
        COALESCE(employee_age, 35)::SMALLINT as current_age,
        COALESCE(level_id, 2)::SMALLINT as level_id
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ simulation_year }}
      AND event_type = 'hire'
      AND employee_id IS NOT NULL
      -- Only include if not already in workforce compensation table
      AND employee_id NOT IN (
          SELECT employee_id
          FROM {{ ref('int_employee_compensation_by_year') }}
          WHERE simulation_year = {{ simulation_year }}
      )
),

-- Get baseline deferral rates for fallback
baseline_deferral_rates AS (
    SELECT
        employee_id,
        CASE
            WHEN current_age < 30 THEN 'young'::VARCHAR
            WHEN current_age < 45 THEN 'mid_career'::VARCHAR
            WHEN current_age < 55 THEN 'senior'::VARCHAR
            ELSE 'mature'::VARCHAR
        END as age_segment,
        CASE
            WHEN level_id >= 5 OR employee_compensation >= 250000 THEN 'executive'::VARCHAR
            WHEN level_id >= 4 OR employee_compensation >= 150000 THEN 'high'::VARCHAR
            WHEN level_id >= 3 OR employee_compensation >= 100000 THEN 'moderate'::VARCHAR
            ELSE 'low_income'::VARCHAR
        END as income_segment,
        0.03::DECIMAL(5,4) as fallback_rate
    FROM current_year_workforce
),

{% if simulation_year == start_year %}
-- FIRST YEAR: Combine historical enrollments with current escalations
first_year_state AS (
    SELECT
        COALESCE(w.employee_id, he.employee_id, ce.employee_id, mr.employee_id, oo.employee_id) as employee_id,
        {{ simulation_year }} as simulation_year,

        -- E058+E096: Calculate current deferral rate with match-response + escalation additive logic
        -- Priority: opt-out > (match-response + escalation additive) > escalation > match-response > enrollment
        {{ rate_before_voluntary_change(
            'oo.employee_id IS NOT NULL', 'he.employee_id IS NOT NULL',
            'he.initial_deferral_rate, br.fallback_rate, 0.03::DECIMAL(5,4)',
            'ce.new_deferral_rate', 'mr.match_responsive_rate', 'ce.escalation_rate',
            'ce.max_escalation_rate', 'cyw.employee_compensation',
            'COALESCE(' ~ simulation_year ~ ' - YEAR(cyw.employee_birth_date), cyw.current_age)'
        ) }} as rate_before_voluntary_change,

        -- Track escalations
        CASE WHEN ce.employee_id IS NOT NULL THEN 1 ELSE 0 END as escalations_received,
        CAST(ce.effective_date AS TIMESTAMP) as last_escalation_date,
        (ce.employee_id IS NOT NULL) as has_escalations,
        'int_deferral_rate_escalation_events'::VARCHAR as escalation_source,

        -- Current year activity
        (ce.employee_id IS NOT NULL) as had_escalation_this_year,
        CASE WHEN ce.employee_id IS NOT NULL THEN 1 ELSE 0 END as escalation_events_this_year,
        NULL::VARCHAR as latest_escalation_details,

        -- Original enrollment rate (before any escalations)
        -- E096 FIX: Non-enrolled employees should have original_deferral_rate = 0
        CASE
            WHEN he.employee_id IS NULL THEN 0.00::DECIMAL(5,4)  -- Not enrolled
            ELSE COALESCE(he.initial_deferral_rate, br.fallback_rate, 0.03::DECIMAL(5,4))
        END as original_deferral_rate,

        -- Rate change calculation
        CASE
            WHEN COALESCE(he.initial_deferral_rate, br.fallback_rate, 0.03) > 0.0001 AND ce.new_deferral_rate IS NOT NULL
            THEN {{ stable_decimal(initial_rate_change, 8, 4) }}
            ELSE NULL
        END as escalation_rate_change_pct,
        CAST(COALESCE(GREATEST(ce.new_deferral_rate - ce.previous_deferral_rate, 0), 0) AS DECIMAL(5,4)) as total_escalation_amount,

        -- Time metrics
        NULL::INTEGER as years_since_first_escalation,
        CASE
            WHEN ce.effective_date IS NOT NULL
            THEN DATEDIFF('day', ce.effective_date, DATE '{{ simulation_year }}-12-31')
            ELSE NULL
        END as days_since_last_escalation,

        -- Enrollment information
        CASE
            WHEN oo.employee_id IS NOT NULL THEN false
            ELSE (he.employee_id IS NOT NULL)
        END as is_enrolled_flag,
        he.enrollment_date as employee_enrollment_date,

        -- Metadata
        CURRENT_TIMESTAMP as created_at,
        '{{ scenario_id }}'::VARCHAR as scenario_id,
        assignment.plan_design_id,
        CASE
            WHEN COALESCE(w.employee_id, he.employee_id, ce.employee_id, mr.employee_id) IS NULL THEN 'INVALID_EMPLOYEE_ID'
            WHEN COALESCE(ce.new_deferral_rate, mr.match_responsive_rate, he.initial_deferral_rate, br.fallback_rate, 0.03) < 0
                OR COALESCE(ce.new_deferral_rate, mr.match_responsive_rate, he.initial_deferral_rate, br.fallback_rate, 0.03) > 1
                THEN 'INVALID_RATE'
            ELSE 'VALID'
        END as data_quality_flag,

        -- E058: Rate source tracking with match-response
        CASE
            WHEN oo.employee_id IS NOT NULL THEN 'opt_out'
            WHEN he.employee_id IS NULL THEN 'not_enrolled'
            WHEN mr.employee_id IS NOT NULL AND ce.employee_id IS NOT NULL THEN 'match_response_plus_escalation'
            WHEN mr.employee_id IS NOT NULL THEN 'match_response'
            WHEN ce.employee_id IS NOT NULL THEN 'escalation_event'
            WHEN he.source = 'synthetic_baseline' THEN 'census_rate'
            WHEN he.source = 'fct_yearly_events' THEN 'enrollment_event'
            WHEN br.employee_id IS NOT NULL THEN 'demographic_fallback'
            ELSE 'hard_fallback'
        END as rate_source

    FROM current_year_workforce w
    INNER JOIN {{ ref('int_plan_design_assignment_accumulator') }} assignment
        ON w.employee_id = assignment.employee_id
       AND assignment.scenario_id = '{{ scenario_id }}'
       AND assignment.simulation_year = {{ simulation_year }}
    FULL OUTER JOIN first_year_enrolled_employees he ON w.employee_id = he.employee_id
    LEFT JOIN current_year_escalations ce ON COALESCE(w.employee_id, he.employee_id) = ce.employee_id AND ce.rn = 1
    LEFT JOIN current_year_match_response mr ON COALESCE(w.employee_id, he.employee_id) = mr.employee_id AND mr.rn = 1
    LEFT JOIN current_year_opt_outs oo ON COALESCE(w.employee_id, he.employee_id) = oo.employee_id
    LEFT JOIN baseline_deferral_rates br ON COALESCE(w.employee_id, he.employee_id) = br.employee_id
    -- E058: Join workforce for compensation (needed for IRS limit calculation in additive case)
    LEFT JOIN current_year_workforce cyw ON COALESCE(w.employee_id, he.employee_id) = cyw.employee_id
    CROSS JOIN irs_limits il
    -- E096 FIX: Include ALL workforce employees, not just those with enrollment events
    -- Non-enrolled employees get deferral_rate = 0 and is_enrolled_flag = false
    -- This ensures census employees without explicit enrollment data still appear
    WHERE COALESCE(w.employee_id, he.employee_id) IS NOT NULL
),

{% else %}
-- SUBSEQUENT YEARS: Temporal accumulation pattern
subsequent_year_state AS (
    SELECT
        COALESCE(w.employee_id, ps.employee_id, ne.employee_id, ce.employee_id, mr.employee_id, oo.employee_id) as employee_id,
        {{ simulation_year }} as simulation_year,

        -- E058: TEMPORAL LOGIC with match-response + escalation additive handling
        {{ rate_before_voluntary_change(
            'oo.employee_id IS NOT NULL', 'TRUE',
            'ne.initial_deferral_rate, ps.previous_deferral_rate, br.fallback_rate, 0.03::DECIMAL(5,4)',
            'ce.new_deferral_rate', 'mr.match_responsive_rate', 'ce.escalation_rate',
            'ce.max_escalation_rate', 'cyw.employee_compensation',
            'COALESCE(' ~ simulation_year ~ ' - YEAR(cyw.employee_birth_date), cyw.current_age)'
        ) }} as rate_before_voluntary_change,

        -- Track escalations cumulatively
        CASE
            WHEN ce.employee_id IS NOT NULL THEN (COALESCE(ps.previous_escalations_received, 0) + 1)
            ELSE COALESCE(ps.previous_escalations_received, 0)
        END as escalations_received,

        CAST(COALESCE(ce.effective_date, ps.employee_enrollment_date) AS TIMESTAMP) as last_escalation_date,
        (COALESCE(ps.previous_escalations_received, 0) > 0 OR ce.employee_id IS NOT NULL) as has_escalations,
        'int_deferral_rate_escalation_events'::VARCHAR as escalation_source,

        -- Current year activity
        (ce.employee_id IS NOT NULL) as had_escalation_this_year,
        CASE WHEN ce.employee_id IS NOT NULL THEN 1 ELSE 0 END as escalation_events_this_year,
        NULL::VARCHAR as latest_escalation_details,

        -- Original enrollment rate (carry forward or new)
        COALESCE(ne.initial_deferral_rate, ps.original_deferral_rate, br.fallback_rate, 0.03::DECIMAL(5,4)) as original_deferral_rate,

        -- Rate change calculation
        CASE
            WHEN COALESCE(ps.original_deferral_rate, ne.initial_deferral_rate, br.fallback_rate, 0.03) > 0.0001
            THEN {{ stable_decimal(carried_rate_change, 8, 4) }}
            ELSE NULL
        END as escalation_rate_change_pct,

        -- Cumulative escalation increments (#997). Not current - original: match
        -- responses and voluntary decreases also move the rate.
        (
            COALESCE(ps.previous_total_escalation_amount, 0)
            + CASE WHEN ce.employee_id IS NOT NULL THEN COALESCE(
                GREATEST(ce.new_deferral_rate - ce.previous_deferral_rate, 0), 0
            ) ELSE 0 END
        )::DECIMAL(5,4) as total_escalation_amount,

        -- Time metrics (simplified for now)
        NULL::INTEGER as years_since_first_escalation,
        CASE
            WHEN ce.effective_date IS NOT NULL
            THEN DATEDIFF('day', ce.effective_date, DATE '{{ simulation_year }}-12-31')
            ELSE NULL
        END as days_since_last_escalation,

        -- Enrollment information (carry forward or new)
        -- Feature 095 fix: a current-year enrollment (ne) must override a stale
        -- prior-year unenrolled flag. The previous COALESCE returned ps.is_enrolled_flag
        -- first, so a previously-unenrolled employee who newly enrolls resolved to
        -- false and was dropped by the WHERE filter below. Opt-out still wins.
        CASE
            WHEN oo.employee_id IS NOT NULL THEN false
            WHEN ne.employee_id IS NOT NULL THEN true
            ELSE COALESCE(ps.is_enrolled_flag, false)
        END as is_enrolled_flag,
        COALESCE(ne.enrollment_date, ps.employee_enrollment_date) as employee_enrollment_date,

        -- Metadata
        CURRENT_TIMESTAMP as created_at,
        '{{ scenario_id }}'::VARCHAR as scenario_id,
        COALESCE(assignment.plan_design_id, ps.plan_design_id) AS plan_design_id,
        CASE
            WHEN COALESCE(w.employee_id, ps.employee_id, ne.employee_id, ce.employee_id, mr.employee_id) IS NULL THEN 'INVALID_EMPLOYEE_ID'
            WHEN COALESCE(ce.new_deferral_rate, mr.match_responsive_rate, ne.initial_deferral_rate, ps.previous_deferral_rate, br.fallback_rate, 0.03) < 0
                OR COALESCE(ce.new_deferral_rate, mr.match_responsive_rate, ne.initial_deferral_rate, ps.previous_deferral_rate, br.fallback_rate, 0.03) > 1
                THEN 'INVALID_RATE'
            ELSE 'VALID'
        END as data_quality_flag,

        -- E058: Rate source tracking with match-response (subsequent years)
        CASE
            WHEN oo.employee_id IS NOT NULL THEN 'opt_out'
            WHEN mr.employee_id IS NOT NULL AND ce.employee_id IS NOT NULL THEN 'match_response_plus_escalation'
            WHEN mr.employee_id IS NOT NULL THEN 'match_response'
            WHEN ce.employee_id IS NOT NULL THEN 'escalation_event'
            WHEN ne.source = 'synthetic_baseline' THEN 'census_rate'
            WHEN ne.source = 'fct_yearly_events' THEN 'enrollment_event'
            WHEN ps.employee_id IS NOT NULL THEN 'carried_forward'
            WHEN br.employee_id IS NOT NULL THEN 'demographic_fallback'
            ELSE 'hard_fallback'
        END as rate_source

    FROM current_year_workforce w
    INNER JOIN {{ ref('int_plan_design_assignment_accumulator') }} assignment
        ON w.employee_id = assignment.employee_id
       AND assignment.scenario_id = '{{ scenario_id }}'
       AND assignment.simulation_year = {{ simulation_year }}
    FULL OUTER JOIN previous_year_state ps ON w.employee_id = ps.employee_id
    LEFT JOIN current_year_new_enrollments ne ON COALESCE(w.employee_id, ps.employee_id) = ne.employee_id AND ne.rn = 1
    LEFT JOIN current_year_escalations ce ON COALESCE(w.employee_id, ps.employee_id) = ce.employee_id AND ce.rn = 1
    LEFT JOIN current_year_match_response mr ON COALESCE(w.employee_id, ps.employee_id) = mr.employee_id AND mr.rn = 1
    LEFT JOIN current_year_opt_outs oo ON COALESCE(w.employee_id, ps.employee_id) = oo.employee_id
    LEFT JOIN baseline_deferral_rates br ON COALESCE(w.employee_id, ps.employee_id) = br.employee_id
    -- E058: Join workforce for compensation (needed for IRS limit calculation in additive case)
    LEFT JOIN current_year_workforce cyw ON COALESCE(w.employee_id, ps.employee_id) = cyw.employee_id
    CROSS JOIN irs_limits il
    -- Include employees who are enrolled (new enrollments, carry-forward, have escalations, or match-response)
    -- Feature 095 fix: retain a current-year enrollment (ne) even when prior-year
    -- state is unenrolled (false). Mirrors the is_enrolled_flag precedence above.
    WHERE (ps.employee_id IS NOT NULL OR ne.employee_id IS NOT NULL OR ce.employee_id IS NOT NULL OR mr.employee_id IS NOT NULL)
      AND (ne.employee_id IS NOT NULL OR COALESCE(ps.is_enrolled_flag, false) = true)
),

{% endif %}

-- D2: one change per employee/year; latest date wins, with a stable tie-break.
current_year_deferral_changes AS (
  SELECT
    employee_id,
    plan_design_id,
    employee_deferral_rate
  FROM {{ ref('fct_yearly_events') }}
  WHERE simulation_year = {{ simulation_year }}
    AND scenario_id = '{{ scenario_id }}'
    AND event_type = {{ evt_deferral_change() }}
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY scenario_id, plan_design_id, employee_id, simulation_year
    ORDER BY effective_date DESC, event_id DESC
  ) = 1
),

voluntary_change_state AS (
  SELECT
    s.employee_id,
    s.simulation_year,
    s.escalations_received,
    s.last_escalation_date,
    s.has_escalations,
    s.escalation_source,
    s.had_escalation_this_year,
    s.escalation_events_this_year,
    s.latest_escalation_details,
    s.original_deferral_rate,
    s.escalation_rate_change_pct,
    s.total_escalation_amount,
    s.years_since_first_escalation,
    s.days_since_last_escalation,
    s.is_enrolled_flag,
    s.employee_enrollment_date,
    s.created_at,
    s.scenario_id,
    s.plan_design_id,
    s.data_quality_flag,
    s.rate_before_voluntary_change,
    CASE
      WHEN s.rate_source = 'opt_out' THEN 0.00::DECIMAL(5,4)
      WHEN dc.employee_id IS NOT NULL THEN dc.employee_deferral_rate
      ELSE s.rate_before_voluntary_change
    END AS current_deferral_rate,
    CASE
      WHEN s.rate_source = 'opt_out' THEN s.rate_source
      WHEN dc.employee_id IS NOT NULL THEN 'deferral_change'
      ELSE s.rate_source
    END AS rate_source,
    -- Package enrollment elects AIP even when ordinary escalation is disabled.
    {% if var('easy_enroll_enabled', false) %}
    {{ easy_enroll_member(ref('fct_yearly_events'), 's.employee_id', 's.simulation_year',
      's.scenario_id') }} OR
    {% endif %}
    {% if simulation_year == start_year %}
    {{ aip_initial_membership(var('deferral_escalation_mode', 'automatic'), 'census.auto_escalation_opt_out', 's.employee_id') }} AS aip_participant,
    NULL::DECIMAL(5,4) AS previous_nonzero_deferral_rate
    {% else %}
    COALESCE(ps.aip_participant,
      {{ aip_initial_membership(var('deferral_escalation_mode', 'automatic'), 'census.auto_escalation_opt_out', 's.employee_id') }}) AS aip_participant,
    ps.last_nonzero_deferral_rate AS previous_nonzero_deferral_rate
    {% endif %}
  FROM
  {% if simulation_year == start_year %}
    first_year_state s
  {% else %}
    subsequent_year_state s
  LEFT JOIN previous_year_state ps ON s.employee_id = ps.employee_id
  {% endif %}
  LEFT JOIN {{ ref('stg_census_data') }} census ON s.employee_id = census.employee_id
  LEFT JOIN current_year_deferral_changes dc
    ON s.employee_id = dc.employee_id AND s.plan_design_id = dc.plan_design_id
)

SELECT
  employee_id,
  simulation_year,
  escalations_received,
  last_escalation_date,
  has_escalations,
  escalation_source,
  had_escalation_this_year,
  escalation_events_this_year,
  latest_escalation_details,
  original_deferral_rate,
  escalation_rate_change_pct,
  total_escalation_amount,
  years_since_first_escalation,
  days_since_last_escalation,
  is_enrolled_flag,
  employee_enrollment_date,
  created_at,
  scenario_id,
  plan_design_id,
  data_quality_flag,
  rate_before_voluntary_change,
  current_deferral_rate,
  rate_source,
  aip_participant,
  -- A stop (D1) carries the rate in effect just before it, so a restart resumes there.
  CAST(CASE
    WHEN current_deferral_rate > 0 THEN current_deferral_rate
    WHEN rate_before_voluntary_change > 0 THEN rate_before_voluntary_change
    ELSE previous_nonzero_deferral_rate
  END AS DECIMAL(5,4)) AS last_nonzero_deferral_rate
FROM voluntary_change_state
WHERE employee_id IS NOT NULL

/*
  STORY S042-02 IMPLEMENTATION SUMMARY:

  1. ✅ IMPLEMENTS Year N-1 → Year N temporal accumulation pattern (Epic E023)
  2. ✅ FIXES "disappearing employee" bug by carrying forward previous year's state
  3. ✅ APPLIES escalations to carried-forward rates correctly
  4. ✅ MAINTAINS same output schema for backward compatibility

  TEMPORAL LOGIC FLOW:
  - Year 2025: Employee NH_2025_000007 gets 6% from enrollment event
  - Year 2026: Employee NH_2025_000007 carries 6% + 1% escalation = 7%
  - Year 2027: Employee NH_2025_000007 carries 7% + 1% escalation = 8%

  KEY FIXES:
  - Uses {{ this }} to read previous year's state (temporal dependency)
  - Handles first year base case with historical enrollment data
  - Applies current year escalations to previous year rates
  - Maintains enrollment state continuity across simulation years

  EXPECTED OUTCOME:
  Employee NH_2025_000007 will now appear in all simulation years with correct escalated rates.
*/
