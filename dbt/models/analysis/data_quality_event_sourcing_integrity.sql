{{ config(
    materialized='view',
    tags=['data_quality', 'event_sourcing', 'integrity', 'analysis']
) }}

{% set simulation_year = var('simulation_year', 2025) | int %}

-- **Event Sourcing Integrity Validation**
-- Comprehensive validation of event sourcing architecture integrity
-- Ensures events in fct_yearly_events properly flow through to fct_workforce_snapshot

WITH employee_events AS (
    SELECT
        employee_id,
        simulation_year,
        COUNT(CASE WHEN event_type = 'hire' THEN 1 END) AS hire_events,
        COUNT(CASE WHEN event_type = 'termination' THEN 1 END) AS termination_events,
        COUNT(CASE WHEN event_type = 'promotion' THEN 1 END) AS promotion_events,
        COUNT(CASE WHEN event_type = 'raise' THEN 1 END) AS merit_events,
        COUNT(CASE WHEN event_type = 'enrollment' THEN 1 END) AS enrollment_events,

        -- **EVENT TIMING ANALYSIS**
        MIN(CASE WHEN event_type = 'hire' THEN effective_date END) AS first_hire_date,
        MAX(CASE WHEN event_type = 'termination' THEN effective_date END) AS last_termination_date,
        MAX(CASE WHEN event_type = 'promotion' THEN effective_date END) AS last_promotion_date,
        MAX(CASE WHEN event_type = 'raise' THEN effective_date END) AS last_merit_date,

        -- **COMPENSATION TRACKING**
        MAX(CASE WHEN event_type = 'hire' THEN compensation_amount END) AS hire_compensation,
        MAX(CASE WHEN event_type = 'promotion' THEN compensation_amount END) AS promotion_compensation,
        MAX(CASE WHEN event_type = 'raise' THEN compensation_amount END) AS merit_compensation,

        -- **LEVEL TRACKING**
        MAX(CASE WHEN event_type = 'hire' THEN level_id END) AS hire_level,
        MAX(CASE WHEN event_type = 'promotion' THEN level_id END) AS promotion_level,

        -- **EVENT CATEGORY ANALYSIS**
        COUNT(CASE WHEN event_category = 'new_hire_termination' THEN 1 END) AS new_hire_termination_events
    FROM {{ ref('fct_yearly_events') }}
    WHERE simulation_year = {{ simulation_year }}
    GROUP BY employee_id, simulation_year
),

workforce_status AS (
    SELECT
        employee_id,
        simulation_year,
        employment_status,
        detailed_status_code,
        current_compensation,
        level_id AS current_level,
        employee_hire_date,
        termination_date,

        -- **DERIVED STATUS FLAGS**
        CASE WHEN employment_status = 'terminated' THEN 1 ELSE 0 END AS is_terminated,
        CASE WHEN detailed_status_code = 'new_hire_active' THEN 1 ELSE 0 END AS is_new_hire_active,
        CASE WHEN detailed_status_code = 'new_hire_termination' THEN 1 ELSE 0 END AS is_new_hire_terminated,
        CASE WHEN detailed_status_code = 'continuous_active' THEN 1 ELSE 0 END AS is_continuous_active,
        CASE WHEN detailed_status_code = 'experienced_termination' THEN 1 ELSE 0 END AS is_experienced_termination
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ simulation_year }}
),

