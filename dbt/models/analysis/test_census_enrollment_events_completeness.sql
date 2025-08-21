{{
  config(
    materialized='view',
    tags=['data_quality', 'test', 'census_enrollment']
  )
}}

-- Post-Implementation Validation Test for Census Enrollment Events
-- This test should return zero rows after Epic E051 implementation
-- Any returned rows indicate census enrollment events missing from fct_yearly_events

WITH missing_census_events AS (
  SELECT DISTINCT
    s.employee_id,
    s.employee_deferral_rate AS expected_deferral_rate,
    s.effective_date AS expected_enrollment_date,
    s.event_source,
    'MISSING_FROM_YEARLY_EVENTS' AS issue_type
  FROM {{ ref('int_synthetic_baseline_enrollment_events') }} s
  LEFT JOIN {{ ref('fct_yearly_events') }} y
    ON s.employee_id = y.employee_id
    AND y.event_type = 'enrollment'
    AND y.simulation_year = s.simulation_year
  WHERE y.employee_id IS NULL
    AND s.simulation_year = {{ var('simulation_year', 2025) }}
    AND s.event_type = 'enrollment'
)

SELECT
  COUNT(*) AS missing_events_count,
  ROUND(AVG(expected_deferral_rate), 4) AS avg_missing_deferral_rate,
  MIN(expected_enrollment_date) AS earliest_missing_date,
  MAX(expected_enrollment_date) AS latest_missing_date,
  'Expected: 0 after E051 implementation' AS validation_note
FROM missing_census_events

-- Post-implementation, this query should return:
-- missing_events_count: 0
-- All other fields: NULL
-- If missing_events_count > 0, Epic E051 implementation is incomplete
