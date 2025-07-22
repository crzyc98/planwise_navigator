{{ config(materialized='table') }}

{% set simulation_year = var('simulation_year') %}
{% set start_year = var('start_year', var('simulation_year')) | int %}
{% set exp_term_rate = var('total_termination_rate', 0.12) %}

-- Generate termination events using hazard-based probability selection
-- Connects to existing termination hazard infrastructure for demographically-aware modeling
-- Follows same pattern as promotions: WHERE random_value < termination_rate

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
    FROM {{ ref('int_workforce_previous_year_v2') }}
    WHERE employment_status = 'active'
),

active_workforce AS (
    -- Use int_workforce_previous_year_v2 which handles the dependency logic properly
    -- FIXED: All employees who survived to the start of the simulation year should be treated as experienced
    -- This includes baseline workforce members hired in 2024 who are part of the Year 1 starting workforce
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_gross_compensation,
        current_age,
        current_tenure,
        level_id,
        -- FIXED: All employees in int_workforce_previous_year_v2 have survived to simulation start
        -- Therefore they should ALL be subject to experienced termination rates
        'experienced' AS employee_type
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


-- HAZARD-BASED APPROACH: Use probability-based selection following promotion pattern
-- Connect to existing hazard infrastructure for demographically-aware terminations
eligible_for_termination AS (
    SELECT
        w.*,
        h.termination_rate,
        -- Generate deterministic random number for probability comparison
        (ABS(HASH(w.employee_id)) % 1000) / 1000.0 AS random_value
    FROM workforce_with_bands w
    JOIN {{ ref('int_hazard_termination') }} h
        ON w.level_id = h.level_id
        AND w.age_band = h.age_band
        AND w.tenure_band = h.tenure_band
        AND h.year = {{ simulation_year }}
),

-- SOPHISTICATED APPROACH: Hazard-based terminations + quota gap-filling to achieve exactly 12%
final_experienced_terminations AS (
    -- Calculate exactly how many terminations we need (12% of experienced employees only)
    WITH target_calculation AS (
        SELECT ROUND(
            (SELECT COUNT(*) FROM workforce_with_bands WHERE employee_type = 'experienced') * {{ exp_term_rate }}
        ) AS target_count
    )
    SELECT
        w.employee_id,
        w.employee_ssn,
        'termination' AS event_type,
        {{ simulation_year }} AS simulation_year,
        (CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL ((ABS(HASH(w.employee_id)) % 365)) DAY) AS effective_date,
        CASE
            WHEN e.random_value IS NOT NULL AND e.random_value < e.termination_rate THEN 'hazard_termination'
            ELSE 'gap_filling_termination'
        END AS termination_reason,
        w.employee_gross_compensation AS final_compensation,
        w.current_age,
        w.current_tenure,
        w.level_id,
        w.age_band,
        w.tenure_band,
        w.employee_type,
        COALESCE(e.termination_rate, 0.0) AS termination_rate,
        COALESCE(e.random_value, (ABS(HASH(w.employee_id)) % 1000) / 1000.0) AS random_value,
        CASE
            WHEN e.random_value IS NOT NULL AND e.random_value < e.termination_rate THEN 'hazard_termination'
            ELSE 'gap_filling'
        END AS termination_type
    FROM workforce_with_bands w
    LEFT JOIN eligible_for_termination e ON w.employee_id = e.employee_id
    CROSS JOIN target_calculation
    -- FIXED: Apply only to experienced employees (previous year new hires handled separately)
    WHERE w.employee_type = 'experienced'
    QUALIFY ROW_NUMBER() OVER (
        ORDER BY
            -- Prioritize hazard-based terminations first
            CASE WHEN e.random_value IS NOT NULL AND e.random_value < e.termination_rate THEN 0 ELSE 1 END,
            COALESCE(e.random_value, (ABS(HASH(w.employee_id)) % 1000) / 1000.0)
    ) <= target_calculation.target_count
)

-- Return the hazard-based terminations
SELECT * FROM final_experienced_terminations
