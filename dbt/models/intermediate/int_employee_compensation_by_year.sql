{{ config(
    materialized='table',
    indexes=[
        {'columns': ['simulation_year'], 'type': 'btree'},
        {'columns': ['employee_id', 'simulation_year'], 'type': 'btree'}
    ],
    tags=['foundation', 'critical', 'compensation']
) }}

-- Pre-calculate employee compensation for event generation
--
-- **Purpose:**
-- Provides consistent, correct compensation data for all event generation models.
-- This eliminates timing issues and ensures proper compensation compounding.
--
-- **Data Flow:**
-- Year 1: int_baseline_workforce → int_employee_compensation_by_year
-- Year N: fct_workforce_snapshot (year N-1) → int_employee_compensation_by_year (year N)
--
-- **Usage:**
-- All event generation models (merit, promotion, termination) should reference this table
-- instead of trying to figure out the correct compensation source themselves.

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set is_first_year = (simulation_year == start_year) %}

{% if is_first_year %}
-- Year 1: Use baseline workforce compensation
SELECT
    {{ simulation_year }} AS simulation_year,
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    current_compensation AS employee_compensation,
    current_age,
    current_tenure,
    level_id,
    age_band,
    tenure_band,
    employment_status,
    'baseline_workforce' AS data_source,
    -- Additional metadata for validation
    current_compensation AS starting_year_compensation,
    current_compensation AS ending_year_compensation,  -- Will be updated after events
    FALSE AS has_compensation_events
FROM {{ ref('int_baseline_workforce') }}
WHERE employment_status = 'active'

{% else %}
-- Subsequent years: Use helper model to avoid circular dependency
-- CIRCULAR DEPENDENCY FIX: Use int_active_employees_prev_year_snapshot instead of fct_workforce_snapshot
-- This breaks the cycle: int_merit_events -> fct_workforce_snapshot -> int_employee_compensation_by_year
SELECT
    {{ simulation_year }} AS simulation_year,
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    employee_gross_compensation AS employee_compensation,  -- Use helper model's compensation field
    current_age + 1 AS current_age,  -- Increment age for new year
    current_tenure + 1 AS current_tenure,  -- Increment tenure for new year
    level_id,
    -- Recalculate age and tenure bands for the new year
    CASE
        WHEN current_age + 1 < 25 THEN '< 25'
        WHEN current_age + 1 < 35 THEN '25-34'
        WHEN current_age + 1 < 45 THEN '35-44'
        WHEN current_age + 1 < 55 THEN '45-54'
        WHEN current_age + 1 < 65 THEN '55-64'
        ELSE '65+'
    END AS age_band,
    CASE
        WHEN current_tenure + 1 < 2 THEN '< 2'
        WHEN current_tenure + 1 < 5 THEN '2-4'
        WHEN current_tenure + 1 < 10 THEN '5-9'
        WHEN current_tenure + 1 < 20 THEN '10-19'
        ELSE '20+'
    END AS tenure_band,
    employment_status,
    'previous_year_helper_model' AS data_source,
    -- Additional metadata for validation
    employee_gross_compensation AS starting_year_compensation,
    employee_gross_compensation AS ending_year_compensation,  -- Will be updated after events
    FALSE AS has_compensation_events
FROM {{ ref('int_active_employees_prev_year_snapshot') }}
WHERE employment_status = 'active'

{% endif %}
