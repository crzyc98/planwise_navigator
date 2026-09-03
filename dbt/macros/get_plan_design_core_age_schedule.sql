{# Flatten per-design age-banded core schedules; YAML rates are percentages. #}
{% macro get_plan_design_core_age_schedule(plan_design_parameters) %}
{%- set rows = [] -%}
{%- for design_id, parameters in plan_design_parameters | dictsort -%}
  {%- if parameters['employer_core']['family'] == 'age_banded' -%}
    {%- for band in parameters['employer_core'].get('age_schedule', []) -%}
      {%- set _ = rows.append({
        'plan_design_id': design_id, 'band_ordinal': loop.index,
        'min_age': band['min_age'], 'max_age': band['max_age'],
        'rate': band['rate'] / 100.0
      }) -%}
    {%- endfor -%}
  {%- endif -%}
{%- endfor -%}
{%- if rows | length == 0 -%}
SELECT
  CAST(NULL AS VARCHAR) AS plan_design_id,
  CAST(NULL AS INTEGER) AS band_ordinal,
  CAST(NULL AS INTEGER) AS min_age,
  CAST(NULL AS INTEGER) AS max_age,
  CAST(NULL AS DECIMAL(10,6)) AS rate
WHERE FALSE
{%- else -%}
{%- for row in rows %}
SELECT
  '{{ row['plan_design_id'] | replace("'", "''") }}'::VARCHAR AS plan_design_id,
  {{ row['band_ordinal'] }}::INTEGER AS band_ordinal,
  {{ row['min_age'] }}::INTEGER AS min_age,
  {{ row['max_age'] if row['max_age'] is not none else 'NULL' }}::INTEGER AS max_age,
  {{ row['rate'] }}::DECIMAL(10,6) AS rate
{% if not loop.last %}UNION ALL{% endif %}
{%- endfor -%}
{%- endif -%}
{% endmacro %}
