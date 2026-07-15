"""Violation-returning SQL for the Feature 113 invariant catalog."""

EVENT_UNIQUENESS = """
SELECT
  MIN(employee_id) AS employee_id,
  MIN(simulation_year) AS simulation_year,
  event_id,
  COUNT(*) AS duplicate_count
FROM fct_yearly_events
GROUP BY event_id
HAVING COUNT(*) > 1
"""

ENROLLMENT_NO_DUPLICATE = """
WITH enrollment_events AS (
  SELECT
    employee_id,
    simulation_year,
    effective_date,
    event_sequence,
    LAG(effective_date) OVER employee_events AS previous_enrollment_date
  FROM fct_yearly_events
  WHERE event_type = 'enrollment'
  WINDOW employee_events AS (
    PARTITION BY employee_id
    ORDER BY effective_date, simulation_year, event_sequence
  )
)
SELECT
  enroll.employee_id,
  enroll.simulation_year,
  enroll.previous_enrollment_date,
  enroll.effective_date AS duplicate_enrollment_date
FROM enrollment_events enroll
WHERE enroll.previous_enrollment_date IS NOT NULL
  AND NOT EXISTS (
    SELECT 1
    FROM fct_yearly_events opt_out
    WHERE opt_out.employee_id = enroll.employee_id
      AND opt_out.event_type = 'enrollment_change'
      AND COALESCE(opt_out.employee_deferral_rate, 0) = 0
      AND opt_out.effective_date > enroll.previous_enrollment_date
      AND opt_out.effective_date < enroll.effective_date
  )
"""

ENROLLMENT_CENSUS_PERSISTENCE = """
SELECT
  snapshot.employee_id,
  snapshot.simulation_year,
  baseline.employee_deferral_rate AS census_deferral_rate,
  snapshot.is_enrolled_flag,
  snapshot.current_deferral_rate
FROM fct_workforce_snapshot snapshot
JOIN int_baseline_workforce baseline USING (employee_id)
WHERE baseline.is_enrolled_at_census
  AND NOT COALESCE(snapshot.is_enrolled_flag, FALSE)
  AND NOT EXISTS (
    SELECT 1
    FROM fct_yearly_events event
    WHERE event.employee_id = snapshot.employee_id
      AND event.event_type = 'enrollment_change'
      AND COALESCE(event.employee_deferral_rate, 0) = 0
      AND event.simulation_year <= snapshot.simulation_year
  )
"""

CONTINUITY_HEADCOUNT = """
WITH active_counts AS (
  SELECT simulation_year, COUNT(*) AS ending_active
  FROM fct_workforce_snapshot
  WHERE employment_status = 'active'
  GROUP BY simulation_year
),
flows AS (
  SELECT
    simulation_year,
    COUNT(DISTINCT employee_id) FILTER (WHERE event_type = 'hire') AS hires,
    COUNT(DISTINCT employee_id) FILTER (WHERE event_type = 'termination') AS terminations
  FROM fct_yearly_events
  GROUP BY simulation_year
)
SELECT
  '__HEADCOUNT__' AS employee_id,
  current_year.simulation_year,
  previous_year.ending_active AS previous_ending_active,
  current_year.ending_active - flows.hires + flows.terminations AS current_starting_active
FROM active_counts current_year
JOIN active_counts previous_year
  ON previous_year.simulation_year = current_year.simulation_year - 1
JOIN flows ON flows.simulation_year = current_year.simulation_year
WHERE previous_year.ending_active
  <> current_year.ending_active - flows.hires + flows.terminations
"""

CONTINUITY_NO_ZOMBIE = """
SELECT
  snapshot.employee_id,
  snapshot.simulation_year,
  termination.effective_date AS unexplained_termination_date
FROM fct_workforce_snapshot snapshot
JOIN fct_yearly_events termination
  ON termination.employee_id = snapshot.employee_id
 AND termination.event_type = 'termination'
 AND termination.simulation_year <= snapshot.simulation_year
WHERE snapshot.employment_status = 'active'
  AND NOT EXISTS (
    SELECT 1
    FROM fct_yearly_events rehire
    WHERE rehire.employee_id = snapshot.employee_id
      AND rehire.event_type = 'hire'
      AND rehire.effective_date > termination.effective_date
      AND rehire.simulation_year <= snapshot.simulation_year
  )
QUALIFY ROW_NUMBER() OVER (
  PARTITION BY snapshot.employee_id, snapshot.simulation_year
  ORDER BY termination.effective_date DESC
) = 1
"""