-- **INTEGRITY TEST 1**: Employee Lifecycle Consistency
lifecycle_consistency AS (
    SELECT
        'EMPLOYEE_LIFECYCLE_CONSISTENCY' AS test_name,
        {{ simulation_year }} AS simulation_year,
        COUNT(*) AS total_employees_with_events,
        COUNT(ws.employee_id) AS employees_in_snapshot,
        COUNT(*) - COUNT(ws.employee_id) AS missing_from_snapshot,

        -- **TERMINATION CONSISTENCY**
        SUM(CASE WHEN ee.termination_events > 0 AND ws.employment_status != 'terminated' THEN 1 ELSE 0 END) AS termination_status_mismatches,

        -- **HIRE CONSISTENCY**
        SUM(CASE WHEN ee.hire_events > 0 AND ws.detailed_status_code NOT IN ('new_hire_active', 'new_hire_termination') THEN 1 ELSE 0 END) AS hire_status_mismatches,

        -- **NEW HIRE TERMINATION CONSISTENCY**
        SUM(CASE WHEN ee.new_hire_termination_events > 0 AND ws.detailed_status_code != 'new_hire_termination' THEN 1 ELSE 0 END) AS new_hire_termination_mismatches,

        -- **OVERALL PASS/FAIL**
        CASE
            WHEN COUNT(*) = COUNT(ws.employee_id)
                 AND SUM(CASE WHEN ee.termination_events > 0 AND ws.employment_status != 'terminated' THEN 1 ELSE 0 END) = 0
                 AND SUM(CASE WHEN ee.new_hire_termination_events > 0 AND ws.detailed_status_code != 'new_hire_termination' THEN 1 ELSE 0 END) = 0
            THEN 'PASS'
            ELSE 'FAIL'
        END AS test_result,

        CURRENT_TIMESTAMP AS test_timestamp
    FROM employee_events ee
    LEFT JOIN workforce_status ws ON ee.employee_id = ws.employee_id AND ee.simulation_year = ws.simulation_year
),

-- **INTEGRITY TEST 2**: Event Count Validation
event_count_validation AS (
    SELECT
        'EVENT_COUNT_VALIDATION' AS test_name,
        {{ simulation_year }} AS simulation_year,

        -- **EVENT TOTALS**
        SUM(ee.hire_events) AS total_hire_events,
        SUM(ee.termination_events) AS total_termination_events,
        SUM(ee.promotion_events) AS total_promotion_events,
        SUM(ee.merit_events) AS total_merit_events,
        SUM(ee.enrollment_events) AS total_enrollment_events,
        SUM(ee.new_hire_termination_events) AS total_new_hire_termination_events,

        -- **SNAPSHOT TOTALS**
        SUM(ws.is_new_hire_active) AS snapshot_new_hire_active,
        SUM(ws.is_new_hire_terminated) AS snapshot_new_hire_terminated,
        SUM(ws.is_continuous_active) AS snapshot_continuous_active,
        SUM(ws.is_experienced_termination) AS snapshot_experienced_termination,
        SUM(ws.is_terminated) AS snapshot_total_terminated,

        -- **BALANCE CHECKS**
        SUM(ee.hire_events) - (SUM(ws.is_new_hire_active) + SUM(ws.is_new_hire_terminated)) AS hire_balance_diff,
        SUM(ee.termination_events) - SUM(ws.is_terminated) AS termination_balance_diff,
        SUM(ee.new_hire_termination_events) - SUM(ws.is_new_hire_terminated) AS new_hire_termination_balance_diff,

        -- **PASS/FAIL LOGIC**
        CASE
            WHEN ABS(SUM(ee.hire_events) - (SUM(ws.is_new_hire_active) + SUM(ws.is_new_hire_terminated))) <= 1
                 AND ABS(SUM(ee.termination_events) - SUM(ws.is_terminated)) <= 1
                 AND ABS(SUM(ee.new_hire_termination_events) - SUM(ws.is_new_hire_terminated)) <= 1
            THEN 'PASS'
            ELSE 'FAIL'
        END AS test_result,

        CURRENT_TIMESTAMP AS test_timestamp
    FROM employee_events ee
    FULL OUTER JOIN workforce_status ws ON ee.employee_id = ws.employee_id AND ee.simulation_year = ws.simulation_year
),

