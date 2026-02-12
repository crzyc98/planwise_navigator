{#
  Points-Based Tier Lookup Macros for Employer Match Rates

  These macros generate SQL CASE expressions that return the appropriate
  match rate AND max deferral percentage based on an employee's age+tenure points.

  Arguments:
    - points_col: SQL column/expression for points value (integer)
    - points_schedule: List of tier dicts with min_points, rate, and max_deferral_pct (from dbt var)
    - default_rate: Fallback rate when schedule is empty or for edge cases (decimal, e.g., 0.50)
    - default_pct: Fallback max deferral when schedule is empty (decimal, e.g., 0.06)

  Example usage:
    -- Get match rate (returns decimal, e.g., 0.50 for 50%)
    {{ get_points_based_match_rate('applied_points', points_match_tiers, 0.50) }}

    -- Get max deferral percentage (returns decimal, e.g., 0.06 for 6%)
    {{ get_points_based_max_deferral('applied_points', points_match_tiers, 0.06) }}

  Tier matching:
    - Tiers are sorted descending by min_points
    - CASE evaluates top-down, so the first WHEN (highest min_points) that
      matches acts as the implicit upper bound for lower tiers
    - Example: tiers [80, 60, 40, 0] → points=70 skips >=80, hits >=60

  Rate/Percentage conversion:
    - Config sends rates as percentages (e.g., 50 for 50%, 6 for 6%)
    - Macro divides by 100 to get decimal (0.50, 0.06)

  Feature: E046 - Tenure-Based and Points-Based Employer Match Modes
#}

{# Get the match RATE for a points tier #}
{% macro get_points_based_match_rate(points_col, points_schedule, default_rate) %}
{%- if points_schedule and points_schedule | length > 0 -%}
{#- Extract min_points values and sort them descending for correct CASE evaluation -#}
{%- set min_points_list = [] -%}
{%- for tier in points_schedule -%}
  {%- set _ = min_points_list.append(tier['min_points'] | int) -%}
{%- endfor -%}
{%- set sorted_min_points = min_points_list | sort(reverse=true) -%}
{#- Build a lookup dict for rate by min_points -#}
{%- set rate_lookup = {} -%}
{%- for tier in points_schedule -%}
  {%- set _ = rate_lookup.update({tier['min_points'] | int: tier['rate']}) -%}
{%- endfor -%}
CASE
  {%- for min_pt in sorted_min_points %}
  WHEN {{ points_col }} >= {{ min_pt }} THEN {{ rate_lookup[min_pt] / 100.0 }}
  {%- endfor %}
  ELSE {{ default_rate }}
END
{%- else -%}
{{ default_rate }}
{%- endif -%}
{% endmacro %}

{# Get the MAX DEFERRAL PERCENTAGE for a points tier #}
{% macro get_points_based_max_deferral(points_col, points_schedule, default_pct) %}
{%- if points_schedule and points_schedule | length > 0 -%}
{#- Extract min_points values and sort them descending for correct CASE evaluation -#}
{%- set min_points_list = [] -%}
{%- for tier in points_schedule -%}
  {%- set _ = min_points_list.append(tier['min_points'] | int) -%}
{%- endfor -%}
{%- set sorted_min_points = min_points_list | sort(reverse=true) -%}
{#- Build a lookup dict for max_deferral_pct by min_points -#}
{%- set max_deferral_lookup = {} -%}
{%- for tier in points_schedule -%}
  {%- set _ = max_deferral_lookup.update({tier['min_points'] | int: tier['max_deferral_pct']}) -%}
{%- endfor -%}
CASE
  {%- for min_pt in sorted_min_points %}
  WHEN {{ points_col }} >= {{ min_pt }} THEN {{ max_deferral_lookup[min_pt] / 100.0 }}
  {%- endfor %}
  ELSE {{ default_pct }}
END
{%- else -%}
{{ default_pct }}
{%- endif -%}
{% endmacro %}
