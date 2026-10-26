{{ config(severity='error', tags=['data_quality']) }}

-- AIP elections persist; a new Easy Enroll package can elect a nonmember.
WITH membership_violations AS (
  SELECT
    current_state.employee_id,
    current_state.simulation_year,
    'membership_changed' AS violation_type
  FROM {{ ref('int_deferral_rate_state_accumulator') }} current_state
  INNER JOIN {{ ref('int_deferral_rate_state_accumulator') }} previous_state
    ON current_state.scenario_id = previous_state.scenario_id
    AND current_state.plan_design_id = previous_state.plan_design_id
    AND current_state.employee_id = previous_state.employee_id
    AND current_state.simulation_year = previous_state.simulation_year + 1
  WHERE current_state.aip_participant IS DISTINCT FROM previous_state.aip_participant
    {% if var('easy_enroll_enabled', false) %}
    AND NOT (current_state.aip_participant AND
      {{ easy_enroll_member(ref('fct_yearly_events'), 'current_state.employee_id',
        'current_state.simulation_year', 'current_state.scenario_id') }})
    {% endif %}

  UNION ALL

  SELECT
    state.employee_id,
    state.simulation_year,
    'census_opt_out_member' AS violation_type
  FROM {{ ref('int_deferral_rate_state_accumulator') }} state
  INNER JOIN {{ ref('stg_census_data') }} census
    ON state.employee_id = census.employee_id
  WHERE census.auto_escalation_opt_out = TRUE
    AND state.aip_participant = TRUE
    {% if var('easy_enroll_enabled', false) %}
    AND NOT {{ easy_enroll_member(ref('fct_yearly_events'), 'state.employee_id',
      'state.simulation_year', 'state.scenario_id') }}
    {% endif %}
),

-- Some published events have no accumulator row (also present on main).
-- Resolve their membership with the same prior-state/initial-election rule.
escalation_violations AS (
  SELECT
    event.employee_id,
    event.simulation_year,
    'escalation_without_membership' AS violation_type
  FROM {{ ref('fct_yearly_events') }} event
  LEFT JOIN {{ ref('int_deferral_rate_state_accumulator') }} state
    ON event.scenario_id = state.scenario_id
    AND event.plan_design_id = state.plan_design_id
    AND event.employee_id = state.employee_id
    AND event.simulation_year = state.simulation_year
  LEFT JOIN {{ ref('int_deferral_rate_state_accumulator') }} previous_state
    ON event.scenario_id = previous_state.scenario_id
    AND event.plan_design_id = previous_state.plan_design_id
    AND event.employee_id = previous_state.employee_id
    AND event.simulation_year = previous_state.simulation_year + 1
  LEFT JOIN {{ ref('stg_census_data') }} census
    ON event.employee_id = census.employee_id
  WHERE event.event_type = 'deferral_escalation'
    AND NOT COALESCE(state.aip_participant, previous_state.aip_participant,
      {{ aip_initial_membership(var('deferral_escalation_mode', 'automatic'), 'census.auto_escalation_opt_out', 'event.employee_id') }})
    {% if var('easy_enroll_enabled', false) %}
    AND NOT {{ easy_enroll_member(ref('fct_yearly_events'), 'event.employee_id',
      'event.simulation_year', 'event.scenario_id') }}
    {% endif %}
)

SELECT employee_id, simulation_year, violation_type FROM membership_violations
UNION ALL
SELECT employee_id, simulation_year, violation_type FROM escalation_violations
