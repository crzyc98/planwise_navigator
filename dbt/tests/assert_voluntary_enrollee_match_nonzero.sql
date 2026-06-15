{{
  config(
    severity='error',
    tags=['data_quality', 'enrollment', 'voluntary', 'match']
  )
}}

-- FR-004 (feature 095): Voluntary enrollees who are MATCH-ELIGIBLE and contributing
-- must receive a non-zero employer match.
--
-- Scope note: employer match eligibility is governed by int_employee_match_calculations
-- (is_eligible_for_match) — e.g., new hires in a waiting period are legitimately
-- ineligible and absent from the match calc, so they are out of scope here. This guard
-- asserts the narrower, unconditional rule: an employee the system deems match-eligible,
-- who voluntarily enrolled and is contributing (deferral rate > 0), must have match > 0.
-- This is exactly the population the feature-095 accumulator fix restored.
-- Returns offending rows (build fails on any).

WITH voluntary_enrollees AS (
  SELECT DISTINCT employee_id, simulation_year
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'enrollment'
    AND event_category IN (
      'voluntary_enrollment',
      'proactive_voluntary',
      'year_over_year_voluntary'
    )
)

SELECT
  mc.employee_id,
  mc.simulation_year,
  mc.is_eligible_for_match,
  mc.employer_match_amount
FROM {{ ref('int_employee_match_calculations') }} mc
JOIN voluntary_enrollees ve
  ON mc.employee_id = ve.employee_id
  AND mc.simulation_year = ve.simulation_year
WHERE mc.is_eligible_for_match = true
  AND COALESCE(mc.annual_deferrals, 0) > 0
  AND COALESCE(mc.employer_match_amount, 0) <= 0
