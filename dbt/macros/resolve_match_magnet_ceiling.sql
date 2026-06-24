{#
  Match-Magnet Ceiling Resolution (Feature 102)

  Returns a SQL expression for the per-employee deferral rate that the
  voluntary-enrollment "match magnet" snaps toward — i.e. the smallest
  deferral that captures the full employer match for that employee.

  The expression is keyed on `employer_match_status` so the magnet operates
  in ALL match modes (clarification: ceiling is derived from the applicable
  service/tenure/points tier, not a stale default):

    deferral_based     -> scalar ceiling from the active formula (passed in)
    graded_by_service  -> per-employee CASE over employer_match_graded_schedule
    points_based       -> per-employee CASE over points_match_tiers
    tenure_based        -> per-employee CASE over tenure_match_tiers (max_deferral_pct)
    tenure_graded      -> per-employee CASE: max(employee_max) within the band
    disabled / unknown -> 0 (magnet inactive)

  Arguments:
    - status: employer_match_status value (string literal)
    - years_of_service_col: SQL expr for integer years of service
    - points_col: SQL expr for points (FLOOR(age) + FLOOR(tenure))
    - deferral_scalar: numeric literal ceiling for deferral_based mode

  All branches return DECIMAL(5,4). Tier percentages stored as whole numbers
  (e.g. 6 for 6%) are divided by 100; values <= 1 are treated as decimals.
#}

{% macro resolve_match_magnet_ceiling(status, years_of_service_col, points_col, deferral_scalar) %}
{%- set graded_schedule = var('employer_match_graded_schedule', []) -%}
{%- set points_tiers = var('points_match_tiers', []) -%}
{%- set tenure_tiers = var('tenure_match_tiers', []) -%}
{%- set tenure_graded_bands = var('tenure_graded_bands', []) -%}
{%- if status == 'deferral_based' -%}
CAST({{ deferral_scalar }} AS DECIMAL(5,4))
{%- elif status == 'graded_by_service' -%}
CAST(({{ get_tiered_match_max_deferral(years_of_service_col, graded_schedule, 0.06) }}) AS DECIMAL(5,4))
{%- elif status == 'points_based' -%}
CAST(({{ get_points_based_max_deferral(points_col, points_tiers, 0.06) }}) AS DECIMAL(5,4))
{%- elif status == 'tenure_based' -%}
  {%- if tenure_tiers | length > 0 -%}
CASE
  {%- for tier in tenure_tiers %}
  WHEN {{ years_of_service_col }} >= {{ tier.min_years }}
       {%- if tier.max_years is not none %} AND {{ years_of_service_col }} < {{ tier.max_years }}{% endif %}
  THEN CAST({{ (tier.max_deferral_pct | float / 100.0) if (tier.max_deferral_pct | float) > 1 else tier.max_deferral_pct }} AS DECIMAL(5,4))
  {%- endfor %}
  ELSE CAST(0.06 AS DECIMAL(5,4))
END
  {%- else -%}
CAST(0.06 AS DECIMAL(5,4))
  {%- endif -%}
{%- elif status == 'tenure_graded' -%}
  {%- if tenure_graded_bands | length > 0 -%}
CASE
  {%- for band in tenure_graded_bands -%}
  {%- set bns = namespace(bmax=0.0) -%}
  {%- for tier in band['tiers'] -%}
    {%- if tier['employee_max'] is not none and tier['employee_max'] > bns.bmax -%}
      {%- set bns.bmax = tier['employee_max'] -%}
    {%- endif -%}
  {%- endfor %}
  WHEN {{ years_of_service_col }} >= {{ band['min_years'] }}
       {%- if band['max_years'] is not none %} AND {{ years_of_service_col }} < {{ band['max_years'] }}{% endif %}
  THEN CAST({{ bns.bmax }} AS DECIMAL(5,4))
  {%- endfor %}
  ELSE CAST(0 AS DECIMAL(5,4))
END
  {%- else -%}
CAST(0 AS DECIMAL(5,4))
  {%- endif -%}
{%- else -%}
CAST(0 AS DECIMAL(5,4))
{%- endif -%}
{% endmacro %}
