{% macro new_hire_salary_index() -%}
  {%- set rate = var('new_hire_salary_growth_rate', 0.0) | float -%}
  {%- if rate != 0 -%}
    * POWER(1 + {{ rate }}, {{ var('simulation_year') }} - {{ var('start_year', 2025) }})
  {%- endif -%}
{%- endmacro %}
