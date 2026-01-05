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
{#- Extract min_years values and sort them descending for correct CASE evaluation -#}
{%- set min_years_list = [] -%}
{%- for tier in graded_schedule -%}
  {%- set _ = min_years_list.append(tier['min_years'] | int) -%}
{%- endfor -%}
{%- set sorted_min_years = min_years_list | sort(reverse=true) -%}
{#- Build a lookup dict for rate by min_years -#}
{%- set rate_lookup = {} -%}
{%- for tier in graded_schedule -%}
  {%- set _ = rate_lookup.update({tier['min_years'] | int: tier['rate']}) -%}
{%- endfor -%}
CASE
  {%- for min_yr in sorted_min_years %}
  WHEN {{ years_of_service_col }} >= {{ min_yr }} THEN {{ rate_lookup[min_yr] / 100.0 }}
  {%- endfor %}
  ELSE {{ flat_rate }}
END
{%- else -%}
{{ flat_rate }}
{%- endif -%}
{% endmacro %}
