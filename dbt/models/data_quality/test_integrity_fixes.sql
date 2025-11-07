{{ config(
    materialized='table',
    tags=['data_quality', 'testing', 'epic_e045'],
    enabled=false
) }}

-- Comprehensive test to validate Epic E045 integrity fixes
-- Verifies that all critical data integrity issues have been resolved

WITH test_results AS (
    -- Test 1: No duplicate RAISE events
    SELECT
        'duplicate_raise_events' as test_name,
        CASE
            WHEN COUNT(*) = 0 THEN 'PASS'
            ELSE 'FAIL'
        END as test_result,
        COUNT(*) as failure_count,
        'Epic E045-S001: No duplicate RAISE events should exist' as test_description
    FROM (
        SELECT employee_id, simulation_year, effective_date, compensation_amount
        FROM {{ ref('fct_yearly_events') }}
        WHERE event_type = 'raise'
        GROUP BY employee_id, simulation_year, effective_date, compensation_amount
        HAVING COUNT(*) > 1
    )

    UNION ALL

    -- Test 2: No post-termination events
    SELECT
        'post_termination_events' as test_name,
        CASE
            WHEN COUNT(*) = 0 THEN 'PASS'
            ELSE 'FAIL'
        END as test_result,
        COUNT(*) as failure_count,
        'Epic E045-S002: No events should occur after employee termination' as test_description
    FROM {{ ref('fct_yearly_events') }} e
    JOIN (
        SELECT employee_id, effective_date as term_date
        FROM {{ ref('fct_yearly_events') }}
        WHERE event_type = 'termination'
    ) t ON e.employee_id = t.employee_id
    WHERE e.effective_date > t.term_date
    AND e.event_type != 'termination'

    UNION ALL

    -- Test 3: Enrollment consistency
    SELECT
        'enrollment_consistency' as test_name,
        CASE
            WHEN COUNT(*) = 0 THEN 'PASS'
            ELSE 'FAIL'
        END as test_result,
        COUNT(*) as failure_count,
        'Epic E045-S003: Enrolled employees must have enrollment dates' as test_description
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE is_enrolled_flag = true
    AND employee_enrollment_date IS NULL

    UNION ALL

    -- Test 4: Data quality monitoring is working
    SELECT
        'monitoring_system' as test_name,
        CASE
            WHEN COUNT(*) >= 6 THEN 'PASS'
            ELSE 'FAIL'
        END as test_result,
        COUNT(*) as failure_count,
        'Epic E045-S004: Data quality monitoring system should be operational' as test_description
    FROM {{ ref('dq_integrity_violations') }}

    UNION ALL

    -- Test 5: Merit events respect termination dates
    SELECT
        'merit_termination_validation' as test_name,
        CASE
            WHEN COUNT(*) = 0 THEN 'PASS'
            ELSE 'FAIL'
        END as test_result,
        COUNT(*) as failure_count,
        'Epic E045-S002: Merit events should not be generated for terminated employees' as test_description
    FROM {{ ref('int_merit_events') }} m
    JOIN {{ ref('int_termination_events') }} t
        ON m.employee_id = t.employee_id
        AND t.simulation_year <= m.simulation_year
    WHERE m.effective_date > t.effective_date
)

SELECT
    test_name,
    test_result,
    failure_count,
    test_description,
    CURRENT_TIMESTAMP as test_timestamp,
    CASE
        WHEN test_result = 'PASS' THEN '✅'
        ELSE '❌'
    END as status_icon
FROM test_results
ORDER BY
    CASE WHEN test_result = 'FAIL' THEN 1 ELSE 2 END,
    test_name
