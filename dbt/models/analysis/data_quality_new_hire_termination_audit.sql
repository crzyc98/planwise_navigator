{{ config(
    materialized='view',
    tags=['data_quality', 'audit', 'analysis']
) }}

{% set simulation_year = var('simulation_year', 2025) | int %}

-- **Data Quality Audit: New Hire Termination Integrity**
-- Validates that new hire termination events in fct_yearly_events are properly
-- reflected in fct_workforce_snapshot with correct employment status

WITH new_hire_events AS (
    SELECT DISTINCT
        employee_id,
        simulation_year,
        'new_hire' AS event_category
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type = 'hire'
        AND simulation_year = {{ simulation_year }}
),

termination_events AS (
    SELECT DISTINCT
        employee_id,
        simulation_year,
        event_category,
        'termination' AS event_type
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type = 'termination'
        AND simulation_year = {{ simulation_year }}
),

new_hire_termination_events AS (
    SELECT
        t.employee_id,
        t.simulation_year,
        'new_hire_termination' AS expected_status
    FROM termination_events t
    INNER JOIN new_hire_events nh
        ON t.employee_id = nh.employee_id
        AND t.simulation_year = nh.simulation_year
    WHERE t.event_category = 'new_hire_termination'
),

workforce_snapshot_status AS (
    SELECT DISTINCT
        employee_id,
        simulation_year,
        employment_status,
        detailed_status_code
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ simulation_year }}
),

-- **CRITICAL TEST**: Compare events vs snapshot status
audit_results AS (
    SELECT
        'NEW_HIRE_TERMINATION_INTEGRITY' AS test_name,
        {{ simulation_year }} AS simulation_year,
        COUNT(nht.employee_id) AS events_new_hire_terminations,
        COUNT(CASE WHEN ws.employment_status = 'terminated' THEN 1 END) AS snapshot_terminated_count,
        COUNT(CASE WHEN ws.detailed_status_code = 'new_hire_termination' THEN 1 END) AS snapshot_new_hire_termination_count,
        COUNT(nht.employee_id) - COUNT(CASE WHEN ws.employment_status = 'terminated' THEN 1 END) AS missing_terminated_status,
        COUNT(nht.employee_id) - COUNT(CASE WHEN ws.detailed_status_code = 'new_hire_termination' THEN 1 END) AS missing_detailed_status,

        -- **KEY BUSINESS RULE**: All new hire termination events should appear as terminated in snapshot
        CASE
            WHEN COUNT(nht.employee_id) = COUNT(CASE WHEN ws.employment_status = 'terminated' THEN 1 END)
                 AND COUNT(nht.employee_id) = COUNT(CASE WHEN ws.detailed_status_code = 'new_hire_termination' THEN 1 END)
            THEN 'PASS'
            ELSE 'FAIL'
        END AS test_result,

        -- **DIAGNOSTIC INFO**
        ROUND(
            CASE
                WHEN COUNT(nht.employee_id) > 0
                THEN (COUNT(CASE WHEN ws.employment_status = 'terminated' THEN 1 END) * 100.0 / COUNT(nht.employee_id))
                ELSE 100.0
            END, 1
        ) AS employment_status_accuracy_pct,

        ROUND(
            CASE
                WHEN COUNT(nht.employee_id) > 0
                THEN (COUNT(CASE WHEN ws.detailed_status_code = 'new_hire_termination' THEN 1 END) * 100.0 / COUNT(nht.employee_id))
                ELSE 100.0
            END, 1
        ) AS detailed_status_accuracy_pct

    FROM new_hire_termination_events nht
    LEFT JOIN workforce_snapshot_status ws
        ON nht.employee_id = ws.employee_id
        AND nht.simulation_year = ws.simulation_year
),

-- **DETAILED FAILURE ANALYSIS**: Identify specific employees with mismatches
failure_details AS (
    SELECT
        'DETAILED_FAILURE_ANALYSIS' AS test_name,
        nht.employee_id,
        nht.simulation_year,
        ws.employment_status AS snapshot_employment_status,
        ws.detailed_status_code AS snapshot_detailed_status,

        -- **ISSUE CLASSIFICATION**
        CASE
            WHEN ws.employee_id IS NULL THEN 'MISSING_FROM_SNAPSHOT'
            WHEN ws.employment_status != 'terminated' THEN 'WRONG_EMPLOYMENT_STATUS'
            WHEN ws.detailed_status_code != 'new_hire_termination' THEN 'WRONG_DETAILED_STATUS'
            ELSE 'CORRECT'
        END AS issue_type,

        -- **SEVERITY ASSESSMENT**
        CASE
            WHEN ws.employee_id IS NULL THEN 'CRITICAL'
            WHEN ws.employment_status != 'terminated' THEN 'HIGH'
            WHEN ws.detailed_status_code != 'new_hire_termination' THEN 'MEDIUM'
            ELSE 'NONE'
        END AS severity

    FROM new_hire_termination_events nht
    LEFT JOIN workforce_snapshot_status ws
        ON nht.employee_id = ws.employee_id
        AND nht.simulation_year = ws.simulation_year
    WHERE ws.employee_id IS NULL
       OR ws.employment_status != 'terminated'
       OR ws.detailed_status_code != 'new_hire_termination'
),

