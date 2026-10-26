{% macro aip_initial_membership(mode, census_opt_out) -%}
  {%- if mode == 'participant_elected' -%}
    {{ exceptions.raise_compiler_error('participant_elected arrives in #985') }}
  {%- elif mode != 'automatic' -%}
    {{ exceptions.raise_compiler_error('Unsupported deferral_escalation_mode: ' ~ mode) }}
  {%- endif -%}
  {%- if not var('deferral_escalation_enabled', true) -%}
    FALSE
  {%- else -%}
    NOT COALESCE({{ census_opt_out }}, FALSE)
  {%- endif -%}
{%- endmacro %}
