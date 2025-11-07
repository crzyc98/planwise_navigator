{{
  config(
    severity='warn',
    tags=['data_quality', 'deferral_validation', 'rates']
  )
}}

/*
  Data Quality Test: Employee Deferral Rates Validation

  Validates that deferral rates are correctly populated and consistent
  across enrollment events and workforce snapshots.

  Key checks:
  - All enrollment events have valid deferral rates (0-75%)
  - Previous deferral rates are properly tracked
  - Enrolled employees in snapshots have non-zero deferral rates
  - Deferral rate changes are properly reflected

  Returns rows where validation failures are detected.
*/

WITH enrollment_event_violations AS (
    SELECT
        employee_id,
        simulation_year,
        event_type,
        effective_date,
        employee_deferral_rate,
        prev_employee_deferral_rate,
        'enrollment_event_validation' as validation_type,
        CASE
            WHEN employee_deferral_rate IS NULL THEN 'Null deferral rate'
            WHEN employee_deferral_rate < 0 OR employee_deferral_rate > 0.75 THEN 'Invalid rate (outside 0-75%)'
            WHEN event_type = 'enrollment' AND prev_employee_deferral_rate != 0 THEN 'New enrollment has non-zero prev rate'
            ELSE 'Unknown issue'
        END as issue_description
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type IN ('enrollment', 'enrollment_change')
      AND simulation_year = {{ var('simulation_year', 2025) }}
      AND (
          employee_deferral_rate IS NULL
          OR employee_deferral_rate < 0
          OR employee_deferral_rate > 0.75
          OR (event_type = 'enrollment' AND prev_employee_deferral_rate != 0)
      )
),

workforce_snapshot_violations AS (
    SELECT
        employee_id,
        simulation_year,
        is_enrolled_flag,
        current_deferral_rate,
        'workforce_snapshot_validation' as validation_type,
        CASE
            WHEN is_enrolled_flag = true AND current_deferral_rate = 0 THEN 'Enrolled with 0% deferral'
            WHEN is_enrolled_flag = false AND current_deferral_rate > 0 THEN 'Not enrolled but has deferral rate'
            WHEN current_deferral_rate IS NULL THEN 'Null deferral rate in snapshot'
            ELSE 'Unknown issue'
        END as issue_description
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ var('simulation_year', 2025) }}
      AND employment_status = 'active'
      AND (
          (is_enrolled_flag = true AND current_deferral_rate = 0)
          OR (is_enrolled_flag = false AND current_deferral_rate > 0)
          OR current_deferral_rate IS NULL
      )
),

rate_consistency_violations AS (
    SELECT
        ws.employee_id,
        ws.simulation_year,
        ws.current_deferral_rate as snapshot_rate,
        events.latest_deferral_rate as event_rate,
        'rate_consistency_validation' as validation_type,
        CONCAT('Rate mismatch: snapshot=', ROUND(ws.current_deferral_rate * 100, 2), '%, event=', ROUND(events.latest_deferral_rate * 100, 2), '%') as issue_description
    FROM {{ ref('fct_workforce_snapshot') }} ws
    LEFT JOIN (
        SELECT DISTINCT
            employee_id,
            FIRST_VALUE(employee_deferral_rate) OVER (
                PARTITION BY employee_id
                ORDER BY effective_date DESC, event_sequence DESC
            ) AS latest_deferral_rate
        FROM {{ ref('fct_yearly_events') }}
        WHERE event_type IN ('enrollment', 'enrollment_change')
          AND simulation_year = {{ var('simulation_year', 2025) }}
    ) events ON ws.employee_id = events.employee_id
    WHERE ws.simulation_year = {{ var('simulation_year', 2025) }}
      AND ws.is_enrolled_flag = true
      AND ws.employment_status = 'active'
      AND ABS(COALESCE(ws.current_deferral_rate, 0) - COALESCE(events.latest_deferral_rate, 0)) > 0.001
)

-- Return all violations
SELECT
    employee_id,
    simulation_year,
    validation_type,
    issue_description,
    NULL::DECIMAL as rate_value
FROM enrollment_event_violations

UNION ALL

SELECT
    employee_id,
    simulation_year,
    validation_type,
    issue_description,
    current_deferral_rate as rate_value
FROM workforce_snapshot_violations

UNION ALL

SELECT
    employee_id,
    simulation_year,
    validation_type,
    issue_description,
    snapshot_rate as rate_value
FROM rate_consistency_violations

ORDER BY validation_type, employee_id
