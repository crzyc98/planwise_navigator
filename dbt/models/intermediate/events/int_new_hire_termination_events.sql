{{ config(materialized='table') }}

{% set simulation_year = var('simulation_year') %}

-- Generate new hire termination events
-- Refactored to use int_workforce_needs for termination targets

WITH workforce_needs AS (
    -- Get new hire termination targets from centralized workforce planning
    SELECT
        workforce_needs_id,
        scenario_id,
        simulation_year,
        expected_new_hire_terminations,
        new_hire_termination_rate
    FROM {{ ref('int_workforce_needs') }}
    WHERE simulation_year = {{ simulation_year }}
      AND scenario_id = '{{ var('scenario_id', 'default') }}'
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
    WHERE simulation_year = {{ simulation_year }}
),

-- DETERMINISTIC APPROACH: Calculate exact target and select top N
new_hire_terminations AS (
    SELECT
        nh.*,
        -- Generate consistent random value for ordering
        ((CAST(SUBSTR(nh.employee_id, -2) AS INTEGER) * 17 +
          CAST(SUBSTR(nh.employee_id, -4, 2) AS INTEGER) * 31 +
          {{ simulation_year }} * 7) % 100) / 100.0 AS random_value,
        wn.new_hire_termination_rate AS termination_rate
    FROM new_hires_cohort nh
    CROSS JOIN workforce_needs wn
),

-- Use exact target from workforce needs
target_calculation AS (
    SELECT expected_new_hire_terminations AS target_terminations
    FROM workforce_needs
),

filtered_terminations AS (
    SELECT nh.*
    FROM new_hire_terminations nh
    CROSS JOIN target_calculation tc
    QUALIFY ROW_NUMBER() OVER (ORDER BY nh.random_value) <= tc.target_terminations
)

SELECT
    ft.employee_id,
    ft.employee_ssn,
    'termination' AS event_type,
    {{ simulation_year }} AS simulation_year,
    -- New hire terminations occur 30-270 days after their actual hire date (1-9 months)
    -- Use last digits of employee_id for date variation, but relative to hire date
    -- Ensure termination date doesn't exceed simulation year + 3 months for business realism
    LEAST(
        ft.hire_date + INTERVAL (30 + (CAST(SUBSTR(ft.employee_id, -3) AS INTEGER) % 240)) DAY,
        CAST('{{ simulation_year + 1 }}-03-31' AS DATE)
    ) AS effective_date,
    'new_hire_departure' AS termination_reason,
    ft.compensation_amount AS final_compensation,
    ft.employee_age AS current_age,
    0 AS current_tenure, -- New hires have minimal tenure
    ft.level_id,
    -- Age/tenure bands for new hires
    CASE
        WHEN ft.employee_age < 25 THEN '< 25'
        WHEN ft.employee_age < 35 THEN '25-34'
        WHEN ft.employee_age < 45 THEN '35-44'
        WHEN ft.employee_age < 55 THEN '45-54'
        WHEN ft.employee_age < 65 THEN '55-64'
        ELSE '65+'
    END AS age_band,
    '< 2' AS tenure_band, -- All new hires are in lowest tenure band
    ft.termination_rate,
    ft.random_value,
    'new_hire_termination' AS termination_type,
    -- Add reference to workforce planning
    wn.workforce_needs_id,
    wn.scenario_id
FROM filtered_terminations ft
CROSS JOIN workforce_needs wn
ORDER BY ft.employee_id
