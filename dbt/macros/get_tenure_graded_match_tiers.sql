{#
  Tier Expansion Macro for Tenure-Graded Multi-Tier Employer Match

  Flattens the nested `tenure_graded_bands` config (a list of bands, each
  carrying its own ordered, cumulative list of deferral-rate match tiers)
  into a single flat row set suitable for use in a CROSS JOIN.

  Arguments:
    - tenure_graded_bands: List of band dicts (from dbt var), each shaped as:
        {
          "min_years": <int>,
          "max_years": <int|null>,
          "tiers": [
            {"employee_min": <decimal>, "employee_max": <decimal>, "match_rate": <decimal>},
            ...
          ]
        }

  Output columns (one row per tier across all bands):
    - band_min_years (int)
    - band_max_years (int, or NULL for the unbounded top band)
    - employee_min (decimal)
    - employee_max (decimal)
    - match_rate (decimal)

  Consumer-side join contract (see specs/099-tenure-graded-match/contracts/config-schema.md):
    Callers MUST filter
      WHERE ec.years_of_service >= tier.band_min_years
        AND (tier.band_max_years IS NULL OR ec.years_of_service < tier.band_max_years)
    before aggregating, so each employee is scored only against their own band's tiers.

  Feature: 099 - Tenure-Graded Multi-Tier Employer Match Formula
#}

{% macro get_tenure_graded_match_tiers(tenure_graded_bands) %}
{%- set flat_rows = [] -%}
{%- for band in tenure_graded_bands -%}
  {%- for tier in band['tiers'] -%}
    {%- set _ = flat_rows.append({
        'band_min_years': band['min_years'],
        'band_max_years': band['max_years'],
        'employee_min': tier['employee_min'],
        'employee_max': tier['employee_max'],
        'match_rate': tier['match_rate'],
    }) -%}
  {%- endfor -%}
{%- endfor -%}
{%- for row in flat_rows %}
SELECT
    {{ row['band_min_years'] }} AS band_min_years,
    {{ row['band_max_years'] if row['band_max_years'] is not none else 'NULL' }} AS band_max_years,
    {{ row['employee_min'] }} AS employee_min,
    {{ row['employee_max'] }} AS employee_max,
    {{ row['match_rate'] }} AS match_rate
{% if not loop.last %}UNION ALL{% endif %}
{%- endfor -%}
{%- endmacro %}
