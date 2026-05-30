-- Feature 086: Prerequisite chain test — every DC_PLAN_ENROLLMENT event must be
-- preceded (or coincident) by a DC_PLAN_ELIGIBILITY event.
-- Returns rows (violations) when an employee has an enrollment event with no
-- corresponding eligibility event whose simulation_year <= enrollment_year
-- AND effective_date <= enrollment effective_date.
-- Only checks simulation years where eligibility events have been generated.
WITH years_with_eligibility AS (
  SELECT DISTINCT simulation_year
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = {{ evt_eligibility() }}
),

enrollment_events AS (
  SELECT
    enr.employee_id,
    enr.simulation_year,
    enr.effective_date AS enrollment_effective_date
  FROM {{ ref('fct_yearly_events') }} enr
  INNER JOIN years_with_eligibility y ON enr.simulation_year = y.simulation_year
  WHERE enr.event_type = {{ evt_enrollment() }}
),

eligibility_events AS (
  SELECT
    employee_id,
    simulation_year,
    effective_date AS eligibility_effective_date
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = {{ evt_eligibility() }}
)

SELECT
  enr.employee_id,
  enr.simulation_year,
  enr.enrollment_effective_date
FROM enrollment_events enr
LEFT JOIN eligibility_events elig
  ON enr.employee_id = elig.employee_id
  AND elig.simulation_year <= enr.simulation_year
  AND elig.eligibility_effective_date <= enr.enrollment_effective_date
WHERE elig.employee_id IS NULL
