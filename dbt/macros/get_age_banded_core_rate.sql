{# Resolve a percentage-valued age schedule to a decimal core contribution rate. #}
{% macro get_age_banded_core_rate(age_col, age_schedule, flat_rate) %}
{%- if age_schedule and age_schedule | length > 0 -%}
{%- set sorted_schedule = age_schedule | sort(attribute='min_age', reverse=true) -%}
CASE
  {%- for tier in sorted_schedule %}
  WHEN {{ age_col }} >= {{ tier['min_age'] | int }}
    AND ({{ 'TRUE' if tier['max_age'] is none else age_col ~ ' < ' ~ (tier['max_age'] | int) }})
    THEN {{ tier['rate'] / 100.0 }}
  {%- endfor %}
  ELSE {{ flat_rate }}
END
{%- else -%}
{{ flat_rate }}
{%- endif -%}
{% endmacro %}
