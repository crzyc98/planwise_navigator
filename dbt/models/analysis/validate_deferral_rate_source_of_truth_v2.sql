{{ config(materialized='table', enabled=false) }}

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
    enrollment_source,
    is_enrolled_flag,
    employee_enrollment_date,
    data_quality_flag
  FROM {{ ref('int_deferral_rate_state_accumulator_v2') }}
  WHERE is_enrolled_flag = true
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
    {{ var('simulation_year', 2025) }} as simulation_year
  FROM enrollment_events
  WHERE simulation_year <= {{ var('simulation_year', 2025) }}

  UNION ALL

  SELECT
    'DEFERRAL_STATE_COUNT' as metric_name,
    COUNT(DISTINCT employee_id) as count_value,
    {{ var('simulation_year', 2025) }} as simulation_year
  FROM enrolled_employees_v2
  WHERE simulation_year = {{ var('simulation_year', 2025) }}
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
     AND simulation_year = 2025) as actual_deferral_rate,

    (SELECT escalation_source
     FROM enrolled_employees_v2
     WHERE employee_id = 'NH_2025_000007'
     AND simulation_year = 2025) as actual_source,

    -- Check if enrollment event exists
    (SELECT employee_deferral_rate
     FROM enrollment_events
     WHERE employee_id = 'NH_2025_000007'
     AND simulation_year = 2025) as enrollment_event_rate,

    -- Validation result
    CASE
      WHEN (SELECT current_deferral_rate
            FROM enrolled_employees_v2
            WHERE employee_id = 'NH_2025_000007'
            AND simulation_year = 2025) = 0.06
      AND (SELECT escalation_source
           FROM enrolled_employees_v2
           WHERE employee_id = 'NH_2025_000007'
           AND simulation_year = 2025) = 'enrollment_event'
      THEN 'PASS'
      ELSE 'FAIL'
    END as nh_test_result,

    CASE
      WHEN (SELECT current_deferral_rate
            FROM enrolled_employees_v2
            WHERE employee_id = 'NH_2025_000007'
            AND simulation_year = 2025) = 0.06
      AND (SELECT escalation_source
           FROM enrolled_employees_v2
           WHERE employee_id = 'NH_2025_000007'
           AND simulation_year = 2025) = 'enrollment_event'
      THEN 'NH_2025_000007 correctly gets 6% deferral rate from enrollment event'
      ELSE 'NH_2025_000007 does not have expected 6% rate from enrollment event'
    END as nh_issue_description
),

-- Compile final validation results
validation_summary AS (
  -- Coverage test results
  SELECT
    'ENROLLMENT_COVERAGE' as test_name,
    COUNT(*) as total_employees,
    SUM(CASE WHEN coverage_test_result = 'PASS' THEN 1 ELSE 0 END) as passed_count,
    SUM(CASE WHEN coverage_test_result = 'FAIL' THEN 1 ELSE 0 END) as failed_count,
    CASE
      WHEN SUM(CASE WHEN coverage_test_result = 'FAIL' THEN 1 ELSE 0 END) = 0
      THEN 'PASS'
      ELSE 'FAIL'
    END as overall_result,
    CASE
      WHEN SUM(CASE WHEN coverage_test_result = 'FAIL' THEN 1 ELSE 0 END) = 0
      THEN 'All enrolled employees have enrollment event or registry entry'
      ELSE CAST(SUM(CASE WHEN coverage_test_result = 'FAIL' THEN 1 ELSE 0 END) AS VARCHAR) || ' employees lack both enrollment event and registry entry'
    END as summary_description,
    {{ var('simulation_year', 2025) }} as simulation_year
  FROM test_enrollment_coverage

  UNION ALL

  -- NULL rate test results
  SELECT
    'NULL_DEFERRAL_RATES' as test_name,
    COUNT(*) as total_employees,
    SUM(CASE WHEN null_rate_test_result = 'PASS' THEN 1 ELSE 0 END) as passed_count,
    SUM(CASE WHEN null_rate_test_result = 'FAIL' THEN 1 ELSE 0 END) as failed_count,
    CASE
      WHEN SUM(CASE WHEN null_rate_test_result = 'FAIL' THEN 1 ELSE 0 END) = 0
      THEN 'PASS'
      ELSE 'FAIL'
    END as overall_result,
    CASE
      WHEN SUM(CASE WHEN null_rate_test_result = 'FAIL' THEN 1 ELSE 0 END) = 0
      THEN 'No enrolled employees have NULL deferral rates'
      ELSE CAST(SUM(CASE WHEN null_rate_test_result = 'FAIL' THEN 1 ELSE 0 END) AS VARCHAR) || ' enrolled employees have NULL deferral rates'
    END as summary_description,
    {{ var('simulation_year', 2025) }} as simulation_year
  FROM test_null_deferral_rates

  UNION ALL

  -- NH test case results
  SELECT
    'NH_2025_000007_TEST' as test_name,
    1 as total_employees,
    CASE WHEN nh_test_result = 'PASS' THEN 1 ELSE 0 END as passed_count,
    CASE WHEN nh_test_result = 'FAIL' THEN 1 ELSE 0 END as failed_count,
    nh_test_result as overall_result,
    nh_issue_description as summary_description,
    2025 as simulation_year
  FROM test_nh_2025_000007
)

