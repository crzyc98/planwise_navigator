{{ config(materialized='table') }}

-- Year Snapshot Preparation Enhancement
-- Prepares workforce data for the current simulation year with validation

WITH previous_year_workforce AS (
    SELECT * FROM {{ ref('int_workforce_previous_year') }}
),
simulation_parameters AS (
    SELECT
        {{ var('simulation_year') }} as simulation_year,
        '{{ var('simulation_effective_date', var('simulation_year') ~ '-12-31') }}'::DATE as simulation_start_date
),
prepared_snapshot AS (
    SELECT
        w.employee_id,
        w.employee_ssn,
        w.employee_birth_date,
        w.employee_hire_date,
        w.employee_gross_compensation,
        w.current_age,
        w.current_tenure,
        w.level_id,
        w.age_band,
        w.tenure_band,
        w.employment_status,
        w.termination_date,
        w.termination_reason,
        p.simulation_year,
        p.simulation_start_date as effective_date,
        w.is_from_census,
        w.is_cold_start,
        w.last_completed_year,
        -- Cold start indicators
        w.active_employees as baseline_active_count,
        w.total_employees as baseline_total_count
    FROM previous_year_workforce w
    CROSS JOIN simulation_parameters p
    WHERE w.employment_status = 'active'
)
SELECT * FROM prepared_snapshot
