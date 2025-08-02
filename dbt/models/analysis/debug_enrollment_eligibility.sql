{{ config(materialized='table') }}

/*
  Debug Enrollment Eligibility Analysis

  This model provides step-by-step breakdown of enrollment eligibility filtering
  to help diagnose issues with enrollment event generation.

  Usage: dbt run --select debug_enrollment_eligibility --vars '{"simulation_year": 2025, "auto_enrollment_hire_date_cutoff": "2020-01-01", "auto_enrollment_scope": "all_eligible_employees"}'
*/

WITH workforce_base AS (
  SELECT
    employee_id,
    employee_hire_date,
    employment_status,
    current_tenure,
    employee_enrollment_date,
    current_age,
    current_compensation,
    {{ var('simulation_year') }} as simulation_year
  FROM {{ ref('int_baseline_workforce') }}
),

eligibility_breakdown AS (
  SELECT
    *,
    -- Step 1: Employment Status Check
    CASE WHEN employment_status = 'active' THEN 1 ELSE 0 END as step1_active_status,

    -- Step 2: Tenure Check (>= 1 year)
    CASE WHEN current_tenure >= 1 THEN 1 ELSE 0 END as step2_tenure_eligible,

    -- Step 3: Not Already Enrolled Check
    CASE WHEN employee_enrollment_date IS NULL THEN 1 ELSE 0 END as step3_not_enrolled,

    -- Step 4: Hire Date Cutoff Check
    CASE
      WHEN {% if var("auto_enrollment_hire_date_cutoff", null) %}
        employee_hire_date >= '{{ var("auto_enrollment_hire_date_cutoff") }}'::DATE
      {% else %}
        true
      {% endif %}
      THEN 1 ELSE 0
    END as step4_hire_cutoff,

    -- Step 5: Scope Check
    CASE
      WHEN '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' = 'new_hires_only'
        THEN CASE WHEN employee_hire_date >= CAST(simulation_year || '-01-01' AS DATE) THEN 1 ELSE 0 END
      WHEN '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' = 'all_eligible_employees'
        THEN 1
      ELSE 1
    END as step5_scope_check,

    -- Configuration Values for Reference
    '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' as config_scope,
    '{{ var("auto_enrollment_hire_date_cutoff", "null") }}' as config_hire_cutoff,

    -- Combined Eligibility
    CASE
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
              THEN employee_hire_date >= CAST(simulation_year || '-01-01' AS DATE)
            WHEN '{{ var("auto_enrollment_scope", "all_eligible_employees") }}' = 'all_eligible_employees'
              THEN true
            ELSE true
          END
        )
        THEN 1
      ELSE 0
    END as final_eligible
  FROM workforce_base
),

summary_stats AS (
  SELECT
    COUNT(*) as total_employees,
    SUM(step1_active_status) as active_employees,
    SUM(step1_active_status * step2_tenure_eligible) as tenure_eligible,
    SUM(step1_active_status * step2_tenure_eligible * step3_not_enrolled) as not_enrolled_eligible,
    SUM(step1_active_status * step2_tenure_eligible * step3_not_enrolled * step4_hire_cutoff) as hire_cutoff_eligible,
    SUM(final_eligible) as final_eligible_count,

    -- Configuration info
    ANY_VALUE(config_scope) as scope_setting,
    ANY_VALUE(config_hire_cutoff) as hire_cutoff_setting,
    ANY_VALUE(simulation_year) as simulation_year,

    -- Hire date analysis
    MIN(employee_hire_date) as earliest_hire_date,
    MAX(employee_hire_date) as latest_hire_date,
    COUNT(CASE WHEN employee_hire_date >= '{{ var("simulation_year") }}-01-01'::DATE THEN 1 END) as hired_in_sim_year,
    COUNT(CASE WHEN {% if var("auto_enrollment_hire_date_cutoff", null) %}
      employee_hire_date >= '{{ var("auto_enrollment_hire_date_cutoff") }}'::DATE
    {% else %}
      true
    {% endif %} THEN 1 END) as after_cutoff_date
  FROM eligibility_breakdown
),

