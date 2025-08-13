{% macro get_auto_enrollment_scope() %}
  {{ return(var('auto_enrollment_scope', 'all_eligible_employees')) }}
{% endmacro %}

{% macro get_hire_date_cutoff() %}
  {{ return(var('auto_enrollment_hire_date_cutoff', '2020-01-01')) }}
{% endmacro %}

{% macro is_eligible_for_auto_enrollment(hire_date_column, simulation_year_value) %}
  {% set scope = get_auto_enrollment_scope() %}
  {% set cutoff = get_hire_date_cutoff() %}

  CASE
    WHEN '{{ scope }}' = 'new_hires_only' THEN
      -- New hires: hired during simulation year AND after cutoff (inclusive)
      {{ hire_date_column }} >= '{{ cutoff }}'::DATE
      AND {{ hire_date_column }} >= CAST({{ simulation_year_value }} || '-01-01' AS DATE)
      AND {{ hire_date_column }} <= CAST({{ simulation_year_value }} || '-12-31' AS DATE)
    WHEN '{{ scope }}' = 'all_eligible_employees' THEN
      -- All eligible: hired on or after cutoff date (inclusive)
      {{ hire_date_column }} >= '{{ cutoff }}'::DATE
    ELSE false
  END
{% endmacro %}

{% macro get_eligibility_reason(hire_date_column, simulation_year_value, employment_status_column, already_enrolled_flag) %}
  CASE
    WHEN {{ employment_status_column }} != 'active' THEN 'not_active'
    WHEN COALESCE({{ already_enrolled_flag }}, false) = true THEN 'already_enrolled'
    WHEN NOT ({{ is_eligible_for_auto_enrollment(hire_date_column, simulation_year_value) }}) THEN 'outside_scope'
    ELSE 'eligible'
  END
{% endmacro %}
