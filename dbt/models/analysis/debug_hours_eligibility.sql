{{ config(materialized='table') }}

/*
  Debug Hours Eligibility Analysis

  This model provides step-by-step breakdown of hours worked eligibility filtering
  to help diagnose issues with DC plan match and core contribution eligibility.

  Record Types:
  - SUMMARY: Aggregate statistics on hours eligibility
  - CONFIG: Configuration validation (thresholds 0-2080)
  - HOURS_BUCKET: Distribution by hours worked buckets
  - DETAIL: Per-employee breakdown with reason codes

  Usage:
    dbt run --select debug_hours_eligibility --vars "simulation_year: 2025"
    duckdb simulation.duckdb "SELECT * FROM debug_hours_eligibility WHERE record_type = 'SUMMARY'"
*/

{% set simulation_year = var('simulation_year', 2025) %}

-- Read employer core contribution config from nested structure
{% set employer_core_config = var('employer_core_contribution', {}) %}
{% set core_eligibility = employer_core_config.get('eligibility', {}) %}
{% set core_minimum_hours = core_eligibility.get('minimum_hours_annual', 1000) | int %}

-- Read employer match eligibility configuration
{% set employer_match_config = var('employer_match', {}) %}
{% set match_eligibility = employer_match_config.get('eligibility', {}) %}
{% set match_minimum_hours = match_eligibility.get('minimum_hours_annual', 1000) | int %}

WITH employer_eligibility_base AS (
  SELECT
    employee_id,
    simulation_year,
    employment_status,
    current_tenure,
    annual_hours_worked,
    eligible_for_match,
    match_eligibility_reason,
    eligible_for_core,
    eligibility_method,
    core_hours_requirement,
    match_hours_requirement,
    match_apply_eligibility
  FROM {{ ref('int_employer_eligibility') }}
  WHERE simulation_year = {{ simulation_year }}
),

-- Calculate hours calculation breakdown for diagnostics
hours_breakdown AS (
  SELECT
    ee.*,

    -- Step 1: Hours threshold check for Match
    CASE WHEN annual_hours_worked >= {{ match_minimum_hours }} THEN 1 ELSE 0 END AS step1_match_hours_met,

    -- Step 2: Hours threshold check for Core
    CASE WHEN annual_hours_worked >= {{ core_minimum_hours }} THEN 1 ELSE 0 END AS step2_core_hours_met,

    -- Step 3: Employment status at EOY
    CASE WHEN employment_status = 'active' THEN 1 ELSE 0 END AS step3_active_eoy,

    -- Bucket assignment for distribution analysis
    CASE
      WHEN annual_hours_worked = 0 THEN '0 (No Hours)'
      WHEN annual_hours_worked > 0 AND annual_hours_worked < 500 THEN '1-499'
      WHEN annual_hours_worked >= 500 AND annual_hours_worked < 1000 THEN '500-999'
      WHEN annual_hours_worked >= 1000 AND annual_hours_worked < 1500 THEN '1000-1499'
      WHEN annual_hours_worked >= 1500 AND annual_hours_worked < 2000 THEN '1500-1999'
      WHEN annual_hours_worked >= 2000 AND annual_hours_worked <= 2080 THEN '2000-2080 (Full Year)'
      ELSE '2080+ (Anomaly)'
    END AS hours_bucket,

    -- Derive failure reason for hours eligibility
    CASE
      WHEN annual_hours_worked >= {{ match_minimum_hours }} AND annual_hours_worked >= {{ core_minimum_hours }} AND eligible_for_match AND eligible_for_core THEN 'ELIGIBLE_BOTH'
      WHEN annual_hours_worked >= {{ match_minimum_hours }} AND eligible_for_match AND NOT eligible_for_core THEN 'ELIGIBLE_MATCH_ONLY'
      WHEN annual_hours_worked >= {{ core_minimum_hours }} AND eligible_for_core AND NOT eligible_for_match THEN 'ELIGIBLE_CORE_ONLY'
      WHEN annual_hours_worked < {{ match_minimum_hours }} AND annual_hours_worked < {{ core_minimum_hours }} THEN 'INSUFFICIENT_HOURS_BOTH'
      WHEN annual_hours_worked < {{ match_minimum_hours }} THEN 'INSUFFICIENT_HOURS_MATCH'
      WHEN annual_hours_worked < {{ core_minimum_hours }} THEN 'INSUFFICIENT_HOURS_CORE'
      WHEN employment_status != 'active' THEN 'INACTIVE_EOY'
      ELSE match_eligibility_reason
    END AS hours_eligibility_status

  FROM employer_eligibility_base ee
),

