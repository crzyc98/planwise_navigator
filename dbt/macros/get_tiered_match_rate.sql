{#
  Tier Lookup Macro for Service-Based Employer Match Rates

  This macro generates SQL CASE expressions that return the appropriate
  match rate AND max deferral percentage based on an employee's years of service.

  Arguments:
    - years_of_service_col: SQL column/expression for employee tenure (integer years)
    - graded_schedule: List of tier dicts with min_years, rate, and max_deferral_pct (from dbt var)
    - default_rate: Fallback rate when schedule is empty or for edge cases (decimal, e.g., 0.50)
    - default_max_deferral_pct: Fallback max deferral when schedule is empty (decimal, e.g., 0.06)

  Example usage:
    -- Get match rate (returns decimal, e.g., 0.50 for 50%)
    {{ get_tiered_match_rate('years_of_service', employer_match_graded_schedule, 0.50) }}

    -- Get max deferral percentage (returns decimal, e.g., 0.06 for 6%)
    {{ get_tiered_match_max_deferral('years_of_service', employer_match_graded_schedule, 0.06) }}

  Tier matching uses [min, max) convention:
    - min_years is inclusive
    - max_years is exclusive (or null for infinity)
    - Tiers are sorted descending by min_years for correct CASE evaluation

  Rate/Percentage conversion:
    - UI sends rates as percentages (e.g., 50 for 50%, 6 for 6%)
    - Macro divides by 100 to get decimal (0.50, 0.06)

  Feature: E010 - Service-Based Match Contribution Tiers
#}

{# Get the match RATE for a service tier #}
{% macro get_tiered_match_rate(years_of_service_col, graded_schedule, default_rate) %}
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
  ELSE {{ default_rate }}
END
{%- else -%}
{{ default_rate }}
{%- endif -%}
{% endmacro %}

{# Get the MAX DEFERRAL PERCENTAGE for a service tier #}
{% macro get_tiered_match_max_deferral(years_of_service_col, graded_schedule, default_max_deferral_pct) %}
{%- if graded_schedule and graded_schedule | length > 0 -%}
{#- Extract min_years values and sort them descending for correct CASE evaluation -#}
{%- set min_years_list = [] -%}
{%- for tier in graded_schedule -%}
  {%- set _ = min_years_list.append(tier['min_years'] | int) -%}
{%- endfor -%}
{%- set sorted_min_years = min_years_list | sort(reverse=true) -%}
{#- Build a lookup dict for max_deferral_pct by min_years -#}
{%- set max_deferral_lookup = {} -%}
{%- for tier in graded_schedule -%}
  {%- set _ = max_deferral_lookup.update({tier['min_years'] | int: tier['max_deferral_pct']}) -%}
{%- endfor -%}
CASE
  {%- for min_yr in sorted_min_years %}
  WHEN {{ years_of_service_col }} >= {{ min_yr }} THEN {{ max_deferral_lookup[min_yr] / 100.0 }}
  {%- endfor %}
  ELSE {{ default_max_deferral_pct }}
END
{%- else -%}
{{ default_max_deferral_pct }}
{%- endif -%}
{% endmacro %}
