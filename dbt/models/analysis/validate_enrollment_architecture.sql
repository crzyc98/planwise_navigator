{{ config(
    materialized='table',
    tags=['VALIDATION']
) }}

/*
  Enrollment Architecture Validation

  Phase 5 of the enrollment architecture fix - comprehensive validation to ensure
  the fixed event-to-state flow works correctly. This model validates:

  1. Event-to-State Consistency: All enrollment events have corresponding enrollment dates
  2. Duplicate Enrollment Prevention: No duplicate enrollments across years
  3. Enrollment Continuity: Once enrolled, stays enrolled unless opt-out occurs
  4. Specific Test Cases: Validates known edge cases like NH_2026_000787

  Architecture validated:
  int_enrollment_events → int_enrollment_state_accumulator → fct_workforce_snapshot

  This replaces the broken circular dependency that existed with int_historical_enrollment_tracker.
*/

WITH enrollment_events AS (
  -- Get all enrollment events from the fixed event flow
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
  -- Get enrollment state from the fixed accumulator
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
  -- Get enrollment dates from workforce snapshots
  SELECT
    employee_id,
    simulation_year,
    employee_enrollment_date,
    employment_status
  FROM {{ ref('fct_workforce_snapshot') }}
  WHERE employment_status = 'active'
    AND employee_enrollment_date IS NOT NULL
),

-- Validation 1: Event-to-State Consistency
event_state_consistency AS (
  SELECT
    COALESCE(ee.employee_id, es.employee_id) AS employee_id,
    COALESCE(ee.simulation_year, es.simulation_year) AS simulation_year,
    ee.enrollment_event_date,
    ee.enrollment_events_this_year AS event_count,
    es.enrollment_date AS state_enrollment_date,
    es.enrollment_status,
    es.years_since_first_enrollment,
    es.enrollment_source,

    -- Consistency flags
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
    END AS event_state_consistency,

    -- Additional validation details
    CASE
      WHEN ee.enrollment_events_this_year > 1
      THEN 'MULTIPLE_EVENTS_SINGLE_YEAR'
      ELSE 'SINGLE_EVENT_PER_YEAR'
    END AS event_frequency_status

  FROM enrollment_events ee
  FULL OUTER JOIN enrollment_state es
    ON ee.employee_id = es.employee_id
    AND ee.simulation_year = es.simulation_year
),

-- Validation 2: State-to-Snapshot Consistency
state_snapshot_consistency AS (
  SELECT
    COALESCE(es.employee_id, ws.employee_id) AS employee_id,
    COALESCE(es.simulation_year, ws.simulation_year) AS simulation_year,
    es.enrollment_date AS state_enrollment_date,
    es.enrollment_status,
    ws.employee_enrollment_date AS snapshot_enrollment_date,
    ws.employment_status,

    -- Consistency flags
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

-- Validation 3: Duplicate Enrollment Check
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

    -- Get the enrollment dates for analysis
    STRING_AGG(DISTINCT CAST(enrollment_event_date AS VARCHAR), ', ' ORDER BY enrollment_event_date) AS all_enrollment_dates

  FROM enrollment_events
  GROUP BY employee_id
),

-- Validation 4: Enrollment Continuity Check
enrollment_continuity AS (
  SELECT
    employee_id,
    simulation_year,
    enrollment_date,
    enrollment_status,

    -- Check if enrollment status changes over time
    LAG(enrollment_status) OVER (
      PARTITION BY employee_id
      ORDER BY simulation_year
    ) AS previous_enrollment_status,

    LAG(enrollment_date) OVER (
      PARTITION BY employee_id
      ORDER BY simulation_year
    ) AS previous_enrollment_date,

    -- Continuity validation
    CASE
      WHEN LAG(enrollment_status) OVER (
        PARTITION BY employee_id
        ORDER BY simulation_year
      ) = true
      AND enrollment_status != true
      THEN 'ENROLLMENT_DISCONTINUITY'

      WHEN LAG(enrollment_date) OVER (
        PARTITION BY employee_id
        ORDER BY simulation_year
      ) IS NOT NULL
      AND enrollment_date IS NULL
      THEN 'ENROLLMENT_DATE_REGRESSION'

      ELSE 'CONTINUOUS'
    END AS continuity_status

  FROM enrollment_state
),

-- Validation 5: Specific Test Cases
specific_test_cases AS (
  SELECT
    'NH_2026_000787' AS test_employee_id,
    '2027-01-15'::DATE AS expected_enrollment_date,
    2027 AS expected_simulation_year,

    -- Check if this specific case exists in our data
    (SELECT COUNT(*) FROM enrollment_state
     WHERE employee_id = 'NH_2026_000787'
     AND enrollment_date = '2027-01-15'::DATE
     AND simulation_year = 2027) AS case_found_in_state,

    (SELECT COUNT(*) FROM workforce_snapshots
     WHERE employee_id = 'NH_2026_000787'
     AND employee_enrollment_date = '2027-01-15'::DATE
     AND simulation_year = 2027) AS case_found_in_snapshot,

    (SELECT COUNT(*) FROM enrollment_events
     WHERE employee_id = 'NH_2026_000787'
     AND enrollment_event_date = '2027-01-15'::DATE
     AND simulation_year = 2027) AS case_found_in_events,

    -- Validation status for this specific case
    CASE
      WHEN (SELECT COUNT(*) FROM enrollment_state
            WHERE employee_id = 'NH_2026_000787'
            AND enrollment_date = '2027-01-15'::DATE
            AND simulation_year = 2027) > 0
      AND (SELECT COUNT(*) FROM workforce_snapshots
           WHERE employee_id = 'NH_2026_000787'
           AND employee_enrollment_date = '2027-01-15'::DATE
           AND simulation_year = 2027) > 0
      THEN 'SPECIFIC_CASE_VALIDATED'
      ELSE 'SPECIFIC_CASE_NOT_FOUND'
    END AS nh_2026_000787_validation
),

