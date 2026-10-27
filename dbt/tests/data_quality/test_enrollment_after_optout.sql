{{ config(severity='error', tags=['data_quality', 'enrollment_validation', 'opt_out']) }}

-- Employee elections remain allowed. Automatic re-enrollment after ANY prior
-- opt-out is allowed only in an enabled sweep year for the employee's plan.
-- Looking for the latest opt-out before each election also catches employees
-- who opt out again after an invalid re-enrollment.
WITH parameter_rows AS (
{% if var('plan_design_parameters', none) %}
  {{ get_plan_design_parameters(var('plan_design_parameters')) }}
{% else %}
  SELECT
    '{{ var("plan_design_id", "default") }}'::VARCHAR AS plan_design_id,
    {{ var('reenrollment_sweep_enabled', false) }}::BOOLEAN AS reenrollment_sweep_enabled,
    {{ var('reenrollment_sweep_interval_years', 3) }}::INTEGER AS reenrollment_sweep_interval_years,
    {{ var('reenrollment_sweep_first_year', none) if var('reenrollment_sweep_first_year', none) is not none else 'NULL' }}::INTEGER AS reenrollment_sweep_first_year
{% endif %}
), enrollments AS (
  SELECT
    ee.employee_id,
    ee.scenario_id,
    ee.simulation_year,
    ee.effective_date,
    CASE WHEN ee.event_category = 'easy_enroll'
      THEN REGEXP_EXTRACT(ee.event_details, 'original_channel=([^;]+)', 1)
      ELSE ee.event_category END AS event_category,
    MAX(oo.effective_date) AS opt_out_date
  FROM {{ ref('fct_yearly_events') }} ee
  INNER JOIN {{ ref('fct_yearly_events') }} oo
    ON ee.employee_id = oo.employee_id
    AND ee.scenario_id = oo.scenario_id
    AND oo.event_type = 'enrollment_change'
    AND LOWER(oo.event_details) LIKE '%opt-out%'
    AND oo.effective_date < ee.effective_date
  WHERE ee.event_type = 'enrollment'
    AND ee.simulation_year = {{ var('simulation_year') }}
    AND ee.scenario_id = '{{ var("scenario_id", "default") }}'
  GROUP BY ALL
)
SELECT
  ee.employee_id,
  ee.simulation_year AS enrollment_year,
  ee.effective_date AS enrollment_date,
  ee.opt_out_date,
  ee.event_category
FROM enrollments ee
LEFT JOIN {{ ref('int_plan_design_assignment_accumulator') }} assignment
  ON ee.employee_id = assignment.employee_id
  AND ee.scenario_id = assignment.scenario_id
  AND ee.simulation_year = assignment.simulation_year
LEFT JOIN parameter_rows parameters
  ON assignment.plan_design_id = parameters.plan_design_id
WHERE ee.event_category NOT IN ('voluntary_enrollment', 'proactive_voluntary', 'proactive_voluntary_enrollment')
  AND NOT COALESCE((ee.event_category = 'auto_enrollment'
    AND {{ var('auto_enrollment_enabled', true) }}
    AND {{ is_reenrollment_sweep_year('ee.simulation_year', 'parameters.reenrollment_sweep_enabled', 'parameters.reenrollment_sweep_interval_years', 'parameters.reenrollment_sweep_first_year') }}), false)
