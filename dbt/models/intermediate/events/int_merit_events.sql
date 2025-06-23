{{ config(
    materialized='table'
) }}

{% set simulation_year = var('simulation_year') %}

-- Generate merit increase events for active workforce based on hazard rates
-- Applies merit raise percentages from dim_hazard_table to eligible employees

WITH active_workforce AS (
    -- Use int_previous_year_workforce which handles the dependency logic properly
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_gross_compensation,
        current_age,
        current_tenure,
        level_id
    FROM {{ ref('int_previous_year_workforce') }}
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

-- Simple approach: Apply merit to all eligible workforce (no exclusions for now)
eligible_for_merit AS (
    SELECT
        w.*,
        h.merit_raise
    FROM workforce_with_bands w
    JOIN {{ ref('dim_hazard_table') }} h
        ON w.level_id = h.level_id
        AND w.age_band = h.age_band
        AND w.tenure_band = h.tenure_band
        AND h.year = {{ simulation_year }}
    WHERE
        -- Simple merit eligibility rules
        current_tenure >= 1 -- At least 1 year of service
        AND merit_raise > 0 -- Must have a merit increase defined
),

-- Apply COLA adjustments from seed data
cola_adjustments AS (
    SELECT
        year,
        cola_rate
    FROM {{ ref('config_cola_by_year') }}
    WHERE year = {{ simulation_year }}
)

SELECT
    e.employee_id,
    e.employee_ssn,
    'merit_increase' AS event_type,
    {{ simulation_year }} AS simulation_year,
    -- Merit increases typically effective January 1st or July 1st
    -- Use deterministic pattern based on employee_id length instead of HASH
    CASE
        WHEN (LENGTH(e.employee_id) % 2) = 0 THEN CAST({{ simulation_year }} || '-01-01' AS DATE)
        ELSE CAST({{ simulation_year }} || '-07-01' AS DATE)
    END AS effective_date,
    e.employee_gross_compensation AS previous_salary,
    -- Apply merit increase plus COLA
    ROUND(
        e.employee_gross_compensation *
        (1 + e.merit_raise + COALESCE(c.cola_rate, 0.03)), -- Default 3% COLA if not specified
        2
    ) AS new_salary,
    e.merit_raise AS merit_percentage,
    COALESCE(c.cola_rate, 0.03) AS cola_percentage,
    e.current_age,
    e.current_tenure,
    e.level_id,
    e.age_band,
    e.tenure_band
FROM eligible_for_merit e
CROSS JOIN cola_adjustments c
