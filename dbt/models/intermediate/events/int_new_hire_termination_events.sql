{{ config(
  materialized='table',
  tags=['EVENT_GENERATION', 'E068A_EPHEMERAL']
) }}

{% set simulation_year = var('simulation_year') %}

-- Generate new hire termination events
-- Refactored to use int_workforce_needs for termination targets
--
-- EPIC E057 FIX: Updated termination date logic to prevent invalid dates:
-- 1. Termination dates are constrained to simulation year (no 2026 dates for 2025 simulation)
-- 2. Termination dates must be at least 1 day after hire date
-- 3. Employees with late hire dates that would require termination beyond year-end are excluded
-- 4. Uses deterministic employee_id-based logic to ensure reproducible event sourcing

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

-- Get all new hires for current simulation year with in-year termination window
-- E079: Fixed circular dependency by reading from int_hiring_events instead of fct_yearly_events
-- This eliminates the circular dependency: int_new_hire_termination_events -> fct_yearly_events -> int_new_hire_termination_events
eligible_new_hires AS (
    SELECT
        nh.employee_id,
        nh.employee_ssn,
        nh.level_id,
        nh.compensation_amount,
        nh.employee_age,
        nh.effective_date AS hire_date,
        CAST('{{ simulation_year }}-12-31' AS DATE) AS year_end,
        -- Days between hire and year end
        DATEDIFF('day', nh.effective_date, CAST('{{ simulation_year }}-12-31' AS DATE)) AS days_until_year_end
    FROM {{ ref('int_hiring_events') }} nh
    WHERE nh.simulation_year = {{ simulation_year }}
),

-- Compute a guaranteed in-year candidate termination date when possible
eligible_terminations AS (
    SELECT
        e.*,
        CASE
            WHEN e.days_until_year_end >= 1 THEN
                e.hire_date
                + CAST(
                    CAST(
                      1 + (CAST(SUBSTR(e.employee_id, -3) AS INTEGER) % LEAST(240, e.days_until_year_end))
                      AS VARCHAR
                    ) || ' days' AS INTERVAL
                  )
            ELSE NULL
        END AS candidate_termination_date
    FROM eligible_new_hires e
),

-- Filter to valid candidates (in-year termination possible)
valid_candidates AS (
    SELECT
        et.*
    FROM eligible_terminations et
    WHERE et.candidate_termination_date IS NOT NULL
      AND et.candidate_termination_date > et.hire_date
      AND et.candidate_termination_date <= et.year_end
),

-- Assign deterministic random for selection and attach rate
ranked_candidates AS (
    SELECT
        vc.*,
        -- Deterministic random for ordering
        ((CAST(SUBSTR(vc.employee_id, -2) AS INTEGER) * 17 +
          CAST(SUBSTR(vc.employee_id, -4, 2) AS INTEGER) * 31 +
          {{ simulation_year }} * 7) % 100) / 100.0 AS random_value,
        wn.new_hire_termination_rate AS termination_rate
    FROM valid_candidates vc
    CROSS JOIN workforce_needs wn
),

-- Select exactly the target number of terminations from valid candidates
selected_terminations AS (
    SELECT
        rc.*,
        rc.candidate_termination_date AS effective_date
    FROM ranked_candidates rc
    CROSS JOIN (SELECT expected_new_hire_terminations AS target_terminations FROM workforce_needs) tc
    QUALIFY ROW_NUMBER() OVER (ORDER BY rc.random_value) <= tc.target_terminations
)

SELECT
    st.employee_id,
    st.employee_ssn,
    'termination' AS event_type,
    {{ simulation_year }} AS simulation_year,
    st.effective_date,
    'new_hire_departure' AS termination_reason,
    st.compensation_amount AS final_compensation,
    st.employee_age AS current_age,
    0 AS current_tenure, -- New hires have minimal tenure
    st.level_id,
    -- Age/tenure bands for new hires
    CASE
        WHEN st.employee_age < 25 THEN '< 25'
        WHEN st.employee_age < 35 THEN '25-34'
        WHEN st.employee_age < 45 THEN '35-44'
        WHEN st.employee_age < 55 THEN '45-54'
        WHEN st.employee_age < 65 THEN '55-64'
        ELSE '65+'
    END AS age_band,
    '< 2' AS tenure_band, -- All new hires are in lowest tenure band
    st.termination_rate,
    st.random_value,
    'new_hire_termination' AS event_category,  -- E021 FIX: Renamed from termination_type for consistency
    -- Add reference to workforce planning
    wn.workforce_needs_id,
    wn.scenario_id
FROM selected_terminations st
CROSS JOIN workforce_needs wn
ORDER BY st.employee_id
