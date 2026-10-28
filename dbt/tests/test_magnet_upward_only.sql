-- Issue #984: the magnet may lower rates only inside the AE downward window.
-- Compare the unbounded magnet output so the final voluntary cap is irrelevant.
WITH parameter_rows AS (
{% if var('plan_design_parameters', none) %}
  {{ get_plan_design_parameters(var('plan_design_parameters')) }}
{% else %}
  SELECT
    '{{ var('plan_design_id', 'default') }}'::VARCHAR AS plan_design_id,
    {{ var('auto_enrollment_default_deferral_rate', 0.02) }}::DECIMAL(10,6) AS auto_enrollment_default_deferral_rate
{% endif %}
)
SELECT employee_id, raw_deferral_rate, match_optimized_rate
FROM {{ ref('int_voluntary_enrollment_decision') }}
INNER JOIN parameter_rows USING (plan_design_id)
WHERE match_optimized_rate < raw_deferral_rate
  {% if var('auto_enrollment_enabled', true) %}
  AND {{ enrollment_behavior_draw('employee_id', 'simulation_year', '-below-default-') }}
    >= {{ below_default_share('auto_enrollment_default_deferral_rate') }}
  {% endif %}
  {% if var('auto_enrollment_enabled', true) and var('enrollment_match_magnet_downward_enabled', true) and var('enrollment_match_magnet_enabled', true) %}
  AND NOT (
    match_optimized_rate = match_magnet_ceiling
    AND match_magnet_ceiling > 0
    AND match_magnet_ceiling < auto_enrollment_default_deferral_rate
    AND raw_deferral_rate <= auto_enrollment_default_deferral_rate
  )
  {% endif %}
