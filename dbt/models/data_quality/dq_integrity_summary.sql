{{ config(
    materialized='table',
    tags=['data_quality', 'monitoring', 'summary']
) }}

-- Data Quality Summary: High-level view of integrity status
-- Provides executive dashboard view of data quality metrics

WITH current_violations AS (
    SELECT
        check_name,
        violation_count,
        severity,
        description,
        check_timestamp
    FROM {{ ref('dq_integrity_violations') }}
),

-- Calculate overall system health score
health_metrics AS (
    SELECT
        SUM(CASE WHEN severity = 'CRITICAL' AND violation_count > 0 THEN 1 ELSE 0 END) as critical_issues,
        SUM(CASE WHEN severity = 'HIGH' AND violation_count > 0 THEN 1 ELSE 0 END) as high_issues,
        SUM(CASE WHEN severity = 'MEDIUM' AND violation_count > 0 THEN 1 ELSE 0 END) as medium_issues,
        SUM(violation_count) as total_violations,
        COUNT(*) as total_checks,
        CURRENT_TIMESTAMP as last_check_time
    FROM current_violations
),

-- Determine overall system status
system_status AS (
    SELECT
        *,
        CASE
            WHEN critical_issues > 0 THEN 'CRITICAL'
            WHEN high_issues > 0 THEN 'WARNING'
            WHEN medium_issues > 0 THEN 'MINOR_ISSUES'
            ELSE 'HEALTHY'
        END as overall_status,
        CASE
            WHEN critical_issues > 0 THEN 'System has critical data integrity issues requiring immediate attention'
            WHEN high_issues > 0 THEN 'System has data quality issues that should be addressed soon'
            WHEN medium_issues > 0 THEN 'System has minor issues that can be addressed during next maintenance'
            ELSE 'System is operating within acceptable data quality parameters'
        END as status_message,
        -- Calculate health score (0-100, where 100 is perfect)
        CASE
            WHEN total_checks = 0 THEN 0
            ELSE ROUND(100.0 * (total_checks - critical_issues * 3 - high_issues * 2 - medium_issues * 1) / total_checks, 1)
        END as health_score
    FROM health_metrics
)

SELECT
    overall_status,
    health_score,
    status_message,
    critical_issues,
    high_issues,
    medium_issues,
    total_violations,
    total_checks,
    last_check_time,
    CASE
        WHEN overall_status = 'CRITICAL' THEN '🚨'
        WHEN overall_status = 'WARNING' THEN '⚠️'
        WHEN overall_status = 'MINOR_ISSUES' THEN '🟡'
        ELSE '✅'
    END as status_icon
FROM system_status