detailed_breakdown AS (
  SELECT
    -- Employee Details
    employee_id,
    employee_hire_date,
    current_tenure,
    current_age,
    current_compensation,
    employment_status,
    employee_enrollment_date,

    -- Step-by-step filters
    step1_active_status,
    step2_tenure_eligible,
    step3_not_enrolled,
    step4_hire_cutoff,
    step5_scope_check,
    final_eligible,

    -- Failure reason analysis
    CASE
      WHEN step1_active_status = 0 THEN 'Not Active Employee'
      WHEN step2_tenure_eligible = 0 THEN 'Insufficient Tenure (< 1 year)'
      WHEN step3_not_enrolled = 0 THEN 'Already Enrolled'
      WHEN step4_hire_cutoff = 0 THEN 'Hired Before Cutoff Date'
      WHEN step5_scope_check = 0 THEN 'Outside Enrollment Scope'
      WHEN final_eligible = 1 THEN 'ELIGIBLE FOR ENROLLMENT'
      ELSE 'Unknown Issue'
    END as eligibility_status,

    -- Configuration reference
    config_scope,
    config_hire_cutoff
  FROM eligibility_breakdown
)

-- Final output combining summary and sample details
SELECT * FROM (
  SELECT
    'SUMMARY' as record_type,
    'Configuration' as employee_id,
    NULL::DATE as employee_hire_date,
    NULL as current_tenure,
    NULL as current_age,
    NULL as current_compensation,
    scope_setting as employment_status,
    hire_cutoff_setting as employee_enrollment_date,
    total_employees as step1_active_status,
    active_employees as step2_tenure_eligible,
    tenure_eligible as step3_not_enrolled,
    not_enrolled_eligible as step4_hire_cutoff,
    hire_cutoff_eligible as step5_scope_check,
    final_eligible_count as final_eligible,
    CONCAT('Total: ', total_employees, ' | Active: ', active_employees, ' | Final Eligible: ', final_eligible_count) as eligibility_status,
    CONCAT('Scope: ', scope_setting) as config_scope,
    hire_cutoff_setting as config_hire_cutoff
  FROM summary_stats

  UNION ALL

  SELECT
    'DATE_ANALYSIS' as record_type,
    'Hire Dates' as employee_id,
    earliest_hire_date as employee_hire_date,
    NULL as current_tenure,
    NULL as current_age,
    NULL as current_compensation,
    latest_hire_date::VARCHAR as employment_status,
    NULL::VARCHAR as employee_enrollment_date,
    hired_in_sim_year as step1_active_status,
    after_cutoff_date as step2_tenure_eligible,
    NULL as step3_not_enrolled,
    NULL as step4_hire_cutoff,
    NULL as step5_scope_check,
    NULL as final_eligible,
    CONCAT('Hired in ', simulation_year, ': ', hired_in_sim_year, ' | After cutoff: ', after_cutoff_date) as eligibility_status,
    NULL as config_scope,
    NULL as config_hire_cutoff
  FROM summary_stats

  UNION ALL

  SELECT
    'DETAIL' as record_type,
    employee_id,
    employee_hire_date,
    current_tenure,
    current_age,
    current_compensation,
    employment_status,
    employee_enrollment_date,
    step1_active_status,
    step2_tenure_eligible,
    step3_not_enrolled,
    step4_hire_cutoff,
    step5_scope_check,
    final_eligible,
    eligibility_status,
    config_scope,
    config_hire_cutoff
  FROM detailed_breakdown
  WHERE final_eligible = 1 OR step1_active_status = 0  -- Show eligible employees and some ineligible samples
)
ORDER BY record_type,
  CASE WHEN record_type = 'DETAIL' THEN final_eligible END DESC,
  employee_id
LIMIT 1000
