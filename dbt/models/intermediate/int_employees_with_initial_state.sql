{{ config(
    materialized='table',
    indexes=[
        {'columns': ['employee_id']},
        {'columns': ['simulation_year']}
    ],
    tags=['foundation', 'critical', 'event_stream']
) }}

{#
  Unified employee list with initial state for event-stream processing.

  This model creates a master list of every unique employee that existed
  at any point during the simulation, with their initial state (t₀).

  Sources:
  1. Baseline employees from int_snapshot_base (existing workforce at start of year)
  2. New hires from fct_yearly_events (employees entering during the year)

  Each employee gets their initial state, which serves as the starting point
  for the event timeline in int_employee_event_stream.
#}

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH simulation_parameters AS (
    SELECT {{ simulation_year }} AS current_year
),

-- Baseline employees (existing workforce at start of simulation year)
baseline_employees AS (
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        termination_date,
        employment_status,
        simulation_year,
        'baseline' AS employee_source,
        -- Initial state timestamp (start of simulation year)
        CAST(CONCAT({{ simulation_year }}, '-01-01 00:00:00') AS TIMESTAMP) AS initial_state_date
    FROM {{ ref('int_snapshot_base') }}
    WHERE simulation_year = {{ simulation_year }}
),

-- New hires from events (employees entering during the simulation year)
new_hire_employees AS (
    SELECT
        CAST(employee_id AS VARCHAR) AS employee_id,
        employee_ssn,
        -- Calculate birth date from age (approximate)
        CAST(CONCAT({{ simulation_year }}, '-01-01') AS DATE) - INTERVAL (employee_age * 365) DAY AS employee_birth_date,
        effective_date AS employee_hire_date,
        compensation_amount AS employee_gross_compensation,
        employee_age AS current_age,
        0 AS current_tenure, -- New hires start with 0 tenure
        level_id,
        NULL::DATE AS termination_date, -- Will be set by termination events if applicable
        'active' AS employment_status, -- New hires start active
        {{ simulation_year }} AS simulation_year,
        'new_hire' AS employee_source,
        effective_date AS initial_state_date
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ simulation_year }}
        AND UPPER(event_type) = 'HIRE'
        AND employee_id IS NOT NULL
),

-- Unified employee list with initial state
unified_employees AS (
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        termination_date,
        employment_status,
        simulation_year,
        employee_source,
        initial_state_date
    FROM baseline_employees

    UNION ALL

    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        termination_date,
        employment_status,
        simulation_year,
        employee_source,
        initial_state_date
    FROM new_hire_employees
),

-- Final result with unique employees (in case of duplicates)
final_employees AS (
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        termination_date,
        employment_status,
        simulation_year,
        employee_source,
        initial_state_date,
        CURRENT_TIMESTAMP AS snapshot_created_at
    FROM unified_employees
    -- Remove potential duplicates (shouldn't happen, but safety check)
    QUALIFY ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY
        CASE WHEN employee_source = 'baseline' THEN 1 ELSE 2 END,
        initial_state_date
    ) = 1
)

SELECT * FROM final_employees
