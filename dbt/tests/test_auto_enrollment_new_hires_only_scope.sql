{{ config(severity='error', tags=['enrollment_validation']) }}

-- Ordinary AE follows the plan's scope (first-year hire cutoff, then new
-- hires). A configured periodic sweep deliberately includes continuing staff.
WITH parameter_rows AS (
{% if var('plan_design_parameters', none) %}
  {{ get_plan_design_parameters(var('plan_design_parameters')) }}
{% else %}
  SELECT
    '{{ var("plan_design_id", "default") }}'::VARCHAR AS plan_design_id,
    '{{ var("auto_enrollment_scope", "all_eligible_employees") }}'::VARCHAR AS auto_enrollment_scope,
    {{ var('reenrollment_sweep_enabled', false) }}::BOOLEAN AS reenrollment_sweep_enabled,
    {{ var('reenrollment_sweep_interval_years', 3) }}::INTEGER AS reenrollment_sweep_interval_years,
    {{ var('reenrollment_sweep_first_year', none) if var('reenrollment_sweep_first_year', none) is not none else 'NULL' }}::INTEGER AS reenrollment_sweep_first_year
{% endif %}
), hires AS (
  SELECT employee_id, employee_hire_date
  FROM {{ ref('int_employee_compensation_by_year') }}
  WHERE simulation_year = {{ var('simulation_year') }}
  UNION
  SELECT employee_id, effective_date::DATE AS employee_hire_date
  FROM {{ ref('int_hiring_events') }}
  WHERE simulation_year = {{ var('simulation_year') }}
)
SELECT ee.employee_id, ee.simulation_year
FROM {{ ref('int_enrollment_events') }} ee
INNER JOIN {{ ref('int_plan_design_assignment_accumulator') }} assignment
  ON ee.employee_id = assignment.employee_id
  AND ee.scenario_id = assignment.scenario_id
  AND ee.simulation_year = assignment.simulation_year
INNER JOIN parameter_rows parameters
  ON assignment.plan_design_id = parameters.plan_design_id
INNER JOIN hires ON ee.employee_id = hires.employee_id
WHERE ee.event_category = 'auto_enrollment'
  AND ee.scenario_id = '{{ var("scenario_id", "default") }}'
  AND ee.simulation_year = {{ var('simulation_year') }}
  AND parameters.auto_enrollment_scope = 'new_hires_only'
  AND NOT {{ is_eligible_for_auto_enrollment_scope('hires.employee_hire_date', 'ee.simulation_year', 'parameters.auto_enrollment_scope') }}
  AND NOT {{ is_reenrollment_sweep_year('ee.simulation_year', 'parameters.reenrollment_sweep_enabled', 'parameters.reenrollment_sweep_interval_years', 'parameters.reenrollment_sweep_first_year') }}
