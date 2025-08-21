{{
  config(
    materialized='view',
    tags=['data_quality', 'census_enrollment', 'audit_trail']
  )
}}

-- Census Enrollment Events Audit Trail Data Quality Validation
-- Epic E051: Validates that census employees' baseline enrollment events
-- are properly integrated into the fct_yearly_events audit trail

WITH census_baseline_analysis AS (
  SELECT
    'census_baseline_workforce' AS source_table,
    COUNT(*) AS total_census_employees,
    COUNT(CASE WHEN is_from_census = true THEN 1 END) AS census_flag_count,
    COUNT(CASE WHEN is_enrolled_at_census = true THEN 1 END) AS enrolled_at_census_count,
    COUNT(CASE WHEN employee_enrollment_date IS NOT NULL THEN 1 END) AS has_enrollment_date_count,
    ROUND(AVG(CASE WHEN is_enrolled_at_census = true THEN employee_deferral_rate END), 4) AS avg_census_deferral_rate
  FROM {{ ref('int_baseline_workforce') }}
  WHERE is_from_census = true
),

synthetic_events_analysis AS (
  SELECT
    'synthetic_baseline_enrollment_events' AS source_table,
    COUNT(*) AS total_synthetic_events,
    COUNT(CASE WHEN event_type = 'enrollment' THEN 1 END) AS enrollment_events_count,
    COUNT(CASE WHEN has_valid_rate = true THEN 1 END) AS valid_rate_events_count,
    COUNT(CASE WHEN is_pre_simulation_enrollment = true THEN 1 END) AS pre_simulation_events_count,
    ROUND(AVG(employee_deferral_rate), 4) AS avg_synthetic_deferral_rate
  FROM {{ ref('int_synthetic_baseline_enrollment_events') }}
  WHERE simulation_year = {{ var('simulation_year', 2025) }}
),

yearly_events_enrollment_analysis AS (
  SELECT
    'fct_yearly_events_enrollment' AS source_table,
    COUNT(*) AS total_enrollment_events,
    COUNT(DISTINCT employee_id) AS unique_enrolled_employees,
    ROUND(AVG(employee_deferral_rate), 4) AS avg_yearly_events_deferral_rate,
    ROUND(MIN(employee_deferral_rate), 4) AS min_deferral_rate,
    ROUND(MAX(employee_deferral_rate), 4) AS max_deferral_rate
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'enrollment'
    AND simulation_year = {{ var('simulation_year', 2025) }}
),

workforce_snapshot_analysis AS (
  SELECT
    'fct_workforce_snapshot_enrolled' AS source_table,
    COUNT(*) AS total_workforce,
    COUNT(CASE WHEN employee_enrollment_date IS NOT NULL THEN 1 END) AS enrolled_workforce_count,
    ROUND(AVG(current_deferral_rate), 4) AS avg_current_deferral_rate,
    ROUND(AVG(original_deferral_rate), 4) AS avg_original_deferral_rate,
    COUNT(CASE WHEN current_deferral_rate = 0.06 THEN 1 END) AS clustered_at_6_percent_count
  FROM {{ ref('fct_workforce_snapshot') }}
  WHERE simulation_year = {{ var('simulation_year', 2025) }}
    AND employee_enrollment_date IS NOT NULL
),

gap_analysis AS (
  SELECT
    COUNT(CASE WHEN y.employee_id IS NULL THEN 1 END) AS missing_from_yearly_events_count,
    COUNT(CASE WHEN s.employee_id IS NULL THEN 1 END) AS extra_in_yearly_events_count,
    COUNT(CASE WHEN s.employee_id IS NOT NULL AND y.employee_id IS NOT NULL THEN 1 END) AS present_in_both_count,
    ROUND(AVG(CASE WHEN y.employee_id IS NULL THEN s.employee_deferral_rate END), 4) AS avg_missing_deferral_rate,
    ROUND(AVG(CASE WHEN s.employee_id IS NULL THEN y.employee_deferral_rate END), 4) AS avg_extra_deferral_rate
  FROM {{ ref('int_synthetic_baseline_enrollment_events') }} s
  FULL OUTER JOIN (
    SELECT DISTINCT employee_id, employee_deferral_rate
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type = 'enrollment'
      AND simulation_year = {{ var('simulation_year', 2025) }}
  ) y ON s.employee_id = y.employee_id
  WHERE s.simulation_year = {{ var('simulation_year', 2025) }}
),

data_quality_flags AS (
  SELECT
    -- Critical audit trail integrity checks
    CASE WHEN g.missing_from_yearly_events_count > 0
         THEN 'FAIL: Census enrollment events missing from audit trail'
         ELSE 'PASS: All census enrollment events in audit trail'
    END AS audit_trail_integrity_check,

    -- Deferral rate distribution validation
    CASE WHEN w.avg_current_deferral_rate BETWEEN 0.070 AND 0.075
         THEN 'PASS: Workforce deferral rate in expected range (7.0-7.5%)'
         ELSE 'FAIL: Workforce deferral rate outside expected range: ' || CAST(w.avg_current_deferral_rate AS VARCHAR)
    END AS deferral_rate_distribution_check,

    -- Synthetic events data quality
    CASE WHEN s.total_synthetic_events = c.enrolled_at_census_count
         THEN 'PASS: Synthetic events count matches enrolled census count'
         ELSE 'FAIL: Synthetic events mismatch - Synthetic: ' || s.total_synthetic_events || ', Census: ' || c.enrolled_at_census_count
    END AS synthetic_events_count_check,

    -- Rate clustering validation (should not cluster at 6%)
    CASE WHEN w.clustered_at_6_percent_count < (w.enrolled_workforce_count * 0.1)
         THEN 'PASS: No excessive clustering at 6% deferral rate'
         ELSE 'FAIL: Excessive clustering at 6% rate: ' || w.clustered_at_6_percent_count || ' employees'
    END AS rate_clustering_check,

    -- Expected metrics for tracking
    c.total_census_employees,
    c.enrolled_at_census_count,
    c.avg_census_deferral_rate,
    s.total_synthetic_events,
    s.avg_synthetic_deferral_rate,
    y.total_enrollment_events,
    y.avg_yearly_events_deferral_rate,
    w.enrolled_workforce_count,
    w.avg_current_deferral_rate,
    g.missing_from_yearly_events_count,
    g.avg_missing_deferral_rate,
    g.present_in_both_count,

    -- Validation timestamp
    CURRENT_TIMESTAMP AS validation_timestamp
  FROM census_baseline_analysis c
  CROSS JOIN synthetic_events_analysis s
  CROSS JOIN yearly_events_enrollment_analysis y
  CROSS JOIN workforce_snapshot_analysis w
  CROSS JOIN gap_analysis g
)

SELECT * FROM data_quality_flags
