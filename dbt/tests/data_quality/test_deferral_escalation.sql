/*
  Data Quality Singular Test for Deferral Rate Escalation (Epic E035)

  Returns failing rows from fct_yearly_events where deferral_escalation events
  violate any of these rules:
  - employee_deferral_rate must be <= 0.10 (cap)
  - no duplicate employee_id + simulation_year combinations
  - employee_id must not be null
  - event_details must not be null

  Test passes when zero rows are returned.
  Handles the case where no escalation events exist (passes with zero rows).
*/

{% set simulation_year = var('simulation_year', 2025) %}
{% set esc_cap = var('deferral_escalation_cap', 0.10) %}
{% set plan_design_parameters_config = var('plan_design_parameters', none) %}

WITH parameter_rows AS (
{% if plan_design_parameters_config %}
  {{ get_plan_design_parameters(plan_design_parameters_config) }}
{% else %}
  SELECT
    '{{ var('plan_design_id', 'default') }}'::VARCHAR AS plan_design_id,
    {{ esc_cap }}::DECIMAL(10,6) AS deferral_escalation_cap
{% endif %}
),

escalation_events AS (
  SELECT
    event.employee_id,
    event.simulation_year,
    event.effective_date,
    event.employee_deferral_rate,
    event.prev_employee_deferral_rate,
    event.event_details,
    parameters.deferral_escalation_cap
  FROM {{ ref('fct_yearly_events') }} event
  INNER JOIN parameter_rows parameters
    ON event.plan_design_id = parameters.plan_design_id
  WHERE event.event_type = 'deferral_escalation'
    AND event.simulation_year = {{ simulation_year }}
),

-- Failure: rate exceeds cap
rate_violations AS (
  SELECT
    employee_id,
    simulation_year,
    'rate_exceeds_cap' AS violation_type,
    employee_deferral_rate AS violation_value
  FROM escalation_events
  WHERE employee_deferral_rate > deferral_escalation_cap + 0.0001
),

-- Failure: duplicate employee + year
duplicate_violations AS (
  SELECT
    employee_id,
    simulation_year,
    'duplicate_employee_year' AS violation_type,
    n::DOUBLE AS violation_value
  FROM (
    SELECT employee_id, simulation_year, COUNT(*) AS n
    FROM escalation_events
    GROUP BY employee_id, simulation_year
    HAVING COUNT(*) > 1
  ) dups
),

-- Failure: null employee_id
null_employee_violations AS (
  SELECT
    employee_id,
    simulation_year,
    'null_employee_id' AS violation_type,
    NULL::DOUBLE AS violation_value
  FROM escalation_events
  WHERE employee_id IS NULL
),

-- Failure: null event_details
null_details_violations AS (
  SELECT
    employee_id,
    simulation_year,
    'null_event_details' AS violation_type,
    NULL::DOUBLE AS violation_value
  FROM escalation_events
  WHERE event_details IS NULL
)

SELECT * FROM rate_violations
UNION ALL
SELECT * FROM duplicate_violations
UNION ALL
SELECT * FROM null_employee_violations
UNION ALL
SELECT * FROM null_details_violations
