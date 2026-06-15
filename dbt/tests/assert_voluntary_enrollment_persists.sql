{{
  config(
    severity='error',
    tags=['data_quality', 'enrollment', 'voluntary', 'persistence', 'temporal']
  )
}}

-- FR-007 (feature 095): A voluntary enrollment must carry forward into later years'
-- snapshots until a subsequent opt-out/unenroll changes it.
--
-- For each employee who is a participating voluntary enrollee in year Y and remains
-- active in year Y+1 with no opt-out event in Y+1, the year Y+1 snapshot must still
-- show them participating with a non-zero deferral rate.
-- Returns offending rows (build fails on any).

WITH voluntary_years AS (
  SELECT DISTINCT employee_id, simulation_year
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'enrollment'
    AND event_category IN (
      'voluntary_enrollment',
      'proactive_voluntary',
      'year_over_year_voluntary'
    )
),

participating_year_y AS (
  SELECT vy.employee_id, vy.simulation_year
  FROM voluntary_years vy
  JOIN {{ ref('fct_workforce_snapshot') }} ws
    ON vy.employee_id = ws.employee_id
    AND vy.simulation_year = ws.simulation_year
  WHERE ws.participation_status = 'participating'
    AND COALESCE(ws.current_deferral_rate, 0) > 0
),

opt_outs AS (
  SELECT DISTINCT employee_id, simulation_year
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'enrollment_change'
    AND (event_category = 'enrollment_opt_out' OR LOWER(event_details) LIKE '%opt-out%')
)

SELECT
  p.employee_id,
  p.simulation_year AS enrolled_year,
  nxt.simulation_year AS next_year,
  nxt.participation_status AS next_status,
  nxt.current_deferral_rate AS next_rate
FROM participating_year_y p
JOIN {{ ref('fct_workforce_snapshot') }} nxt
  ON p.employee_id = nxt.employee_id
  AND nxt.simulation_year = p.simulation_year + 1
LEFT JOIN opt_outs oo
  ON p.employee_id = oo.employee_id
  AND oo.simulation_year = p.simulation_year + 1
WHERE nxt.employment_status <> 'terminated'
  AND oo.employee_id IS NULL
  AND (nxt.participation_status <> 'participating' OR COALESCE(nxt.current_deferral_rate, 0) <= 0)
