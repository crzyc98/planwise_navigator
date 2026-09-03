{% macro core_family_rate(family) %}
  {% if family == 'flat' %}
    {{ core_family_rate_flat() }}
  {% elif family == 'graded_by_service' %}
    {{ core_family_rate_graded_by_service() }}
  {% elif family == 'points_based' %}
    {{ core_family_rate_points_based() }}
  {% elif family == 'age_banded' %}
    {{ core_family_rate_age_banded() }}
  {% else %}
    {{ exceptions.raise_compiler_error('unsupported core family: ' ~ family) }}
  {% endif %}
{% endmacro %}
