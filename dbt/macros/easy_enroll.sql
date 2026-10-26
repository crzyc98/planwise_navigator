{# Apply only to the winning self-directed enrollment, after channel deduplication.
   AE enablement is currently run-global. Per-design parameters resolve scope,
   window and default rate, but do not define a separate AE enable switch. #}
{% macro easy_enroll_selected(category, employee_id, simulation_year) -%}
(
  {{ category }} IN ('voluntary_enrollment', 'proactive_voluntary',
    'proactive_voluntary_enrollment', 'year_over_year_voluntary')
  AND {{ enrollment_behavior_draw(employee_id, simulation_year, '-easy-enroll-channel-') }}
    < {{ var('easy_enroll_channel_share_with_auto_enrollment', 0.57)
      if var('auto_enrollment_enabled', true)
      else var('easy_enroll_channel_share_without_auto_enrollment', 0.45) }}
)
{%- endmacro %}

{% macro easy_enroll_package_rate(employee_id, simulation_year) -%}
  {%- set packages = var('easy_enroll_packages', [
    {'rate': 0.06, 'share': 0.30}, {'rate': 0.08, 'share': 0.50},
    {'rate': 0.10, 'share': 0.20}
  ]) -%}
  {%- set ns = namespace(cumulative=0.0) -%}
CASE
  {%- for package in packages %}
    {%- set ns.cumulative = ns.cumulative + package.share %}
  WHEN {{ enrollment_behavior_draw(employee_id, simulation_year, '-easy-enroll-package-') }}
    < {{ ns.cumulative }} THEN {{ package.rate }}
  {%- endfor %}
  ELSE {{ packages[-1].rate }}
END
{%- endmacro %}

{# Enrollment history is immutable and survives year boundaries and plan transfers.
   Event generation reads intermediate enrollments; state reads published facts. #}
{% macro easy_enroll_member(relation, employee_id, simulation_year, scenario_id) -%}
EXISTS (
  SELECT 1
  FROM {{ relation }} ee
  WHERE ee.employee_id = {{ employee_id }}
    AND ee.scenario_id = {{ scenario_id }}
    AND ee.simulation_year <= {{ simulation_year }}
    AND ee.event_type = 'enrollment'
    AND ee.event_category = 'easy_enroll'
)
{%- endmacro %}
