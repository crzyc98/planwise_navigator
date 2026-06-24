{{ config(severity='error', tags=['data_quality']) }}

{#
  Feature 101 — Same-Year Enroll → Opt-Out Window guard.

  For employees who voluntarily enroll AND opt out within the SAME simulation
  year, assert the two invariants together:
    (a) year-end status is not-participating with a zero deferral rate
        (feature 095 — must not regress), AND
    (b) they are credited a NON-ZERO active-window employee contribution
        (feature 101 — the fix), proportional to their enrolled window.

  Returns one row per violating employee-year; the test passes when empty.

  Severity is configured in schema.yml: `warn` until the crediting logic lands
  (so it does not block US1/US2 delivery), then `error` (US3, enforcing).
#}

WITH enroll_optout AS (
    SELECT
        employee_id,
        simulation_year,
        MAX(CASE WHEN event_type = {{ evt_enrollment() }} THEN effective_date::DATE END) AS enroll_date,
        MAX(CASE WHEN event_type = {{ evt_enrollment_change() }}
                  AND LOWER(event_details) LIKE '%opt-out%' THEN effective_date::DATE END) AS opt_out_date
    FROM {{ ref('fct_yearly_events') }}
    WHERE {{ is_enrollment_event('event_type') }}
      AND employee_id IS NOT NULL
    GROUP BY employee_id, simulation_year
),

same_year_enroll_optout AS (
    SELECT employee_id, simulation_year
    FROM enroll_optout
    WHERE enroll_date IS NOT NULL
      AND opt_out_date IS NOT NULL
      AND opt_out_date >= enroll_date
)

SELECT
    s.employee_id,
    s.simulation_year,
    snap.participation_status,
    snap.current_deferral_rate,
    contrib.active_enrollment_days,
    contrib.annual_contribution_amount
FROM same_year_enroll_optout s
LEFT JOIN {{ ref('fct_workforce_snapshot') }} snap
    ON s.employee_id = snap.employee_id
   AND s.simulation_year = snap.simulation_year
LEFT JOIN {{ ref('int_employee_contributions') }} contrib
    ON s.employee_id = contrib.employee_id
   AND s.simulation_year = contrib.simulation_year
WHERE
    -- (a) year-end status must remain not-participating at rate 0
    COALESCE(snap.participation_status, 'participating') <> 'not_participating'
    OR COALESCE(snap.current_deferral_rate, 1) <> 0
    -- (b) active-window contribution must be credited when the window has enrolled
    -- days (a degenerate zero-day window correctly yields $0 — FR-007).
    OR (COALESCE(contrib.annual_contribution_amount, 0) <= 0
        AND COALESCE(contrib.active_enrollment_days, 0) > 0)
