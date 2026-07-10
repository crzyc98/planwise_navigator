{{
  config(
    severity='error',
    tags=['data_quality', 'event_validation']
  )
}}

/*
  Event sequences must advance chronologically. On the same effective date,
  event_priority defines the deterministic ordering. This detects both a hire
  preceding a later termination and same-day priority inversions.
*/

WITH sequenced_events AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    simulation_year,
    event_type,
    effective_date,
    event_sequence,
    {{ event_priority('event_type') }} AS priority,
    LAG(effective_date) OVER (
      PARTITION BY scenario_id, plan_design_id, employee_id, simulation_year
      ORDER BY event_sequence
    ) AS previous_effective_date,
    LAG({{ event_priority('event_type') }}) OVER (
      PARTITION BY scenario_id, plan_design_id, employee_id, simulation_year
      ORDER BY event_sequence
    ) AS previous_priority
  FROM {{ ref('fct_yearly_events') }}
)

SELECT
  scenario_id,
  plan_design_id,
  employee_id,
  simulation_year,
  event_type,
  effective_date,
  event_sequence,
  previous_effective_date,
  priority,
  previous_priority
FROM sequenced_events
WHERE effective_date < previous_effective_date
   OR (
    effective_date = previous_effective_date
    AND priority < previous_priority
  )
