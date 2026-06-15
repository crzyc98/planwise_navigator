{{
  config(
    severity='error',
    tags=['data_quality', 'enrollment', 'snapshot', 'consistency']
  )
}}

-- FR-005 (feature 095): participation_status and current_deferral_rate must be
-- mutually consistent in fct_workforce_snapshot.
--   participating      => current_deferral_rate > 0
--   not_participating   => current_deferral_rate = 0
-- Returns offending rows (build fails on any).

SELECT
  employee_id,
  simulation_year,
  participation_status,
  current_deferral_rate
FROM {{ ref('fct_workforce_snapshot') }}
WHERE (participation_status = 'participating' AND COALESCE(current_deferral_rate, 0) <= 0)
   OR (participation_status = 'not_participating' AND COALESCE(current_deferral_rate, 0) > 0)
