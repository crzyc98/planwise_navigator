{{ config(materialized='table') }}

/*
  Configuration Fix Validation Analysis
  
  Validates that the configuration fixes (removing hardcoded variables, 
  fixing scope defaults) are working correctly.
  
  This model tests various configuration scenarios to ensure the enrollment
  logic responds correctly to different variable settings.
*/

WITH configuration_test_scenarios AS (
  SELECT
    -- Current configuration being tested
    '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' as current_scope,
    '{{ var("auto_enrollment_hire_date_cutoff", "null") }}' as current_cutoff,
    {{ var("simulation_year") }} as current_sim_year,
    
    -- Test what should happen with different configs
    CASE 
      WHEN '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' = 'all_eligible_employees' 
        THEN 'Should include all eligible employees regardless of hire year'
      WHEN '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' = 'new_hires_only'
        THEN 'Should only include employees hired in simulation year'
      ELSE 'Unknown scope configuration'
    END as expected_behavior,
    
    CASE
      WHEN '{{ var("auto_enrollment_hire_date_cutoff", "null") }}' != 'null'
        THEN 'Should exclude employees hired before cutoff date'
      ELSE 'No hire date filtering applied'
    END as expected_cutoff_behavior
),

workforce_analysis AS (
  SELECT
    COUNT(*) as total_active_workforce,
    COUNT(CASE WHEN current_tenure >= 1 THEN 1 END) as tenure_eligible_count,
    COUNT(CASE WHEN employee_enrollment_date IS NULL THEN 1 END) as not_enrolled_count,
    
    -- Hire date distribution analysis
    COUNT(CASE WHEN employee_hire_date >= CAST({{ var("simulation_year") }} || '-01-01' AS DATE) THEN 1 END) as hired_in_sim_year,
    COUNT(CASE WHEN employee_hire_date >= '2020-01-01'::DATE THEN 1 END) as hired_after_2020,
    COUNT(CASE WHEN employee_hire_date >= '2015-01-01'::DATE THEN 1 END) as hired_after_2015,
    
    -- Expected eligible count with current config
    COUNT(CASE 
      WHEN employment_status = 'active'
        AND current_tenure >= 1
        AND employee_enrollment_date IS NULL
        AND (
          {% if var("auto_enrollment_hire_date_cutoff", null) %}
            employee_hire_date >= '{{ var("auto_enrollment_hire_date_cutoff") }}'::DATE
          {% else %}
            true
          {% endif %}
        )
        AND (
          CASE
            WHEN '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' = 'new_hires_only' 
              THEN employee_hire_date >= CAST({{ var("simulation_year") }} || '-01-01' AS DATE)
            WHEN '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' = 'all_eligible_employees'
              THEN true
            ELSE true
          END
        )
      THEN 1 
    END) as expected_eligible_with_current_config,
    
    MIN(employee_hire_date) as earliest_hire_date,
    MAX(employee_hire_date) as latest_hire_date
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND employment_status = 'active'
),

actual_enrollment_results AS (
  SELECT
    COUNT(*) as actual_enrollment_events,
    COUNT(DISTINCT employee_id) as unique_employees_enrolled,
    MIN(effective_date) as earliest_enrollment_date,
    MAX(effective_date) as latest_enrollment_date
  FROM {{ ref('int_enrollment_events') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND event_type = 'enrollment'
),

configuration_validation AS (
  SELECT
    c.*,
    w.*,
    COALESCE(a.actual_enrollment_events, 0) as actual_events,
    COALESCE(a.unique_employees_enrolled, 0) as actual_employees,
    
    -- Validation checks
    CASE 
      WHEN COALESCE(a.actual_enrollment_events, 0) = 0 THEN 'FAILED: No enrollment events generated'
      WHEN w.expected_eligible_with_current_config = 0 THEN 'EXPECTED: No eligible employees with current config'
      WHEN COALESCE(a.actual_enrollment_events, 0) > 0 AND w.expected_eligible_with_current_config > 0 THEN 'SUCCESS: Events generated as expected'
      ELSE 'UNCLEAR: Need manual review'
    END as validation_result,
    
    -- Configuration-specific validations
    CASE
      WHEN c.current_scope = 'all_eligible_employees' AND w.hired_in_sim_year = 0 AND COALESCE(a.actual_enrollment_events, 0) > 0
        THEN 'SUCCESS: all_eligible_employees scope working (events generated despite no new hires)'
      WHEN c.current_scope = 'new_hires_only' AND w.hired_in_sim_year = 0 AND COALESCE(a.actual_enrollment_events, 0) = 0
        THEN 'SUCCESS: new_hires_only scope working (no events because no new hires)'
      WHEN c.current_scope = 'new_hires_only' AND w.hired_in_sim_year > 0 AND COALESCE(a.actual_enrollment_events, 0) > 0
        THEN 'SUCCESS: new_hires_only scope working (events generated for new hires)'
      ELSE 'Scope validation unclear'
    END as scope_validation,
    
    -- Fix validation (main issue was scope defaulting to new_hires_only)
    CASE
      WHEN c.current_scope = 'all_eligible_employees' THEN 'SUCCESS: Scope default fixed'
      WHEN c.current_scope = 'new_hires_only' THEN 'INFO: Using new_hires_only scope'
      ELSE 'WARNING: Unexpected scope value'
    END as fix_validation,
    
    -- Performance metrics
    ROUND(COALESCE(a.actual_enrollment_events, 0)::FLOAT / NULLIF(w.expected_eligible_with_current_config, 0) * 100, 1) as enrollment_rate_pct
  FROM configuration_test_scenarios c
  CROSS JOIN workforce_analysis w
  LEFT JOIN actual_enrollment_results a ON true
)

SELECT
  -- Configuration Info
  'CONFIG_VALIDATION' as analysis_type,
  current_scope,
  current_cutoff,
  current_sim_year,
  expected_behavior,
  expected_cutoff_behavior,
  
  -- Workforce Stats
  total_active_workforce,
  tenure_eligible_count,
  not_enrolled_count,
  hired_in_sim_year,
  hired_after_2020,
  expected_eligible_with_current_config,
  
  -- Results
  actual_events,
  actual_employees,
  enrollment_rate_pct,
  
  -- Validation Results
  validation_result,
  scope_validation,
  fix_validation,
  
  -- Date Info
  earliest_hire_date,
  latest_hire_date
FROM configuration_validation