{# Render per-design scalar parameters as a typed inline relation. #}
{% macro get_plan_design_parameters(plan_design_parameters) %}
{%- if plan_design_parameters | length == 0 -%}
SELECT
  CAST(NULL AS VARCHAR) AS plan_design_id,
  CAST(NULL AS DECIMAL(10,6)) AS match_cap_percent,
  CAST(NULL AS DECIMAL(10,6)) AS employer_core_contribution_rate,
  CAST(NULL AS DECIMAL(10,6)) AS auto_enrollment_default_deferral_rate,
  CAST(NULL AS INTEGER) AS auto_enrollment_window_days,
  CAST(NULL AS VARCHAR) AS auto_enrollment_scope,
  CAST(NULL AS DECIMAL(10,6)) AS deferral_escalation_increment,
  CAST(NULL AS DECIMAL(10,6)) AS deferral_escalation_cap,
  CAST(NULL AS INTEGER) AS eligibility_waiting_period_days
WHERE FALSE
{%- else -%}
{%- for design_id, parameters in plan_design_parameters | dictsort %}
SELECT
  '{{ design_id | replace("'", "''") }}'::VARCHAR AS plan_design_id,
  {{ parameters['match']['cap_percent'] }}::DECIMAL(10,6) AS match_cap_percent,
  {{ parameters['employer_core']['contribution_rate'] }}::DECIMAL(10,6) AS employer_core_contribution_rate,
  {{ parameters['auto_enrollment']['default_deferral_rate'] }}::DECIMAL(10,6) AS auto_enrollment_default_deferral_rate,
  {{ parameters['auto_enrollment']['window_days'] }}::INTEGER AS auto_enrollment_window_days,
  '{{ parameters['auto_enrollment']['scope'] }}'::VARCHAR AS auto_enrollment_scope,
  {{ parameters['deferral_escalation']['increment'] }}::DECIMAL(10,6) AS deferral_escalation_increment,
  {{ parameters['deferral_escalation']['cap'] }}::DECIMAL(10,6) AS deferral_escalation_cap,
  {{ parameters['eligibility']['waiting_period_days'] }}::INTEGER AS eligibility_waiting_period_days
{% if not loop.last %}UNION ALL{% endif %}
{%- endfor -%}
{%- endif -%}
{% endmacro %}
