{{ config(severity='error', tags=['enrollment_validation']) }}

-- The latest rate decision after a sweep must reach both state accumulators.
WITH swept AS (
  SELECT employee_id, scenario_id, simulation_year, effective_date
  FROM {{ ref('fct_yearly_events') }}
  WHERE (event_type = 'enrollment' OR event_category = 'reenrollment_sweep')
    AND event_details LIKE 'Re-enrollment sweep - %'
    AND simulation_year = {{ var('simulation_year') }}
    AND scenario_id = '{{ var("scenario_id", "default") }}'
), latest_decision AS (
  SELECT
    e.employee_id, e.scenario_id, e.simulation_year,
    e.employee_deferral_rate,
    e.event_type = 'enrollment_change' AND LOWER(e.event_details) LIKE '%opt-out%' AS opted_out
  FROM {{ ref('fct_yearly_events') }} e
  INNER JOIN swept s USING (employee_id, scenario_id, simulation_year)
  WHERE e.effective_date >= s.effective_date
    AND e.event_type IN ('enrollment', 'enrollment_change', 'deferral_escalation', 'deferral_match_response', 'deferral_change')
    AND e.employee_deferral_rate IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (
    PARTITION BY e.scenario_id, e.employee_id, e.simulation_year
    ORDER BY e.effective_date DESC, e.event_sequence DESC, e.event_id DESC
  ) = 1
)
SELECT e.employee_id, e.simulation_year, e.employee_deferral_rate
FROM latest_decision e
LEFT JOIN {{ ref('int_enrollment_state_accumulator') }} enrollment
  USING (employee_id, scenario_id, simulation_year)
LEFT JOIN {{ ref('int_deferral_rate_state_accumulator') }} deferral
  USING (employee_id, scenario_id, simulation_year)
WHERE enrollment.enrollment_status IS DISTINCT FROM NOT e.opted_out
  OR deferral.is_enrolled_flag IS DISTINCT FROM NOT e.opted_out
  OR deferral.current_deferral_rate IS DISTINCT FROM e.employee_deferral_rate
