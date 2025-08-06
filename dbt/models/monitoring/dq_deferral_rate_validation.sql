{{ config(
    materialized='view',
    tags=['data_quality', 'deferral_validation']
) }}

/*
  Data Quality Validation for Employee Deferral Rates

  This model validates that deferral rates are correctly populated and consistent
  across enrollment events and workforce snapshots. Key checks include:
  - All enrollment events have valid deferral rates (0-75%)
  - Previous deferral rates are properly tracked
  - Enrolled employees in snapshots have non-zero deferral rates
  - Deferral rate changes are properly reflected
*/

WITH enrollment_event_checks AS (
    -- Check that all enrollment events have valid deferral rates
    SELECT
        'enrollment_events_have_rates' AS check_name,
        COUNT(*) AS total_records,
        COUNT(CASE WHEN employee_deferral_rate IS NULL THEN 1 END) AS null_rates,
        COUNT(CASE WHEN employee_deferral_rate < 0 OR employee_deferral_rate > 0.75 THEN 1 END) AS invalid_rates,
        COUNT(CASE WHEN event_type = 'enrollment' AND prev_employee_deferral_rate != 0 THEN 1 END) AS invalid_prev_rates,
        MIN(employee_deferral_rate) AS min_rate,
        MAX(employee_deferral_rate) AS max_rate,
        AVG(employee_deferral_rate) AS avg_rate
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type IN ('enrollment', 'enrollment_change')
      AND simulation_year = {{ var('simulation_year', 2025) }}
),

workforce_snapshot_checks AS (
    -- Check that enrolled employees have appropriate deferral rates
    SELECT
        'workforce_snapshot_rates' AS check_name,
        COUNT(*) AS total_enrolled,
        COUNT(CASE WHEN is_enrolled_flag = true AND current_deferral_rate = 0 THEN 1 END) AS enrolled_with_zero_rate,
        COUNT(CASE WHEN is_enrolled_flag = false AND current_deferral_rate > 0 THEN 1 END) AS not_enrolled_with_rate,
        COUNT(CASE WHEN current_deferral_rate IS NULL THEN 1 END) AS null_rates,
        MIN(current_deferral_rate) AS min_rate,
        MAX(current_deferral_rate) AS max_rate,
        AVG(CASE WHEN is_enrolled_flag = true THEN current_deferral_rate END) AS avg_enrolled_rate
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ var('simulation_year', 2025) }}
      AND employment_status = 'active'
),

rate_consistency_checks AS (
    -- Check consistency between enrollment events and workforce snapshot
    SELECT
        'rate_consistency' AS check_name,
        COUNT(DISTINCT ws.employee_id) AS employees_with_mismatch
    FROM {{ ref('fct_workforce_snapshot') }} ws
    LEFT JOIN (
        -- Get the latest enrollment event for each employee
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
),

demographic_rate_analysis AS (
    -- Analyze deferral rates by demographics
    SELECT
        'demographic_analysis' AS check_name,
        age_band,
        COUNT(*) AS employee_count,
        AVG(current_deferral_rate) AS avg_deferral_rate,
        MIN(current_deferral_rate) AS min_rate,
        MAX(current_deferral_rate) AS max_rate,
        STDDEV(current_deferral_rate) AS rate_stddev
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE simulation_year = {{ var('simulation_year', 2025) }}
      AND employment_status = 'active'
      AND is_enrolled_flag = true
    GROUP BY age_band
),

summary_metrics AS (
    -- Overall summary of deferral rate data quality
    SELECT
        'summary' AS metric_type,
        (SELECT COUNT(*) FROM {{ ref('fct_yearly_events') }}
         WHERE event_type = 'enrollment'
           AND simulation_year = {{ var('simulation_year', 2025) }}) AS total_enrollments,
        (SELECT COUNT(*) FROM {{ ref('fct_yearly_events') }}
         WHERE event_type = 'enrollment_change'
           AND simulation_year = {{ var('simulation_year', 2025) }}) AS total_rate_changes,
        (SELECT COUNT(*) FROM {{ ref('fct_workforce_snapshot') }}
         WHERE is_enrolled_flag = true
           AND simulation_year = {{ var('simulation_year', 2025) }}
           AND employment_status = 'active') AS total_enrolled_employees,
        (SELECT AVG(current_deferral_rate) FROM {{ ref('fct_workforce_snapshot') }}
         WHERE is_enrolled_flag = true
           AND simulation_year = {{ var('simulation_year', 2025) }}
           AND employment_status = 'active') AS avg_portfolio_deferral_rate
)

-- Final output combining all checks
SELECT
    'enrollment_events' AS validation_category,
    check_name,
    total_records,
    null_rates,
    invalid_rates,
    CAST(null_rates AS FLOAT) / NULLIF(total_records, 0) AS null_rate_pct,
    CAST(invalid_rates AS FLOAT) / NULLIF(total_records, 0) AS invalid_rate_pct,
    min_rate,
    max_rate,
    avg_rate,
    CASE
        WHEN null_rates > 0 THEN 'FAIL: Null deferral rates found'
        WHEN invalid_rates > 0 THEN 'FAIL: Invalid deferral rates (outside 0-75%)'
        WHEN invalid_prev_rates > 0 THEN 'FAIL: New enrollments should have prev_rate = 0'
        ELSE 'PASS'
    END AS validation_status
FROM enrollment_event_checks

UNION ALL

SELECT
    'workforce_snapshot' AS validation_category,
    check_name,
    total_enrolled AS total_records,
    null_rates,
    enrolled_with_zero_rate + not_enrolled_with_rate AS invalid_rates,
    CAST(null_rates AS FLOAT) / NULLIF(total_enrolled, 0) AS null_rate_pct,
    CAST(enrolled_with_zero_rate + not_enrolled_with_rate AS FLOAT) / NULLIF(total_enrolled, 0) AS invalid_rate_pct,
    min_rate,
    max_rate,
    avg_enrolled_rate AS avg_rate,
    CASE
        WHEN null_rates > 0 THEN 'FAIL: Null deferral rates in snapshot'
        WHEN enrolled_with_zero_rate > 0 THEN 'WARNING: Enrolled employees with 0% deferral'
        WHEN not_enrolled_with_rate > 0 THEN 'FAIL: Non-enrolled with deferral rate'
        ELSE 'PASS'
    END AS validation_status
FROM workforce_snapshot_checks

UNION ALL

SELECT
    'consistency' AS validation_category,
    check_name,
    employees_with_mismatch AS total_records,
    0 AS null_rates,
    employees_with_mismatch AS invalid_rates,
    0 AS null_rate_pct,
    1.0 AS invalid_rate_pct,
    NULL AS min_rate,
    NULL AS max_rate,
    NULL AS avg_rate,
    CASE
        WHEN employees_with_mismatch > 0 THEN 'FAIL: Event/snapshot rate mismatch'
        ELSE 'PASS'
    END AS validation_status
FROM rate_consistency_checks

ORDER BY
    validation_category,
    check_name
