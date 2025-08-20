{{ config(
    materialized='incremental',
    unique_key=['employee_id', 'simulation_year'],
    on_schema_change='sync_all_columns',
    indexes=[
        {'columns': ['simulation_year', 'employee_id'], 'type': 'btree', 'unique': true},
        {'columns': ['simulation_year'], 'type': 'btree'},
        {'columns': ['employee_id'], 'type': 'btree'},
        {'columns': ['enrollment_status'], 'type': 'btree'}
    ]
) }}

/*
  Temporal State Accumulator for Enrollment Tracking

  This model implements a temporal state accumulator pattern to track enrollment
  state across simulation years without circular dependencies. It builds enrollment
  state year-by-year using:
  - Current year's events from fct_yearly_events
  - Previous year's state from this same model (temporal dependency)
  - Baseline workforce for first year initialization

  Key Features:
  - Incremental materialization with unique_key=['employee_id', 'simulation_year']
  - Handles base case (first simulation year) with no prior enrollment
  - Accumulates enrollment history across simulation years
  - Tracks enrollment_date, enrollment_status, and enrollment changes
  - No circular dependencies (only uses fct_yearly_events + own previous data)

  Phase 1 Fix: Replaces int_historical_enrollment_tracker to solve 321 employees
  with enrollment events but no enrollment dates in workforce snapshots.
*/

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}

-- Debug: Current processing year
-- simulation_year = {{ simulation_year }}, start_year = {{ start_year }}

-- Get all enrollment-related events for current simulation year
-- Read directly from int_enrollment_events to avoid circular dependency
WITH current_year_enrollment_events AS (
    SELECT
        employee_id,
        event_type,
        effective_date,
        event_details,
        simulation_year,
        event_category,  -- Added to track enrollment method
        -- Parse enrollment-related information from events
        CASE
            WHEN event_type = 'enrollment' THEN effective_date
            ELSE NULL
        END AS new_enrollment_date,
        CASE
            WHEN event_type = 'enrollment' THEN true
            WHEN event_type = 'enrollment_change' AND LOWER(event_details) LIKE '%opt-out%' THEN false
            ELSE NULL
        END AS enrollment_status_change,
        -- Track enrollment method from event_category
        CASE
            WHEN event_type = 'enrollment' AND event_category = 'auto_enrollment' THEN 'auto'
            WHEN event_type = 'enrollment' AND event_category IN ('voluntary_enrollment', 'proactive_enrollment', 'executive_enrollment') THEN 'voluntary'
            ELSE NULL
        END AS enrollment_method,
        -- Track opt-out events
        CASE
            WHEN event_type = 'enrollment_change' AND LOWER(event_details) LIKE '%opt-out%' THEN true
            ELSE false
        END AS is_opt_out_event,
        -- Add event priority for handling multiple events per employee
        ROW_NUMBER() OVER (
            PARTITION BY employee_id, event_type
            ORDER BY effective_date DESC
        ) AS event_priority
    FROM {{ ref('int_enrollment_events') }}
    WHERE simulation_year = {{ simulation_year }}
        AND event_type IN ('enrollment', 'enrollment_change')
        AND employee_id IS NOT NULL
),

-- Consolidate current year enrollment events (latest event per type per employee)
current_year_enrollment_summary AS (
    SELECT
        employee_id,
        simulation_year,
        -- Get the latest enrollment event date
        MAX(CASE WHEN event_type = 'enrollment' AND event_priority = 1 THEN new_enrollment_date END) AS enrollment_event_date,
        -- Get enrollment method if enrolled this year
        MAX(CASE WHEN event_type = 'enrollment' AND event_priority = 1 THEN enrollment_method END) AS enrollment_method_this_year,
        -- Determine final enrollment status after all events this year
        CASE
            -- If there's an opt-out event, status is false regardless of enrollment events
            WHEN MAX(CASE WHEN event_type = 'enrollment_change' AND enrollment_status_change = false THEN 1 ELSE 0 END) = 1
                THEN false
            -- If there's an enrollment event and no opt-out, status is true
            WHEN MAX(CASE WHEN event_type = 'enrollment' THEN 1 ELSE 0 END) = 1
                THEN true
            -- No enrollment events this year
            ELSE NULL
        END AS has_enrollment_event_this_year,
        -- Track if there was an opt-out this year
        MAX(CASE WHEN is_opt_out_event = true THEN 1 ELSE 0 END) = 1 AS had_opt_out_this_year,
        -- Count of enrollment events for tracking
        COUNT(CASE WHEN event_type = 'enrollment' THEN 1 END) AS enrollment_events_count,
        COUNT(CASE WHEN event_type = 'enrollment_change' THEN 1 END) AS enrollment_change_events_count
    FROM current_year_enrollment_events
    WHERE event_priority = 1  -- Only use the latest event of each type
    GROUP BY employee_id, simulation_year
),

