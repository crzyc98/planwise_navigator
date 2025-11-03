{{
  config(
    severity='error',
    tags=['data_quality', 'monitoring', 'integrity', 'epic_e045']
  )
}}

/*
  Data Quality Test: Automated Detection of Integrity Violations

  Monitors critical integrity issues identified in Epic E045:
  1. Duplicate raise events
  2. Post-termination events
  3. Enrollment consistency
  4. Compensation vs contributions consistency
  5. Event sequence validity
  6. Orphaned events

  Returns rows where any integrity violations are detected.
*/

WITH duplicate_raise_violations AS (
    SELECT
        employee_id,
        simulation_year,
        effective_date,
        compensation_amount,
        COUNT(*) as duplicate_count,
        'duplicate_raise_events' as violation_type,
        'CRITICAL' as severity,
        CONCAT('Multiple identical RAISE events: ', COUNT(*), ' duplicates') as description
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type = 'raise'
    GROUP BY employee_id, simulation_year, effective_date, compensation_amount
    HAVING COUNT(*) > 1
),

post_termination_violations AS (
    SELECT
        e.employee_id,
        e.simulation_year,
        e.effective_date,
        t.term_date as termination_date,
        e.event_type,
        'post_termination_events' as violation_type,
        'CRITICAL' as severity,
        CONCAT('Event (', e.event_type, ') after termination on ', t.term_date) as description
    FROM {{ ref('fct_yearly_events') }} e
    JOIN (
        SELECT employee_id, effective_date as term_date
        FROM {{ ref('fct_yearly_events') }}
        WHERE event_type = 'termination'
    ) t ON e.employee_id = t.employee_id
    WHERE e.effective_date > t.term_date
    AND e.event_type != 'termination'
),

enrollment_consistency_violations AS (
    SELECT
        employee_id,
        simulation_year,
        is_enrolled_flag,
        'enrollment_consistency' as violation_type,
        'HIGH' as severity,
        'Marked as enrolled but missing enrollment date' as description
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE is_enrolled_flag = true
    AND employee_enrollment_date IS NULL
),

compensation_consistency_violations AS (
    SELECT
        employee_id,
        simulation_year,
        ytd_contributions,
        prorated_annual_compensation,
        'compensation_vs_contributions' as violation_type,
        'HIGH' as severity,
        CONCAT('Contributions ($', ROUND(ytd_contributions, 2), ') exceed compensation ($', ROUND(prorated_annual_compensation, 2), ')') as description
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE ytd_contributions > prorated_annual_compensation
    AND ytd_contributions > 0
    AND prorated_annual_compensation > 0
),

event_sequence_violations AS (
    SELECT
        employee_id,
        simulation_year,
        event_type,
        effective_date,
        event_sequence,
        'invalid_event_sequence' as violation_type,
        'MEDIUM' as severity,
        CONCAT('Invalid event sequence: ', COALESCE(CAST(event_sequence AS VARCHAR), 'NULL')) as description
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_sequence IS NULL
    OR event_sequence < 0
),

orphaned_events_violations AS (
    SELECT
        e.employee_id,
        e.simulation_year,
        e.event_type,
        e.effective_date,
        'orphaned_events' as violation_type,
        'MEDIUM' as severity,
        CONCAT('Event (', e.event_type, ') for employee not in workforce snapshot') as description
    FROM {{ ref('fct_yearly_events') }} e
    LEFT JOIN {{ ref('fct_workforce_snapshot') }} w
        ON e.employee_id = w.employee_id
        AND e.simulation_year = w.simulation_year
    WHERE w.employee_id IS NULL
)

-- Return all violations
SELECT employee_id, simulation_year, violation_type, severity, description,
       NULL::DATE as effective_date, NULL::DECIMAL as amount
FROM duplicate_raise_violations

UNION ALL

SELECT employee_id, simulation_year, violation_type, severity, description,
       effective_date, NULL::DECIMAL as amount
FROM post_termination_violations

UNION ALL

SELECT employee_id, simulation_year, violation_type, severity, description,
       NULL::DATE as effective_date, NULL::DECIMAL as amount
FROM enrollment_consistency_violations

UNION ALL

SELECT employee_id, simulation_year, violation_type, severity, description,
       NULL::DATE as effective_date, ytd_contributions as amount
FROM compensation_consistency_violations

UNION ALL

SELECT employee_id, simulation_year, violation_type, severity, description,
       effective_date, NULL::DECIMAL as amount
FROM event_sequence_violations

UNION ALL

SELECT employee_id, simulation_year, violation_type, severity, description,
       effective_date, NULL::DECIMAL as amount
FROM orphaned_events_violations

ORDER BY
    CASE severity
        WHEN 'CRITICAL' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3
        ELSE 4
    END,
    simulation_year,
    employee_id
