{{ config(
    materialized='table',
    indexes=[
        {'columns': ['simulation_year', 'employee_id'], 'unique': False}
    ],
    tags=["snapshot_processing", "critical", "termination"]
) }}

WITH base_workforce AS (
    SELECT * FROM {{ ref('int_snapshot_base') }}
),

termination_events AS (
    SELECT
        simulation_year,
        TRIM(CAST(employee_id AS VARCHAR)) AS employee_id,
        effective_date,
        event_details AS termination_reason
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ var('simulation_year') }}
        AND UPPER(event_type) = 'TERMINATION'
        AND event_category IN ('experienced_termination', 'new_hire_termination')
        AND employee_id IS NOT NULL
        -- Validate effective_date is within the simulation year
        AND effective_date >= CAST(CONCAT({{ var('simulation_year') }}, '-01-01') AS DATE)
        AND effective_date <= CAST(CONCAT({{ var('simulation_year') }}, '-12-31') AS DATE)
),

-- DEBUG: Count termination events for validation
termination_event_counts AS (
    SELECT COUNT(*) AS total_termination_events
    FROM termination_events
),

-- DEBUG: Count base workforce for validation
base_workforce_counts AS (
    SELECT COUNT(*) AS total_base_employees
    FROM base_workforce
),

workforce_with_terminations AS (
    SELECT
        TRIM(CAST(base.employee_id AS VARCHAR)) AS employee_id,
        base.employee_ssn,
        base.employee_birth_date,
        base.employee_hire_date,
        base.employee_gross_compensation,
        base.current_age,
        base.current_tenure,
        base.level_id,
        base.termination_date,
        base.employment_status,
        base.simulation_year,
        base.snapshot_created_at,
        term.effective_date AS termination_event_date,
        term.termination_reason AS event_termination_reason
    FROM base_workforce base
    LEFT JOIN termination_events term
        ON TRIM(CAST(base.employee_id AS VARCHAR)) = TRIM(term.employee_id)
),

-- DEBUG: Count successful JOIN matches for validation
termination_match_counts AS (
    SELECT
        COUNT(*) AS total_employees_processed,
        COUNT(termination_event_date) AS employees_with_termination_events,
        COUNT(*) - COUNT(termination_event_date) AS employees_without_termination_events
    FROM workforce_with_terminations
),

final_result AS (
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,

        -- Apply termination logic
        CASE
            WHEN termination_event_date IS NOT NULL THEN termination_event_date
            ELSE termination_date
        END AS termination_date,

        CASE
            WHEN termination_event_date IS NOT NULL THEN 'terminated'
            ELSE employment_status
        END AS employment_status,

        -- Capture termination reason from events (preserving NULL values as per original pattern)
        CASE
            WHEN termination_event_date IS NOT NULL THEN event_termination_reason
            ELSE NULL
        END AS termination_reason,

        simulation_year,
        snapshot_created_at
    FROM workforce_with_terminations
)

-- Log debug information during model compilation
{% if var('simulation_year') is defined %}
  {% set debug_query %}
    SELECT
      (SELECT COUNT(*) FROM ({{ termination_events }}) t) as total_termination_events,
      (SELECT COUNT(*) FROM ({{ base_workforce }}) b) as total_base_employees,
      (SELECT COUNT(termination_event_date) FROM ({{ workforce_with_terminations }}) w) as employees_with_termination_events
  {% endset %}

  {% if execute %}
    {{ log("=== TERMINATION PROCESSING DEBUG (Year " ~ var('simulation_year') ~ ") ===", info=true) }}
    {{ log("Debug info will be available in compiled SQL", info=true) }}
  {% endif %}
{% endif %}

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
    termination_reason,
    simulation_year,
    snapshot_created_at
FROM final_result
