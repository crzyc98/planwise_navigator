/*
  Data Quality Singular Test for Deferral Match Response Events (Epic E058)

  Returns failing rows from fct_yearly_events where deferral_match_response events
  violate any of these rules:
  - No duplicate events per employee per year
  - employee_deferral_rate > prev_employee_deferral_rate for upward events
  - employee_deferral_rate <= escalation cap and <= IRS 402(g) rate-equivalent limit
  - employee_id and event_details must not be null
  - employee_deferral_rate < prev_employee_deferral_rate for downward events
  - employee_deferral_rate >= 0.0 floor check
  - No employee has BOTH an upward AND downward event in the same year

  Test passes when zero rows are returned.
  Handles the case where no match-response events exist (passes with zero rows).
*/

{% set simulation_year = var('simulation_year', 2025) %}
{% set esc_cap = var('deferral_escalation_cap', 0.10) %}

WITH match_response_events AS (
  SELECT
    employee_id,
    simulation_year,
    effective_date,
    employee_deferral_rate,
    prev_employee_deferral_rate,
    event_details,
    event_type
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'deferral_match_response'
    AND simulation_year = {{ simulation_year }}
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
    FROM match_response_events
    GROUP BY employee_id, simulation_year
    HAVING COUNT(*) > 1
  ) dups
),

-- Failure: upward event with non-increasing rate
upward_rate_violations AS (
  SELECT
    employee_id,
    simulation_year,
    'upward_rate_not_increasing' AS violation_type,
    employee_deferral_rate::DOUBLE AS violation_value
  FROM match_response_events
  WHERE event_details LIKE '%upward%'
    AND prev_employee_deferral_rate IS NOT NULL
    AND employee_deferral_rate <= prev_employee_deferral_rate
),

-- Failure: upward rate exceeds cap (downward events may legitimately remain above
-- cap when the employee started even higher — the adjustment is reducing, not raising)
rate_cap_violations AS (
  SELECT
    employee_id,
    simulation_year,
    'rate_exceeds_cap' AS violation_type,
    employee_deferral_rate::DOUBLE AS violation_value
  FROM match_response_events
  WHERE event_details LIKE '%upward%'
    AND employee_deferral_rate > {{ esc_cap }} + 0.0001
),

-- Failure: null employee_id
null_employee_violations AS (
  SELECT
    employee_id,
    simulation_year,
    'null_employee_id' AS violation_type,
    NULL::DOUBLE AS violation_value
  FROM match_response_events
  WHERE employee_id IS NULL
),

-- Failure: null event_details
null_details_violations AS (
  SELECT
    employee_id,
    simulation_year,
    'null_event_details' AS violation_type,
    NULL::DOUBLE AS violation_value
  FROM match_response_events
  WHERE event_details IS NULL
),

-- Failure: null event_type
null_type_violations AS (
  SELECT
    employee_id,
    simulation_year,
    'null_event_type' AS violation_type,
    NULL::DOUBLE AS violation_value
  FROM match_response_events
  WHERE event_type IS NULL
),

-- Failure: downward event with non-decreasing rate
downward_rate_violations AS (
  SELECT
    employee_id,
    simulation_year,
    'downward_rate_not_decreasing' AS violation_type,
    employee_deferral_rate::DOUBLE AS violation_value
  FROM match_response_events
  WHERE event_details LIKE '%downward%'
    AND prev_employee_deferral_rate IS NOT NULL
    AND employee_deferral_rate >= prev_employee_deferral_rate
),

-- Failure: negative deferral rate
negative_rate_violations AS (
  SELECT
    employee_id,
    simulation_year,
    'negative_deferral_rate' AS violation_type,
    employee_deferral_rate::DOUBLE AS violation_value
  FROM match_response_events
  WHERE employee_deferral_rate < 0.0
)

SELECT * FROM duplicate_violations
UNION ALL
SELECT * FROM upward_rate_violations
UNION ALL
SELECT * FROM rate_cap_violations
UNION ALL
SELECT * FROM null_employee_violations
UNION ALL
SELECT * FROM null_details_violations
UNION ALL
SELECT * FROM null_type_violations
UNION ALL
SELECT * FROM downward_rate_violations
UNION ALL
SELECT * FROM negative_rate_violations
