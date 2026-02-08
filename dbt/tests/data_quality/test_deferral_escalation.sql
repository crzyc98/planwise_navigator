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

WITH escalation_events AS (
  SELECT
    employee_id,
    simulation_year,
    effective_date,
    employee_deferral_rate,
    prev_employee_deferral_rate,
    event_details
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'deferral_escalation'
    AND simulation_year = {{ simulation_year }}
),

-- Failure: rate exceeds cap
rate_violations AS (
  SELECT
    employee_id,
    simulation_year,
    'rate_exceeds_cap' AS violation_type,
    employee_deferral_rate AS violation_value
  FROM escalation_events
  WHERE employee_deferral_rate > {{ esc_cap }} + 0.0001
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
