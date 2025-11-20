-- Converted from validation model to test
-- Added simulation_year filter for performance

/*
  Data Quality Test for Story S042-01: Deferral Rate State Accumulator V2

  Validates the new source of truth architecture:
  1. Every enrolled employee has enrollment event OR registry entry
  2. No employees with NULL deferral rates who are enrolled
  3. Enrollment events and deferral state have matching employee counts
  4. Specific validation: Employee NH_2025_000007 gets 6% from enrollment event
*/

WITH enrolled_employees_v2 AS (
  -- Get all enrolled employees from v2 accumulator
  SELECT
    employee_id,
    simulation_year,
    current_deferral_rate,
    escalation_source,
    rate_source,
    is_enrolled_flag,
    employee_enrollment_date,
    data_quality_flag
  FROM {{ ref('int_deferral_rate_state_accumulator_v2') }}
  WHERE is_enrolled_flag = true
    AND simulation_year = {{ var('simulation_year') }}
),

enrollment_events AS (
  -- Get all enrollment events for comparison
  SELECT DISTINCT
    employee_id,
    simulation_year,
    employee_deferral_rate,
    event_category,
    effective_date
  FROM {{ ref('int_enrollment_events') }}
  WHERE LOWER(event_type) = 'enrollment'
    AND employee_deferral_rate IS NOT NULL
    AND simulation_year = {{ var('simulation_year') }}
),

enrollment_registry_data AS (
  -- Get enrollment registry data if it exists
  SELECT
    employee_id,
    first_enrollment_year,
    first_enrollment_date,
    is_enrolled,
    enrollment_source
  FROM main.enrollment_registry
  WHERE is_enrolled = true
),

-- Test 1: Every enrolled employee has enrollment event OR registry entry
test_enrollment_coverage AS (
  SELECT
    ee.employee_id,
    ee.simulation_year,
    ee.current_deferral_rate,
    ee.escalation_source,

    -- Check for enrollment event
    CASE WHEN en.employee_id IS NOT NULL THEN true ELSE false END as has_enrollment_event,
    en.employee_deferral_rate as event_deferral_rate,

    -- Check for registry entry
    CASE WHEN er.employee_id IS NOT NULL THEN true ELSE false END as has_registry_entry,

    -- Validation result
    CASE
      WHEN en.employee_id IS NOT NULL OR er.employee_id IS NOT NULL THEN 'PASS'
      ELSE 'FAIL'
    END as coverage_test_result,

    -- Issue description
    CASE
      WHEN en.employee_id IS NOT NULL AND er.employee_id IS NOT NULL
        THEN 'Employee has both enrollment event and registry entry'
      WHEN en.employee_id IS NOT NULL
        THEN 'Employee has enrollment event (primary source)'
      WHEN er.employee_id IS NOT NULL
        THEN 'Employee has registry entry (fallback source)'
      ELSE 'ERROR: Enrolled employee has neither enrollment event nor registry entry'
    END as coverage_issue_description

  FROM enrolled_employees_v2 ee
  LEFT JOIN enrollment_events en
    ON ee.employee_id = en.employee_id
    AND en.simulation_year <= ee.simulation_year
  LEFT JOIN enrollment_registry_data er
    ON ee.employee_id = er.employee_id
    AND er.first_enrollment_year <= ee.simulation_year
),

-- Test 2: No NULL deferral rates for enrolled employees
test_null_deferral_rates AS (
  SELECT
    employee_id,
    simulation_year,
    current_deferral_rate,
    escalation_source,

    CASE
      WHEN current_deferral_rate IS NOT NULL THEN 'PASS'
      ELSE 'FAIL'
    END as null_rate_test_result,

    CASE
      WHEN current_deferral_rate IS NOT NULL
        THEN 'Employee has valid deferral rate'
      ELSE 'ERROR: Enrolled employee has NULL deferral rate'
    END as null_rate_issue_description

  FROM enrolled_employees_v2
),

-- Test 3: Enrollment events and deferral state employee count consistency
test_employee_count_consistency AS (
  SELECT
    'ENROLLMENT_EVENTS_COUNT' as metric_name,
    COUNT(DISTINCT employee_id) as count_value,
    {{ var('simulation_year') }} as simulation_year
  FROM enrollment_events
  WHERE simulation_year <= {{ var('simulation_year') }}

  UNION ALL

  SELECT
    'DEFERRAL_STATE_COUNT' as metric_name,
    COUNT(DISTINCT employee_id) as count_value,
    {{ var('simulation_year') }} as simulation_year
  FROM enrolled_employees_v2
  WHERE simulation_year = {{ var('simulation_year') }}
),

