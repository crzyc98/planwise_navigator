{% macro resolve_parameter(job_level, event_type, parameter_name, fiscal_year=none) %}

  {%- set fiscal_year = fiscal_year or var('simulation_year', 2025) -%}
  {%- set scenario_id = var('scenario_id', 'default') -%}

  (
    SELECT parameter_value
    FROM {{ ref('int_effective_parameters') }}
    WHERE scenario_id = '{{ scenario_id }}'
      AND fiscal_year = {{ fiscal_year }}
      AND job_level = {{ job_level }}
      AND event_type = '{{ event_type }}'
      AND parameter_name = '{{ parameter_name }}'
    LIMIT 1
  )

{% endmacro %}


{% macro get_parameter_value(job_level, event_type, parameter_name, fiscal_year=none) %}

  {%- set fiscal_year = fiscal_year or var('simulation_year', 2025) -%}
  {%- set scenario_id = var('scenario_id', 'default') -%}

  COALESCE(
    {{ resolve_parameter(job_level, event_type, parameter_name, fiscal_year) }},
    -- Fallback to hardcoded defaults if parameter not found
    CASE
      WHEN '{{ parameter_name }}' = 'merit_base' AND {{ job_level }} = 1 THEN 0.035
      WHEN '{{ parameter_name }}' = 'merit_base' AND {{ job_level }} = 2 THEN 0.040
      WHEN '{{ parameter_name }}' = 'merit_base' AND {{ job_level }} = 3 THEN 0.045
      WHEN '{{ parameter_name }}' = 'merit_base' AND {{ job_level }} = 4 THEN 0.050
      WHEN '{{ parameter_name }}' = 'merit_base' AND {{ job_level }} = 5 THEN 0.055
      WHEN '{{ parameter_name }}' = 'cola_rate' THEN 0.005
      WHEN '{{ parameter_name }}' = 'promotion_raise' THEN 0.12
      WHEN '{{ parameter_name }}' = 'new_hire_salary_adjustment' THEN 1.1489720153602505
      -- Epic E035: Deferral escalation defaults
      WHEN '{{ parameter_name }}' = 'escalation_rate' THEN 0.01  -- 1% default increment
      WHEN '{{ parameter_name }}' = 'max_escalation_rate' THEN 0.10  -- 10% maximum rate cap
      WHEN '{{ parameter_name }}' = 'tenure_threshold' THEN 1  -- 1 year minimum tenure
      WHEN '{{ parameter_name }}' = 'age_threshold' THEN 21  -- 21 minimum age
      WHEN '{{ parameter_name }}' = 'max_escalations' THEN 10  -- Maximum 10 escalations
      ELSE 1.0
    END
  )

{% endmacro %}


{% macro validate_parameter_ranges(parameter_name, parameter_value) %}

  CASE
    WHEN '{{ parameter_name }}' = 'merit_base' AND ({{ parameter_value }} < 0 OR {{ parameter_value }} > 0.5)
      THEN FALSE
    WHEN '{{ parameter_name }}' = 'cola_rate' AND ({{ parameter_value }} < 0 OR {{ parameter_value }} > 0.1)
      THEN FALSE
    WHEN '{{ parameter_name }}' = 'promotion_raise' AND ({{ parameter_value }} < 0 OR {{ parameter_value }} > 1.0)
      THEN FALSE
    WHEN '{{ parameter_name }}' = 'promotion_probability' AND ({{ parameter_value }} < 0 OR {{ parameter_value }} > 1.0)
      THEN FALSE
    WHEN '{{ parameter_name }}' = 'escalation_rate' AND ({{ parameter_value }} < 0 OR {{ parameter_value }} > 0.1)
      THEN FALSE
    WHEN '{{ parameter_name }}' = 'max_escalation_rate' AND ({{ parameter_value }} < 0 OR {{ parameter_value }} > 1.0)
      THEN FALSE
    WHEN '{{ parameter_name }}' = 'tenure_threshold' AND ({{ parameter_value }} < 0 OR {{ parameter_value }} > 30)
      THEN FALSE
    WHEN '{{ parameter_name }}' = 'age_threshold' AND ({{ parameter_value }} < 18 OR {{ parameter_value }} > 70)
      THEN FALSE
    WHEN '{{ parameter_name }}' = 'max_escalations' AND ({{ parameter_value }} < 0 OR {{ parameter_value }} > 20)
      THEN FALSE
    ELSE TRUE
  END

{% endmacro %}
