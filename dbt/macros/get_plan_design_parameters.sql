{# Render per-design scalar parameters as a typed inline relation. #}
{% macro get_plan_design_parameters(plan_design_parameters) %}
{%- if plan_design_parameters | length == 0 -%}
SELECT
  CAST(NULL AS VARCHAR) AS plan_design_id,
  CAST(NULL AS VARCHAR) AS match_formula_family,
  CAST(NULL AS VARCHAR) AS match_template,
  CAST(NULL AS DECIMAL(10,6)) AS match_cap_percent,
  CAST(NULL AS DECIMAL(10,6)) AS employer_core_contribution_rate,
  CAST(NULL AS DECIMAL(10,6)) AS auto_enrollment_default_deferral_rate,
  CAST(NULL AS INTEGER) AS auto_enrollment_window_days,
  CAST(NULL AS VARCHAR) AS auto_enrollment_scope,
  CAST(NULL AS DECIMAL(10,6)) AS deferral_escalation_increment,
  CAST(NULL AS DECIMAL(10,6)) AS deferral_escalation_cap,
  CAST(NULL AS INTEGER) AS eligibility_waiting_period_days,
  CAST(NULL AS VARCHAR) AS core_formula_family,
  CAST(NULL AS BOOLEAN) AS core_integration_enabled,
  CAST(NULL AS VARCHAR) AS core_integration_level_mode,
  CAST(NULL AS INTEGER) AS core_integration_level_value,
  CAST(NULL AS DECIMAL(10,6)) AS core_integration_disparity_rate
WHERE FALSE
{%- else -%}
{%- for design_id, parameters in plan_design_parameters | dictsort %}
SELECT
  '{{ design_id | replace("'", "''") }}'::VARCHAR AS plan_design_id,
  '{{ parameters['match'].get('family', 'deferral_based') }}'::VARCHAR AS match_formula_family,
  '{{ parameters['match'].get('match_template', 'tiered') | replace("'", "''") }}'::VARCHAR AS match_template,
  {{ parameters['match']['cap_percent'] }}::DECIMAL(10,6) AS match_cap_percent,
  {{ parameters['employer_core']['contribution_rate'] }}::DECIMAL(10,6) AS employer_core_contribution_rate,
  {{ parameters['auto_enrollment']['default_deferral_rate'] }}::DECIMAL(10,6) AS auto_enrollment_default_deferral_rate,
  {{ parameters['auto_enrollment']['window_days'] }}::INTEGER AS auto_enrollment_window_days,
  '{{ parameters['auto_enrollment']['scope'] }}'::VARCHAR AS auto_enrollment_scope,
  {{ parameters['deferral_escalation']['increment'] }}::DECIMAL(10,6) AS deferral_escalation_increment,
  {{ parameters['deferral_escalation']['cap'] }}::DECIMAL(10,6) AS deferral_escalation_cap,
  {{ parameters['eligibility']['waiting_period_days'] }}::INTEGER AS eligibility_waiting_period_days,
  '{{ parameters['employer_core'].get('family', 'flat') }}'::VARCHAR AS core_formula_family,
  {{ parameters['employer_core'].get('integration_enabled', false) | lower }}::BOOLEAN AS core_integration_enabled,
  '{{ parameters['employer_core'].get('integration_level_mode', 'ss_wage_base') }}'::VARCHAR AS core_integration_level_mode,
  {{ parameters['employer_core'].get('integration_level_value') if parameters['employer_core'].get('integration_level_value') is not none else 'NULL' }}::INTEGER AS core_integration_level_value,
  {{ parameters['employer_core'].get('integration_disparity_rate', 0.0) }}::DECIMAL(10,6) AS core_integration_disparity_rate
{% if not loop.last %}UNION ALL{% endif %}
{%- endfor -%}
{%- endif -%}
{% endmacro %}
