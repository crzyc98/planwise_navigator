{{ config(
    materialized='incremental',
    incremental_strategy='delete+insert',
    unique_key=['employee_id', 'simulation_year'],
    on_schema_change='ignore',
    tags=['STATE_ACCUMULATION']
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

WITH
-- Get current year's new enrollment events (for new employees this year)
current_year_new_enrollments_from_events AS (
    SELECT
        employee_id,
        effective_date as enrollment_date,
        employee_deferral_rate as initial_deferral_rate,
        simulation_year,
        'int_enrollment_events' as source,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date
        ) as rn
    FROM {{ ref('int_enrollment_events') }}
    WHERE LOWER(event_type) = 'enrollment'
      AND employee_id IS NOT NULL
      AND employee_deferral_rate IS NOT NULL
      AND simulation_year = {{ simulation_year }}
),

-- FALLBACK: Get current year enrollments from fct_yearly_events
current_year_new_enrollments_from_yearly_events AS (
    SELECT
        employee_id,
        effective_date as enrollment_date,
        -- Extract deferral rate from event_details using regex
        CASE
            WHEN REGEXP_EXTRACT(event_details, '([0-9]+\.?[0-9]*)%\s*deferral', 1) IS NOT NULL
                 AND REGEXP_EXTRACT(event_details, '([0-9]+\.?[0-9]*)%\s*deferral', 1) != ''
            THEN CAST(REGEXP_EXTRACT(event_details, '([0-9]+\.?[0-9]*)%\s*deferral', 1) AS DECIMAL(6,4)) / 100.0
            ELSE 0.06  -- Default fallback
        END as initial_deferral_rate,
        simulation_year,
        'fct_yearly_events' as source,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date
        ) as rn
    FROM {{ ref('fct_yearly_events') }}
    WHERE LOWER(event_type) = 'enrollment'
      AND employee_id IS NOT NULL
      AND simulation_year = {{ simulation_year }}
      -- Only include if not already in int_enrollment_events
      AND employee_id NOT IN (
          SELECT employee_id
          FROM current_year_new_enrollments_from_events
          WHERE rn = 1
      )
),

-- Combine both sources for current year
current_year_new_enrollments AS (
    SELECT employee_id, enrollment_date, initial_deferral_rate, simulation_year, source, rn
    FROM current_year_new_enrollments_from_events
    UNION ALL
    SELECT employee_id, enrollment_date, initial_deferral_rate, simulation_year, source, rn
    FROM current_year_new_enrollments_from_yearly_events
),

-- Get current year's escalation events
current_year_escalations AS (
    SELECT
        employee_id,
        effective_date,
        new_deferral_rate,
        escalation_rate,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date DESC
        ) as rn
    FROM {{ ref('int_deferral_rate_escalation_events') }}
    WHERE simulation_year = {{ simulation_year }}
        AND employee_id IS NOT NULL
        AND new_deferral_rate IS NOT NULL
),

-- Capture current year's opt-out events (set deferral to 0 and unenroll)
current_year_opt_outs AS (
    SELECT DISTINCT
        employee_id,
        effective_date
    FROM {{ ref('int_enrollment_events') }}
    WHERE simulation_year = {{ simulation_year }}
      AND LOWER(event_type) = 'enrollment_change'
      AND COALESCE(employee_deferral_rate, 0) = 0
      AND employee_id IS NOT NULL
),

{% if simulation_year == start_year %}
-- BASE CASE: First simulation year - get enrollments from both int_enrollment_events and fct_yearly_events
historical_enrollments_from_events AS (
    SELECT
        employee_id,
        effective_date as enrollment_date,
        employee_deferral_rate as initial_deferral_rate,
        simulation_year as enrollment_year,
        'int_enrollment_events' as source,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY simulation_year, effective_date
        ) as rn
    FROM {{ ref('int_enrollment_events') }}
    WHERE LOWER(event_type) = 'enrollment'
      AND employee_id IS NOT NULL
      AND employee_deferral_rate IS NOT NULL
      AND simulation_year <= {{ simulation_year }}
),

