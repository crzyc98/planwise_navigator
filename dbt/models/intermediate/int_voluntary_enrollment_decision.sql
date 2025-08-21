{{ config(materialized='table') }}

/*
  Voluntary Enrollment Decision Engine - Epic E053

  Implements realistic voluntary enrollment behavior based on demographics:
  - Age and job level influence enrollment decisions
  - Match optimization behavior where employees tend toward match-maximizing rates
  - ~60% voluntary enrollment rate for non-auto enrollment plans
  - Deferral rates range between 1%-10% with demographic clustering

  Key Features:
  - Demographic segmentation (age, income, job level)
  - Enrollment probability matrix calculation
  - Deferral rate selection with match optimization
  - Deterministic random decisions for reproducibility
  - Integration with existing enrollment pipeline

  Dependencies:
  - int_employee_compensation_by_year (employee demographics)
  - enrollment_registry (enrollment tracking - no circular dependencies)

  Output:
  - Employee enrollment decisions with selected deferral rates
  - Event-ready data for int_enrollment_events integration
*/

WITH active_workforce AS (
  -- Active employees with current demographics
  SELECT DISTINCT
    employee_id,
    employee_ssn,
    employee_hire_date,
    {{ var('simulation_year') }} as simulation_year,
    current_age,
    current_tenure,
    level_id,
    employee_compensation,
    employment_status
  FROM {{ ref('int_employee_compensation_by_year') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND employment_status = 'active'
    AND employee_id IS NOT NULL
),

current_enrollment_status AS (
  -- Check enrollment status from enrollment registry (avoids circular dependency)
  {% set start_year = var('start_year', 2025) | int %}
  {% set current_year = var('simulation_year') | int %}

  SELECT
    employee_id,
    is_enrolled as is_currently_enrolled
  FROM main.enrollment_registry
  WHERE is_enrolled = true
    AND employee_id IS NOT NULL
    AND first_enrollment_year <= {{ current_year }}
),

eligible_employees AS (
  -- Employees eligible for voluntary enrollment (not currently enrolled)
  SELECT
    aw.*,
    COALESCE(ces.is_currently_enrolled, false) as is_currently_enrolled
  FROM active_workforce aw
  LEFT JOIN current_enrollment_status ces ON aw.employee_id = ces.employee_id
  WHERE COALESCE(ces.is_currently_enrolled, false) = false
),

demographic_segmentation AS (
  -- Segment employees by age, income, and job level
  SELECT
    *,
    -- Age segmentation
    CASE
      WHEN current_age < 31 THEN 'young'
      WHEN current_age < 46 THEN 'mid_career'
      WHEN current_age < 56 THEN 'mature'
      ELSE 'senior'
    END as age_segment,

    -- Income segmentation
    CASE
      WHEN employee_compensation < 50000 THEN 'low'
      WHEN employee_compensation < 100000 THEN 'moderate'
      WHEN employee_compensation < 200000 THEN 'high'
      ELSE 'executive'
    END as income_segment,

    -- Job level segmentation
    CASE
      WHEN level_id <= 2 THEN 'individual'
      WHEN level_id <= 4 THEN 'senior'
      WHEN level_id <= 6 THEN 'manager'
      ELSE 'executive'
    END as job_level_segment
  FROM eligible_employees
),

enrollment_probability_calculation AS (
  -- Calculate enrollment probability using demographic matrix
  SELECT
    *,
    -- Base enrollment rate by age
    CASE age_segment
      WHEN 'young' THEN {{ var('voluntary_enrollment_base_rates_by_age_young', 0.30) }}
      WHEN 'mid_career' THEN {{ var('voluntary_enrollment_base_rates_by_age_mid_career', 0.55) }}
      WHEN 'mature' THEN {{ var('voluntary_enrollment_base_rates_by_age_mature', 0.70) }}
      ELSE {{ var('voluntary_enrollment_base_rates_by_age_senior', 0.80) }}
    END as base_enrollment_rate,

    -- Income multiplier
    CASE income_segment
      WHEN 'low' THEN {{ var('voluntary_enrollment_income_multipliers_low', 0.70) }}
      WHEN 'moderate' THEN {{ var('voluntary_enrollment_income_multipliers_moderate', 1.00) }}
      WHEN 'high' THEN {{ var('voluntary_enrollment_income_multipliers_high', 1.15) }}
      ELSE {{ var('voluntary_enrollment_income_multipliers_executive', 1.25) }}
    END as income_multiplier,

    -- Job level multiplier
    CASE job_level_segment
      WHEN 'individual' THEN {{ var('voluntary_enrollment_job_level_multipliers_individual', 0.90) }}
      WHEN 'senior' THEN {{ var('voluntary_enrollment_job_level_multipliers_senior', 1.00) }}
      WHEN 'manager' THEN {{ var('voluntary_enrollment_job_level_multipliers_manager', 1.10) }}
      ELSE {{ var('voluntary_enrollment_job_level_multipliers_executive', 1.20) }}
    END as job_level_multiplier,

    -- Deterministic random value for enrollment decision
    (ABS(HASH(employee_id || '-voluntary-enroll-' || CAST({{ var('simulation_year') }} AS VARCHAR))) % 1000) / 1000.0 as enrollment_random

  FROM demographic_segmentation
),

deferral_rate_selection AS (
  -- Select deferral rates with demographic influences and match optimization
  SELECT
    *,
    (base_enrollment_rate * income_multiplier * job_level_multiplier) as final_enrollment_probability,

    -- Select deferral rate based on demographics
    CASE
      WHEN age_segment = 'young' THEN
        CASE income_segment
          WHEN 'low' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_young_low', 0.03) }}
          WHEN 'moderate' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_young_moderate', 0.03) }}
          WHEN 'high' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_young_high', 0.04) }}
          ELSE {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_young_executive', 0.06) }}
        END
      WHEN age_segment = 'mid_career' THEN
        CASE income_segment
          WHEN 'low' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_mid_career_low', 0.04) }}
          WHEN 'moderate' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_mid_career_moderate', 0.06) }}
          WHEN 'high' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_mid_career_high', 0.08) }}
          ELSE {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_mid_career_executive', 0.10) }}
        END
      WHEN age_segment = 'mature' THEN
        CASE income_segment
          WHEN 'low' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_mature_low', 0.05) }}
          WHEN 'moderate' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_mature_moderate', 0.08) }}
          WHEN 'high' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_mature_high', 0.10) }}
          ELSE {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_mature_executive', 0.12) }}
        END
      ELSE -- senior
        CASE income_segment
          WHEN 'low' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_senior_low', 0.06) }}
          WHEN 'moderate' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_senior_moderate', 0.10) }}
          WHEN 'high' THEN {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_senior_high', 0.12) }}
          ELSE {{ var('voluntary_enrollment_deferral_rates_demographic_base_rates_senior_executive', 0.15) }}
        END
    END as selected_deferral_rate,

    -- Deterministic random value for deferral rate variation
    (ABS(HASH(employee_id || '-deferral-rate-' || CAST({{ var('simulation_year') }} AS VARCHAR))) % 1000) / 1000.0 as deferral_random

  FROM enrollment_probability_calculation
),

match_optimization AS (
  -- Apply match optimization behavior (cluster around match thresholds)
  SELECT
    *,
    -- Apply match optimization if enabled
    CASE
      WHEN {{ var('voluntary_enrollment_deferral_rates_match_optimization', true) }}
        AND '{{ var('employer_match_active_formula', 'simple_match') }}' = 'tiered_match'
      THEN
        -- For tiered match, cluster around 3% and 5% (common thresholds)
        CASE
          WHEN deferral_random < 0.3 AND selected_deferral_rate >= 0.025 THEN 0.03  -- 30% cluster at 3%
          WHEN deferral_random < 0.6 AND selected_deferral_rate >= 0.045 THEN 0.05  -- 30% cluster at 5%
          ELSE selected_deferral_rate  -- Keep original rate
        END
      WHEN {{ var('voluntary_enrollment_deferral_rates_match_optimization', true) }}
        AND '{{ var('employer_match_active_formula', 'simple_match') }}' = 'simple_match'
      THEN
        -- For simple match, cluster around match cap (6%)
        CASE
          WHEN deferral_random < 0.4 AND selected_deferral_rate >= 0.05 THEN 0.06  -- 40% cluster at match cap
          ELSE selected_deferral_rate
        END
      ELSE selected_deferral_rate  -- No match optimization
    END as optimized_deferral_rate

  FROM deferral_rate_selection
),

enrollment_decisions AS (
  -- Final enrollment decisions
  SELECT
    employee_id,
    employee_ssn,
    employee_hire_date,
    simulation_year,
    current_age,
    current_tenure,
    level_id,
    employee_compensation,
    age_segment,
    income_segment,
    job_level_segment,
    final_enrollment_probability,

    -- Enrollment decision
    CASE
      WHEN enrollment_random < final_enrollment_probability THEN true
      ELSE false
    END as will_enroll,

    -- Selected deferral rate (capped between 1% and 10%)
    GREATEST(0.01, LEAST(0.10, optimized_deferral_rate)) as selected_deferral_rate,

    -- Event details for integration
    'voluntary_enrollment' as event_category,
    CAST((simulation_year || '-01-15 10:00:00') AS TIMESTAMP) as proposed_effective_date,

    -- Audit and tracking fields
    base_enrollment_rate,
    income_multiplier,
    job_level_multiplier,
    enrollment_random,
    deferral_random,
    optimized_deferral_rate as raw_deferral_rate

  FROM match_optimization
),

-- Performance metrics for monitoring
summary_metrics AS (
  SELECT
    COUNT(*) as total_eligible_employees,
    COUNT(CASE WHEN will_enroll THEN 1 END) as voluntary_enrollments,
    ROUND(COUNT(CASE WHEN will_enroll THEN 1 END) * 100.0 / COUNT(*), 1) as enrollment_percentage,
    ROUND(AVG(CASE WHEN will_enroll THEN selected_deferral_rate END), 3) as avg_deferral_rate,
    COUNT(CASE WHEN will_enroll AND selected_deferral_rate = 0.03 THEN 1 END) as enrollments_at_3_percent,
    COUNT(CASE WHEN will_enroll AND selected_deferral_rate = 0.06 THEN 1 END) as enrollments_at_6_percent
  FROM enrollment_decisions
)

-- Return enrollment decisions for integration with enrollment events
SELECT
  employee_id,
  employee_ssn,
  employee_hire_date,
  simulation_year,
  current_age,
  current_tenure,
  level_id,
  employee_compensation,
  age_segment,
  income_segment,
  job_level_segment,
  will_enroll,
  selected_deferral_rate,
  event_category,
  proposed_effective_date,
  final_enrollment_probability,

  -- Audit fields for data quality monitoring
  base_enrollment_rate,
  income_multiplier,
  job_level_multiplier,
  enrollment_random,
  deferral_random,
  raw_deferral_rate

FROM enrollment_decisions
WHERE will_enroll = true  -- Only return employees who will enroll

-- Add summary comment for monitoring
-- Summary metrics available in summary_metrics CTE for data quality validation
