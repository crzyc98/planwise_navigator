{{ config(
    materialized='table',
    indexes=[
        {'columns': ['employee_id', 'simulation_year'], 'unique': true}
    ],
    tags=['employer_contributions', 'core_contributions', 'mvp']
) }}

/*
  Employer Core Contributions Model - Story S039-01

  Calculates employer core (non-elective) contribution amounts
  based on simple business rules:
  - 2% flat rate of eligible compensation for eligible employees
  - 0% for ineligible employees

  This is an MVP implementation focusing on simplicity and correctness.
  Future enhancements may include:
  - Level-based contribution rates
  - Parameter-driven rates via comp_levers
  - Service-based vesting schedules
  - Pro-ration for partial year employment
*/

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH employee_compensation AS (
    -- Get current year compensation for all employees
    SELECT
        employee_id,
        simulation_year,
        employee_compensation,
        employment_status
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = {{ simulation_year }}
        AND employee_id IS NOT NULL
),

-- Always-on proration source for employer contributions
workforce_proration AS (
    -- Use contribution model as the single source for prorated base
    SELECT
        employee_id,
        simulation_year,
        total_contribution_base_compensation AS prorated_annual_compensation,
        employment_status
    FROM {{ ref('int_employee_contributions') }}
    WHERE simulation_year = {{ simulation_year }}
),

eligibility_check AS (
    -- Get eligibility status for all employees
    SELECT
        employee_id,
        simulation_year,
        eligible_for_core,
        eligible_for_contributions,
        annual_hours_worked
    FROM {{ ref('int_employer_eligibility') }}
    WHERE simulation_year = {{ simulation_year }}
        AND employee_id IS NOT NULL
)

SELECT
    comp.employee_id,
    comp.simulation_year,
    COALESCE(wf.prorated_annual_compensation, comp.employee_compensation) AS eligible_compensation,
    COALESCE(wf.employment_status, comp.employment_status) AS employment_status,
    elig.eligible_for_core,
    elig.annual_hours_worked,

    -- Core contribution calculation
    -- MVP: Simple 2% flat rate for eligible employees
    CASE
        WHEN elig.eligible_for_core = TRUE AND COALESCE(wf.prorated_annual_compensation, comp.employee_compensation) > 0
        THEN ROUND(COALESCE(wf.prorated_annual_compensation, comp.employee_compensation) * 0.02, 2)
        ELSE 0.00
    END AS employer_core_amount,

    -- Contribution rate for reference
    CASE
        WHEN elig.eligible_for_core = TRUE
        THEN 0.02
        ELSE 0.00
    END AS core_contribution_rate,

    -- Metadata
    'mvp_flat_rate' AS contribution_method,
    0.02 AS standard_core_rate,
    CURRENT_TIMESTAMP AS created_at,
    '{{ var("scenario_id", "default") }}' AS scenario_id,
    '{{ var("parameter_scenario_id", "default") }}' AS parameter_scenario_id

FROM employee_compensation comp
LEFT JOIN workforce_proration wf
    ON comp.employee_id = wf.employee_id AND comp.simulation_year = wf.simulation_year
LEFT JOIN eligibility_check elig
    ON comp.employee_id = elig.employee_id
    AND comp.simulation_year = elig.simulation_year
ORDER BY comp.employee_id
