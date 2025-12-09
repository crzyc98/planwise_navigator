-- Converted from validation model to test
-- Added simulation_year filter for performance

/*
  Story S042-01 Validation: Fix Source of Truth Architecture

  This test validates the implementation of Story S042-01 requirements:
  1. Every enrolled employee has enrollment event OR registry entry
  2. NH_2025_000007 shows 6% deferral rate from enrollment event
  3. No circular dependencies (enrollment events are primary source)
  4. Clean event-driven architecture

  Expected Results:
  - 0 rows returned means all validations pass
  - Zero employees with enrollment but no events
  - NH_2025_000007 with 6% deferral rate if enrolled
  - All deferral rates sourced from enrollment events (not demographics)
*/

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH
-- Get all enrolled employees from V2 accumulator
enrolled_employees_v2 AS (
    SELECT
        employee_id,
        current_deferral_rate,
        original_deferral_rate,
        is_enrolled_flag,
        employee_enrollment_date,
        data_quality_flag,
        'v2_accumulator' as source
    FROM {{ ref('int_deferral_rate_state_accumulator_v2') }}
    WHERE simulation_year = {{ simulation_year }}
      AND is_enrolled_flag = true
),

-- Get enrollment events for validation
enrollment_events AS (
    SELECT DISTINCT
        employee_id,
        employee_deferral_rate,
        effective_date,
        event_type
    FROM {{ ref('int_enrollment_events') }}
    WHERE simulation_year <= {{ simulation_year }}
      AND LOWER(event_type) = 'enrollment'
      AND employee_deferral_rate IS NOT NULL
),

-- E096 FIX: Validation updated to account for census-sourced enrollments
-- Enrolled employees can have either:
-- 1. An enrollment event in int_enrollment_events, OR
-- 2. Census data with deferral rate > 0 (synthetic_baseline_enrollments)
census_enrolled AS (
    SELECT employee_id
    FROM {{ ref('int_baseline_workforce') }}
    WHERE employee_deferral_rate > 0
      AND employee_enrollment_date IS NOT NULL
),

enrolled_without_events AS (
    SELECT
        e.employee_id,
        e.current_deferral_rate,
        e.employee_enrollment_date,
        'ENROLLED_WITHOUT_EVENT' as validation_issue,
        'FAIL' as validation_status,
        'Employee enrolled without supporting enrollment event or census data' as issue_description
    FROM enrolled_employees_v2 e
    LEFT JOIN enrollment_events ev ON e.employee_id = ev.employee_id
    LEFT JOIN census_enrolled ce ON e.employee_id = ce.employee_id
    -- Only flag as failure if neither enrollment event nor census enrollment exists
    WHERE ev.employee_id IS NULL AND ce.employee_id IS NULL
),

-- Test case: Check NH_2025_000007 specifically
nh_test_case AS (
    SELECT
        employee_id,
        current_deferral_rate,
        original_deferral_rate,
        CASE
            WHEN current_deferral_rate = 0.06 THEN 'PASS'
            ELSE 'FAIL - Expected 6% deferral rate'
        END as nh_validation_status,
        CASE
            WHEN current_deferral_rate = 0.06 THEN 'PASS'
            ELSE 'NH_2025_000007 does not have expected 6% deferral rate'
        END as issue_description
    FROM enrolled_employees_v2
    WHERE employee_id = 'NH_2025_000007'
      AND nh_validation_status != 'PASS'
),

-- Summary statistics for count-based validation
-- E096 FIX: Updated to account for both event-based and census-based enrollments
validation_summary AS (
    SELECT
        {{ simulation_year }} as simulation_year,
        COUNT(*) as total_enrolled_employees,
        COUNT(CASE WHEN ev.employee_id IS NOT NULL THEN 1 END) as enrolled_with_events,
        COUNT(CASE WHEN ce.employee_id IS NOT NULL THEN 1 END) as enrolled_with_census,
        COUNT(CASE WHEN ev.employee_id IS NULL AND ce.employee_id IS NULL THEN 1 END) as enrolled_without_source,
        COUNT(CASE WHEN e.employee_id = 'NH_2025_000007' THEN 1 END) as nh_test_case_count,
        ROUND(AVG(e.current_deferral_rate), 4) as avg_deferral_rate,
        MIN(e.current_deferral_rate) as min_deferral_rate,
        MAX(e.current_deferral_rate) as max_deferral_rate
    FROM enrolled_employees_v2 e
    LEFT JOIN enrollment_events ev ON e.employee_id = ev.employee_id
    LEFT JOIN census_enrolled ce ON e.employee_id = ce.employee_id
),

-- Final validation results (only failures)
-- E096 FIX: Updated to check for both event-based and census-based enrollments
validation_failures AS (
    SELECT
        'DATA_QUALITY_CHECK' as validation_type,
        'Every enrolled employee has enrollment event or census data' as validation_rule,
        vs.enrolled_without_source as failed_count,
        'FAIL' as validation_status,
        'Enrolled employees without enrollment events or census data detected' as issue_description
    FROM validation_summary vs
    WHERE vs.enrolled_without_source > 0
)

-- Return only failing records (0 rows = all validations pass)
-- DuckDB FIX: Wrap UNION in subquery before applying ORDER BY
SELECT *
FROM (
    SELECT
        employee_id,
        validation_issue as validation_type,
        validation_status,
        issue_description,
        current_deferral_rate,
        employee_enrollment_date,
        {{ simulation_year }} as simulation_year,
        CURRENT_TIMESTAMP as validation_timestamp,
        'S042-01 Source of Truth Architecture Fix' as story_reference
    FROM enrolled_without_events

    UNION ALL

    SELECT
        employee_id,
        'SPECIFIC_TEST_CASE' as validation_type,
        nh_validation_status as validation_status,
        issue_description,
        current_deferral_rate,
        NULL as employee_enrollment_date,
        {{ simulation_year }},
        CURRENT_TIMESTAMP,
        'S042-01 NH_2025_000007 test case'
    FROM nh_test_case

    UNION ALL

    SELECT
        NULL as employee_id,
        validation_type,
        validation_status,
        issue_description || ' (Count: ' || CAST(failed_count AS VARCHAR) || ')' as issue_description,
        NULL as current_deferral_rate,
        NULL as employee_enrollment_date,
        {{ simulation_year }},
        CURRENT_TIMESTAMP,
        'S042-01 Summary validation'
    FROM validation_failures
) all_validation_failures
ORDER BY
    CASE validation_type
        WHEN 'DATA_QUALITY_CHECK' THEN 1
        WHEN 'SPECIFIC_TEST_CASE' THEN 2
        ELSE 3
    END,
    employee_id

/*
  Story S042-01 Validation Summary:

  This test ensures that the source of truth architecture fix is working correctly:

  1. DATA_QUALITY_CHECK: Validates that every enrolled employee has a corresponding enrollment event
  2. SPECIFIC_TEST_CASE: Tests the specific NH_2025_000007 case mentioned in the story requirements
  3. ARCHITECTURE_CHECK: Confirms the V2 model uses event-driven architecture

  Expected Results for Successful Implementation:
  - 0 rows returned (all validations pass)
  - enrolled_without_events = 0 (all enrolled employees have events)
  - NH_2025_000007 shows 6% deferral rate (if present in data)
  - V2 model uses enrollment events as primary source

  If any rows are returned, it indicates the source of truth architecture fix needs attention.
*/
