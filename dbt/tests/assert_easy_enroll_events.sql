{{ config(severity='error', tags=['enrollment', 'easy_enroll']) }}

-- Package selection must preserve a self-directed winning channel and never
-- create an auto enrollment or an AE opt-out for the same employee-year.
SELECT e.employee_id, e.simulation_year
FROM {{ ref('fct_yearly_events') }} e
WHERE e.event_category = 'easy_enroll'
  AND (
    NOT {{ var('easy_enroll_enabled', true) }}
    OR e.event_type != 'enrollment'
    OR REGEXP_EXTRACT(e.event_details, 'original_channel=([^;]+)', 1) NOT IN (
      'voluntary_enrollment', 'proactive_voluntary',
      'proactive_voluntary_enrollment', 'year_over_year_voluntary'
    )
    OR e.employee_deferral_rate IS NULL
    OR e.employee_deferral_rate NOT IN (
      {% for package in var('easy_enroll_packages', [
        {'rate': 0.06}, {'rate': 0.08}, {'rate': 0.10}
      ]) %}
      {{ package.rate }}{% if not loop.last %},{% endif %}
      {% endfor %}
    )
    OR EXISTS (
      SELECT 1
      FROM {{ ref('fct_yearly_events') }} other
      WHERE other.scenario_id = e.scenario_id
        AND other.employee_id = e.employee_id
        AND other.simulation_year = e.simulation_year
        AND (other.event_category = 'auto_enrollment'
          OR other.event_type = 'enrollment_change')
    )
  )

{% set channel_share = var('easy_enroll_channel_share_with_auto_enrollment', 0.57)
  if var('auto_enrollment_enabled', true)
  else var('easy_enroll_channel_share_without_auto_enrollment', 0.45) %}
{% if var('easy_enroll_enabled', true) and channel_share > 0 %}
UNION ALL

-- Inspect the source population too, so losing every EE selection cannot pass.
SELECT MIN(e.employee_id) AS employee_id, e.simulation_year
FROM {{ ref('fct_yearly_events') }} e
WHERE e.simulation_year = {{ var('simulation_year') }}
  AND e.event_type = 'enrollment'
GROUP BY e.scenario_id, e.simulation_year
HAVING COUNT(*) FILTER (WHERE e.event_category IN (
    'voluntary_enrollment', 'proactive_voluntary',
    'proactive_voluntary_enrollment', 'year_over_year_voluntary'
  )) > 0
  AND COUNT(*) FILTER (WHERE e.event_category = 'easy_enroll') = 0
{% endif %}
