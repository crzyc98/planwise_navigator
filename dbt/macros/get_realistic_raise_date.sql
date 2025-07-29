{%- macro get_realistic_raise_date(employee_id_column, simulation_year) -%}
  {%- set methodology = var('raise_timing_methodology', 'legacy') -%}
  
  {%- if methodology == 'calendar_driven' -%}
    {# Use new calendar-driven approach for predictable dates #}
    {{ get_calendar_event_date('raise', simulation_year, employee_id_column) }}
  {%- elif methodology == 'realistic' -%}
    {# Use existing realistic timing calculation #}
    {{ realistic_timing_calculation(employee_id_column, simulation_year) }}
  {%- else -%}
    {# Use legacy timing calculation #}
    {{ legacy_timing_calculation(employee_id_column, simulation_year) }}
  {%- endif -%}
{%- endmacro -%}
