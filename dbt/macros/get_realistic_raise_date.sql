{%- macro get_realistic_raise_date(employee_id_column, simulation_year) -%}
  {%- if var('raise_timing_methodology', 'legacy') == 'realistic' -%}
    {{ realistic_timing_calculation(employee_id_column, simulation_year) }}
  {%- else -%}
    {{ legacy_timing_calculation(employee_id_column, simulation_year) }}
  {%- endif -%}
{%- endmacro -%}
