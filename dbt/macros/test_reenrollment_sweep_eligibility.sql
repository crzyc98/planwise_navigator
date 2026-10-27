{# Audit the published election against state available before event generation. #}
{% test reenrollment_sweep_eligibility(model) %}
WITH swept AS (
  SELECT employee_id, scenario_id, simulation_year, effective_date
  FROM {{ model }}
  WHERE event_type = 'enrollment' AND event_details LIKE 'Re-enrollment sweep - %'
    AND simulation_year = {{ var('simulation_year') }}
    AND scenario_id = '{{ var('scenario_id', 'default') }}'
), checked AS (
  SELECT s.employee_id, s.simulation_year, s.effective_date,
    (SELECT MAX(o.effective_date) FROM {{ ref('fct_yearly_events') }} o
      WHERE o.employee_id = s.employee_id AND o.scenario_id = s.scenario_id
        AND o.simulation_year < s.simulation_year
        AND o.event_type = 'enrollment_change'
        AND LOWER(o.event_details) LIKE '%opt-out%') AS latest_opt_out_date,
    COALESCE(
      (SELECT e.employee_deferral_rate FROM {{ ref('fct_yearly_events') }} e
        WHERE e.employee_id = s.employee_id AND e.scenario_id = s.scenario_id
          AND e.simulation_year < s.simulation_year
          AND e.effective_date >= MAKE_DATE(s.simulation_year, 1, 1)
          AND e.effective_date <= s.effective_date
          AND e.employee_deferral_rate IS NOT NULL
          AND e.event_type IN ('enrollment', 'benefit_enrollment', 'enrollment_change',
            'deferral_escalation', 'deferral_match_response', 'deferral_change')
        ORDER BY e.effective_date DESC, e.event_sequence DESC, e.event_id DESC LIMIT 1),
      d.current_deferral_rate, b.employee_deferral_rate, 0) AS rate_at_sweep
  FROM swept s
  LEFT JOIN {{ ref('int_deferral_rate_state_accumulator') }} d
    ON s.employee_id = d.employee_id AND s.scenario_id = d.scenario_id
    AND d.simulation_year = s.simulation_year - 1
  LEFT JOIN {{ ref('int_baseline_workforce') }} b ON s.employee_id = b.employee_id
)
SELECT employee_id, simulation_year, effective_date, latest_opt_out_date, rate_at_sweep
FROM checked
WHERE latest_opt_out_date >= effective_date OR rate_at_sweep > 0
{% endtest %}
