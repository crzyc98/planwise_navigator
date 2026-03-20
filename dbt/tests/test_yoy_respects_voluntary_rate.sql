-- Test: Year-over-year voluntary enrollment respects voluntary_enrollment_rate
-- When voluntary_enrollment_rate is set to 0.0, no year-over-year conversion
-- events should be generated. This test returns rows that violate the rule
-- (i.e., it passes when the query returns zero rows).

SELECT
  employee_id,
  simulation_year,
  event_category
FROM {{ ref('int_enrollment_events') }}
WHERE event_category = 'year_over_year_voluntary'
  AND simulation_year = {{ var('simulation_year') }}
  AND {{ var('voluntary_enrollment_rate', 1.0) }} = 0.0
