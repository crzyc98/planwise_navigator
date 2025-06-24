{{ config(materialized='table') }}

{% set simulation_year = var('simulation_year') %}
{% set start_year = var('start_year', var('simulation_year')) | int %}
{% set exp_term_rate = var('total_termination_rate', 0.12) %}

-- Generate termination events implementing Epic 11.5 precise sequence:
-- 1. Process experienced employee terminations first
-- 2. Calculate additional terminations needed for total_termination_rate
-- 3. Later: new hire terminations will be handled separately after hiring

WITH simulation_config AS (
    SELECT
        {{ simulation_year }} AS current_year,
        {{ exp_term_rate }} AS experienced_termination_rate,
        {{ var('target_growth_rate', 0.03) }} AS target_growth_rate
),

incumbent_pool AS (
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        employment_status,
        termination_date
    FROM {{ ref('int_workforce_previous_year') }}
    WHERE employment_status = 'active'
),

active_workforce AS (
    -- Use int_workforce_previous_year which handles the dependency logic properly
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        -- Flag new hires vs experienced employees (hired in previous year vs earlier)
        CASE
            WHEN EXTRACT(YEAR FROM employee_hire_date) = (SELECT current_year - 1 FROM simulation_config)
            THEN 'new_hire'
            ELSE 'experienced'
        END AS employee_type
    FROM incumbent_pool
    WHERE employment_status = 'active'
),

workforce_with_bands AS (
    SELECT
        *,
        -- Age bands for hazard lookup
        CASE
            WHEN current_age < 25 THEN '< 25'
            WHEN current_age < 35 THEN '25-34'
            WHEN current_age < 45 THEN '35-44'
            WHEN current_age < 55 THEN '45-54'
            WHEN current_age < 65 THEN '55-64'
            ELSE '65+'
        END AS age_band,
        -- Tenure bands for hazard lookup
        CASE
            WHEN current_tenure < 2 THEN '< 2'
            WHEN current_tenure < 5 THEN '2-4'
            WHEN current_tenure < 10 THEN '5-9'
            WHEN current_tenure < 20 THEN '10-19'
            ELSE '20+'
        END AS tenure_band
    FROM active_workforce
),

-- Get experienced population (hired before current simulation year)
-- NOTE: This CTE is kept for potential future use but terminations now apply to entire active_workforce
experienced_population AS (
    SELECT w.*
    FROM workforce_with_bands w
    WHERE w.employee_type = 'experienced'
),

-- Calculate termination quota - apply to entire active workforce to ensure consistent terminations
quota AS (
    SELECT CEIL(COUNT(*) * {{ exp_term_rate }}) AS target_terminations
    FROM active_workforce -- CHANGE: calculate quota from all active workforce
),

-- REVISED APPROACH: Quota-first termination selection
-- Apply to entire active workforce to ensure consistent terminations
final_experienced_terminations AS (
    SELECT
        aw.employee_id,
        aw.employee_ssn,
        'termination' AS event_type,
        sc.current_year AS simulation_year,
        -- Assign a random effective date within the year
        (CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL ((ABS(HASH(aw.employee_id)) % 365)) DAY) AS effective_date,
        'quota_termination' AS termination_reason, -- Default reason
        aw.employee_gross_compensation AS final_compensation,
        aw.current_age,
        aw.current_tenure,
        aw.level_id,
        -- Add age and tenure bands for consistency
        CASE
            WHEN aw.current_age < 25 THEN '< 25'
            WHEN aw.current_age < 35 THEN '25-34'
            WHEN aw.current_age < 45 THEN '35-44'
            WHEN aw.current_age < 55 THEN '45-54'
            WHEN aw.current_age < 65 THEN '55-64'
            ELSE '65+'
        END AS age_band,
        CASE
            WHEN aw.current_tenure < 2 THEN '< 2'
            WHEN aw.current_tenure < 5 THEN '2-4'
            WHEN aw.current_tenure < 10 THEN '5-9'
            WHEN aw.current_tenure < 20 THEN '10-19'
            ELSE '20+'
        END AS tenure_band,
        aw.employee_type,
        -- Assign the overall rate for logging/analysis
        {{ exp_term_rate }} AS termination_rate,
        (ABS(HASH(aw.employee_id)) % 1000) / 1000.0 AS random_value,
        'experienced_termination' AS termination_type
    FROM active_workforce aw
    CROSS JOIN simulation_config sc
    -- Select exactly the 'target_terminations' based on a deterministic "random" order
    QUALIFY ROW_NUMBER() OVER (ORDER BY ABS(HASH(aw.employee_id)) ASC) <= (SELECT target_terminations FROM quota)
)

-- Return the quota-based terminations
SELECT * FROM final_experienced_terminations
