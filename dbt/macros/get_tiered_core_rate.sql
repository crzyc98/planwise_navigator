{#
  Tier Lookup Macro for Service-Based Core Contribution Rates

  This macro generates a SQL CASE expression that returns the appropriate
  contribution rate based on an employee's years of service.

  Arguments:
    - years_of_service_col: SQL column/expression for employee tenure (integer years)
    - graded_schedule: List of tier dicts with min_years and rate (from dbt var)
    - flat_rate: Fallback rate when schedule is empty or for edge cases

  Example usage:
    {{ get_tiered_core_rate('COALESCE(snap.years_of_service, 0)', employer_core_graded_schedule, employer_core_contribution_rate) }}

  Tier matching uses [min, max) convention:
    - min_years is inclusive
    - max_years is exclusive (or null for infinity)
    - Tiers are sorted descending by min_years for correct CASE evaluation

  Rate conversion:
    - UI sends rates as percentages (e.g., 6.0 for 6%)
    - Macro divides by 100 to get decimal (0.06)
#}

{% macro get_tiered_core_rate(years_of_service_col, graded_schedule, flat_rate) %}
{%- if graded_schedule and graded_schedule | length > 0 -%}
CASE
  {%- for tier in graded_schedule | sort(attribute='min_years', reverse=true) %}
  WHEN {{ years_of_service_col }} >= {{ tier['min_years'] }} THEN {{ tier['rate'] / 100.0 }}
  {%- endfor %}
  ELSE {{ flat_rate }}
END
{%- else -%}
{{ flat_rate }}
{%- endif -%}
{% endmacro %}