-- Summary statistics
summary_stats AS (
  SELECT
    COUNT(*) AS total_employees,
    SUM(step1_match_hours_met) AS match_hours_eligible,
    SUM(step2_core_hours_met) AS core_hours_eligible,
    SUM(step3_active_eoy) AS active_at_eoy,
    SUM(CASE WHEN eligible_for_match THEN 1 ELSE 0 END) AS final_match_eligible,
    SUM(CASE WHEN eligible_for_core THEN 1 ELSE 0 END) AS final_core_eligible,
    ROUND(AVG(annual_hours_worked), 1) AS avg_hours_worked,
    MIN(annual_hours_worked) AS min_hours_worked,
    MAX(annual_hours_worked) AS max_hours_worked,
    ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY annual_hours_worked), 1) AS median_hours_worked,
    {{ simulation_year }} AS simulation_year,
    ANY_VALUE(match_hours_requirement) AS match_hours_threshold,
    ANY_VALUE(core_hours_requirement) AS core_hours_threshold
  FROM hours_breakdown
),

-- Hours bucket distribution
bucket_distribution AS (
  SELECT
    hours_bucket,
    COUNT(*) AS employee_count,
    SUM(CASE WHEN eligible_for_match THEN 1 ELSE 0 END) AS match_eligible_count,
    SUM(CASE WHEN eligible_for_core THEN 1 ELSE 0 END) AS core_eligible_count,
    ROUND(100.0 * COUNT(*) / SUM(COUNT(*)) OVER (), 2) AS pct_of_total,
    ROW_NUMBER() OVER (ORDER BY
      CASE hours_bucket
        WHEN '0 (No Hours)' THEN 1
        WHEN '1-499' THEN 2
        WHEN '500-999' THEN 3
        WHEN '1000-1499' THEN 4
        WHEN '1500-1999' THEN 5
        WHEN '2000-2080 (Full Year)' THEN 6
        ELSE 7
      END
    ) AS bucket_order
  FROM hours_breakdown
  GROUP BY hours_bucket
),

-- Configuration validation
config_validation AS (
  SELECT
    {{ match_minimum_hours }} AS match_hours_threshold,
    {{ core_minimum_hours }} AS core_hours_threshold,
    CASE
      WHEN {{ match_minimum_hours }} < 0 OR {{ match_minimum_hours }} > 2080 THEN 'INVALID'
      ELSE 'VALID'
    END AS match_threshold_status,
    CASE
      WHEN {{ core_minimum_hours }} < 0 OR {{ core_minimum_hours }} > 2080 THEN 'INVALID'
      ELSE 'VALID'
    END AS core_threshold_status,
    CASE
      WHEN {{ match_minimum_hours }} >= 0 AND {{ match_minimum_hours }} <= 2080
           AND {{ core_minimum_hours }} >= 0 AND {{ core_minimum_hours }} <= 2080 THEN 'ALL_VALID'
      ELSE 'CONFIGURATION_ERROR'
    END AS overall_config_status
),

-- Detailed employee breakdown
detailed_breakdown AS (
  SELECT
    employee_id,
    simulation_year,
    employment_status,
    current_tenure,
    annual_hours_worked,
    hours_bucket,
    step1_match_hours_met,
    step2_core_hours_met,
    step3_active_eoy,
    eligible_for_match,
    eligible_for_core,
    hours_eligibility_status,
    match_eligibility_reason,
    match_hours_requirement,
    core_hours_requirement
  FROM hours_breakdown
)

