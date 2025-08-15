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

SELECT
    employee_id,
    {{ simulation_year }} AS simulation_year,
    employment_status,

    -- MVP: Simple hours worked assumption
    -- Active employees work standard 2080 hours (40 hours/week * 52 weeks)
    CASE
        WHEN employment_status = 'active' THEN 2080
        ELSE 0
    END AS annual_hours_worked,

    -- Eligibility determination
    -- Requires active status and meets minimum hours threshold (1000)
    CASE
        WHEN employment_status = 'active' AND 2080 >= 1000 THEN TRUE
        ELSE FALSE
    END AS eligible_for_match,

    CASE
        WHEN employment_status = 'active' AND 2080 >= 1000 THEN TRUE
        ELSE FALSE
    END AS eligible_for_core,

    -- Combined eligibility flag for convenience
    CASE
        WHEN employment_status = 'active' AND 2080 >= 1000 THEN TRUE
        ELSE FALSE
    END AS eligible_for_contributions,

    -- Metadata
    'mvp_simple_eligibility' AS eligibility_method,
    CURRENT_TIMESTAMP AS created_at,
    '{{ var("scenario_id", "default") }}' AS scenario_id

FROM {{ ref('int_baseline_workforce') }}
WHERE simulation_year = {{ simulation_year }}
    AND employee_id IS NOT NULL
ORDER BY employee_id
