{{ config(
    severity='error',
    tags=['data_quality', 'employer_contributions', 'eligibility', 'service_credit']
) }}

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set scenario_id = var('scenario_id', 'default') %}
{% set plan_design_id = var('plan_design_id', 'default') %}

/*
  An eligible employee must meet the configured completed-service threshold.
  The sole service exception is the corresponding explicit hire-year setting.
*/
WITH scoped_eligibility AS (
  SELECT
    eligibility.*,
    EXTRACT(YEAR FROM workforce.employee_hire_date) = eligibility.simulation_year
      AS is_hire_year
  FROM {{ ref('int_employer_eligibility') }} eligibility
  INNER JOIN {{ ref('int_workforce_state_accumulator') }} workforce
    ON eligibility.employee_id = workforce.employee_id
   AND eligibility.simulation_year = workforce.simulation_year
   AND workforce.scenario_id = '{{ scenario_id }}'
   AND workforce.plan_design_id = '{{ plan_design_id }}'
  WHERE eligibility.scenario_id = '{{ scenario_id }}'
    AND eligibility.simulation_year = {{ simulation_year }}
),

violations AS (
  SELECT
    'core' AS contribution_type,
    employee_id,
    simulation_year,
    current_tenure,
    core_tenure_requirement AS tenure_requirement,
    core_allow_new_hires AS allow_new_hires,
    is_hire_year
  FROM scoped_eligibility
  WHERE eligible_for_core
    AND current_tenure < core_tenure_requirement
    AND NOT (core_allow_new_hires AND is_hire_year)

  UNION ALL

  SELECT
    'match' AS contribution_type,
    employee_id,
    simulation_year,
    current_tenure,
    match_tenure_requirement AS tenure_requirement,
    match_allow_new_hires AS allow_new_hires,
    is_hire_year
  FROM scoped_eligibility
  WHERE match_apply_eligibility
    AND eligible_for_match
    AND current_tenure < match_tenure_requirement
    AND NOT (match_allow_new_hires AND is_hire_year)
)

SELECT *
FROM violations
