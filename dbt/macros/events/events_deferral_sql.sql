{% macro events_deferral_sql(cohort_table, simulation_year) %}
  {#-
    Generate deferral escalation events for E068A fused event generation

    This macro extracts deferral escalation event logic from
    int_deferral_rate_escalation_events.sql and optimizes it for
    in-memory CTE processing within the fused fct_yearly_events model.

    Parameters:
    - cohort_table: CTE name containing cohort data with RNG values
    - simulation_year: Current simulation year

    Returns: SQL for deferral escalation events CTE
  #}

  WITH deferral_escalation_events_base AS (
    SELECT
      e.employee_id,
      e.employee_ssn,
      'deferral_escalation' AS event_type,
      e.simulation_year,
      e.effective_date,
      e.event_details,
      CAST(NULL AS DECIMAL(18,2)) AS compensation_amount,
      CAST(NULL AS DECIMAL(18,2)) AS previous_compensation,
      e.new_deferral_rate::DECIMAL(5,4) AS employee_deferral_rate,
      e.previous_deferral_rate::DECIMAL(5,4) AS prev_employee_deferral_rate,
      e.current_age AS employee_age,
      e.current_tenure AS employee_tenure,
      e.level_id,
      e.age_band,
      e.tenure_band,
      CAST(NULL AS DECIMAL(10,4)) AS event_probability,
      'deferral_escalation' AS event_category
    FROM {{ ref('int_deferral_rate_escalation_events') }} e
    WHERE e.simulation_year = {{ simulation_year }}
  )

  SELECT
    employee_id,
    employee_ssn,
    event_type,
    simulation_year,
    effective_date,
    event_details,
    compensation_amount,
    previous_compensation,
    employee_deferral_rate,
    prev_employee_deferral_rate,
    employee_age,
    employee_tenure,
    level_id,
    age_band,
    tenure_band,
    event_probability,
    event_category
  FROM deferral_escalation_events_base

{% endmacro %}
