{% macro aip_initial_membership(mode, census_opt_out, employee_id) -%}
  {%- if mode not in ['automatic', 'participant_elected'] -%}
    {{ exceptions.raise_compiler_error('Unsupported deferral_escalation_mode: ' ~ mode) }}
  {%- endif -%}
  {%- if not var('deferral_escalation_enabled', true) -%}
    FALSE
  {%- elif mode == 'participant_elected' -%}
    (
      NOT COALESCE({{ census_opt_out }}, FALSE)
      -- No simulation year: membership is a stable, seeded employee election.
      AND (PLANALIGN_HASH(CAST({{ employee_id }} AS VARCHAR) || '-aip-elect-'
        || '{{ subsystem_seed("deferral_behavior") }}') % 1000000) / 1000000.0
        < {{ var('deferral_escalation_participant_elected_signup_probability', 0.0) }}
    )
  {%- else -%}
    NOT COALESCE({{ census_opt_out }}, FALSE)
  {%- endif -%}
{%- endmacro %}
