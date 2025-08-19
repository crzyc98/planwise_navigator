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

-- Read employer core contribution config from nested structure
{% set employer_core_config = var('employer_core_contribution', {}) %}
{% set core_eligibility = employer_core_config.get('eligibility', {}) %}

-- Extract eligibility parameters with defaults
{% set core_minimum_tenure_years = core_eligibility.get('minimum_tenure_years', 1) | int %}
{% set core_require_active_eoy = core_eligibility.get('require_active_at_year_end', true) %}
{% set core_minimum_hours = core_eligibility.get('minimum_hours_annual', 1000) | int %}
{% set core_allow_new_hires = core_eligibility.get('allow_new_hires', true) %}
{% set core_allow_terminated_new_hires = core_eligibility.get('allow_terminated_new_hires', false) %}
{% set core_allow_experienced_terminations = core_eligibility.get('allow_experienced_terminations', false) %}

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
        CAST(NULL AS DATE) AS termination_date
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = {{ simulation_year }}
        AND employee_id IS NOT NULL
),

-- Get new hire and termination events for the simulation year to get more accurate dates
events_data AS (
    SELECT
        employee_id,
        MAX(hire_date) AS event_hire_date,
        MAX(termination_date) AS event_termination_date
    FROM (
        SELECT employee_id,
               effective_date AS hire_date,
               CAST(NULL AS DATE) AS termination_date
        FROM {{ ref('int_hiring_events') }}
        WHERE simulation_year = {{ simulation_year }}

        UNION ALL

        SELECT employee_id,
               CAST(NULL AS DATE) AS hire_date,
               effective_date AS termination_date
        FROM {{ ref('int_termination_events') }}
        WHERE simulation_year = {{ simulation_year }}
    ) s
    GROUP BY employee_id
),

-- Flag employees classified as new-hire terminations in this simulation year
new_hire_termination_flags AS (
    SELECT
        employee_id,
        TRUE AS has_new_hire_termination
    FROM {{ ref('int_new_hire_termination_events') }}
    WHERE simulation_year = {{ simulation_year }}
    GROUP BY employee_id
),

-- Flag employees with experienced terminations (non-new-hire) in this simulation year
experienced_termination_flags AS (
    SELECT
        t.employee_id,
        TRUE AS has_experienced_termination
    FROM {{ ref('int_termination_events') }} t
    WHERE t.simulation_year = {{ simulation_year }}
      AND t.employee_id NOT IN (
          SELECT employee_id FROM {{ ref('int_new_hire_termination_events') }} WHERE simulation_year = {{ simulation_year }}
      )
    GROUP BY t.employee_id
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
    ae.current_tenure,
    ae.employee_hire_date,
    ae.termination_date,
    ed.event_hire_date,
    ed.event_termination_date,
    COALESCE(nht.has_new_hire_termination, FALSE) AS has_new_hire_termination,
    COALESCE(ext.has_experienced_termination, FALSE) AS has_experienced_termination,

    -- Identify new hires within the simulation year
    CASE
        WHEN ed.event_hire_date::DATE >= '{{ simulation_year }}-01-01'::DATE
             AND ed.event_hire_date::DATE <= '{{ simulation_year }}-12-31'::DATE
        THEN true
        WHEN ae.employee_hire_date::DATE >= '{{ simulation_year }}-01-01'::DATE
             AND ae.employee_hire_date::DATE <= '{{ simulation_year }}-12-31'::DATE
        THEN true
        ELSE false
    END AS is_new_hire_this_year,

    -- Derive end-of-year employment status using event termination when present
    CASE
        WHEN COALESCE(ed.event_termination_date::DATE, ae.termination_date::DATE) IS NOT NULL
             AND COALESCE(ed.event_termination_date::DATE, ae.termination_date::DATE) <= '{{ simulation_year }}-12-31'::DATE
        THEN 'terminated'
        ELSE 'active'
    END AS employment_status_eoy,

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
        ELSE 2080
    END AS annual_hours_worked
FROM all_employees ae
LEFT JOIN events_data ed ON ae.employee_id = ed.employee_id
LEFT JOIN new_hire_termination_flags nht ON ae.employee_id = nht.employee_id
LEFT JOIN experienced_termination_flags ext ON ae.employee_id = ext.employee_id
)

SELECT
    employee_id,
    simulation_year,
    employment_status_eoy AS employment_status,
    current_tenure,
    ROUND(annual_hours_worked, 0)::INTEGER AS annual_hours_worked,

    -- Match eligibility - original simple logic
    -- Requires active status and meets minimum hours threshold (1000)
    CASE
        WHEN employment_status_eoy = 'active' AND annual_hours_worked >= 1000 THEN TRUE
        ELSE FALSE
    END AS eligible_for_match,

    -- Core eligibility: allow configurable exceptions for new hires and their terminations
    CASE
        WHEN annual_hours_worked >= {{ core_minimum_hours }}
         AND (
              -- Meets tenure normally
              current_tenure >= {{ core_minimum_tenure_years }}
              -- or allowed as a new hire this year
              OR ({{ 'true' if core_allow_new_hires else 'false' }} AND is_new_hire_this_year)
         )
         AND (
              -- Require active at EOY unless exceptions are allowed
              {% if core_require_active_eoy %}
                  employment_status_eoy = 'active'
                  OR ({{ 'true' if core_allow_terminated_new_hires else 'false' }} AND is_new_hire_this_year AND employment_status_eoy = 'terminated')
                  OR ({{ 'true' if core_allow_experienced_terminations else 'false' }} AND NOT is_new_hire_this_year AND employment_status_eoy = 'terminated')
              {% else %}
                  TRUE
              {% endif %}
         )
         -- If not allowed, exclude employees flagged as new-hire terminations even when termination is next year
         AND (
               {% if core_allow_terminated_new_hires %}
                   TRUE
               {% else %}
                   NOT (is_new_hire_this_year AND COALESCE(has_new_hire_termination, FALSE))
               {% endif %}
         )
         -- If not allowed, exclude employees with experienced termination in the current year
         AND (
                {% if core_allow_experienced_terminations %}
                    TRUE
                {% else %}
                    NOT (NOT is_new_hire_this_year AND COALESCE(has_experienced_termination, FALSE))
                {% endif %}
         )
        THEN TRUE
        ELSE FALSE
    END AS eligible_for_core,

    -- Combined eligibility flag for convenience (uses match criteria for backward compatibility)
    CASE
        WHEN employment_status_eoy = 'active' AND annual_hours_worked >= 1000 THEN TRUE
        ELSE FALSE
    END AS eligible_for_contributions,

    -- Metadata
    'prorated_hours_with_tenure' AS eligibility_method,
    {{ core_minimum_tenure_years }} AS core_tenure_requirement,
    {{ core_minimum_hours }} AS core_hours_requirement,
    {{ core_require_active_eoy }} AS core_requires_active_eoy,
    {{ core_allow_new_hires }} AS core_allow_new_hires,
    {{ core_allow_terminated_new_hires }} AS core_allow_terminated_new_hires,
    {{ core_allow_experienced_terminations }} AS core_allow_experienced_terminations,
    CURRENT_TIMESTAMP AS created_at,
    '{{ var("scenario_id", "default") }}' AS scenario_id

FROM hours_calculation
ORDER BY employee_id
