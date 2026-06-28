{{ config(severity='error', tags=['data_quality']) }}

{#
  Issue #316 — per-employee auto-escalation opt-out guard.

  Employees flagged `auto_escalation_opt_out = TRUE` in the census must never
  generate a `deferral_escalation` event in any simulation year. The escalation
  event generator derives `in_auto_escalation_program` from this flag, so an
  opted-out employee should produce zero escalation events.

  Returns one row per violating (employee, year); the test passes when empty.
#}

SELECT
    e.employee_id,
    e.simulation_year,
    COUNT(*) AS escalation_event_count
FROM {{ ref('fct_yearly_events') }} e
JOIN {{ ref('stg_census_data') }} c
    ON e.employee_id = c.employee_id
WHERE e.event_type = 'deferral_escalation'
  AND c.auto_escalation_opt_out = TRUE
GROUP BY e.employee_id, e.simulation_year
