{{
  config(
    severity='error',
    tags=['data_quality', 'enrollment', 'architecture', 'epic_e023']
  )
}}

/*
  Data Quality Test: Enrollment Architecture Validation

  Phase 5 of the enrollment architecture fix - comprehensive validation to ensure
  the fixed event-to-state flow works correctly.

  Validates:
  1. Event-to-State Consistency: All enrollment events have corresponding enrollment dates
  2. Duplicate Enrollment Prevention: No duplicate enrollments across years
  3. Enrollment Continuity: Once enrolled, stays enrolled unless opt-out occurs
  4. State-to-Snapshot Consistency: Enrollment state propagates to workforce snapshot

  Architecture validated:
  int_enrollment_events → int_enrollment_state_accumulator → fct_workforce_snapshot

  Returns rows where validation failures are detected.
*/

WITH enrollment_events AS (
  SELECT
    employee_id,
    simulation_year,
    effective_date AS enrollment_event_date,
    COUNT(*) OVER (PARTITION BY employee_id) AS total_enrollment_events_per_employee,
    COUNT(*) OVER (PARTITION BY employee_id, simulation_year) AS enrollment_events_this_year,
    ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY simulation_year, effective_date) AS enrollment_sequence
  FROM {{ ref('int_enrollment_events') }}
),

enrollment_state AS (
  SELECT
    employee_id,
    simulation_year,
    enrollment_date,
    enrollment_status,
    enrollment_events_this_year AS state_enrollment_events,
    years_since_first_enrollment,
    enrollment_source,
    is_enrolled
  FROM {{ ref('int_enrollment_state_accumulator') }}
  WHERE enrollment_status = true
),

workforce_snapshots AS (
  SELECT
    employee_id,
    simulation_year,
    employee_enrollment_date,
    employment_status
  FROM {{ ref('fct_workforce_snapshot') }}
  WHERE employment_status = 'active'
    AND employee_enrollment_date IS NOT NULL
),

event_state_consistency AS (
  SELECT
    COALESCE(ee.employee_id, es.employee_id) AS employee_id,
    COALESCE(ee.simulation_year, es.simulation_year) AS simulation_year,
    ee.enrollment_event_date,
    es.enrollment_date AS state_enrollment_date,
    CASE
      WHEN ee.employee_id IS NOT NULL AND es.employee_id IS NULL
      THEN 'EVENT_WITHOUT_STATE'
      WHEN ee.employee_id IS NULL AND es.employee_id IS NOT NULL
      THEN 'STATE_WITHOUT_EVENT'
      WHEN ee.enrollment_event_date IS NOT NULL AND es.enrollment_date IS NULL
      THEN 'EVENT_DATE_NOT_IN_STATE'
      WHEN ee.enrollment_event_date != es.enrollment_date
      THEN 'DATE_MISMATCH'
      ELSE 'CONSISTENT'
    END AS event_state_consistency
  FROM enrollment_events ee
  FULL OUTER JOIN enrollment_state es
    ON ee.employee_id = es.employee_id
    AND ee.simulation_year = es.simulation_year
),

state_snapshot_consistency AS (
  SELECT
    COALESCE(es.employee_id, ws.employee_id) AS employee_id,
    COALESCE(es.simulation_year, ws.simulation_year) AS simulation_year,
    es.enrollment_date AS state_enrollment_date,
    ws.employee_enrollment_date AS snapshot_enrollment_date,
    CASE
      WHEN es.employee_id IS NOT NULL AND ws.employee_id IS NULL
      THEN 'STATE_WITHOUT_SNAPSHOT'
      WHEN es.employee_id IS NULL AND ws.employee_id IS NOT NULL
      THEN 'SNAPSHOT_WITHOUT_STATE'
      WHEN es.enrollment_date IS NOT NULL AND ws.employee_enrollment_date IS NULL
      THEN 'STATE_DATE_NOT_IN_SNAPSHOT'
      WHEN es.enrollment_date != ws.employee_enrollment_date
      THEN 'DATE_MISMATCH'
      ELSE 'CONSISTENT'
    END AS state_snapshot_consistency
  FROM enrollment_state es
  FULL OUTER JOIN workforce_snapshots ws
    ON es.employee_id = ws.employee_id
    AND es.simulation_year = ws.simulation_year
),

