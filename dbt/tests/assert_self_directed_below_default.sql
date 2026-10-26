-- Deliberate below-default choices survive both magnet directions and reach
-- the enrollment event unchanged, apart from the existing voluntary clamp.
{% set auto_default = var('auto_enrollment_default_deferral_rate', 0.02) %}
{% set share = below_default_share(auto_default) if var('auto_enrollment_enabled', true) else 0.0 %}

WITH choices AS (
  SELECT
    employee_id,
    simulation_year,
    event_category,
    employee_deferral_rate,
    {{ below_default_rate(auto_default,
      enrollment_behavior_draw('employee_id', 'simulation_year', '-below-default-step-')) }} AS chosen_rate
  FROM {{ ref('int_enrollment_events') }}
  WHERE event_type = 'enrollment'
    AND event_category IN ('proactive_voluntary', 'voluntary_enrollment', 'year_over_year_voluntary')
    AND {{ enrollment_behavior_draw('employee_id', 'simulation_year', '-below-default-') }} < {{ share }}
)
SELECT employee_id, simulation_year, event_category, employee_deferral_rate, chosen_rate
FROM choices
WHERE ABS(employee_deferral_rate - CASE
  WHEN event_category = 'year_over_year_voluntary' THEN chosen_rate
  ELSE GREATEST(0.01, LEAST({{ var('voluntary_max_deferral_rate', 0.15) }}, chosen_rate))
END) > 0.00000001
