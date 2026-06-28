{{ config(severity='error', tags=['data_quality']) }}

{#
  Feature 101 follow-up (issue #336, item 1) — single-window assumption guard.

  The same-year enroll → opt-out proration in `int_employee_contributions`
  credits a SINGLE active-enrollment window (latest enrollment event →
  opt-out event). That is correct only while an employee cannot enroll,
  opt out, and re-enroll within one simulation year. The enrollment state
  accumulator enforces this today (no same-year re-enrollment), so this test
  asserts the assumption still holds.

  Returns one row per violating employee-year; the test passes when empty.
  A violation means a multi-cycle case now exists and the window CTE must be
  extended to sum all active sub-windows (see issue #336).

  A violation is any employee-year with:
    - more than one enrollment event, OR
    - more than one opt-out enrollment_change, OR
    - an enrollment event dated AFTER an opt-out event (re-enrollment).
#}

WITH enrollment_activity AS (
    SELECT
        employee_id,
        simulation_year,
        COUNT(*) FILTER (WHERE event_type = {{ evt_enrollment() }}) AS enroll_count,
        COUNT(*) FILTER (
            WHERE event_type = {{ evt_enrollment_change() }}
              AND LOWER(event_details) LIKE '%opt-out%'
        ) AS opt_out_count,
        MAX(CASE WHEN event_type = {{ evt_enrollment() }} THEN effective_date::DATE END) AS last_enroll_date,
        MIN(CASE WHEN event_type = {{ evt_enrollment_change() }}
                  AND LOWER(event_details) LIKE '%opt-out%' THEN effective_date::DATE END) AS first_opt_out_date
    FROM {{ ref('fct_yearly_events') }}
    WHERE {{ is_enrollment_event('event_type') }}
      AND employee_id IS NOT NULL
    GROUP BY employee_id, simulation_year
)

SELECT
    employee_id,
    simulation_year,
    enroll_count,
    opt_out_count,
    last_enroll_date,
    first_opt_out_date
FROM enrollment_activity
WHERE enroll_count > 1
   OR opt_out_count > 1
   OR (last_enroll_date IS NOT NULL
       AND first_opt_out_date IS NOT NULL
       AND last_enroll_date > first_opt_out_date)
