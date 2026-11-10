{#
  CTEs for the census calendar (#1163), built from a relation with
  employee_hire_date:
    census_calendar: the census year, the latest hire year holding at least 1%
      of rows (ignores a handful of stray future-dated hires).
    plan_calendar: the census plan year. setup.plan_year_start_date and
      plan_year_end_date win when set (one alone implies the other, a year
      apart); otherwise the census year, and 2024 only when the census has no
      usable hire dates.
  The caller supplies the comma after the last CTE.
#}
{% macro census_plan_calendar(relation) %}
census_hire_years AS (
  SELECT YEAR(employee_hire_date) AS hire_year, COUNT(*) AS hire_count
  FROM {{ relation }}
  GROUP BY YEAR(employee_hire_date)
),
census_calendar AS (
  SELECT MAKE_DATE(MAX(hire_year), 1, 1) AS year_start,
    MAKE_DATE(MAX(hire_year) + 1, 1, 1) AS year_end
  FROM census_hire_years
  WHERE hire_count >= GREATEST(1, (SELECT COUNT(*) FROM {{ relation }}) * 0.01)
),
plan_calendar AS (
  {%- set start_date = var('plan_year_start_date', none) %}
  {%- set end_date = var('plan_year_end_date', none) %}
  SELECT
    {% if start_date -%}
    CAST('{{ start_date }}' AS DATE)
    {%- elif end_date -%}
    CAST(CAST('{{ end_date }}' AS DATE) - INTERVAL 1 YEAR + INTERVAL 1 DAY AS DATE)
    {%- else -%}
    COALESCE(year_start, DATE '2024-01-01')
    {%- endif %} AS plan_start,
    {% if end_date -%}
    CAST('{{ end_date }}' AS DATE)
    {%- elif start_date -%}
    CAST(CAST('{{ start_date }}' AS DATE) + INTERVAL 1 YEAR - INTERVAL 1 DAY AS DATE)
    {%- else -%}
    COALESCE(CAST(year_end - INTERVAL 1 DAY AS DATE), DATE '2024-12-31')
    {%- endif %} AS plan_end
  FROM census_calendar
)
{% endmacro %}
