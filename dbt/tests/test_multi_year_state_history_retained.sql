{{ config(severity='error', tags=['data_quality']) }}

-- Completed simulation years must remain represented in the temporal
-- accumulators; a later-year refresh must not erase prior history.
WITH required_years AS (
  SELECT year AS simulation_year
  FROM range({{ var('simulation_start_year') }}, {{ var('simulation_year') }} + 1) AS years(year)
),
missing_enrollment_years AS (
  SELECT required_years.simulation_year
  FROM required_years
  LEFT JOIN {{ ref('int_enrollment_state_accumulator') }} accumulator
    ON accumulator.simulation_year = required_years.simulation_year
  GROUP BY required_years.simulation_year
  HAVING COUNT(accumulator.employee_id) = 0
)
SELECT * FROM missing_enrollment_years
