{% macro data_quality_flag(employee_id_col='employee_id', simulation_year_col='simulation_year', effective_date_col='effective_date', compensation_amount_col='compensation_amount', event_type_col='event_type') %}
CASE
  WHEN {{ employee_id_col }} IS NULL THEN 'INVALID_EMPLOYEE_ID'
  WHEN {{ simulation_year_col }} IS NULL THEN 'INVALID_SIMULATION_YEAR'
  WHEN {{ effective_date_col }} IS NULL THEN 'INVALID_EFFECTIVE_DATE'
  WHEN {{ compensation_amount_col }} IS NULL AND {{ event_type_col }} NOT IN ({{ evt_termination() }},{{ evt_enrollment() }},{{ evt_enrollment_change() }},{{ evt_deferral_escalation() }}) THEN 'INVALID_COMPENSATION'
  ELSE {{ dq_valid() }}
END
{% endmacro %}
