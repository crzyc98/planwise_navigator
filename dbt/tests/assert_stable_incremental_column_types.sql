{{ config(severity='error', tags=['data_quality', 'schema', 'critical']) }}

-- These incremental columns must have their final type from year one onward.
-- Otherwise dbt alters and inserts into the same table in one transaction,
-- which fails to commit on DuckDB 1.5.5 (#750).
{% set contracts = [
  ('int_employee_compensation_by_year', 'employee_birth_date', 'TIMESTAMP'),
  ('int_employee_compensation_by_year', 'employee_hire_date', 'TIMESTAMP'),
  ('int_employee_compensation_by_year', 'employee_enrollment_date', 'TIMESTAMP'),
  ('int_workforce_needs', 'starting_new_hire_count', 'BIGINT'),
  ('int_deferral_rate_state_accumulator', 'last_escalation_date', 'TIMESTAMP'),
  ('int_deferral_rate_state_accumulator', 'total_escalation_amount', 'DECIMAL(5,4)'),
  ('fct_workforce_snapshot', 'last_escalation_date', 'TIMESTAMP'),
  ('fct_workforce_snapshot', 'total_escalation_amount', 'DECIMAL(5,4)')
] %}

WITH expected AS (
  {% for model, column, data_type in contracts %}
  {% set relation = ref(model) %}
  SELECT
    '{{ relation.schema }}' AS table_schema,
    '{{ relation.identifier }}' AS table_name,
    '{{ column }}' AS column_name,
    '{{ data_type }}' AS expected_type
  {% if not loop.last %}UNION ALL{% endif %}
  {% endfor %}
)

SELECT
  expected.table_name,
  expected.column_name,
  expected.expected_type,
  actual.data_type AS actual_type
FROM expected
LEFT JOIN information_schema.columns actual
  ON actual.table_catalog = '{{ target.database }}'
  AND actual.table_schema = expected.table_schema
  AND actual.table_name = expected.table_name
  AND actual.column_name = expected.column_name
WHERE actual.column_name IS NULL
  OR actual.data_type <> expected.expected_type
