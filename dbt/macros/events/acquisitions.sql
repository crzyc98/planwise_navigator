{% macro acquisitions_joining(simulation_year) %}
  {#-
    Acquisitions (#1226) whose effective date falls in simulation_year.

    Reads the `acquisitions` var exported from workforce.acquisitions. Each
    entry keeps its 1-based position in the configured list as `ordinal`,
    which fixes the member SSN block. Returns an empty list when none join.
  -#}
  {%- set joining = [] -%}
  {%- for item in var('acquisitions', []) -%}
    {%- if ((item['effective_date'] | string)[:4] | int) == (simulation_year | int) -%}
      {%- do joining.append({
        'id': item['id'],
        'headcount': item['headcount'] | int,
        'effective_date': item['effective_date'] | string,
        'ordinal': loop.index
      }) -%}
    {%- endif -%}
  {%- endfor -%}
  {{ return(joining) }}
{% endmacro %}


{% macro carried_tenure_at(hire_date_column, year_end_tenure_column, simulation_year, end_date) %}
  {#-
    Service at end_date for an employee whose tenure does not start at the
    hire date (acquired members carry prior service, #1226). Year-end tenure
    advances by one per simulated year, so taking off the years since the hire
    year gives the service carried in, which is then added to the years served
    up to end_date.
  -#}
  GREATEST(0,
    {{ year_end_tenure_column }}
    - ({{ simulation_year }} - YEAR({{ hire_date_column }}))
    + {{ calculate_tenure(hire_date_column, end_date) }}
  )
{% endmacro %}