-- Final comprehensive validation report
all_validation_results AS (
SELECT
  -- Employee and timing information
  COALESCE(esc.employee_id, ssc.employee_id, dec.employee_id, ec.employee_id) AS employee_id,
  COALESCE(esc.simulation_year, ssc.simulation_year, ec.simulation_year) AS simulation_year,

  -- Event data
  esc.enrollment_event_date,
  esc.event_count,
  esc.event_frequency_status,

  -- State data
  esc.state_enrollment_date,
  esc.enrollment_status,
  esc.years_since_first_enrollment,
  esc.enrollment_source,

  -- Snapshot data
  ssc.snapshot_enrollment_date,
  ssc.employment_status,

  -- Validation results
  esc.event_state_consistency,
  ssc.state_snapshot_consistency,
  dec.duplicate_status,
  ec.continuity_status,

  -- Duplicate enrollment details
  dec.years_with_enrollment_events,
  dec.total_enrollment_events,
  dec.first_enrollment_year,
  dec.last_enrollment_year,
  dec.all_enrollment_dates,

  -- Continuity details
  ec.previous_enrollment_status,
  ec.previous_enrollment_date,

  -- Overall validation status
  CASE
    WHEN esc.event_state_consistency NOT IN ('CONSISTENT', 'STATE_WITHOUT_EVENT')
      OR ssc.state_snapshot_consistency != 'CONSISTENT'
      OR dec.duplicate_status = 'DUPLICATE_ENROLLMENTS_ACROSS_YEARS'
      OR ec.continuity_status IN ('ENROLLMENT_DISCONTINUITY', 'ENROLLMENT_DATE_REGRESSION')
    THEN 'VALIDATION_FAILED'
    ELSE 'VALIDATION_PASSED'
  END AS overall_validation_status,

  -- Issue summary
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

    ELSE 'No issues detected - enrollment architecture working correctly'
  END AS issue_description,

  -- Test case marker
  'MAIN_VALIDATION' AS validation_type,

  -- Metadata
  CURRENT_TIMESTAMP AS validation_timestamp

FROM event_state_consistency esc
FULL OUTER JOIN state_snapshot_consistency ssc
  ON esc.employee_id = ssc.employee_id
  AND esc.simulation_year = ssc.simulation_year
FULL OUTER JOIN duplicate_enrollment_check dec
  ON COALESCE(esc.employee_id, ssc.employee_id) = dec.employee_id
FULL OUTER JOIN enrollment_continuity ec
  ON COALESCE(esc.employee_id, ssc.employee_id) = ec.employee_id
  AND COALESCE(esc.simulation_year, ssc.simulation_year) = ec.simulation_year

UNION ALL

-- Add the specific test case as a separate validation
SELECT
  stc.test_employee_id AS employee_id,
  stc.expected_simulation_year AS simulation_year,
  stc.expected_enrollment_date AS enrollment_event_date,
  stc.case_found_in_events AS event_count,
  'SPECIFIC_TEST_CASE' AS event_frequency_status,
  stc.expected_enrollment_date AS state_enrollment_date,
  CASE WHEN stc.case_found_in_state > 0 THEN true ELSE false END AS enrollment_status,
  NULL AS years_since_first_enrollment,
  'test_case' AS enrollment_source,
  stc.expected_enrollment_date AS snapshot_enrollment_date,
  'active' AS employment_status,
  stc.nh_2026_000787_validation AS event_state_consistency,
  stc.nh_2026_000787_validation AS state_snapshot_consistency,
  'SPECIFIC_TEST_CASE' AS duplicate_status,
  'SPECIFIC_TEST_CASE' AS continuity_status,
  NULL AS years_with_enrollment_events,
  stc.case_found_in_events AS total_enrollment_events,
  stc.expected_simulation_year AS first_enrollment_year,
  stc.expected_simulation_year AS last_enrollment_year,
  CAST(stc.expected_enrollment_date AS VARCHAR) AS all_enrollment_dates,
  NULL AS previous_enrollment_status,
  NULL AS previous_enrollment_date,
  stc.nh_2026_000787_validation AS overall_validation_status,
  CASE
    WHEN stc.nh_2026_000787_validation = 'SPECIFIC_CASE_VALIDATED'
    THEN 'NH_2026_000787 enrollment date 2027-01-15 found in both state and snapshot - test case passed'
    ELSE 'NH_2026_000787 enrollment date 2027-01-15 not found - test case failed'
  END AS issue_description,
  'TEST_CASE_NH_2026_000787' AS validation_type,
  CURRENT_TIMESTAMP AS validation_timestamp

FROM specific_test_cases stc
)

-- Final result with proper ordering
SELECT * FROM all_validation_results
ORDER BY
  CASE WHEN overall_validation_status LIKE '%FAILED%' OR overall_validation_status = 'SPECIFIC_CASE_NOT_FOUND' THEN 0 ELSE 1 END,
  validation_type,
  employee_id,
  simulation_year
