{{ config(
    materialized='table',
    tags=['data_quality', 'monitoring']
) }}

-- Data Quality Monitoring: Automated detection of integrity violations
-- Monitors the three critical integrity issues identified in Epic E045

WITH duplicate_raise_check AS (
    SELECT
        'duplicate_raise_events' as check_name,
        COUNT(*) as violation_count,
        CURRENT_TIMESTAMP as check_timestamp,
        'CRITICAL' as severity,
        'Multiple identical RAISE events for same employee/date/amount' as description
    FROM (
        SELECT employee_id, simulation_year, effective_date, compensation_amount
        FROM {{ ref('fct_yearly_events') }}
        WHERE event_type = 'raise'
        GROUP BY employee_id, simulation_year, effective_date, compensation_amount
        HAVING COUNT(*) > 1
    )
),

post_termination_check AS (
    SELECT
        'post_termination_events' as check_name,
        COUNT(DISTINCT e.employee_id) as violation_count,
        CURRENT_TIMESTAMP as check_timestamp,
        'CRITICAL' as severity,
        'Events occurring after employee termination date' as description
    FROM {{ ref('fct_yearly_events') }} e
    JOIN (
        SELECT employee_id, effective_date as term_date
        FROM {{ ref('fct_yearly_events') }}
        WHERE event_type = 'termination'
    ) t ON e.employee_id = t.employee_id
    WHERE e.effective_date > t.term_date
    AND e.event_type != 'termination'
),

enrollment_consistency_check AS (
    SELECT
        'enrollment_consistency' as check_name,
        COUNT(*) as violation_count,
        CURRENT_TIMESTAMP as check_timestamp,
        'HIGH' as severity,
        'Employees marked as enrolled but missing enrollment dates' as description
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE is_enrolled_flag = true
    AND employee_enrollment_date IS NULL
),

-- Additional quality checks for comprehensive monitoring
compensation_consistency_check AS (
    SELECT
        'compensation_vs_contributions' as check_name,
        COUNT(*) as violation_count,
        CURRENT_TIMESTAMP as check_timestamp,
        'HIGH' as severity,
        'Employees with contributions exceeding their compensation' as description
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE ytd_contributions > prorated_annual_compensation
    AND ytd_contributions > 0
    AND prorated_annual_compensation > 0
),

event_sequence_check AS (
    SELECT
        'invalid_event_sequence' as check_name,
        COUNT(*) as violation_count,
        CURRENT_TIMESTAMP as check_timestamp,
        'MEDIUM' as severity,
        'Events with invalid or null sequence numbers' as description
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_sequence IS NULL
    OR event_sequence < 0
),

-- Orphaned events check
orphaned_events_check AS (
    SELECT
        'orphaned_events' as check_name,
        COUNT(*) as violation_count,
        CURRENT_TIMESTAMP as check_timestamp,
        'MEDIUM' as severity,
        'Events for employees not in workforce snapshot' as description
    FROM {{ ref('fct_yearly_events') }} e
    LEFT JOIN {{ ref('fct_workforce_snapshot') }} w
        ON e.employee_id = w.employee_id
        AND e.simulation_year = w.simulation_year
    WHERE w.employee_id IS NULL
)

-- Union all checks
SELECT * FROM duplicate_raise_check
UNION ALL
SELECT * FROM post_termination_check
UNION ALL
SELECT * FROM enrollment_consistency_check
UNION ALL
SELECT * FROM compensation_consistency_check
UNION ALL
SELECT * FROM event_sequence_check
UNION ALL
SELECT * FROM orphaned_events_check
