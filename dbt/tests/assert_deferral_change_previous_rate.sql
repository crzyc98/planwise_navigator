-- D2/D3 and canonical state contract. Rates above the voluntary/IRS cap may
-- decrease toward it; an increase must never breach it or reverse direction.
WITH changes AS (
  SELECT employee_id, scenario_id, plan_design_id, simulation_year, effective_date,
    event_category, employee_deferral_rate, prev_employee_deferral_rate,
    COUNT(*) OVER (PARTITION BY scenario_id, employee_id, simulation_year) AS change_count
  FROM {{ ref('fct_yearly_events') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND scenario_id = '{{ var("scenario_id", "default") }}'
    AND event_type = {{ evt_deferral_change() }}
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
CROSS JOIN irs_limits il
WHERE state.employee_id IS NULL
  OR events.prev_employee_deferral_rate IS DISTINCT FROM state.rate_before_voluntary_change
  OR events.employee_deferral_rate IS DISTINCT FROM state.current_deferral_rate
  OR events.change_count <> 1
  OR events.employee_deferral_rate IS NULL
  OR events.employee_deferral_rate <= 0
  OR (events.event_category = 'proactive_decrease' AND (
    events.employee_deferral_rate >= events.prev_employee_deferral_rate
    OR events.employee_deferral_rate < LEAST(0.01, events.prev_employee_deferral_rate)))
  OR (events.event_category = 'proactive_increase' AND (
    events.employee_deferral_rate <= events.prev_employee_deferral_rate
    OR events.employee_deferral_rate > {{ deferral_change_cap('w.employee_compensation',
      'COALESCE(' ~ var('simulation_year') ~ ' - YEAR(w.employee_birth_date), w.current_age)') }}))
  OR events.event_category NOT IN ('proactive_increase', 'proactive_decrease')
  OR EXISTS (
    SELECT 1 FROM {{ ref('fct_yearly_events') }} later
    WHERE later.scenario_id = events.scenario_id
      AND later.employee_id = events.employee_id
      AND later.simulation_year = events.simulation_year
      AND later.event_type IN ('enrollment', 'benefit_enrollment', 'enrollment_change',
        'deferral_escalation', 'deferral_match_response')
      AND later.effective_date > events.effective_date
  )
