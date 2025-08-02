{{ config(materialized='table') }}

/*
  Enrollment Event Count Validation Analysis

  Provides comprehensive count validation for enrollment events to verify
  that the fixes are working properly and events are being generated.

  Usage: dbt run --select debug_enrollment_event_counts --vars '{"simulation_year": 2025, "auto_enrollment_hire_date_cutoff": "2020-01-01", "auto_enrollment_scope": "all_eligible_employees"}'
*/

WITH baseline_counts AS (
  SELECT
    COUNT(*) as total_workforce,
    COUNT(CASE WHEN employment_status = 'active' THEN 1 END) as active_employees,
    COUNT(CASE WHEN employment_status = 'active' AND current_tenure >= 1 THEN 1 END) as tenure_eligible,
    COUNT(CASE WHEN employment_status = 'active' AND current_tenure >= 1 AND employee_enrollment_date IS NULL THEN 1 END) as not_enrolled_eligible,
    MIN(employee_hire_date) as earliest_hire,
    MAX(employee_hire_date) as latest_hire,
    COUNT(CASE WHEN {% if var("auto_enrollment_hire_date_cutoff", null) %}
      employee_hire_date >= '{{ var("auto_enrollment_hire_date_cutoff") }}'::DATE
    {% else %}
      true
    {% endif %} THEN 1 END) as after_cutoff,
    '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' as config_scope,
    '{{ var("auto_enrollment_hire_date_cutoff", "null") }}' as config_cutoff
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

enrollment_event_counts AS (
  SELECT
    COUNT(*) as total_enrollment_events,
    COUNT(CASE WHEN event_type = 'enrollment' THEN 1 END) as enrollment_events,
    COUNT(CASE WHEN event_type = 'enrollment_change' THEN 1 END) as opt_out_events,
    COUNT(DISTINCT employee_id) as unique_employees_with_events,
    MIN(effective_date) as earliest_event_date,
    MAX(effective_date) as latest_event_date
  FROM {{ ref('int_enrollment_events') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

optimized_event_counts AS (
  SELECT
    COUNT(*) as optimized_total_events,
    COUNT(CASE WHEN event_type = 'enrollment' THEN 1 END) as optimized_enrollment_events,
    COUNT(CASE WHEN event_type = 'enrollment_change' THEN 1 END) as optimized_opt_out_events,
    COUNT(DISTINCT employee_id) as optimized_unique_employees
  FROM {{ ref('int_enrollment_events_optimized') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

demographic_breakdown AS (
  SELECT
    age_segment,
    income_segment,
    COUNT(*) as employee_count,
    COUNT(CASE WHEN will_enroll = true THEN 1 END) as enrolled_count,
    ROUND(AVG(final_enrollment_probability), 3) as avg_enrollment_prob
  FROM (
    SELECT
      CASE
        WHEN current_age < 30 THEN 'young'
        WHEN current_age < 45 THEN 'mid_career'
        WHEN current_age < 60 THEN 'mature'
        ELSE 'senior'
      END as age_segment,
      CASE
        WHEN current_compensation < 50000 THEN 'low_income'
        WHEN current_compensation < 100000 THEN 'moderate'
        WHEN current_compensation < 200000 THEN 'high'
        ELSE 'executive'
      END as income_segment,
      (ABS(HASH(employee_id || '{{ var("simulation_year") }}' || '42')) % 1000000) / 1000000.0 < 0.5 as will_enroll,
      0.5 as final_enrollment_probability
    FROM {{ ref('int_baseline_workforce') }}
    WHERE employment_status = 'active'
      AND current_tenure >= 1
      AND employee_enrollment_date IS NULL
      AND simulation_year = {{ var('simulation_year') }}
  ) demo_calc
  GROUP BY age_segment, income_segment
),

validation_summary AS (
  SELECT
    'VALIDATION_SUMMARY' as record_type,
    b.total_workforce,
    b.active_employees,
    b.tenure_eligible,
    b.not_enrolled_eligible,
    COALESCE(e.total_enrollment_events, 0) as actual_events_generated,
    COALESCE(o.optimized_total_events, 0) as optimized_events_generated,
    b.config_scope,
    b.config_cutoff,

    -- Calculate expected vs actual
    CASE
      WHEN COALESCE(e.total_enrollment_events, 0) = 0 THEN 'FAILED - No events generated'
      WHEN COALESCE(e.total_enrollment_events, 0) < b.not_enrolled_eligible * 0.1 THEN 'LOW - Fewer events than expected'
      WHEN COALESCE(e.total_enrollment_events, 0) > b.not_enrolled_eligible * 0.8 THEN 'HIGH - More events than expected'
      ELSE 'NORMAL - Event count within expected range'
    END as validation_status,

    -- Success metrics
    CASE WHEN COALESCE(e.total_enrollment_events, 0) > 0 THEN 'SUCCESS' ELSE 'FAILED' END as fix_status,
    ROUND(COALESCE(e.total_enrollment_events, 0)::FLOAT / NULLIF(b.not_enrolled_eligible, 0) * 100, 1) as enrollment_rate_pct,

    -- Date range validation
    b.earliest_hire,
    b.latest_hire,
    e.earliest_event_date,
    e.latest_event_date
  FROM baseline_counts b
  FULL OUTER JOIN enrollment_event_counts e ON true
  FULL OUTER JOIN optimized_event_counts o ON true
)

-- Final comprehensive report
SELECT
  record_type,
  total_workforce,
  active_employees,
  tenure_eligible,
  not_enrolled_eligible,
  actual_events_generated,
  optimized_events_generated,
  config_scope,
  config_cutoff,
  validation_status,
  fix_status,
  enrollment_rate_pct,
  earliest_hire,
  latest_hire,
  earliest_event_date,
  latest_event_date
FROM validation_summary

UNION ALL

SELECT
  'DEMOGRAPHIC_BREAKDOWN' as record_type,
  NULL as total_workforce,
  employee_count as active_employees,
  enrolled_count as tenure_eligible,
  NULL as not_enrolled_eligible,
  NULL as actual_events_generated,
  NULL as optimized_events_generated,
  age_segment as config_scope,
  income_segment as config_cutoff,
  CONCAT('Enrollment Rate: ', ROUND(enrolled_count::FLOAT / NULLIF(employee_count, 0) * 100, 1), '%') as validation_status,
  CONCAT('Avg Prob: ', avg_enrollment_prob) as fix_status,
  NULL as enrollment_rate_pct,
  NULL as earliest_hire,
  NULL as latest_hire,
  NULL as earliest_event_date,
  NULL as latest_event_date
FROM demographic_breakdown
ORDER BY record_type, config_scope
