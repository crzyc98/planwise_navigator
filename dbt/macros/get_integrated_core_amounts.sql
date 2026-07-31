{# Resolve an integrated core level and its separately rounded contribution pieces. #}
{% macro get_integrated_core_amounts(recognized_compensation, ss_wage_base, base_rate, level_mode, level_value, disparity_rate) %}
  {% if level_mode == 'percent_of_ss_wage_base' %}
    {% set integration_level = "CAST(ROUND(" ~ ss_wage_base ~ " * " ~ level_value ~ " / 100.0, 0) AS INTEGER)" %}
  {% elif level_mode == 'fixed_dollar' %}
    {% set integration_level = "CAST(ROUND(" ~ level_value ~ ", 0) AS INTEGER)" %}
  {% else %}
    {% set integration_level = ss_wage_base %}
  {% endif %}

  {{ integration_level }} AS integration_level_applied,
  GREATEST(0, {{ recognized_compensation }} - {{ integration_level }})
    AS excess_compensation,
  ROUND({{ base_rate }} * {{ recognized_compensation }}, 2) AS base_core_amount,
  ROUND(
    {{ disparity_rate }}
    * GREATEST(0, {{ recognized_compensation }} - {{ integration_level }}),
    2
  ) AS disparity_core_amount
{% endmacro %}
