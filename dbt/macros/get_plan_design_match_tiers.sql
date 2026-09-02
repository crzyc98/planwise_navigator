{# Flatten every supported same-family match schedule by plan design. #}
{% macro get_plan_design_match_tiers(plan_design_parameters) %}
{%- set rows = [] -%}
{%- for design_id, parameters in plan_design_parameters | dictsort -%}
  {%- for tier in parameters['match'].get('tiers', []) -%}
    {%- set _ = rows.append({
      'plan_design_id': design_id, 'family': 'deferral_based',
      'band_min': none, 'band_max': none, 'tier_ordinal': loop.index,
      'employee_min': tier['employee_min'], 'employee_max': tier['employee_max'],
      'match_rate': tier['match_rate'], 'max_deferral_pct': tier['employee_max']
    }) -%}
  {%- endfor -%}
  {%- for band in parameters['match'].get('graded_schedule', []) -%}
    {%- set _ = rows.append({
      'plan_design_id': design_id, 'family': 'graded_by_service',
      'band_min': band['min_value'], 'band_max': band['max_value'],
      'tier_ordinal': loop.index, 'employee_min': 0,
      'employee_max': band['max_deferral_pct'], 'match_rate': band['match_rate'],
      'max_deferral_pct': band['max_deferral_pct']
    }) -%}
  {%- endfor -%}
  {%- for band in parameters['match'].get('points_tiers', []) -%}
    {%- set _ = rows.append({
      'plan_design_id': design_id, 'family': 'points_based',
      'band_min': band['min_value'], 'band_max': band['max_value'],
      'tier_ordinal': loop.index, 'employee_min': 0,
      'employee_max': band['max_deferral_pct'], 'match_rate': band['match_rate'],
      'max_deferral_pct': band['max_deferral_pct']
    }) -%}
  {%- endfor -%}
  {%- for band in parameters['match'].get('tenure_graded_bands', []) -%}
    {%- set band_ordinal = loop.index -%}
    {%- for tier in band['tiers'] -%}
      {%- set _ = rows.append({
        'plan_design_id': design_id, 'family': 'tenure_graded',
        'band_min': band['min_years'], 'band_max': band['max_years'],
        'tier_ordinal': (band_ordinal * 1000) + loop.index,
        'employee_min': tier['employee_min'], 'employee_max': tier['employee_max'],
        'match_rate': tier['match_rate'], 'max_deferral_pct': tier['employee_max']
      }) -%}
    {%- endfor -%}
  {%- endfor -%}
{%- endfor -%}
{%- if rows | length == 0 -%}
SELECT
  CAST(NULL AS VARCHAR) AS plan_design_id,
  CAST(NULL AS VARCHAR) AS formula_family,
  CAST(NULL AS INTEGER) AS band_min_value,
  CAST(NULL AS INTEGER) AS band_max_value,
  CAST(NULL AS INTEGER) AS tier_ordinal,
  CAST(NULL AS DECIMAL(10,6)) AS employee_min,
  CAST(NULL AS DECIMAL(10,6)) AS employee_max,
  CAST(NULL AS DECIMAL(10,6)) AS match_rate,
  CAST(NULL AS DECIMAL(10,6)) AS max_deferral_pct
WHERE FALSE
{%- else -%}
{%- for row in rows %}
SELECT
  '{{ row['plan_design_id'] | replace("'", "''") }}'::VARCHAR AS plan_design_id,
  '{{ row['family'] }}'::VARCHAR AS formula_family,
  {{ row['band_min'] if row['band_min'] is not none else 'NULL' }}::INTEGER AS band_min_value,
  {{ row['band_max'] if row['band_max'] is not none else 'NULL' }}::INTEGER AS band_max_value,
  {{ row['tier_ordinal'] }}::INTEGER AS tier_ordinal,
  {{ row['employee_min'] }}::DECIMAL(10,6) AS employee_min,
  {{ row['employee_max'] }}::DECIMAL(10,6) AS employee_max,
  {{ row['match_rate'] }}::DECIMAL(10,6) AS match_rate,
  {{ row['max_deferral_pct'] }}::DECIMAL(10,6) AS max_deferral_pct
{% if not loop.last %}UNION ALL{% endif %}
{%- endfor -%}
{%- endif -%}
{% endmacro %}
