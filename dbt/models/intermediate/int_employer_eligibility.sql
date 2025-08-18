{{ config(
    materialized='table',
    indexes=[
        {'columns': ['employee_id', 'simulation_year'], 'unique': true}
    ],
    tags=['employer_contributions', 'eligibility', 'foundation']
) }}

/*
  Employer Contribution Eligibility Model - Story S039-01

  Determines eligibility for employer contributions (both match and core)
  based on simple business rules:
  - Active employment status required
  - Assumes 2080 hours worked for active employees (standard full-time)
  - 1000 hour threshold for eligibility

  This is an MVP implementation focusing on simplicity and correctness.
  Future enhancements may include:
  - Actual hours worked tracking
  - Part-time employee logic
  - Service-based eligibility rules
*/

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set core_minimum_tenure_years = var('core_minimum_tenure_years', 1) | int %}
{% set core_require_active_eoy = var('core_require_active_eoy', true) %}
{% set core_minimum_hours = var('core_minimum_hours', 1000) | int %}

-- IMPORTANT: Use per-year compensation snapshot as the base population
-- Using int_baseline_workforce limited eligibility to the first year only.
-- Switching to int_employee_compensation_by_year ensures all active employees
-- (continuous and new hires) are present for every simulation_year.
WITH baseline_data AS (
    SELECT
        employee_id,
        employment_status,
        current_tenure,
        employee_hire_date,
        termination_date
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = {{ simulation_year }}
        AND employee_id IS NOT NULL
),

-- Get new hire and termination events for the simulation year to get more accurate dates
events_data AS (
    SELECT
        employee_id,
        MAX(CASE WHEN event_type = 'hire' THEN effective_date END) AS event_hire_date,
        MAX(CASE WHEN event_type = 'termination' THEN effective_date END) AS event_termination_date
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ simulation_year }}
        AND event_type IN ('hire', 'termination')
    GROUP BY employee_id
),

-- Get newly hired employees from yearly events (not in baseline workforce)
new_hires_data AS (
    SELECT
        ye.employee_id,
        'active' AS employment_status,
        0.0 AS current_tenure,  -- New hires start with 0 tenure
        ye.effective_date AS employee_hire_date,
        NULL AS termination_date
    FROM {{ ref('fct_yearly_events') }} ye
    WHERE ye.simulation_year = {{ simulation_year }}
        AND ye.event_type = 'hire'
        AND ye.employee_id IS NOT NULL
        -- Only include if not already in baseline workforce
        AND ye.employee_id NOT IN (
            SELECT employee_id
            FROM baseline_data
        )
),

-- Combine baseline workforce with new hires
all_employees AS (
    SELECT * FROM baseline_data
    UNION ALL
    SELECT * FROM new_hires_data
),

hours_calculation AS (
SELECT
    ae.employee_id,
    {{ simulation_year }} AS simulation_year,
    ae.employment_status,
    ae.current_tenure,
    ae.employee_hire_date,
    ae.termination_date,
    ed.event_hire_date,
    ed.event_termination_date,

    -- Calculate prorated annual hours based on actual employment period
    CASE
        -- New hire in simulation year (use event hire date if available)
        WHEN COALESCE(ed.event_hire_date::DATE, ae.employee_hire_date::DATE) >= '{{ simulation_year }}-01-01'::DATE
             AND COALESCE(ed.event_termination_date::DATE, ae.termination_date::DATE) IS NULL THEN
            -- New hire, still active: prorate from hire date to year-end
            GREATEST(0,
                DATEDIFF('day',
                    COALESCE(ed.event_hire_date::DATE, ae.employee_hire_date::DATE),
                    '{{ simulation_year }}-12-31'::DATE
                ) + 1
            ) * (2080.0 / 365.0)

        -- Terminated during simulation year
        WHEN COALESCE(ed.event_termination_date::DATE, ae.termination_date::DATE) IS NOT NULL
             AND COALESCE(ed.event_termination_date::DATE, ae.termination_date::DATE) <= '{{ simulation_year }}-12-31'::DATE THEN
            -- Terminated: prorate from year start (or hire date if later) to termination
            GREATEST(0,
                DATEDIFF('day',
                    GREATEST(
                        COALESCE(ed.event_hire_date::DATE, ae.employee_hire_date::DATE, '{{ simulation_year }}-01-01'::DATE),
                        '{{ simulation_year }}-01-01'::DATE
                    ),
                    COALESCE(ed.event_termination_date::DATE, ae.termination_date::DATE)
                ) + 1
            ) * (2080.0 / 365.0)

        -- Full year active employee
        WHEN ae.employment_status = 'active' THEN 2080

        -- All other cases (inactive, etc.)
        ELSE 0
    END AS annual_hours_worked
FROM all_employees ae
LEFT JOIN events_data ed ON ae.employee_id = ed.employee_id
)

SELECT
    employee_id,
    simulation_year,
    employment_status,
    current_tenure,
    ROUND(annual_hours_worked, 0)::INTEGER AS annual_hours_worked,

    -- Match eligibility - original simple logic
    -- Requires active status and meets minimum hours threshold (1000)
    CASE
        WHEN employment_status = 'active' AND annual_hours_worked >= 1000 THEN TRUE
        ELSE FALSE
    END AS eligible_for_match,

    -- Core contribution eligibility - enhanced with tenure and year-end requirements
    CASE
        WHEN employment_status = 'active'
            AND annual_hours_worked >= {{ core_minimum_hours }}
            AND current_tenure >= {{ core_minimum_tenure_years }}
            {% if core_require_active_eoy %}
            AND employment_status = 'active'  -- Must be active at year-end
            {% endif %}
        THEN TRUE
        ELSE FALSE
    END AS eligible_for_core,

    -- Combined eligibility flag for convenience (uses match criteria for backward compatibility)
    CASE
        WHEN employment_status = 'active' AND annual_hours_worked >= 1000 THEN TRUE
        ELSE FALSE
    END AS eligible_for_contributions,

    -- Metadata
    'prorated_hours_with_tenure' AS eligibility_method,
    {{ core_minimum_tenure_years }} AS core_tenure_requirement,
    {{ core_minimum_hours }} AS core_hours_requirement,
    {{ core_require_active_eoy }} AS core_requires_active_eoy,
    CURRENT_TIMESTAMP AS created_at,
    '{{ var("scenario_id", "default") }}' AS scenario_id

FROM hours_calculation
ORDER BY employee_id
