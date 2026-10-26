-- D3: the voluntary change starts from the canonical post-escalation rate.
-- Restrict both inputs to this year; with no deferral changes this is vacuous.
SELECT
  events.employee_id,
  events.simulation_year,
  events.prev_employee_deferral_rate,
  state.rate_before_voluntary_change
FROM {{ ref('fct_yearly_events') }} events
LEFT JOIN {{ ref('int_deferral_rate_state_accumulator') }} state
  ON events.scenario_id = state.scenario_id
  AND events.plan_design_id = state.plan_design_id
  AND events.employee_id = state.employee_id
  AND events.simulation_year = state.simulation_year
  AND state.simulation_year = {{ var('simulation_year') }}
WHERE events.simulation_year = {{ var('simulation_year') }}
  AND events.scenario_id = '{{ var("scenario_id", "default") }}'
  AND events.event_type = {{ evt_deferral_change() }}
  AND (state.employee_id IS NULL
    OR events.prev_employee_deferral_rate IS DISTINCT FROM state.rate_before_voluntary_change)