-- **INTEGRITY TEST 3**: Compensation Flow Integrity
compensation_flow_integrity AS (
    SELECT
        'COMPENSATION_FLOW_INTEGRITY' AS test_name,
        {{ simulation_year }} AS simulation_year,

        COUNT(*) AS employees_with_compensation_events,

        -- **HIRE COMPENSATION CONSISTENCY**
        COUNT(CASE
            WHEN ee.hire_events > 0
                 AND ee.hire_compensation IS NOT NULL
                 AND ws.current_compensation IS NOT NULL
                 AND ABS(ee.hire_compensation - ws.current_compensation) > 1000  -- Allow for rounding differences
            THEN 1
        END) AS hire_compensation_mismatches,

        -- **PROMOTION COMPENSATION CONSISTENCY**
        COUNT(CASE
            WHEN ee.promotion_events > 0
                 AND ee.promotion_compensation IS NOT NULL
                 AND ws.current_compensation IS NOT NULL
                 AND ABS(ee.promotion_compensation - ws.current_compensation) > 1000
            THEN 1
        END) AS promotion_compensation_mismatches,

        -- **MERIT COMPENSATION CONSISTENCY**
        COUNT(CASE
            WHEN ee.merit_events > 0
                 AND ee.merit_compensation IS NOT NULL
                 AND ws.current_compensation IS NOT NULL
                 AND ABS(ee.merit_compensation - ws.current_compensation) > 1000
            THEN 1
        END) AS merit_compensation_mismatches,

        -- **LEVEL CONSISTENCY**
        COUNT(CASE
            WHEN ee.promotion_events > 0
                 AND ee.promotion_level IS NOT NULL
                 AND ws.current_level IS NOT NULL
                 AND ee.promotion_level != ws.current_level
            THEN 1
        END) AS level_mismatches,

        CASE
            WHEN COUNT(CASE
                    WHEN ee.hire_events > 0
                         AND ee.hire_compensation IS NOT NULL
                         AND ws.current_compensation IS NOT NULL
                         AND ABS(ee.hire_compensation - ws.current_compensation) > 1000
                    THEN 1
                END) = 0
                 AND COUNT(CASE
                    WHEN ee.promotion_events > 0
                         AND ee.promotion_level IS NOT NULL
                         AND ws.current_level IS NOT NULL
                         AND ee.promotion_level != ws.current_level
                    THEN 1
                END) = 0
            THEN 'PASS'
            ELSE 'FAIL'
        END AS test_result,

        CURRENT_TIMESTAMP AS test_timestamp
    FROM employee_events ee
    INNER JOIN workforce_status ws ON ee.employee_id = ws.employee_id AND ee.simulation_year = ws.simulation_year
    WHERE ee.hire_events > 0 OR ee.promotion_events > 0 OR ee.merit_events > 0
),

-- **INTEGRITY TEST 4**: Timeline Consistency
timeline_consistency AS (
    SELECT
        'TIMELINE_CONSISTENCY' AS test_name,
        {{ simulation_year }} AS simulation_year,

        COUNT(*) AS employees_with_timeline_events,

        -- **HIRE DATE CONSISTENCY**
        COUNT(CASE
            WHEN ee.first_hire_date IS NOT NULL
                 AND ws.employee_hire_date IS NOT NULL
                 AND ee.first_hire_date != ws.employee_hire_date
            THEN 1
        END) AS hire_date_mismatches,

        -- **TERMINATION DATE CONSISTENCY**
        COUNT(CASE
            WHEN ee.last_termination_date IS NOT NULL
                 AND ws.termination_date IS NOT NULL
                 AND DATE(ee.last_termination_date) != DATE(ws.termination_date)
            THEN 1
        END) AS termination_date_mismatches,

        -- **LOGICAL SEQUENCE VALIDATION** (hire before termination)
        COUNT(CASE
            WHEN ee.first_hire_date IS NOT NULL
                 AND ee.last_termination_date IS NOT NULL
                 AND ee.first_hire_date > ee.last_termination_date
            THEN 1
        END) AS illogical_sequence_errors,

        CASE
            WHEN COUNT(CASE
                    WHEN ee.first_hire_date IS NOT NULL
                         AND ws.employee_hire_date IS NOT NULL
                         AND ee.first_hire_date != ws.employee_hire_date
                    THEN 1
                END) = 0
                 AND COUNT(CASE
                    WHEN ee.last_termination_date IS NOT NULL
                         AND ws.termination_date IS NOT NULL
                         AND DATE(ee.last_termination_date) != DATE(ws.termination_date)
                    THEN 1
                END) = 0
                 AND COUNT(CASE
                    WHEN ee.first_hire_date IS NOT NULL
                         AND ee.last_termination_date IS NOT NULL
                         AND ee.first_hire_date > ee.last_termination_date
                    THEN 1
                END) = 0
            THEN 'PASS'
            ELSE 'FAIL'
        END AS test_result,

        CURRENT_TIMESTAMP AS test_timestamp
    FROM employee_events ee
    INNER JOIN workforce_status ws ON ee.employee_id = ws.employee_id AND ee.simulation_year = ws.simulation_year
    WHERE ee.first_hire_date IS NOT NULL OR ee.last_termination_date IS NOT NULL
)

