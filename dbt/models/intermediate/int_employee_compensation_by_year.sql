{{ config(
    materialized='incremental',
    unique_key="employee_id || '_' || simulation_year",
    incremental_strategy='delete+insert',
    on_schema_change='ignore',
    tags=['FOUNDATION', 'critical', 'compensation']
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
-- Year 1: Union baseline workforce with new hires to fix circular dependency
-- Baseline workforce (existing employees)
WITH y1_union AS (
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
    employee_enrollment_date,  -- Include enrollment status for enrollment events
    CASE WHEN employee_enrollment_date IS NOT NULL THEN true ELSE false END AS is_enrolled_flag,  -- Backup enrollment status flag
    'baseline_workforce' AS data_source,
    -- Additional metadata for validation
    current_compensation AS starting_year_compensation,
    current_compensation AS ending_year_compensation,  -- Will be updated after events
    FALSE AS has_compensation_events
FROM {{ ref('int_baseline_workforce') }}
WHERE employment_status = 'active'

UNION ALL

-- New hires for Year 1 (from staging model to break circular dependency)
-- SUPPORTING FIX (E055): Only include new hires that don't exist in baseline workforce
-- This prevents compensation source conflicts for employees
SELECT
    simulation_year,
    employee_id,
    employee_ssn,
    employee_birth_date,
    employee_hire_date,
    employee_compensation,
    current_age,
    current_tenure,
    level_id,
    age_band,
    tenure_band,
    employment_status,
    employee_enrollment_date,
    is_enrolled_flag,
    data_source,
    starting_year_compensation,
    ending_year_compensation,
    has_compensation_events
FROM {{ ref('int_new_hire_compensation_staging') }}
-- Ensure we don't duplicate employees who might exist in baseline workforce
WHERE employee_id NOT IN (
    SELECT employee_id
    FROM {{ ref('int_baseline_workforce') }}
    WHERE employment_status = 'active'
)
)

-- Ensure one row per employee in year 1
SELECT * FROM (
  SELECT y1_union.*, ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY data_source DESC) AS rn
  FROM y1_union
) dedup
WHERE rn = 1

{% else %}
-- Subsequent years: Use helper model to avoid circular dependency
-- CIRCULAR DEPENDENCY FIX: Use int_active_employees_prev_year_snapshot instead of fct_workforce_snapshot
-- This breaks the cycle: int_merit_events -> fct_workforce_snapshot -> int_employee_compensation_by_year
WITH base AS (
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
    employee_enrollment_date,  -- Preserve enrollment status from previous year
    is_enrolled_flag,  -- Backup enrollment status flag
    'previous_year_helper_model' AS data_source,
    -- Additional metadata for validation
    employee_gross_compensation AS starting_year_compensation,
    employee_gross_compensation AS ending_year_compensation,  -- Will be updated after events
    FALSE AS has_compensation_events
FROM {{ ref('int_active_employees_prev_year_snapshot') }}
WHERE employment_status = 'active'
)

SELECT *
FROM (
  SELECT b.*, ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY employee_id) AS rn
  FROM base b
)
WHERE rn = 1

{% endif %}

{% if is_incremental() %}
-- Note: This model generates compensation data for the current simulation_year only
-- Data is filtered by the simulation_year variable in the CTEs above
{% endif %}
