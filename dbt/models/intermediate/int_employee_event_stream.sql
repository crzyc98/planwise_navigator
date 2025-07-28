{{ config(
    materialized='table',
    indexes=[
        {'columns': ['employee_id', 'effective_date', 'event_priority']},
        {'columns': ['simulation_year']}
    ],
    tags=['foundation', 'critical', 'event_stream']
) }}

{#
  Chronological event stream for all employees in the simulation.

  This model creates a single, time-ordered stream of every event that
  changes an employee's state during the simulation period.

  Event Priority (for same-day ordering):
  - 1: Termination (highest priority - should be processed last)
  - 2: Promotion
  - 3: Merit/Raise
  - 9: Initial State (lowest priority - processed first)

  Each row represents a point-in-time change for an employee.
#}

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH simulation_parameters AS (
    SELECT {{ simulation_year }} AS current_year
),

-- Initial states for all employees (t₀)
initial_state_events AS (
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_gross_compensation AS compensation_amount,
        current_age,
        current_tenure,
        level_id,
        termination_date,
        employment_status,
        simulation_year,
        initial_state_date AS effective_date,
        'initial_state' AS event_type,
        'INITIAL' AS event_category,
        employee_source AS event_details,
        9 AS event_priority, -- Lowest priority for initial states
        'Initial employee state at start of simulation' AS event_description
    FROM {{ ref('int_employees_with_initial_state') }}
    WHERE simulation_year = {{ simulation_year }}
),

-- All simulation events from fct_yearly_events
simulation_events AS (
    SELECT
        CAST(employee_id AS VARCHAR) AS employee_id,
        employee_ssn,
        -- Birth date calculation for hire events, NULL for others
        CASE
            WHEN UPPER(event_type) = 'HIRE' AND employee_age IS NOT NULL THEN
                -- More accurate birth date calculation accounting for leap years
                effective_date - INTERVAL (employee_age * 365.25) DAY
            ELSE NULL
        END AS employee_birth_date,
        -- Hire date for hire events, NULL for others
        CASE
            WHEN UPPER(event_type) = 'HIRE' THEN effective_date
            ELSE NULL
        END AS employee_hire_date,
        compensation_amount,
        level_id,
        -- Termination date for termination events only
        CASE
            WHEN UPPER(event_type) = 'TERMINATION' THEN effective_date
            ELSE NULL
        END AS termination_date,
        -- Employment status based on event type
        CASE
            WHEN UPPER(event_type) = 'TERMINATION' THEN 'terminated'
            WHEN UPPER(event_type) = 'HIRE' THEN 'active'
            ELSE NULL -- Let final state calculation determine this
        END AS employment_status,
        simulation_year,
        effective_date,
        LOWER(event_type) AS event_type,
        event_category,
        event_details,
        -- Event priority for same-day ordering
        CASE
            WHEN UPPER(event_type) = 'TERMINATION' THEN 1  -- Highest priority
            WHEN UPPER(event_type) = 'PROMOTION' THEN 2
            WHEN UPPER(event_type) = 'RAISE' THEN 3
            WHEN UPPER(event_type) = 'HIRE' THEN 4
            ELSE 5
        END AS event_priority,
        CONCAT(UPPER(event_type), ' event for employee ', employee_id) AS event_description
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ simulation_year }}
        AND employee_id IS NOT NULL
        AND effective_date IS NOT NULL
),

-- Combined event stream
combined_event_stream AS (
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        compensation_amount,
        level_id,
        termination_date,
        employment_status,
        simulation_year,
        effective_date,
        event_type,
        event_category,
        event_details,
        event_priority,
        event_description
    FROM initial_state_events

    UNION ALL

    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        compensation_amount,
        level_id,
        termination_date,
        employment_status,
        simulation_year,
        effective_date,
        event_type,
        event_category,
        event_details,
        event_priority,
        event_description
    FROM simulation_events
),

-- Propagate birth/hire dates and employment status through event timeline
date_and_status_propagated_stream AS (
    SELECT
        employee_id,
        employee_ssn,
        -- Propagate birth date through timeline
        COALESCE(
            employee_birth_date,
            FIRST_VALUE(employee_birth_date IGNORE NULLS) OVER (
                PARTITION BY employee_id
                ORDER BY effective_date ASC, event_priority ASC
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            )
        ) AS employee_birth_date,
        -- Propagate hire date through timeline
        COALESCE(
            employee_hire_date,
            FIRST_VALUE(employee_hire_date IGNORE NULLS) OVER (
                PARTITION BY employee_id
                ORDER BY effective_date ASC, event_priority ASC
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            )
        ) AS employee_hire_date,
        compensation_amount,
        level_id,
        termination_date,
        simulation_year,
        effective_date,
        event_type,
        event_category,
        event_details,
        event_priority,
        event_description,
        -- Propagate employment status through timeline
        COALESCE(
            employment_status,
            LAST_VALUE(employment_status IGNORE NULLS) OVER (
                PARTITION BY employee_id
                ORDER BY effective_date ASC, event_priority ASC
                ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
            ),
            'active'
        ) AS employment_status
    FROM combined_event_stream
),

-- Calculate age and tenure dynamically based on event date
temporal_calculations AS (
    SELECT
        *,
        -- Calculate age at the time of each event
        CASE
            WHEN employee_birth_date IS NOT NULL THEN
                DATE_DIFF('year', employee_birth_date, effective_date)
            ELSE NULL
        END AS calculated_age,
        -- Calculate tenure at the time of each event
        CASE
            WHEN employee_hire_date IS NOT NULL AND employee_hire_date <= effective_date THEN
                DATE_DIFF('year', employee_hire_date, effective_date)
            WHEN event_type = 'hire' THEN 0  -- New hires start with 0 tenure
            ELSE NULL
        END AS calculated_tenure
    FROM date_and_status_propagated_stream
),

-- Final event stream with sequence numbers
final_event_stream AS (
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        compensation_amount,
        calculated_age AS current_age,      -- Use dynamically calculated age
        calculated_tenure AS current_tenure, -- Use dynamically calculated tenure
        level_id,
        termination_date,
        employment_status,
        simulation_year,
        effective_date,
        event_type,
        event_category,
        event_details,
        event_priority,
        event_description,
        -- Sequence number for event ordering
        ROW_NUMBER() OVER (
            PARTITION BY employee_id
            ORDER BY effective_date ASC, event_priority ASC
        ) AS event_sequence,
        -- Total events per employee
        COUNT(*) OVER (PARTITION BY employee_id) AS total_events_per_employee,
        CURRENT_TIMESTAMP AS stream_created_at
    FROM temporal_calculations
)

SELECT * FROM final_event_stream
ORDER BY employee_id, effective_date, event_priority
