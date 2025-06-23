{{ config(materialized='table') }}

{% set simulation_year = var('simulation_year') %}

-- Epic 11.5 Step g: Generate new hire termination events
-- Applies new_hire_termination_rate to gross hire cohort from current year

WITH simulation_config AS (
    SELECT
        {{ simulation_year }} AS current_year,
        {{ var('new_hire_termination_rate', 0.1) }} AS new_hire_termination_rate
),

-- Get all new hires for current simulation year
new_hires_cohort AS (
    SELECT
        employee_id,
        employee_ssn,
        level_id,
        compensation_amount,
        employee_age,
        birth_date,
        effective_date AS hire_date
    FROM {{ ref('int_hiring_events') }}
    WHERE simulation_year = (SELECT current_year FROM simulation_config)
),

-- Apply new hire termination rate
new_hire_terminations AS (
    SELECT
        nh.*,
        -- Simple deterministic "random" value based on employee_id length
        (LENGTH(nh.employee_id) % 10) / 10.0 AS random_value,
        (SELECT new_hire_termination_rate FROM simulation_config) AS termination_rate
    FROM new_hires_cohort nh
),

-- Filter based on termination probability
filtered_terminations AS (
    SELECT *
    FROM new_hire_terminations
    WHERE random_value < termination_rate
)

SELECT
    employee_id,
    employee_ssn,
    'termination' AS event_type,
    (SELECT current_year FROM simulation_config) AS simulation_year,
    -- New hire terminations occur later in the year (after 3-9 months)
    -- Use deterministic date based on employee_id length
    (CAST('{{ simulation_year }}-04-01' AS DATE) + INTERVAL ((LENGTH(employee_id) % 275)) DAY) AS effective_date,
    'new_hire_departure' AS termination_reason,
    compensation_amount AS final_compensation,
    employee_age AS current_age,
    0 AS current_tenure, -- New hires have minimal tenure
    level_id,
    -- Age/tenure bands for new hires
    CASE
        WHEN employee_age < 25 THEN '< 25'
        WHEN employee_age < 35 THEN '25-34'
        WHEN employee_age < 45 THEN '35-44'
        WHEN employee_age < 55 THEN '45-54'
        WHEN employee_age < 65 THEN '55-64'
        ELSE '65+'
    END AS age_band,
    '< 2' AS tenure_band, -- All new hires are in lowest tenure band
    termination_rate,
    random_value,
    'new_hire_termination' AS termination_type
FROM filtered_terminations
ORDER BY employee_id
