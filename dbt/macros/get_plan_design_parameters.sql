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
  CAST(NULL AS BOOLEAN) AS reenrollment_sweep_enabled,
  CAST(NULL AS INTEGER) AS reenrollment_sweep_interval_years,
  CAST(NULL AS INTEGER) AS reenrollment_sweep_first_year,
  CAST(NULL AS VARCHAR) AS reenrollment_sweep_method,
  CAST(NULL AS BOOLEAN) AS reenrollment_sweep_include_non_contributors,
  CAST(NULL AS BOOLEAN) AS reenrollment_sweep_include_below_default,
  CAST(NULL AS BOOLEAN) AS reenrollment_sweep_include_below_aip_cap,
  CAST(NULL AS DECIMAL(10,6)) AS reenrollment_sweep_decline_probability,

  CAST(NULL AS DECIMAL(10,6)) AS deferral_escalation_increment,
  CAST(NULL AS DECIMAL(10,6)) AS deferral_escalation_cap,
  CAST(NULL AS INTEGER) AS eligibility_waiting_period_days,
  CAST(NULL AS VARCHAR) AS core_formula_family,
  CAST(NULL AS BOOLEAN) AS core_integration_enabled,
  CAST(NULL AS VARCHAR) AS core_integration_level_mode,
  CAST(NULL AS INTEGER) AS core_integration_level_value,
  CAST(NULL AS DECIMAL(10,6)) AS core_integration_disparity_rate,
  CAST(NULL AS INTEGER) AS core_points_min_service_years,
  CAST(NULL AS DECIMAL(10,6)) AS core_points_pre_service_rate
WHERE FALSE
{%- else -%}
{%- for design_id, parameters in plan_design_parameters | dictsort %}
{% set sweep = parameters['auto_enrollment'].get('reenrollment_sweep', {}) %}
{% set core = parameters['employer_core'] %}
SELECT
  '{{ design_id | replace("'", "''") }}'::VARCHAR AS plan_design_id,
  '{{ (parameters['match'].get('family', 'deferral_based') | string) | replace("'", "''") }}'::VARCHAR AS match_formula_family,
  '{{ (parameters['match'].get('match_template', 'tiered') | string) | replace("'", "''") }}'::VARCHAR AS match_template,
  {{ parameters['match']['cap_percent'] | float }}::DECIMAL(10,6) AS match_cap_percent,
  {{ parameters['employer_core']['contribution_rate'] | float }}::DECIMAL(10,6) AS employer_core_contribution_rate,
  {{ parameters['auto_enrollment']['default_deferral_rate'] | float }}::DECIMAL(10,6) AS auto_enrollment_default_deferral_rate,
  {{ parameters['auto_enrollment']['window_days'] | int }}::INTEGER AS auto_enrollment_window_days,
  '{{ (parameters['auto_enrollment']['scope'] | string) | replace("'", "''") }}'::VARCHAR AS auto_enrollment_scope,
  {{ 'true' if sweep.get('enabled', false) else 'false' }}::BOOLEAN AS reenrollment_sweep_enabled,
  {{ sweep.get('interval_years', 3) | int }}::INTEGER AS reenrollment_sweep_interval_years,
  {{ (sweep.get('first_year') | int) if sweep.get('first_year') is not none else 'NULL' }}::INTEGER AS reenrollment_sweep_first_year,
  '{{ (sweep.get('method', "enroll_at_default") | string) | replace("'", "''") }}'::VARCHAR AS reenrollment_sweep_method,
  {{ 'true' if sweep.get('include_non_contributors', true) else 'false' }}::BOOLEAN AS reenrollment_sweep_include_non_contributors,
  {{ 'true' if sweep.get('include_below_default', false) else 'false' }}::BOOLEAN AS reenrollment_sweep_include_below_default,
  {{ 'true' if sweep.get('include_below_aip_cap', false) else 'false' }}::BOOLEAN AS reenrollment_sweep_include_below_aip_cap,
  {{ sweep.get('decline_probability', 0.10) | float }}::DECIMAL(10,6) AS reenrollment_sweep_decline_probability,
  {{ parameters['deferral_escalation']['increment'] | float }}::DECIMAL(10,6) AS deferral_escalation_increment,
  {{ parameters['deferral_escalation']['cap'] | float }}::DECIMAL(10,6) AS deferral_escalation_cap,
  {{ parameters['eligibility']['waiting_period_days'] | int }}::INTEGER AS eligibility_waiting_period_days,
  '{{ (parameters['employer_core'].get('family', 'flat') | string) | replace("'", "''") }}'::VARCHAR AS core_formula_family,
  {{ 'true' if parameters['employer_core'].get('integration_enabled', false) else 'false' }}::BOOLEAN AS core_integration_enabled,
  '{{ (parameters['employer_core'].get('integration_level_mode', 'ss_wage_base') | string) | replace("'", "''") }}'::VARCHAR AS core_integration_level_mode,
  {{ (parameters['employer_core'].get('integration_level_value') | int) if parameters['employer_core'].get('integration_level_value') is not none else 'NULL' }}::INTEGER AS core_integration_level_value,
  {{ parameters['employer_core'].get('integration_disparity_rate', 0.0) | float }}::DECIMAL(10,6) AS core_integration_disparity_rate,
  {{ (core.get('points_min_service_years') | int) if core.get('points_min_service_years') is not none else 'NULL' }}::INTEGER AS core_points_min_service_years,
  {{ ((core.get('points_pre_service_rate') | float) / 100.0) if core.get('points_pre_service_rate') is not none else 'NULL' }}::DECIMAL(10,6) AS core_points_pre_service_rate
{% if not loop.last %}UNION ALL{% endif %}
{%- endfor -%}
{%- endif -%}
{% endmacro %}
