-- D2/D3 and canonical state contract. Rates above the voluntary/IRS cap may
-- decrease toward it; an increase must never breach it or reverse direction.
{{ config(severity='error') }}
WITH changes AS (
  SELECT employee_id, scenario_id, plan_design_id, simulation_year, effective_date,
    event_category, employee_deferral_rate, prev_employee_deferral_rate,
    COUNT(*) OVER (PARTITION BY scenario_id, employee_id, simulation_year) AS change_count
  FROM {{ ref('fct_yearly_events') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND scenario_id = '{{ var("scenario_id", "default") }}'
    AND event_type = {{ evt_deferral_change() }}
    AND event_category <> 'reenrollment_sweep'
),
irs_limits AS (
  SELECT base_limit, catch_up_limit, catch_up_age_threshold,
    super_catch_up_limit, super_catch_up_age_min, super_catch_up_age_max
  FROM {{ ref('config_irs_limits') }}
  ORDER BY CASE WHEN limit_year = {{ var('simulation_year') }} THEN 0 ELSE 1 END,
    ABS(limit_year - {{ var('simulation_year') }})
  LIMIT 1
)
SELECT events.employee_id, events.simulation_year,
  events.prev_employee_deferral_rate, state.rate_before_voluntary_change
FROM changes events
LEFT JOIN {{ ref('int_deferral_rate_state_accumulator') }} state
  ON events.scenario_id = state.scenario_id
  AND events.plan_design_id = state.plan_design_id
  AND events.employee_id = state.employee_id
  AND events.simulation_year = state.simulation_year
LEFT JOIN {{ ref('int_employee_compensation_by_year') }} w
  ON events.employee_id = w.employee_id AND events.simulation_year = w.simulation_year
LEFT JOIN {{ ref('int_deferral_rate_state_accumulator') }} previous_state
  ON events.scenario_id = previous_state.scenario_id
  AND events.employee_id = previous_state.employee_id
  AND events.simulation_year - 1 = previous_state.simulation_year
CROSS JOIN irs_limits il
WHERE state.employee_id IS NULL
  OR events.prev_employee_deferral_rate IS DISTINCT FROM state.rate_before_voluntary_change
  OR events.employee_deferral_rate IS DISTINCT FROM state.current_deferral_rate
  OR events.change_count <> 1
  OR EXISTS (
    SELECT 1 FROM {{ ref('fct_yearly_events') }} opted_out
    WHERE opted_out.scenario_id = events.scenario_id
      AND opted_out.employee_id = events.employee_id
      AND opted_out.simulation_year = events.simulation_year
      AND opted_out.event_type = 'enrollment_change'
      AND COALESCE(opted_out.employee_deferral_rate, 0) = 0
  )
  OR events.employee_deferral_rate IS NULL
  OR events.employee_deferral_rate < 0
  OR (events.event_category <> 'stop' AND events.employee_deferral_rate = 0)
  OR (events.event_category = 'stop' AND (
    events.employee_deferral_rate <> 0 OR events.prev_employee_deferral_rate <= 0
    OR state.is_enrolled_flag IS DISTINCT FROM TRUE
    OR state.last_nonzero_deferral_rate IS DISTINCT FROM events.prev_employee_deferral_rate))
  OR (events.event_category = 'restart' AND (
    previous_state.is_enrolled_flag IS DISTINCT FROM TRUE
    OR previous_state.current_deferral_rate IS DISTINCT FROM 0
    OR previous_state.last_nonzero_deferral_rate IS NULL
    OR events.prev_employee_deferral_rate <> 0
    OR state.is_enrolled_flag IS DISTINCT FROM TRUE
    OR NOT {{ has_unreversed_stop(ref('fct_yearly_events'), 'events.employee_id',
      'events.scenario_id', 'events.simulation_year') }}
    OR events.employee_deferral_rate IS DISTINCT FROM CAST(LEAST(
      previous_state.last_nonzero_deferral_rate,
      {{ deferral_change_cap('w.employee_compensation',
        'COALESCE(' ~ var('simulation_year') ~ ' - YEAR(w.employee_birth_date), w.current_age)') }}
    ) AS DECIMAL(5,4))))
  OR (events.event_category IN ('proactive_decrease', 'aip_response_decrease') AND (
    events.employee_deferral_rate >= events.prev_employee_deferral_rate
    OR events.employee_deferral_rate < LEAST(0.01, events.prev_employee_deferral_rate)))
  OR (events.event_category = 'proactive_increase' AND (
    events.employee_deferral_rate <= events.prev_employee_deferral_rate
    OR events.employee_deferral_rate > {{ deferral_change_cap('w.employee_compensation',
      'COALESCE(' ~ var('simulation_year') ~ ' - YEAR(w.employee_birth_date), w.current_age)') }}))
  OR events.event_category NOT IN ('proactive_increase', 'proactive_decrease', 'aip_response_decrease', 'stop', 'restart')
  OR events.effective_date IS NULL
  OR events.effective_date <= MAKE_DATE(events.simulation_year, 1, 1)
  OR events.effective_date > MAKE_DATE(events.simulation_year, 12, 31)
  OR EXISTS (
    SELECT 1 FROM {{ ref('int_employee_termination_dates') }} termination
    WHERE termination.employee_id = events.employee_id
      AND termination.simulation_year = events.simulation_year
      AND events.effective_date > termination.termination_date
  )
  OR (events.event_category = 'aip_response_decrease' AND NOT EXISTS (
    SELECT 1 FROM {{ ref('fct_yearly_events') }} escalation
    WHERE escalation.scenario_id = events.scenario_id
      AND escalation.employee_id = events.employee_id
      AND escalation.simulation_year = events.simulation_year
      AND escalation.event_type = 'deferral_escalation'
      AND events.effective_date > escalation.effective_date
      AND events.effective_date <= CAST(escalation.effective_date AS DATE)
        + {{ var('deferral_rate_changes_post_escalation_decrease_window_days', 90) }}
  ))
  OR (events.event_category = 'proactive_decrease' AND EXISTS (
    SELECT 1 FROM {{ ref('fct_yearly_events') }} escalation
    WHERE escalation.scenario_id = events.scenario_id
      AND escalation.employee_id = events.employee_id
      AND escalation.simulation_year = events.simulation_year
      AND escalation.event_type = 'deferral_escalation'
  ))
  {% if var('deferral_rate_changes_enabled', false) and var('deferral_rate_changes_post_escalation_decrease_leaves_escalation', false) %}
  OR (events.event_category = 'aip_response_decrease' AND state.aip_participant)
  {% endif %}
  OR EXISTS (
    SELECT 1 FROM {{ ref('fct_yearly_events') }} later
    WHERE later.scenario_id = events.scenario_id
      AND later.employee_id = events.employee_id
      AND later.simulation_year = events.simulation_year
      AND later.event_type IN ('enrollment', 'benefit_enrollment', 'enrollment_change',
        'deferral_escalation', 'deferral_match_response')
      AND later.effective_date >= events.effective_date
  )
