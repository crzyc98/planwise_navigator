{{ config(
    materialized='table',
    indexes=[
        {'columns': ['simulation_year', 'employee_id'], 'unique': False}
    ],
    tags=["snapshot_processing", "critical", "promotion"]
) }}

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH workforce_after_terminations AS (
    SELECT * FROM {{ ref('int_snapshot_termination') }}
),

promotion_events AS (
    SELECT
        simulation_year,
        CAST(employee_id AS VARCHAR) AS employee_id,
        level_id, -- Contains the target level for promotion
        compensation_amount
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ var('simulation_year') }}
        AND event_type = 'promotion'
        AND employee_id IS NOT NULL
),

workforce_with_promotions AS (
    SELECT
        w.employee_id,
        w.employee_ssn,
        w.employee_birth_date,
        w.employee_hire_date,
        CASE
            WHEN p.employee_id IS NOT NULL THEN p.compensation_amount
            ELSE w.employee_gross_compensation
        END AS employee_gross_compensation,
        w.current_age,
        w.current_tenure,
        CASE
            WHEN p.employee_id IS NOT NULL THEN p.level_id
            ELSE w.level_id
        END AS level_id,
        w.termination_date,
        w.employment_status,
        w.termination_reason,
        w.simulation_year,
        w.snapshot_created_at
    FROM workforce_after_terminations w
    LEFT JOIN promotion_events p
        ON CAST(w.employee_id AS VARCHAR) = p.employee_id
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
FROM workforce_with_promotions