-- FALLBACK: Extract from fct_yearly_events for employees missing from int_enrollment_events
historical_enrollments_from_yearly_events AS (
    SELECT
        employee_id,
        effective_date as enrollment_date,
        -- Extract deferral rate from event_details using regex
        CASE
            WHEN REGEXP_EXTRACT(event_details, '([0-9]+\.?[0-9]*)%\s*deferral', 1) IS NOT NULL
                 AND REGEXP_EXTRACT(event_details, '([0-9]+\.?[0-9]*)%\s*deferral', 1) != ''
            THEN CAST(REGEXP_EXTRACT(event_details, '([0-9]+\.?[0-9]*)%\s*deferral', 1) AS DECIMAL(6,4)) / 100.0
            ELSE 0.06  -- Default fallback
        END as initial_deferral_rate,
        simulation_year as enrollment_year,
        'fct_yearly_events' as source,
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY simulation_year, effective_date
        ) as rn
    FROM {{ ref('fct_yearly_events') }}
    WHERE LOWER(event_type) = 'enrollment'
      AND employee_id IS NOT NULL
      AND simulation_year <= {{ simulation_year }}
      -- Only include if not already in int_enrollment_events
      AND employee_id NOT IN (
          SELECT employee_id
          FROM historical_enrollments_from_events
          WHERE rn = 1
      )
),

-- Combine both sources
historical_enrollments AS (
    SELECT * FROM historical_enrollments_from_events
    UNION ALL
    SELECT * FROM historical_enrollments_from_yearly_events
),

-- EPIC E049: Use synthetic baseline events instead of hard-coded 6% rates
-- Get pre-enrolled employees from synthetic baseline enrollment events
synthetic_baseline_enrollments AS (
    SELECT
        employee_id,
        effective_date as enrollment_date,
        employee_deferral_rate as initial_deferral_rate,  -- Use actual census rates
        EXTRACT(YEAR FROM effective_date) as enrollment_year,
        'synthetic_baseline' as source,
        1 as rn  -- Synthetic events are primary source
    FROM {{ ref('int_synthetic_baseline_enrollment_events') }}
    WHERE simulation_year = {{ simulation_year }}
        AND employee_id IS NOT NULL
        AND employee_deferral_rate > 0
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
        current_deferral_rate as previous_deferral_rate,
        escalations_received as previous_escalations_received,
        original_deferral_rate,
        employee_enrollment_date,
        is_enrolled_flag
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
        employee_compensation::DECIMAL(12,2) as employee_compensation,
        current_age::SMALLINT as current_age,
        level_id::SMALLINT as level_id
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = {{ simulation_year }}
      AND employment_status = 'active'
      AND employee_id IS NOT NULL

    UNION

    -- Include new hires that might not be in compensation table yet
    SELECT
        employee_id::VARCHAR as employee_id,
        employee_ssn::VARCHAR as employee_ssn,
        compensation_amount::DECIMAL(12,2) as employee_compensation,
        employee_age::SMALLINT as current_age,
        level_id::SMALLINT as level_id
    FROM {{ ref('int_hiring_events') }}
    WHERE simulation_year = {{ simulation_year }}
      AND employee_id IS NOT NULL

    UNION

    -- FALLBACK: Extract employee list from fct_yearly_events if workforce tables are empty
    SELECT DISTINCT
        employee_id::VARCHAR as employee_id,
        'UNKNOWN'::VARCHAR as employee_ssn,
        50000.00::DECIMAL(12,2) as employee_compensation,  -- Default compensation
        35::SMALLINT as current_age,                       -- Default age
        2::SMALLINT as level_id                            -- Default level
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ simulation_year }}
      AND event_type IN ('enrollment', 'hire')
      AND employee_id IS NOT NULL
      -- Only include if not already in workforce tables
      AND employee_id NOT IN (
          SELECT employee_id
          FROM {{ ref('int_employee_compensation_by_year') }}
          WHERE simulation_year = {{ simulation_year }}
          UNION
          SELECT employee_id
          FROM {{ ref('int_hiring_events') }}
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
        COALESCE(w.employee_id, he.employee_id, ce.employee_id, oo.employee_id) as employee_id,
        {{ simulation_year }} as simulation_year,

        -- Calculate current deferral rate with opt-out override
        CASE
            WHEN oo.employee_id IS NOT NULL THEN 0.00::DECIMAL(5,4)
            ELSE COALESCE(
                ce.new_deferral_rate,      -- Latest escalation this year
                he.initial_deferral_rate,  -- Initial enrollment rate
                br.fallback_rate,          -- Demographic fallback
                0.03::DECIMAL(5,4)         -- Hard fallback
            )
        END as current_deferral_rate,

        -- Track escalations
        CASE WHEN ce.employee_id IS NOT NULL THEN 1 ELSE 0 END as escalations_received,
        ce.effective_date as last_escalation_date,
        (ce.employee_id IS NOT NULL) as has_escalations,
        'int_deferral_rate_escalation_events'::VARCHAR as escalation_source,

        -- Current year activity
        (ce.employee_id IS NOT NULL) as had_escalation_this_year,
        CASE WHEN ce.employee_id IS NOT NULL THEN 1 ELSE 0 END as escalation_events_this_year,
        NULL::VARCHAR as latest_escalation_details,

        -- Original enrollment rate (before any escalations)
        COALESCE(he.initial_deferral_rate, br.fallback_rate, 0.03::DECIMAL(5,4)) as original_deferral_rate,

        -- Rate change calculation
        CASE
            WHEN COALESCE(he.initial_deferral_rate, br.fallback_rate, 0.03) > 0.0001 AND ce.new_deferral_rate IS NOT NULL
            THEN ((ce.new_deferral_rate - COALESCE(he.initial_deferral_rate, br.fallback_rate, 0.03)) / COALESCE(he.initial_deferral_rate, br.fallback_rate, 0.03))::DECIMAL(8,4)
            ELSE NULL
        END as escalation_rate_change_pct,
        COALESCE(ce.escalation_rate, 0.0000::DECIMAL(5,4)) as total_escalation_amount,

        -- Time metrics
        NULL::INTEGER as years_since_first_escalation,
        CASE
            WHEN ce.effective_date IS NOT NULL
            THEN (DATE '{{ simulation_year }}-12-31' - ce.effective_date)::INTEGER
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
        'default'::VARCHAR as scenario_id,
        CASE
            WHEN COALESCE(w.employee_id, he.employee_id, ce.employee_id) IS NULL THEN 'INVALID_EMPLOYEE_ID'
            WHEN COALESCE(ce.new_deferral_rate, he.initial_deferral_rate, br.fallback_rate, 0.03) < 0
                OR COALESCE(ce.new_deferral_rate, he.initial_deferral_rate, br.fallback_rate, 0.03) > 1
                THEN 'INVALID_RATE'
            ELSE 'VALID'
        END as data_quality_flag,

        -- Epic E049: Rate source tracking for lineage
        CASE
            WHEN oo.employee_id IS NOT NULL THEN 'opt_out'
            WHEN ce.employee_id IS NOT NULL THEN 'escalation_event'
            WHEN he.source = 'synthetic_baseline' THEN 'census_rate'
            WHEN he.source = 'int_enrollment_events' THEN 'enrollment_event'
            WHEN he.source = 'fct_yearly_events' THEN 'fallback_event'
            WHEN br.employee_id IS NOT NULL THEN 'demographic_fallback'
            ELSE 'hard_fallback'
        END as rate_source

    FROM current_year_workforce w
    FULL OUTER JOIN first_year_enrolled_employees he ON w.employee_id = he.employee_id
    LEFT JOIN current_year_escalations ce ON COALESCE(w.employee_id, he.employee_id) = ce.employee_id AND ce.rn = 1
    LEFT JOIN current_year_opt_outs oo ON COALESCE(w.employee_id, he.employee_id) = oo.employee_id
    LEFT JOIN baseline_deferral_rates br ON COALESCE(w.employee_id, he.employee_id) = br.employee_id
    -- Only include employees who are enrolled (have enrollment events)
    WHERE he.employee_id IS NOT NULL
)

