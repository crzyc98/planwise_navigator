{{ config(
    materialized='table',
    indexes=[
        {'columns': ['simulation_year', 'employee_id'], 'unique': False}
    ],
    tags=["snapshot_processing", "critical", "merit"]
) }}

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH simulation_parameters AS (
    SELECT {{ simulation_year }} AS current_year
),

workforce_after_promotions AS (
    SELECT * FROM {{ ref('int_snapshot_promotion') }}
),

-- Get all events for current simulation year
current_year_events AS (
    SELECT *
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = (SELECT current_year FROM simulation_parameters)
),

workforce_with_merit AS (
    SELECT
        w.employee_id,
        w.employee_ssn,
        w.employee_birth_date,
        w.employee_hire_date,
        CASE
            WHEN r.employee_id IS NOT NULL THEN r.compensation_amount
            ELSE w.employee_gross_compensation
        END AS employee_gross_compensation,
        w.current_age,
        w.current_tenure,
        w.level_id,
        w.termination_date,
        w.employment_status,
        w.termination_reason,
        w.simulation_year,
        w.snapshot_created_at
    FROM workforce_after_promotions w
    LEFT JOIN current_year_events r
        ON CAST(w.employee_id AS VARCHAR) = CAST(r.employee_id AS VARCHAR)
        AND r.event_type = 'raise'
)

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
FROM workforce_with_merit