-- Final output with detailed results
SELECT
  test_name,
  total_employees,
  passed_count,
  failed_count,
  overall_result,
  summary_description,
  simulation_year,

  -- Test priority (higher priority issues first)
  CASE
    WHEN test_name = 'NH_2025_000007_TEST' THEN 1
    WHEN test_name = 'NULL_DEFERRAL_RATES' THEN 2
    WHEN test_name = 'ENROLLMENT_COVERAGE' THEN 3
    ELSE 4
  END as test_priority,

  -- Overall assessment
  CASE
    WHEN overall_result = 'PASS' THEN 'Source of truth architecture working correctly'
    ELSE 'Source of truth architecture issue detected - needs investigation'
  END as architecture_assessment,

  CURRENT_TIMESTAMP as validation_timestamp

FROM validation_summary

UNION ALL

-- Add count consistency check
SELECT
  'EMPLOYEE_COUNT_CONSISTENCY' as test_name,
  2 as total_employees, -- Two metrics being compared
  CASE
    WHEN ABS((SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'ENROLLMENT_EVENTS_COUNT') -
             (SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'DEFERRAL_STATE_COUNT')) <=
             0.05 * (SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'ENROLLMENT_EVENTS_COUNT')
    THEN 1 ELSE 0
  END as passed_count,
  CASE
    WHEN ABS((SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'ENROLLMENT_EVENTS_COUNT') -
             (SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'DEFERRAL_STATE_COUNT')) >
             0.05 * (SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'ENROLLMENT_EVENTS_COUNT')
    THEN 1 ELSE 0
  END as failed_count,
  CASE
    WHEN ABS((SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'ENROLLMENT_EVENTS_COUNT') -
             (SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'DEFERRAL_STATE_COUNT')) <=
             0.05 * (SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'ENROLLMENT_EVENTS_COUNT')
    THEN 'PASS' ELSE 'FAIL'
  END as overall_result,
  'Events: ' || (SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'ENROLLMENT_EVENTS_COUNT') ||
  ', State: ' || (SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'DEFERRAL_STATE_COUNT') ||
  ' - ' ||
  CASE
    WHEN ABS((SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'ENROLLMENT_EVENTS_COUNT') -
             (SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'DEFERRAL_STATE_COUNT')) <=
             0.05 * (SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'ENROLLMENT_EVENTS_COUNT')
    THEN 'Employee counts are consistent'
    ELSE 'Employee count mismatch detected'
  END as summary_description,
  {{ var('simulation_year', 2025) }} as simulation_year,
  4 as test_priority,
  CASE
    WHEN ABS((SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'ENROLLMENT_EVENTS_COUNT') -
             (SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'DEFERRAL_STATE_COUNT')) <=
             0.05 * (SELECT count_value FROM test_employee_count_consistency WHERE metric_name = 'ENROLLMENT_EVENTS_COUNT')
    THEN 'Employee count consistency validated'
    ELSE 'Employee count inconsistency - check event processing'
  END as architecture_assessment,
  CURRENT_TIMESTAMP as validation_timestamp

ORDER BY test_priority, overall_result DESC

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
- All tests should PASS
- NH_2025_000007 should show 6% rate from 'enrollment_event' source
- Zero employees with NULL rates or missing source events
- Consistent employee counts between events and state
*/