{% else %}
-- SUBSEQUENT YEARS: Temporal accumulation pattern
subsequent_year_state AS (
    SELECT
        COALESCE(w.employee_id, ps.employee_id, ne.employee_id, ce.employee_id, oo.employee_id) as employee_id,
        {{ simulation_year }} as simulation_year,

        -- TEMPORAL LOGIC with opt-out override: Apply escalations, enrollment, or carry-forward unless opted out
        CASE
            WHEN oo.employee_id IS NOT NULL THEN 0.00::DECIMAL(5,4)
            ELSE COALESCE(
                ce.new_deferral_rate,                    -- Current year escalation overwrites all
                ne.initial_deferral_rate,                -- New enrollment this year
                ps.previous_deferral_rate,               -- Carry forward from previous year
                br.fallback_rate,                        -- Demographic fallback
                0.03::DECIMAL(5,4)                       -- Hard fallback
            )
        END as current_deferral_rate,

        -- Track escalations cumulatively
        CASE
            WHEN ce.employee_id IS NOT NULL THEN (COALESCE(ps.previous_escalations_received, 0) + 1)
            ELSE COALESCE(ps.previous_escalations_received, 0)
        END as escalations_received,

        COALESCE(ce.effective_date, ps.employee_enrollment_date) as last_escalation_date,
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
            THEN ((COALESCE(ce.new_deferral_rate, ne.initial_deferral_rate, ps.previous_deferral_rate, br.fallback_rate, 0.03) -
                   COALESCE(ps.original_deferral_rate, ne.initial_deferral_rate, br.fallback_rate, 0.03)) /
                   COALESCE(ps.original_deferral_rate, ne.initial_deferral_rate, br.fallback_rate, 0.03))::DECIMAL(8,4)
            ELSE NULL
        END as escalation_rate_change_pct,

        -- Total escalation amount calculation
        CASE
            WHEN ce.employee_id IS NOT NULL AND ps.original_deferral_rate IS NOT NULL
            THEN (ce.new_deferral_rate - ps.original_deferral_rate)::DECIMAL(5,4)
            WHEN ps.previous_deferral_rate IS NOT NULL AND ps.original_deferral_rate IS NOT NULL
            THEN (ps.previous_deferral_rate - ps.original_deferral_rate)::DECIMAL(5,4)
            ELSE 0.0000::DECIMAL(5,4)
        END as total_escalation_amount,

        -- Time metrics (simplified for now)
        NULL::INTEGER as years_since_first_escalation,
        CASE
            WHEN ce.effective_date IS NOT NULL
            THEN (DATE '{{ simulation_year }}-12-31' - ce.effective_date)::INTEGER
            ELSE NULL
        END as days_since_last_escalation,

        -- Enrollment information (carry forward or new)
        CASE
            WHEN oo.employee_id IS NOT NULL THEN false
            ELSE COALESCE(ps.is_enrolled_flag, ne.employee_id IS NOT NULL, false)
        END as is_enrolled_flag,
        COALESCE(ne.enrollment_date, ps.employee_enrollment_date) as employee_enrollment_date,

        -- Metadata
        CURRENT_TIMESTAMP as created_at,
        'default'::VARCHAR as scenario_id,
        CASE
            WHEN COALESCE(w.employee_id, ps.employee_id, ne.employee_id, ce.employee_id) IS NULL THEN 'INVALID_EMPLOYEE_ID'
            WHEN COALESCE(ce.new_deferral_rate, ne.initial_deferral_rate, ps.previous_deferral_rate, br.fallback_rate, 0.03) < 0
                OR COALESCE(ce.new_deferral_rate, ne.initial_deferral_rate, ps.previous_deferral_rate, br.fallback_rate, 0.03) > 1
                THEN 'INVALID_RATE'
            ELSE 'VALID'
        END as data_quality_flag,

        -- Epic E049: Rate source tracking for lineage (subsequent years)
        CASE
            WHEN oo.employee_id IS NOT NULL THEN 'opt_out'
            WHEN ce.employee_id IS NOT NULL THEN 'escalation_event'
            WHEN ne.source = 'synthetic_baseline' THEN 'census_rate'
            WHEN ne.source = 'int_enrollment_events' THEN 'enrollment_event'
            WHEN ps.employee_id IS NOT NULL THEN 'carried_forward'
            WHEN br.employee_id IS NOT NULL THEN 'demographic_fallback'
            ELSE 'hard_fallback'
        END as rate_source

    FROM current_year_workforce w
    FULL OUTER JOIN previous_year_state ps ON w.employee_id = ps.employee_id
    LEFT JOIN current_year_new_enrollments ne ON COALESCE(w.employee_id, ps.employee_id) = ne.employee_id AND ne.rn = 1
    LEFT JOIN current_year_escalations ce ON COALESCE(w.employee_id, ps.employee_id) = ce.employee_id AND ce.rn = 1
    LEFT JOIN current_year_opt_outs oo ON COALESCE(w.employee_id, ps.employee_id) = oo.employee_id
    LEFT JOIN baseline_deferral_rates br ON COALESCE(w.employee_id, ps.employee_id) = br.employee_id
    -- Include employees who are enrolled (new enrollments, carry-forward, or have escalations)
    WHERE (ps.employee_id IS NOT NULL OR ne.employee_id IS NOT NULL OR ce.employee_id IS NOT NULL)
      AND COALESCE(ps.is_enrolled_flag, ne.employee_id IS NOT NULL, false) = true
)

{% endif %}

-- Final selection with temporal logic
SELECT *
FROM
{% if simulation_year == start_year %}
    first_year_state
{% else %}
    subsequent_year_state
{% endif %}
WHERE employee_id IS NOT NULL

{% if is_incremental() %}
    -- Incremental processing - delete+insert strategy keyed by year
    AND simulation_year = {{ simulation_year }}
{% endif %}

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
