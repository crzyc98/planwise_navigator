{{ config(
    materialized='table',
    indexes=[
        {'columns': ['simulation_year'], 'type': 'btree'},
        {'columns': ['employee_id', 'simulation_year'], 'type': 'btree'}
    ],
    tags=['foundation', 'critical', 'event_generation']
) }}

-- Dependency-free model that provides active employees for event generation
--
-- **Purpose:**
-- Provides active employee data for event generation without circular dependencies.
-- This model acts as the single source of truth for all event models.
--
-- **Circular Dependency Solution:**
-- This model breaks the circular dependency by:
-- 1. For year 1 (start year): Use int_baseline_workforce directly
-- 2. For subsequent years: Use int_active_employees_prev_year_snapshot which uses
--    dynamic relation references to get previous year's completed workforce snapshot
-- 3. Never references fct_yearly_events or current year data
--
-- **Data Flow for Year 1:**
-- int_baseline_workforce → int_workforce_active_for_events → event models → fct_yearly_events → fct_workforce_snapshot
--
-- **Data Flow for Year N (N > 1):**
-- fct_workforce_snapshot (year N-1) → int_active_employees_prev_year_snapshot → int_workforce_active_for_events → event models → fct_yearly_events → fct_workforce_snapshot (year N)

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set is_first_year = (simulation_year == start_year) %}

{% if is_first_year %}
-- Year 1: Use baseline workforce directly
SELECT
    {{ simulation_year }} AS simulation_year,
    employee_id,
    employee_ssn,
    employee_hire_date AS hire_date,
    current_compensation AS employee_gross_compensation,
    current_age,
    current_tenure,
    level_id AS job_level,
    age_band,
    tenure_band,
    employment_status
FROM {{ ref('int_baseline_workforce') }}
WHERE employment_status = 'active'

{% else %}
-- Subsequent years: Use previous year's completed workforce snapshot
SELECT
    {{ simulation_year }} AS simulation_year,
    employee_id,
    employee_ssn,
    employee_hire_date AS hire_date,
    employee_gross_compensation,
    current_age,
    current_tenure,
    level_id AS job_level,
    age_band,
    tenure_band,
    employment_status
FROM {{ ref('int_active_employees_prev_year_snapshot') }}
WHERE simulation_year = {{ simulation_year }}
  AND employment_status = 'active'

{% endif %}
