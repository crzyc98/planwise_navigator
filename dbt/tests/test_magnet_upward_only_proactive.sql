-- Issue #984: the magnet may lower rates only inside the AE downward window.
-- Compare the unbounded magnet output so the final voluntary cap is irrelevant.
SELECT employee_id, raw_deferral_rate, match_optimized_rate
FROM {{ ref('int_proactive_voluntary_enrollment') }}
WHERE match_optimized_rate < raw_deferral_rate
  {% if var('auto_enrollment_enabled', true) and below_default_share(var('auto_enrollment_default_deferral_rate', 0.02)) > 0 %}
  AND {{ enrollment_behavior_draw('employee_id', 'simulation_year', '-below-default-') }}
    >= {{ below_default_share(var('auto_enrollment_default_deferral_rate', 0.02)) }}
  {% endif %}
  {% if var('auto_enrollment_enabled', true) and var('enrollment_match_magnet_downward_enabled', false) and var('enrollment_match_magnet_enabled', true) %}
  AND NOT (
    match_optimized_rate = match_magnet_ceiling
    AND match_magnet_ceiling > 0
    AND match_magnet_ceiling < {{ var('auto_enrollment_default_deferral_rate', 0.02) }}
    AND raw_deferral_rate <= {{ var('auto_enrollment_default_deferral_rate', 0.02) }}
  )
  {% endif %}