{% if simulation_year == start_year %}
-- Base case: First simulation year - start with baseline workforce
baseline_enrollment_state AS (
    SELECT DISTINCT
        employee_id,
        {{ simulation_year }} AS simulation_year,
        employee_enrollment_date AS baseline_enrollment_date,
        CASE WHEN employee_enrollment_date IS NOT NULL THEN true ELSE false END AS baseline_enrollment_status,
        0 AS years_since_first_enrollment,
        'baseline' AS enrollment_source
    FROM {{ ref('int_baseline_workforce') }}
    WHERE employment_status = 'active'
        AND employee_id IS NOT NULL
),

-- Combine baseline with current year events for first year
first_year_enrollment_state AS (
    SELECT
        COALESCE(bl.employee_id, ev.employee_id) AS employee_id,
        {{ simulation_year }} AS simulation_year,
        -- Determine effective enrollment date: prioritize events over baseline
        CASE
            WHEN ev.enrollment_event_date IS NOT NULL THEN ev.enrollment_event_date
            WHEN bl.baseline_enrollment_date IS NOT NULL THEN bl.baseline_enrollment_date
            ELSE NULL
        END AS enrollment_date,
        -- Determine effective enrollment status
        CASE
            WHEN ev.has_enrollment_event_this_year IS NOT NULL THEN ev.has_enrollment_event_this_year
            WHEN bl.baseline_enrollment_status IS NOT NULL THEN bl.baseline_enrollment_status
            ELSE false
        END AS enrollment_status,
        -- Calculate years since first enrollment (0 for first year)
        CASE
            WHEN ev.enrollment_event_date IS NOT NULL OR bl.baseline_enrollment_date IS NOT NULL THEN 0
            ELSE NULL
        END AS years_since_first_enrollment,
        -- Track enrollment source for debugging
        CASE
            WHEN ev.enrollment_event_date IS NOT NULL THEN 'event_' || CAST({{ simulation_year }} AS VARCHAR)
            WHEN bl.baseline_enrollment_date IS NOT NULL THEN 'baseline'
            ELSE 'none'
        END AS enrollment_source,
        -- Track enrollment method (auto vs voluntary)
        CASE
            WHEN ev.enrollment_method_this_year IS NOT NULL THEN ev.enrollment_method_this_year
            WHEN bl.baseline_enrollment_date IS NOT NULL THEN NULL  -- Census enrollments are pre-existing, not simulation decisions
            ELSE NULL
        END AS enrollment_method,
        -- Track if ever opted out (for first year, just current year)
        COALESCE(ev.had_opt_out_this_year, false) AS ever_opted_out,
        -- Track if ever enrolled then unenrolled (false for first year)
        false AS ever_unenrolled,
        -- Event counts
        COALESCE(ev.enrollment_events_count, 0) AS enrollment_events_this_year,
        COALESCE(ev.enrollment_change_events_count, 0) AS enrollment_change_events_this_year
    FROM baseline_enrollment_state bl
    FULL OUTER JOIN current_year_enrollment_summary ev ON bl.employee_id = ev.employee_id
)

{% else %}
-- Subsequent years: Get previous year's state from this same model
previous_year_enrollment_state AS (
    SELECT
        employee_id,
        simulation_year AS previous_simulation_year,
        enrollment_date AS previous_enrollment_date,
        enrollment_status AS previous_enrollment_status,
        years_since_first_enrollment AS previous_years_since_first_enrollment,
        enrollment_source AS previous_enrollment_source,
        enrollment_method AS previous_enrollment_method,
        ever_opted_out AS previous_ever_opted_out,
        ever_unenrolled AS previous_ever_unenrolled
    FROM {{ this }}
    WHERE simulation_year = {{ simulation_year - 1 }}
        AND employee_id IS NOT NULL
),

-- Get all employees who are active in current year (from workforce or events)
current_year_active_employees AS (
    SELECT DISTINCT employee_id
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ simulation_year }}
        AND employee_id IS NOT NULL

    UNION

    SELECT DISTINCT employee_id
    FROM previous_year_enrollment_state
    WHERE employee_id IS NOT NULL
),

