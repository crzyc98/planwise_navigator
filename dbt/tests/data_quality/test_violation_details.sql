-- Converted from validation model to test
-- Added simulation_year filter for performance

-- Data Quality Violation Details: Specific records causing integrity issues
-- Returns only failing records for dbt test

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH duplicate_raise_details AS (
    SELECT
        'duplicate_raise_events' as violation_type,
        employee_id,
        simulation_year,
        effective_date,
        compensation_amount,
        NULL as additional_info,
        COUNT(*) as occurrence_count
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type = 'raise'
      AND simulation_year = {{ simulation_year }}
    GROUP BY employee_id, simulation_year, effective_date, compensation_amount
    HAVING COUNT(*) > 1
),

post_termination_details AS (
    SELECT
        'post_termination_events' as violation_type,
        e.employee_id,
        e.simulation_year,
        e.effective_date,
        e.compensation_amount,
        'Event after termination on ' || t.term_date as additional_info,
        1 as occurrence_count
    FROM {{ ref('fct_yearly_events') }} e
    JOIN (
        SELECT employee_id, effective_date as term_date
        FROM {{ ref('fct_yearly_events') }}
        WHERE event_type = 'termination'
          AND simulation_year = {{ simulation_year }}
    ) t ON e.employee_id = t.employee_id
    WHERE e.effective_date > t.term_date
    AND e.event_type != 'termination'
    AND e.simulation_year = {{ simulation_year }}
),

enrollment_consistency_details AS (
    SELECT
        'enrollment_consistency' as violation_type,
        employee_id,
        simulation_year,
        NULL as effective_date,
        NULL as compensation_amount,
        'Enrolled but missing enrollment date' as additional_info,
        1 as occurrence_count
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE is_enrolled_flag = true
    AND employee_enrollment_date IS NULL
    AND simulation_year = {{ simulation_year }}
),

compensation_consistency_details AS (
    SELECT
        'compensation_vs_contributions' as violation_type,
        employee_id,
        simulation_year,
        NULL as effective_date,
        prorated_annual_compensation as compensation_amount,
        'Contributions (' || ROUND(ytd_contributions, 2) || ') exceed compensation (' || ROUND(prorated_annual_compensation, 2) || ')' as additional_info,
        1 as occurrence_count
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE ytd_contributions > prorated_annual_compensation
    AND ytd_contributions > 0
    AND prorated_annual_compensation > 0
    AND simulation_year = {{ simulation_year }}
),

orphaned_events_details AS (
    SELECT
        'orphaned_events' as violation_type,
        e.employee_id,
        e.simulation_year,
        e.effective_date,
        e.compensation_amount,
        'Event exists but employee not in workforce snapshot' as additional_info,
        1 as occurrence_count
    FROM {{ ref('fct_yearly_events') }} e
    LEFT JOIN {{ ref('fct_workforce_snapshot') }} w
        ON e.employee_id = w.employee_id
        AND e.simulation_year = w.simulation_year
    WHERE w.employee_id IS NULL
      AND e.simulation_year = {{ simulation_year }}
)

-- Union all violation details and return failures for dbt test
SELECT
    violation_type,
    employee_id,
    simulation_year,
    effective_date,
    compensation_amount,
    additional_info,
    occurrence_count,
    CURRENT_TIMESTAMP as detected_at
FROM duplicate_raise_details

UNION ALL

SELECT
    violation_type,
    employee_id,
    simulation_year,
    effective_date,
    compensation_amount,
    additional_info,
    occurrence_count,
    CURRENT_TIMESTAMP as detected_at
FROM post_termination_details

UNION ALL

SELECT
    violation_type,
    employee_id,
    simulation_year,
    effective_date,
    compensation_amount,
    additional_info,
    occurrence_count,
    CURRENT_TIMESTAMP as detected_at
FROM enrollment_consistency_details

UNION ALL

SELECT
    violation_type,
    employee_id,
    simulation_year,
    effective_date,
    compensation_amount,
    additional_info,
    occurrence_count,
    CURRENT_TIMESTAMP as detected_at
FROM compensation_consistency_details

UNION ALL

SELECT
    violation_type,
    employee_id,
    simulation_year,
    effective_date,
    compensation_amount,
    additional_info,
    occurrence_count,
    CURRENT_TIMESTAMP as detected_at
FROM orphaned_events_details

ORDER BY violation_type, employee_id, simulation_year
