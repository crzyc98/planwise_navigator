{{ config(
    severity='error',
    tags=['data_quality', 'employer_contributions', 'eligibility', 'service_credit']
) }}

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set scenario_id = var('scenario_id', 'default') %}
{% set plan_design_id = var('plan_design_id', 'default') %}

/*
  Eligibility must copy the current build year's authoritative workforce
  service exactly. Any missing workforce row or unequal value is a violation.
*/
WITH scoped_workforce AS (
  SELECT
    employee_id,
    simulation_year,
    current_tenure
  FROM {{ ref('int_workforce_state_accumulator') }}
  WHERE scenario_id = '{{ scenario_id }}'
    AND plan_design_id = '{{ plan_design_id }}'
    AND simulation_year = {{ simulation_year }}
),

scoped_eligibility AS (
  SELECT
    employee_id,
    simulation_year,
    current_tenure,
    scenario_id
  FROM {{ ref('int_employer_eligibility') }}
  WHERE scenario_id = '{{ scenario_id }}'
    AND simulation_year = {{ simulation_year }}
)

SELECT
  eligibility.scenario_id,
  '{{ plan_design_id }}' AS plan_design_id,
  eligibility.employee_id,
  eligibility.simulation_year,
  eligibility.current_tenure AS eligibility_current_tenure,
  workforce.current_tenure AS workforce_current_tenure
FROM scoped_eligibility eligibility
LEFT JOIN scoped_workforce workforce
  ON eligibility.employee_id = workforce.employee_id
 AND eligibility.simulation_year = workforce.simulation_year
WHERE workforce.employee_id IS NULL
   OR eligibility.current_tenure IS DISTINCT FROM workforce.current_tenure
