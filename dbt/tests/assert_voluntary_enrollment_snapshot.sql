{{
  config(
    severity='error',
    tags=['data_quality', 'enrollment', 'voluntary', 'snapshot']
  )
}}

-- FR-009 / FR-010 (feature 095): Voluntary enrollees must appear as participating
-- with their selected deferral rate in fct_workforce_snapshot.
--
-- Permanent regression guard for the int_deferral_rate_state_accumulator fix:
-- a previously-unenrolled employee who voluntarily (incl. proactive / year-over-year)
-- enrolls and does NOT opt out in the same year MUST be 'participating' with a
-- non-zero deferral rate in the snapshot. Returns offending rows (build fails on any).

WITH voluntary_enrollments AS (
  SELECT DISTINCT
    employee_id,
    simulation_year
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'enrollment'
    AND event_category IN (
      'voluntary_enrollment',
      'proactive_voluntary',
      'year_over_year_voluntary'
    )
),

same_year_opt_outs AS (
  SELECT DISTINCT
    employee_id,
    simulation_year
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'enrollment_change'
    AND (
      event_category = 'enrollment_opt_out'
      OR LOWER(event_details) LIKE '%opt-out%'
    )
),

voluntary_not_opted_out AS (
  SELECT ve.employee_id, ve.simulation_year
  FROM voluntary_enrollments ve
  LEFT JOIN same_year_opt_outs oo
    ON ve.employee_id = oo.employee_id
    AND ve.simulation_year = oo.simulation_year
  WHERE oo.employee_id IS NULL
)

SELECT
  v.employee_id,
  v.simulation_year,
  ws.participation_status,
  ws.current_deferral_rate
FROM voluntary_not_opted_out v
LEFT JOIN {{ ref('fct_workforce_snapshot') }} ws
  ON v.employee_id = ws.employee_id
  AND v.simulation_year = ws.simulation_year
WHERE ws.employee_id IS NULL
   OR ws.participation_status <> 'participating'
   OR COALESCE(ws.current_deferral_rate, 0) <= 0
