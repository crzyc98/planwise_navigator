{{ config(materialized='table') }}

{% set simulation_year = var('simulation_year') %}

-- Generate promotion events for eligible workforce based on hazard probabilities
-- Applies promotion rates from dim_hazard_table to current workforce

WITH active_workforce AS (
    -- Use int_workforce_previous_year which handles the dependency logic properly
    SELECT
        employee_id,
        employee_ssn,
        employee_birth_date,
        employee_hire_date,
        employee_gross_compensation,
        current_age,
        current_tenure,
        level_id
    FROM {{ ref('int_workforce_previous_year') }}
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

eligible_for_promotion AS (
    SELECT
        w.*,
        h.promotion_rate,
        -- Generate random number for probability comparison
        (ABS(HASH(w.employee_id)) % 1000) / 1000.0 AS random_value
    FROM workforce_with_bands w
    JOIN {{ ref('dim_hazard_table') }} h
        ON w.level_id = h.level_id
        AND w.age_band = h.age_band
        AND w.tenure_band = h.tenure_band
        AND h.year = {{ simulation_year }}
    WHERE
        -- Business rules for promotion eligibility
        current_tenure >= 1 -- Minimum 1 year tenure
        AND w.level_id < 5 -- Can't promote beyond max level
        AND current_age < 65 -- No promotions near retirement
)

SELECT
    employee_id,
    employee_ssn,
    'promotion' AS event_type,
    {{ simulation_year }} AS simulation_year,
    (CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL ((ABS(HASH(employee_id)) % 365)) DAY) AS effective_date, -- Deterministic date in year
    level_id AS from_level,
    level_id + 1 AS to_level, -- Single level promotion
    employee_gross_compensation AS previous_salary,
    -- Calculate new salary with promotion increase (15-25% increase)
    ROUND(employee_gross_compensation * (1.15 + ((ABS(HASH(employee_id)) % 100) / 1000.0)), 2) AS new_salary,
    current_age,
    current_tenure,
    age_band,
    tenure_band,
    promotion_rate,
    random_value
FROM eligible_for_promotion
WHERE random_value < promotion_rate -- Apply probability threshold