SNAPSHOT_EXPLAINED_BY_EVENTS = """
WITH candidate_state AS (
  SELECT
    snapshot.employee_id,
    snapshot.simulation_year,
    snapshot.is_enrolled_flag,
    snapshot.current_deferral_rate,
    baseline.is_enrolled_at_census,
    baseline.employee_deferral_rate AS census_deferral_rate,
    event.event_type,
    event.employee_deferral_rate AS event_deferral_rate,
    ROW_NUMBER() OVER (
      PARTITION BY snapshot.employee_id, snapshot.simulation_year
      ORDER BY event.effective_date DESC NULLS LAST, event.event_sequence DESC NULLS LAST
    ) AS state_rank
  FROM fct_workforce_snapshot snapshot
  LEFT JOIN int_baseline_workforce baseline USING (employee_id)
  LEFT JOIN fct_yearly_events event
    ON event.employee_id = snapshot.employee_id
   AND event.simulation_year <= snapshot.simulation_year
   AND event.event_type IN (
     'enrollment', 'enrollment_change', 'deferral_escalation',
     'deferral_match_response'
   )
),
expected_state AS (
  SELECT
    employee_id,
    simulation_year,
    is_enrolled_flag,
    current_deferral_rate,
    CASE
      WHEN event_type IS NULL THEN COALESCE(is_enrolled_at_census, FALSE)
      WHEN event_type = 'enrollment_change' AND COALESCE(event_deferral_rate, 0) = 0 THEN FALSE
      ELSE TRUE
    END AS expected_enrolled,
    COALESCE(event_deferral_rate, census_deferral_rate, 0) AS expected_deferral_rate
  FROM candidate_state
  WHERE state_rank = 1
)
SELECT
  employee_id,
  simulation_year,
  is_enrolled_flag AS snapshot_enrolled,
  expected_enrolled,
  current_deferral_rate AS snapshot_deferral_rate,
  expected_deferral_rate
FROM expected_state
WHERE is_enrolled_flag IS DISTINCT FROM expected_enrolled
   OR ABS(COALESCE(current_deferral_rate, 0) - expected_deferral_rate) > 0.000001
"""

SNAPSHOT_NO_FOREIGN_ROWS = """
SELECT employee_id, simulation_year, source, scenario_id, plan_design_id
FROM (
  SELECT
    employee_id,
    simulation_year,
    'event' AS source,
    scenario_id,
    plan_design_id
  FROM fct_yearly_events
  WHERE simulation_year NOT BETWEEN 2025 AND 2027
     OR scenario_id <> 'invariant_reference'
     OR plan_design_id <> 'invariant_tiered_401k'

  UNION ALL

  SELECT
    snapshot.employee_id,
    snapshot.simulation_year,
    'snapshot' AS source,
    NULL AS scenario_id,
    NULL AS plan_design_id
  FROM fct_workforce_snapshot snapshot
  WHERE snapshot.simulation_year NOT BETWEEN 2025 AND 2027
     OR NOT EXISTS (
       SELECT 1 FROM int_baseline_workforce baseline
       WHERE baseline.employee_id = snapshot.employee_id
     )
     AND NOT EXISTS (
       SELECT 1 FROM fct_yearly_events hire
       WHERE hire.employee_id = snapshot.employee_id
         AND hire.event_type = 'hire'
         AND hire.simulation_year <= snapshot.simulation_year
     )
) violations
"""

GROWTH_EXACTNESS = """
WITH actual AS (
  SELECT simulation_year, COUNT(*) AS ending_active
  FROM fct_workforce_snapshot
  WHERE employment_status = 'active'
  GROUP BY simulation_year
)
SELECT
  '__HEADCOUNT__' AS employee_id,
  needs.simulation_year,
  needs.starting_workforce_count,
  needs.target_growth_rate,
  CAST(ROUND(
    needs.starting_workforce_count * (1 + needs.target_growth_rate)
  ) AS INTEGER) AS rounded_target,
  needs.target_ending_workforce AS solver_target,
  actual.ending_active
FROM int_workforce_needs needs
JOIN actual USING (simulation_year)
WHERE needs.target_ending_workforce <> CAST(ROUND(
        needs.starting_workforce_count * (1 + needs.target_growth_rate)
      ) AS INTEGER)
   OR actual.ending_active <> needs.target_ending_workforce
"""

DEFERRAL_EXPLAINED_CHANGES = """
WITH yearly_rates AS (
  SELECT
    employee_id,
    simulation_year,
    current_deferral_rate,
    LAG(current_deferral_rate) OVER (
      PARTITION BY employee_id ORDER BY simulation_year
    ) AS previous_deferral_rate
  FROM fct_workforce_snapshot
)
SELECT
  rates.employee_id,
  rates.simulation_year,
  rates.previous_deferral_rate,
  rates.current_deferral_rate
FROM yearly_rates rates
WHERE rates.previous_deferral_rate IS NOT NULL
  AND ABS(
    COALESCE(rates.current_deferral_rate, 0)
    - COALESCE(rates.previous_deferral_rate, 0)
  ) > 0.000001
  AND NOT EXISTS (
    SELECT 1
    FROM fct_yearly_events event
    WHERE event.employee_id = rates.employee_id
      AND event.simulation_year = rates.simulation_year
      AND event.event_type IN (
        'enrollment', 'enrollment_change', 'deferral_escalation',
        'deferral_match_response'
      )
  )
"""

DEFERRAL_CAP_RESPECTED = """
SELECT
  employee_id,
  simulation_year,
  employee_deferral_rate,
  0.06 AS configured_escalation_cap
FROM fct_yearly_events
WHERE event_type = 'deferral_escalation'
  AND employee_deferral_rate > 0.06 + 0.000001
"""

DEFERRAL_OPTOUT_NOT_ESCALATED = """
SELECT
  event.employee_id,
  event.simulation_year,
  event.effective_date,
  event.employee_deferral_rate
FROM fct_yearly_events event
JOIN int_baseline_workforce baseline USING (employee_id)
WHERE event.event_type = 'deferral_escalation'
  AND baseline.auto_escalation_opt_out
"""
