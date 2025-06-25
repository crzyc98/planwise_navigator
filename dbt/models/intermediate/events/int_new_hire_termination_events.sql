{{ config(materialized='table') }}

{% set simulation_year = var('simulation_year') %}

-- Epic 11.5 Step g: Generate new hire termination events
-- Applies new_hire_termination_rate to gross hire cohort from current year

WITH simulation_config AS (
    SELECT
        {{ simulation_year }} AS current_year,
        {{ var('new_hire_termination_rate', 0.25) }} AS new_hire_termination_rate
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

-- DETERMINISTIC APPROACH: Calculate exact target and select top N
new_hire_terminations AS (
    SELECT
        nh.*,
        -- Generate consistent random value for ordering
        ((CAST(SUBSTR(nh.employee_id, -2) AS INTEGER) * 17 +
          CAST(SUBSTR(nh.employee_id, -4, 2) AS INTEGER) * 31 +
          sc.current_year * 7) % 100) / 100.0 AS random_value,
        sc.new_hire_termination_rate AS termination_rate
    FROM new_hires_cohort nh
    CROSS JOIN simulation_config sc
),

-- Calculate exact target and select deterministically
target_calculation AS (
    SELECT ROUND(COUNT(*) * (SELECT new_hire_termination_rate FROM simulation_config)) AS target_terminations
    FROM new_hires_cohort
),

filtered_terminations AS (
    SELECT nh.*
    FROM new_hire_terminations nh
    CROSS JOIN target_calculation tc
    QUALIFY ROW_NUMBER() OVER (ORDER BY nh.random_value) <= tc.target_terminations
)

SELECT
    employee_id,
    employee_ssn,
    'termination' AS event_type,
    (SELECT current_year FROM simulation_config) AS simulation_year,
    -- New hire terminations occur 3-9 months after start of year (spread throughout year)
    -- Use last digits of employee_id for date variation (90-275 days = ~3-9 months)
    (CAST('{{ simulation_year }}-01-01' AS DATE) + INTERVAL (90 + (CAST(SUBSTR(employee_id, -3) AS INTEGER) % 185)) DAY) AS effective_date,
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