-- **SUMMARY STATISTICS**: Overall data quality metrics
summary_stats AS (
    SELECT
        'SUMMARY_STATISTICS' AS test_name,
        {{ simulation_year }} AS simulation_year,

        -- **EVENT COUNTS**
        (SELECT COUNT(*) FROM new_hire_events) AS total_new_hires,
        (SELECT COUNT(*) FROM termination_events) AS total_terminations,
        (SELECT COUNT(*) FROM new_hire_termination_events) AS total_new_hire_terminations,

        -- **SNAPSHOT COUNTS**
        (SELECT COUNT(*) FROM workforce_snapshot_status WHERE employment_status = 'active') AS snapshot_active_employees,
        (SELECT COUNT(*) FROM workforce_snapshot_status WHERE employment_status = 'terminated') AS snapshot_terminated_employees,
        (SELECT COUNT(*) FROM workforce_snapshot_status WHERE detailed_status_code = 'new_hire_active') AS snapshot_new_hire_active,
        (SELECT COUNT(*) FROM workforce_snapshot_status WHERE detailed_status_code = 'new_hire_termination') AS snapshot_new_hire_terminated,

        -- **DATA QUALITY SCORE**
        CASE
            WHEN (SELECT COUNT(*) FROM new_hire_termination_events) = 0 THEN 100.0
            ELSE ROUND(
                (SELECT COUNT(*) FROM workforce_snapshot_status ws
                 INNER JOIN new_hire_termination_events nht ON ws.employee_id = nht.employee_id
                 WHERE ws.employment_status = 'terminated' AND ws.detailed_status_code = 'new_hire_termination'
                ) * 100.0 / (SELECT COUNT(*) FROM new_hire_termination_events), 1
            )
        END AS overall_data_quality_score,

        CURRENT_TIMESTAMP AS audit_timestamp
)

-- **FINAL OUTPUT**: Union all audit results for comprehensive view
SELECT
    test_name,
    simulation_year,
    events_new_hire_terminations,
    snapshot_terminated_count,
    snapshot_new_hire_termination_count,
    missing_terminated_status,
    missing_detailed_status,
    test_result,
    employment_status_accuracy_pct,
    detailed_status_accuracy_pct,
    NULL AS employee_id,
    NULL AS issue_type,
    NULL AS severity,
    NULL AS total_new_hires,
    NULL AS overall_data_quality_score,
    CURRENT_TIMESTAMP AS audit_timestamp
FROM audit_results

UNION ALL

SELECT
    test_name,
    simulation_year,
    NULL AS events_new_hire_terminations,
    NULL AS snapshot_terminated_count,
    NULL AS snapshot_new_hire_termination_count,
    NULL AS missing_terminated_status,
    NULL AS missing_detailed_status,
    CASE WHEN COUNT(*) = 0 THEN 'PASS' ELSE 'FAIL' END AS test_result,
    NULL AS employment_status_accuracy_pct,
    NULL AS detailed_status_accuracy_pct,
    employee_id,
    issue_type,
    severity,
    NULL AS total_new_hires,
    NULL AS overall_data_quality_score,
    CURRENT_TIMESTAMP AS audit_timestamp
FROM failure_details
GROUP BY test_name, simulation_year, employee_id, issue_type, severity

UNION ALL

SELECT
    test_name,
    simulation_year,
    NULL AS events_new_hire_terminations,
    NULL AS snapshot_terminated_count,
    NULL AS snapshot_new_hire_termination_count,
    NULL AS missing_terminated_status,
    NULL AS missing_detailed_status,
    CASE WHEN overall_data_quality_score >= 95.0 THEN 'PASS' ELSE 'FAIL' END AS test_result,
    NULL AS employment_status_accuracy_pct,
    NULL AS detailed_status_accuracy_pct,
    NULL AS employee_id,
    NULL AS issue_type,
    NULL AS severity,
    total_new_hires,
    overall_data_quality_score,
    audit_timestamp
FROM summary_stats

ORDER BY test_name, employee_id
