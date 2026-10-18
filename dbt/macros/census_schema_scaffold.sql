{% macro census_schema_scaffold() %}
  SELECT
    NULL::VARCHAR AS employee_id,
    NULL::VARCHAR AS employee_ssn,
    NULL::DATE AS employee_birth_date,
    NULL::DATE AS employee_hire_date,
    NULL::DATE AS employee_termination_date,
    NULL::DECIMAL(12,2) AS employee_gross_compensation,
    NULL::BOOLEAN AS active,
    NULL::DECIMAL(12,2) AS employee_capped_compensation,
    NULL::DECIMAL(7,5) AS employee_deferral_rate,
    NULL::DECIMAL(12,2) AS employee_contribution,
    NULL::DECIMAL(12,2) AS pre_tax_contribution,
    NULL::DECIMAL(12,2) AS roth_contribution,
    NULL::DECIMAL(12,2) AS after_tax_contribution,
    NULL::DECIMAL(12,2) AS employer_core_contribution,
    NULL::DECIMAL(12,2) AS employer_match_contribution,
    NULL::DATE AS eligibility_entry_date,
    NULL::DECIMAL(5,2) AS scheduled_hours_per_week,
    NULL::BOOLEAN AS auto_escalation_opt_out,
    NULL::BOOLEAN AS eligibility_override
  WHERE FALSE
{% endmacro %}
