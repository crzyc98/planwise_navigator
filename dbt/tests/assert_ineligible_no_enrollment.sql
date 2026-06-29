-- Feature 103: plan-ineligible employees must never enroll, contribute, or receive
-- employer match. Fails if any employee resolved is_plan_ineligible_override = TRUE
-- has an enrollment/contribution/match event in fct_yearly_events for that year.
--
-- Covers acceptance criteria for US1 (new-hire dial) and US2 (census override):
-- the suppression cascades from "never enrolled" through contributions and match.

WITH ineligible AS (
  SELECT employee_id, simulation_year
  FROM {{ ref('int_plan_eligibility_override') }}
  WHERE is_plan_ineligible_override
),

participation_events AS (
  SELECT
    employee_id,
    simulation_year,
    event_type,
    event_category
  FROM {{ ref('fct_yearly_events') }}
  WHERE LOWER(event_type) IN ('enrollment', 'contribution', 'employer_match')
     OR LOWER(COALESCE(event_category, '')) LIKE '%enrollment%'
)

SELECT
  i.employee_id,
  i.simulation_year,
  pe.event_type,
  pe.event_category
FROM ineligible i
JOIN participation_events pe
  ON pe.employee_id = i.employee_id
  AND pe.simulation_year = i.simulation_year