-- Combine previous year state with current year events
subsequent_year_enrollment_state AS (
    SELECT
        COALESCE(py.employee_id, ev.employee_id, ae.employee_id) AS employee_id,
        {{ simulation_year }} AS simulation_year,
        -- Determine effective enrollment date: prioritize new events, then carry forward
        CASE
            WHEN ev.enrollment_event_date IS NOT NULL THEN ev.enrollment_event_date
            WHEN py.previous_enrollment_date IS NOT NULL THEN py.previous_enrollment_date
            ELSE NULL
        END AS enrollment_date,
        -- Determine effective enrollment status: apply current year changes or carry forward
        CASE
            WHEN ev.has_enrollment_event_this_year IS NOT NULL THEN ev.has_enrollment_event_this_year
            WHEN py.previous_enrollment_status IS NOT NULL THEN py.previous_enrollment_status
            ELSE false
        END AS enrollment_status,
        -- Calculate years since first enrollment
        CASE
            WHEN ev.enrollment_event_date IS NOT NULL THEN 0  -- New enrollment this year
            WHEN py.previous_enrollment_date IS NOT NULL THEN (py.previous_years_since_first_enrollment + 1)
            ELSE NULL
        END AS years_since_first_enrollment,
        -- Track enrollment source
        CASE
            WHEN ev.enrollment_event_date IS NOT NULL THEN 'event_' || CAST({{ simulation_year }} AS VARCHAR)
            WHEN py.previous_enrollment_source IS NOT NULL THEN py.previous_enrollment_source
            ELSE 'none'
        END AS enrollment_source,
        -- Track enrollment method: new enrollment this year or carry forward
        CASE
            WHEN ev.enrollment_method_this_year IS NOT NULL THEN ev.enrollment_method_this_year
            WHEN py.previous_enrollment_method IS NOT NULL THEN py.previous_enrollment_method
            ELSE NULL
        END AS enrollment_method,
        -- Track if ever opted out: accumulate across years
        CASE
            WHEN ev.had_opt_out_this_year = true THEN true
            WHEN py.previous_ever_opted_out = true THEN true
            ELSE false
        END AS ever_opted_out,
        -- Track if ever enrolled then unenrolled
        CASE
            -- If was enrolled previously and now not enrolled (and not due to opt-out), mark as unenrolled
            WHEN py.previous_enrollment_status = true
                AND ev.has_enrollment_event_this_year = false
                AND ev.had_opt_out_this_year = false THEN true
            -- Carry forward previous unenrollment status
            WHEN py.previous_ever_unenrolled = true THEN true
            ELSE false
        END AS ever_unenrolled,
        -- Event counts
        COALESCE(ev.enrollment_events_count, 0) AS enrollment_events_this_year,
        COALESCE(ev.enrollment_change_events_count, 0) AS enrollment_change_events_this_year
    FROM current_year_active_employees ae
    LEFT JOIN previous_year_enrollment_state py ON ae.employee_id = py.employee_id
    LEFT JOIN current_year_enrollment_summary ev ON ae.employee_id = ev.employee_id
)

{% endif %}

-- Final selection with metadata
SELECT
    employee_id,
    simulation_year,
    enrollment_date,
    enrollment_status,
    years_since_first_enrollment,
    enrollment_source,
    enrollment_method,  -- Added: track auto vs voluntary
    ever_opted_out,     -- Added: track opt-out history
    ever_unenrolled,    -- Added: track unenrollment history
    enrollment_events_this_year,
    enrollment_change_events_this_year,
    -- Add calculated fields for compatibility with existing models
    CASE WHEN enrollment_status = true THEN enrollment_date ELSE NULL END AS effective_enrollment_date,
    CASE WHEN enrollment_status = true THEN true ELSE false END AS is_enrolled,
    -- Add metadata
    CURRENT_TIMESTAMP AS created_at,
    '{{ var("scenario_id", "default") }}' AS scenario_id,
    -- Data quality validation
    CASE
        WHEN employee_id IS NULL THEN 'INVALID_EMPLOYEE_ID'
        WHEN simulation_year IS NULL THEN 'INVALID_SIMULATION_YEAR'
        WHEN enrollment_status IS NULL THEN 'INVALID_ENROLLMENT_STATUS'
        ELSE 'VALID'
    END AS data_quality_flag
FROM
{% if simulation_year == start_year %}
    first_year_enrollment_state
{% else %}
    subsequent_year_enrollment_state
{% endif %}
WHERE employee_id IS NOT NULL
    AND simulation_year = {{ simulation_year }}

{% if is_incremental() %}
    -- For incremental runs, only process current simulation year
    AND simulation_year = {{ simulation_year }}
{% endif %}

ORDER BY employee_id
