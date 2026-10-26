-- Deliberate below-default choices survive both magnet directions and reach
-- the enrollment event unchanged, apart from the existing voluntary clamp.
{% set auto_default = 'auto_enrollment_default_deferral_rate' %}
{% set share = below_default_share(auto_default) if var('auto_enrollment_enabled', true) else 0.0 %}

WITH parameter_rows AS (
{% if var('plan_design_parameters', none) %}
  {{ get_plan_design_parameters(var('plan_design_parameters')) }}
{% else %}
  SELECT
    '{{ var('plan_design_id', 'default') }}'::VARCHAR AS plan_design_id,
    {{ var('auto_enrollment_default_deferral_rate', 0.02) }}::DECIMAL(10,6) AS auto_enrollment_default_deferral_rate
{% endif %}
),
choices AS (
  SELECT
    employee_id,
    simulation_year,
    event_category,
    employee_deferral_rate,
    {{ below_default_rate(auto_default,
      enrollment_behavior_draw('employee_id', 'simulation_year', '-below-default-step-')) }} AS chosen_rate
  FROM {{ ref('int_enrollment_events') }} events
  INNER JOIN {{ ref('int_plan_design_assignment_accumulator') }} assignment
    USING (scenario_id, employee_id, simulation_year)
  INNER JOIN parameter_rows parameters USING (plan_design_id)
  WHERE event_type = 'enrollment'
    AND event_category IN ('proactive_voluntary', 'voluntary_enrollment', 'year_over_year_voluntary')
    AND {{ enrollment_behavior_draw('employee_id', 'simulation_year', '-below-default-') }} < {{ share }}
)
SELECT employee_id, simulation_year, event_category, employee_deferral_rate, chosen_rate
FROM choices
WHERE ABS(employee_deferral_rate - GREATEST(0.01, LEAST({{ var('voluntary_max_deferral_rate', 0.15) }}, chosen_rate))) > 0.00000001
