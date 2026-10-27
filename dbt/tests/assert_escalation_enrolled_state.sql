{{ config(severity='error', tags=['escalation', 'enrollment_validation']) }}

-- Missing state is also invalid: opted-out employees can drop out of the
-- deferral accumulator in later years, so an inner join would hide the bug.
SELECT
  event.employee_id,
  event.simulation_year,
  state.is_enrolled_flag,
  state.current_deferral_rate
FROM {{ ref('fct_yearly_events') }} event
LEFT JOIN {{ ref('int_deferral_rate_state_accumulator') }} state
  ON state.employee_id = event.employee_id
  AND state.scenario_id = event.scenario_id
  AND state.plan_design_id = event.plan_design_id
  AND state.simulation_year = event.simulation_year
WHERE event.event_type = 'deferral_escalation'
  AND event.simulation_year = {{ var('simulation_year') }}
  AND event.scenario_id = '{{ var('scenario_id', 'default') }}'
  AND (
    state.employee_id IS NULL
    OR NOT state.is_enrolled_flag
    OR (state.current_deferral_rate = 0 AND state.rate_source = 'opt_out')
  )
