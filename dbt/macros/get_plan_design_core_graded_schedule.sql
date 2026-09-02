{# Flatten per-design service-graded core schedules. #}
{% macro get_plan_design_core_graded_schedule(plan_design_parameters) %}
{%- set rows = [] -%}
{%- for design_id, parameters in plan_design_parameters | dictsort -%}
  {%- for band in parameters['employer_core'].get('graded_schedule', []) -%}
    {%- set _ = rows.append({
      'plan_design_id': design_id, 'band_ordinal': loop.index,
      'min_years': band['min_years'], 'max_years': band['max_years'],
      'rate': band['rate']
    }) -%}
  {%- endfor -%}
{%- endfor -%}
{%- if rows | length == 0 -%}
SELECT
  CAST(NULL AS VARCHAR) AS plan_design_id,
  CAST(NULL AS INTEGER) AS band_ordinal,
  CAST(NULL AS INTEGER) AS min_years,
  CAST(NULL AS INTEGER) AS max_years,
  CAST(NULL AS DECIMAL(10,6)) AS rate
WHERE FALSE
{%- else -%}
{%- for row in rows %}
SELECT
  '{{ row['plan_design_id'] | replace("'", "''") }}'::VARCHAR AS plan_design_id,
  {{ row['band_ordinal'] }}::INTEGER AS band_ordinal,
  {{ row['min_years'] }}::INTEGER AS min_years,
  {{ row['max_years'] if row['max_years'] is not none else 'NULL' }}::INTEGER AS max_years,
  {{ row['rate'] }}::DECIMAL(10,6) AS rate
{% if not loop.last %}UNION ALL{% endif %}
{%- endfor -%}
{%- endif -%}
{% endmacro %}
