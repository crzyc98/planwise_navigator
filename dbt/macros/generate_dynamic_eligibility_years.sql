{% macro generate_dynamic_eligibility_years() %}
  {#- Generate dynamic eligibility determinations for configurable year range -#}

  {%- set start_year = var('simulation_start_year', 2025) -%}
  {%- set end_year = var('simulation_end_year', 2029) -%}

  {%- for year in range(start_year, end_year + 1) -%}

    SELECT
      employee_id,
      employee_ssn,
      employee_hire_date,
      employment_status,
      current_age,
      current_tenure,
      level_id,
      current_compensation,
      waiting_period_days,
      {{ year }} as simulation_year,
      DATEDIFF('day', employee_hire_date, '{{ year }}-01-01'::DATE) as days_since_hire,
      DATEDIFF('day', employee_hire_date, '{{ year }}-01-01'::DATE) >= waiting_period_days as is_eligible,
      CASE
        WHEN DATEDIFF('day', employee_hire_date, '{{ year }}-01-01'::DATE) >= waiting_period_days THEN 'eligible_service_met'
        ELSE 'pending_service_requirement'
      END as eligibility_reason,
      '{{ year }}-01-01'::DATE as eligibility_evaluation_date
    FROM eligibility_calculation

    {%- if not loop.last %}
    UNION ALL
    {%- endif -%}

  {%- endfor %}

{% endmacro %}
