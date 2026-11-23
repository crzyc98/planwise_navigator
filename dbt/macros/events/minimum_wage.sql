{% macro minimum_wage_step(simulation_year) %}
  {#-
    The minimum wage step (#1229) whose effective date falls in simulation_year,
    as {'hourly_rate': float, 'effective_date': 'YYYY-MM-DD'}, or none.

    Reads the `minimum_wage_steps` var exported from compensation.minimum_wage.
    Config allows one step per calendar year.
  -#}
  {%- set steps = [] -%}
  {%- for item in var('minimum_wage_steps', []) -%}
    {%- if ((item['effective_date'] | string)[:4] | int) == (simulation_year | int) -%}
      {%- do steps.append({
        'hourly_rate': item['hourly_rate'] | float,
        'effective_date': ((item['effective_date'] | string)[:10]) | replace("'", "''")
      }) -%}
    {%- endif -%}
  {%- endfor -%}
  {%- if steps | length > 1 -%}
    {{ exceptions.raise_compiler_error('More than one minimum wage step in ' ~ simulation_year) }}
  {%- endif -%}
  {{ return(steps[0] if steps else none) }}
{% endmacro %}


{% macro census_hourly_rate_now(census_rate, census_pay, current_pay) %}
  {#- A census hourly rate moved with pay since the census: hours stay fixed,
      so the rate rises in proportion to the annual pay rate (#1229). -#}
  ({{ census_rate }} * {{ current_pay }} / NULLIF({{ census_pay }}, 0))
{% endmacro %}


{% macro minimum_wage_needs_rates_message() %}
  {{- return('A minimum wage needs an hourly rate per person, but no census row has one. '
    ~ 'Add one of these census columns: hourly_rate, hours_worked or scheduled_hours_per_week.') -}}
{% endmacro %}


{% macro pay_after_minimum_wage(t, through, merit_on_through) %}
  {#-
    Pay after a minimum wage floor (#1229) once the promotion and merit raise
    dated after it have applied, up to `through`. The floor event holds pay on
    its date (it already includes any promotion or raise on or before it), and
    later events compound on it by their own ratio, as a merit raise compounds
    on a promotion. `merit_on_through` says whether a raise dated exactly
    `through` counts (it does at year end and for the raise event itself).
    Columns come from `t`: minimum_wage_salary, minimum_wage_date,
    promotion_date, promotion_ratio, merit_date, merit_raise_rate.
  -#}
  ROUND({{ t }}.minimum_wage_salary
    * CASE WHEN {{ t }}.promotion_date > {{ t }}.minimum_wage_date
        AND {{ t }}.promotion_date <= {{ through }}
      THEN COALESCE({{ t }}.promotion_ratio, 1) ELSE 1 END
    * CASE WHEN {{ t }}.merit_date > {{ t }}.minimum_wage_date
        AND ({{ t }}.merit_date < {{ through }} OR {{ merit_on_through }})
      THEN 1 + COALESCE({{ t }}.merit_raise_rate, 0) ELSE 1 END, 2)
{% endmacro %}