-- Final output combining all record types
SELECT * FROM (
  -- SUMMARY record
  SELECT
    'SUMMARY' AS record_type,
    'Hours Eligibility Summary' AS employee_id,
    simulation_year,
    NULL AS employment_status,
    NULL::DOUBLE AS current_tenure,
    avg_hours_worked::INTEGER AS annual_hours_worked,
    CONCAT(min_hours_worked, '-', max_hours_worked) AS hours_bucket,
    match_hours_eligible AS step1_match_hours_met,
    core_hours_eligible AS step2_core_hours_met,
    active_at_eoy AS step3_active_eoy,
    final_match_eligible AS eligible_for_match,
    final_core_eligible AS eligible_for_core,
    CONCAT('Total: ', total_employees, ' | Match Eligible: ', final_match_eligible, ' | Core Eligible: ', final_core_eligible) AS hours_eligibility_status,
    CONCAT('Match: ', match_hours_threshold, ' | Core: ', core_hours_threshold) AS match_eligibility_reason,
    match_hours_threshold AS match_hours_requirement,
    core_hours_threshold AS core_hours_requirement
  FROM summary_stats

  UNION ALL

  -- CONFIG record
  SELECT
    'CONFIG' AS record_type,
    'Configuration Validation' AS employee_id,
    {{ simulation_year }} AS simulation_year,
    overall_config_status AS employment_status,
    NULL::DOUBLE AS current_tenure,
    NULL AS annual_hours_worked,
    NULL AS hours_bucket,
    match_hours_threshold AS step1_match_hours_met,
    core_hours_threshold AS step2_core_hours_met,
    NULL AS step3_active_eoy,
    CASE WHEN match_threshold_status = 'VALID' THEN 1 ELSE 0 END AS eligible_for_match,
    CASE WHEN core_threshold_status = 'VALID' THEN 1 ELSE 0 END AS eligible_for_core,
    CONCAT('Match Threshold: ', match_threshold_status, ' | Core Threshold: ', core_threshold_status) AS hours_eligibility_status,
    CONCAT('Valid range: 0-2080 hours') AS match_eligibility_reason,
    match_hours_threshold AS match_hours_requirement,
    core_hours_threshold AS core_hours_requirement
  FROM config_validation

  UNION ALL

  -- HOURS_BUCKET records
  SELECT
    'HOURS_BUCKET' AS record_type,
    hours_bucket AS employee_id,
    {{ simulation_year }} AS simulation_year,
    NULL AS employment_status,
    NULL::DOUBLE AS current_tenure,
    employee_count AS annual_hours_worked,
    hours_bucket,
    match_eligible_count AS step1_match_hours_met,
    core_eligible_count AS step2_core_hours_met,
    bucket_order AS step3_active_eoy,
    match_eligible_count AS eligible_for_match,
    core_eligible_count AS eligible_for_core,
    CONCAT('Count: ', employee_count, ' (', pct_of_total, '%) | Match: ', match_eligible_count, ' | Core: ', core_eligible_count) AS hours_eligibility_status,
    NULL AS match_eligibility_reason,
    NULL AS match_hours_requirement,
    NULL AS core_hours_requirement
  FROM bucket_distribution

  UNION ALL

  -- DETAIL records (sample of employees with edge cases)
  SELECT
    'DETAIL' AS record_type,
    employee_id,
    simulation_year,
    employment_status,
    current_tenure,
    annual_hours_worked,
    hours_bucket,
    step1_match_hours_met,
    step2_core_hours_met,
    step3_active_eoy,
    CASE WHEN eligible_for_match THEN 1 ELSE 0 END AS eligible_for_match,
    CASE WHEN eligible_for_core THEN 1 ELSE 0 END AS eligible_for_core,
    hours_eligibility_status,
    match_eligibility_reason,
    match_hours_requirement,
    core_hours_requirement
  FROM detailed_breakdown
  WHERE
    -- Include edge cases: near threshold, ineligible, or anomalies
    annual_hours_worked BETWEEN ({{ match_minimum_hours }} - 100) AND ({{ match_minimum_hours }} + 100)
    OR annual_hours_worked < 500
    OR annual_hours_worked > 2080
    OR NOT eligible_for_match
    OR NOT eligible_for_core
    -- Also include a sample of fully eligible employees
    OR (eligible_for_match AND eligible_for_core AND annual_hours_worked >= 2000)
)
ORDER BY
  CASE record_type
    WHEN 'SUMMARY' THEN 1
    WHEN 'CONFIG' THEN 2
    WHEN 'HOURS_BUCKET' THEN 3
    WHEN 'DETAIL' THEN 4
  END,
  CASE WHEN record_type = 'HOURS_BUCKET' THEN step3_active_eoy END,  -- bucket_order
  -- For DETAIL: prioritize edge cases (ineligible, low hours, anomalies) over full-year eligible
  CASE WHEN record_type = 'DETAIL' THEN
    CASE
      WHEN eligible_for_match = 0 OR eligible_for_core = 0 THEN 1  -- Ineligible first
      WHEN annual_hours_worked < 500 THEN 2  -- Very low hours
      WHEN annual_hours_worked > 2080 THEN 3  -- Anomalies
      WHEN annual_hours_worked BETWEEN 900 AND 1100 THEN 4  -- Near threshold
      ELSE 5  -- Full year eligible
    END
  END,
  CASE WHEN record_type = 'DETAIL' THEN annual_hours_worked END ASC,  -- Within priority, show lowest hours first
  employee_id
LIMIT 2000
