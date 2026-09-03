{% macro match_family_arm(family) %}
  {% if family == 'deferral_based' %}
    {{ match_family_arm_deferral_based() }}
  {% elif family == 'graded_by_service' %}
    {{ match_family_arm_graded_by_service() }}
  {% elif family == 'tenure_graded' %}
    {{ match_family_arm_tenure_graded() }}
  {% elif family == 'points_based' %}
    {{ match_family_arm_points_based() }}
  {% else %}
    {{ exceptions.raise_compiler_error('unsupported match family: ' ~ family) }}
  {% endif %}
{% endmacro %}