duplicate_enrollment_check AS (
  SELECT
    employee_id,
    COUNT(DISTINCT simulation_year) AS years_with_enrollment_events,
    MIN(simulation_year) AS first_enrollment_year,
    MAX(simulation_year) AS last_enrollment_year,
    COUNT(*) AS total_enrollment_events,
    CASE
      WHEN COUNT(DISTINCT simulation_year) > 1
      THEN 'DUPLICATE_ENROLLMENTS_ACROSS_YEARS'
      ELSE 'SINGLE_ENROLLMENT_ONLY'
    END AS duplicate_status,
    STRING_AGG(DISTINCT CAST(enrollment_event_date AS VARCHAR), ', ' ORDER BY enrollment_event_date) AS all_enrollment_dates
  FROM enrollment_events
  GROUP BY employee_id
),

enrollment_continuity AS (
  SELECT
    employee_id,
    simulation_year,
    enrollment_date,
    enrollment_status,
    LAG(enrollment_status) OVER (PARTITION BY employee_id ORDER BY simulation_year) AS previous_enrollment_status,
    LAG(enrollment_date) OVER (PARTITION BY employee_id ORDER BY simulation_year) AS previous_enrollment_date,
    CASE
      WHEN LAG(enrollment_status) OVER (PARTITION BY employee_id ORDER BY simulation_year) = true
      AND enrollment_status != true
      THEN 'ENROLLMENT_DISCONTINUITY'
      WHEN LAG(enrollment_date) OVER (PARTITION BY employee_id ORDER BY simulation_year) IS NOT NULL
      AND enrollment_date IS NULL
      THEN 'ENROLLMENT_DATE_REGRESSION'
      ELSE 'CONTINUOUS'
    END AS continuity_status
  FROM enrollment_state
)

SELECT
  COALESCE(esc.employee_id, ssc.employee_id, dec.employee_id, ec.employee_id) AS employee_id,
  COALESCE(esc.simulation_year, ssc.simulation_year, ec.simulation_year) AS simulation_year,
  esc.enrollment_event_date,
  esc.state_enrollment_date,
  ssc.snapshot_enrollment_date,
  esc.event_state_consistency,
  ssc.state_snapshot_consistency,
  dec.duplicate_status,
  ec.continuity_status,
  dec.years_with_enrollment_events,
  dec.total_enrollment_events,
  dec.all_enrollment_dates,
  CASE
    WHEN esc.event_state_consistency = 'EVENT_WITHOUT_STATE'
    THEN 'Enrollment event exists but no corresponding state record'
    WHEN esc.event_state_consistency = 'STATE_WITHOUT_EVENT'
    THEN 'Enrollment state exists but no triggering event found'
    WHEN esc.event_state_consistency = 'DATE_MISMATCH'
    THEN 'Enrollment event date does not match state enrollment date'
    WHEN ssc.state_snapshot_consistency = 'STATE_DATE_NOT_IN_SNAPSHOT'
    THEN 'Enrollment state date not reflected in workforce snapshot'
    WHEN dec.duplicate_status = 'DUPLICATE_ENROLLMENTS_ACROSS_YEARS'
    THEN 'Employee has enrollment events in multiple years (should only enroll once)'
    WHEN ec.continuity_status = 'ENROLLMENT_DISCONTINUITY'
    THEN 'Employee lost enrollment status between years without opt-out event'
    WHEN ec.continuity_status = 'ENROLLMENT_DATE_REGRESSION'
    THEN 'Employee lost enrollment date between years'
    ELSE 'Unknown validation failure'
  END AS issue_description
FROM event_state_consistency esc
FULL OUTER JOIN state_snapshot_consistency ssc
  ON esc.employee_id = ssc.employee_id
  AND esc.simulation_year = ssc.simulation_year
FULL OUTER JOIN duplicate_enrollment_check dec
  ON COALESCE(esc.employee_id, ssc.employee_id) = dec.employee_id
FULL OUTER JOIN enrollment_continuity ec
  ON COALESCE(esc.employee_id, ssc.employee_id) = ec.employee_id
  AND COALESCE(esc.simulation_year, ssc.simulation_year) = ec.simulation_year
WHERE
  esc.event_state_consistency NOT IN ('CONSISTENT', 'STATE_WITHOUT_EVENT')
  OR ssc.state_snapshot_consistency != 'CONSISTENT'
  OR dec.duplicate_status = 'DUPLICATE_ENROLLMENTS_ACROSS_YEARS'
  OR ec.continuity_status IN ('ENROLLMENT_DISCONTINUITY', 'ENROLLMENT_DATE_REGRESSION')
ORDER BY
  employee_id,
  simulation_year