-- Test 4: Specific test case - NH_2025_000007 should get 6% from enrollment event
test_nh_2025_000007 AS (
  SELECT
    'NH_2025_000007' as test_employee_id,
    0.06 as expected_deferral_rate,
    'enrollment_event' as expected_source,

    -- Check if employee exists in v2 model
    (SELECT current_deferral_rate
     FROM enrolled_employees_v2
     WHERE employee_id = 'NH_2025_000007'
     AND simulation_year = {{ var('simulation_year') }}) as actual_deferral_rate,

    (SELECT escalation_source
     FROM enrolled_employees_v2
     WHERE employee_id = 'NH_2025_000007'
     AND simulation_year = {{ var('simulation_year') }}) as actual_source,

    -- Check if enrollment event exists
    (SELECT employee_deferral_rate
     FROM enrollment_events
     WHERE employee_id = 'NH_2025_000007'
     AND simulation_year = {{ var('simulation_year') }}) as enrollment_event_rate,

    -- Validation result
    CASE
      WHEN (SELECT current_deferral_rate
            FROM enrolled_employees_v2
            WHERE employee_id = 'NH_2025_000007'
            AND simulation_year = {{ var('simulation_year') }}) = 0.06
      AND (SELECT escalation_source
           FROM enrolled_employees_v2
           WHERE employee_id = 'NH_2025_000007'
           AND simulation_year = {{ var('simulation_year') }}) = 'enrollment_event'
      THEN 'PASS'
      ELSE 'FAIL'
    END as nh_test_result,

    CASE
      WHEN (SELECT current_deferral_rate
            FROM enrolled_employees_v2
            WHERE employee_id = 'NH_2025_000007'
            AND simulation_year = {{ var('simulation_year') }}) = 0.06
      AND (SELECT escalation_source
           FROM enrolled_employees_v2
           WHERE employee_id = 'NH_2025_000007'
           AND simulation_year = {{ var('simulation_year') }}) = 'enrollment_event'
      THEN 'NH_2025_000007 correctly gets 6% deferral rate from enrollment event'
      ELSE 'NH_2025_000007 does not have expected 6% rate from enrollment event'
    END as nh_issue_description
),

-- Compile failing records only (for dbt test)
failing_coverage_tests AS (
  SELECT
    'ENROLLMENT_COVERAGE' as test_name,
    employee_id,
    coverage_test_result as validation_result,
    coverage_issue_description as issue_description,
    simulation_year
  FROM test_enrollment_coverage
  WHERE coverage_test_result = 'FAIL'
),

failing_null_rate_tests AS (
  SELECT
    'NULL_DEFERRAL_RATES' as test_name,
    employee_id,
    null_rate_test_result as validation_result,
    null_rate_issue_description as issue_description,
    simulation_year
  FROM test_null_deferral_rates
  WHERE null_rate_test_result = 'FAIL'
),

failing_nh_tests AS (
  SELECT
    'NH_2025_000007_TEST' as test_name,
    test_employee_id as employee_id,
    nh_test_result as validation_result,
    nh_issue_description as issue_description,
    {{ var('simulation_year') }} as simulation_year
  FROM test_nh_2025_000007
  WHERE nh_test_result = 'FAIL'
),

failing_count_consistency_tests AS (
  SELECT
    'EMPLOYEE_COUNT_CONSISTENCY' as test_name,
    NULL as employee_id,
    CASE
      WHEN ABS((SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'ENROLLMENT_EVENTS_COUNT') -
               (SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'DEFERRAL_STATE_COUNT')) >
               0.05 * (SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'ENROLLMENT_EVENTS_COUNT')
      THEN 'FAIL' ELSE 'PASS'
    END as validation_result,
    'Events: ' || (SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'ENROLLMENT_EVENTS_COUNT') ||
    ', State: ' || (SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'DEFERRAL_STATE_COUNT') ||
    ' - Employee count mismatch detected' as issue_description,
    {{ var('simulation_year') }} as simulation_year
  WHERE validation_result = 'FAIL'
)

-- Return only failing records (0 rows = test passes)
SELECT * FROM failing_coverage_tests
UNION ALL
SELECT * FROM failing_null_rate_tests
UNION ALL
SELECT * FROM failing_nh_tests
UNION ALL
SELECT * FROM failing_count_consistency_tests

/*
Story S042-01 Data Quality Tests Summary:

1. ENROLLMENT_COVERAGE: Validates that every enrolled employee in the v2 accumulator
   has either an enrollment event or registry entry (no orphaned enrollments)

2. NULL_DEFERRAL_RATES: Ensures no enrolled employees have NULL deferral rates
   (all enrolled employees must have valid rates)

3. NH_2025_000007_TEST: Specific test case to verify that employee NH_2025_000007
   gets the expected 6% deferral rate from enrollment event, not demographic fallback

4. EMPLOYEE_COUNT_CONSISTENCY: Validates that enrollment events and deferral state
   have consistent employee counts (within 5% tolerance)

Expected Results Post-Fix:
- All tests should return 0 rows (PASS)
- NH_2025_000007 should show 6% rate from 'enrollment_event' source
- Zero employees with NULL rates or missing source events
- Consistent employee counts between events and state
*/
