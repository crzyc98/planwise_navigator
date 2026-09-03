{# Flatten per-design points-based core schedules; YAML rates are percentages. #}
{% macro get_plan_design_core_points_schedule(plan_design_parameters) %}
{%- set rows = [] -%}
{%- for design_id, parameters in plan_design_parameters | dictsort -%}
  {%- if parameters['employer_core']['family'] == 'points_based' -%}
    {%- for band in parameters['employer_core'].get('points_schedule', []) -%}
      {%- set _ = rows.append({
        'plan_design_id': design_id, 'band_ordinal': loop.index,
        'min_points': band['min_points'], 'max_points': band['max_points'],
        'rate': band['rate'] / 100.0
      }) -%}
    {%- endfor -%}
  {%- endif -%}
{%- endfor -%}
{%- if rows | length == 0 -%}
SELECT
  CAST(NULL AS VARCHAR) AS plan_design_id,
  CAST(NULL AS INTEGER) AS band_ordinal,
  CAST(NULL AS INTEGER) AS min_points,
  CAST(NULL AS INTEGER) AS max_points,
  CAST(NULL AS DECIMAL(10,6)) AS rate
WHERE FALSE
{%- else -%}
{%- for row in rows %}
SELECT
  '{{ row['plan_design_id'] | replace("'", "''") }}'::VARCHAR AS plan_design_id,
  {{ row['band_ordinal'] }}::INTEGER AS band_ordinal,
  {{ row['min_points'] }}::INTEGER AS min_points,
  {{ row['max_points'] if row['max_points'] is not none else 'NULL' }}::INTEGER AS max_points,
  {{ row['rate'] }}::DECIMAL(10,6) AS rate
{% if not loop.last %}UNION ALL{% endif %}
{%- endfor -%}
{%- endif -%}
{% endmacro %}