-- **FINAL OUTPUT**: Union all integrity test results
SELECT
    test_name,
    simulation_year,
    total_employees_with_events,
    employees_in_snapshot,
    missing_from_snapshot,
    termination_status_mismatches,
    hire_status_mismatches,
    new_hire_termination_mismatches,
    NULL AS total_hire_events,
    NULL AS hire_balance_diff,
    NULL AS termination_balance_diff,
    NULL AS new_hire_termination_balance_diff,
    NULL AS hire_compensation_mismatches,
    NULL AS level_mismatches,
    NULL AS hire_date_mismatches,
    NULL AS illogical_sequence_errors,
    test_result,
    test_timestamp
FROM lifecycle_consistency

UNION ALL

SELECT
    test_name,
    simulation_year,
    NULL AS total_employees_with_events,
    NULL AS employees_in_snapshot,
    NULL AS missing_from_snapshot,
    NULL AS termination_status_mismatches,
    NULL AS hire_status_mismatches,
    NULL AS new_hire_termination_mismatches,
    total_hire_events,
    hire_balance_diff,
    termination_balance_diff,
    new_hire_termination_balance_diff,
    NULL AS hire_compensation_mismatches,
    NULL AS level_mismatches,
    NULL AS hire_date_mismatches,
    NULL AS illogical_sequence_errors,
    test_result,
    test_timestamp
FROM event_count_validation

UNION ALL

SELECT
    test_name,
    simulation_year,
    employees_with_compensation_events AS total_employees_with_events,
    NULL AS employees_in_snapshot,
    NULL AS missing_from_snapshot,
    NULL AS termination_status_mismatches,
    NULL AS hire_status_mismatches,
    NULL AS new_hire_termination_mismatches,
    NULL AS total_hire_events,
    NULL AS hire_balance_diff,
    NULL AS termination_balance_diff,
    NULL AS new_hire_termination_balance_diff,
    hire_compensation_mismatches,
    level_mismatches,
    NULL AS hire_date_mismatches,
    NULL AS illogical_sequence_errors,
    test_result,
    test_timestamp
FROM compensation_flow_integrity

UNION ALL

SELECT
    test_name,
    simulation_year,
    employees_with_timeline_events AS total_employees_with_events,
    NULL AS employees_in_snapshot,
    NULL AS missing_from_snapshot,
    NULL AS termination_status_mismatches,
    NULL AS hire_status_mismatches,
    NULL AS new_hire_termination_mismatches,
    NULL AS total_hire_events,
    NULL AS hire_balance_diff,
    NULL AS termination_balance_diff,
    NULL AS new_hire_termination_balance_diff,
    NULL AS hire_compensation_mismatches,
    NULL AS level_mismatches,
    hire_date_mismatches,
    illogical_sequence_errors,
    test_result,
    test_timestamp
FROM timeline_consistency

ORDER BY
    CASE test_name
        WHEN 'EMPLOYEE_LIFECYCLE_CONSISTENCY' THEN 1
        WHEN 'EVENT_COUNT_VALIDATION' THEN 2
        WHEN 'COMPENSATION_FLOW_INTEGRITY' THEN 3
        WHEN 'TIMELINE_CONSISTENCY' THEN 4
        ELSE 5
    END
