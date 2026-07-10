{{ config(severity='error', tags=['enrollment', 'data_quality']) }}

-- A census participant without an intervening opt-out must not receive a new
-- enrollment event in a later simulation year.
WITH census_participants AS (
  SELECT employee_id
  FROM {{ ref('int_baseline_workforce') }}
  WHERE is_enrolled_at_census
),
later_enrollments AS (
  SELECT e.employee_id, e.simulation_year, e.event_id
  FROM {{ ref('fct_yearly_events') }} e
  JOIN census_participants c ON e.employee_id = c.employee_id
  WHERE e.event_type = 'enrollment'
    AND e.simulation_year > {{ var('simulation_start_year') }}
    AND NOT EXISTS (
      SELECT 1 FROM {{ ref('fct_yearly_events') }} prior
      WHERE prior.employee_id = e.employee_id
        AND prior.scenario_id = e.scenario_id
        AND prior.plan_design_id = e.plan_design_id
        AND prior.simulation_year < e.simulation_year
        AND prior.event_type = 'enrollment_change'
        AND LOWER(COALESCE(prior.event_details, '')) LIKE '%opt-out%'
    )
)
SELECT * FROM later_enrollments
