{{ config(materialized='table') }}

/*
  Eligibility Determination Model (Epic E022: Story S022-01) - BASELINE VERSION

  Determines employee eligibility for DC plan participation based on employee master data
  and plan configuration. This approach provides eligibility determination without depending
  on event infrastructure, making it foundational for other models.

  Business Logic:
  - Eligibility is determined from employee hire date and waiting period configuration
  - Each employee has an eligibility_date calculated as hire_date + waiting_period_days
  - Current eligibility status is derived by comparing eligibility_date to the evaluation date
  - Supports immediate eligibility (0 days) and various waiting periods

  Performance:
  - Uses baseline workforce data for fast calculation
  - No dependency on event infrastructure
  - Materialized as table for optimal query performance

  Usage:
    This model is consumed by:
    - Enrollment models for filtering eligible employees
    - Event generation models for eligibility events
    - Contribution models for participation validation
    - Reporting and analytics
*/

WITH
-- Base employee data with eligibility configuration
employee_eligibility_base AS (
  SELECT
    employee_id,
    employee_ssn,
    employee_hire_date,
    employment_status,
    current_age,
    current_tenure,
    level_id,
    current_compensation,
    waiting_period_days,
    employee_eligibility_date,
    current_eligibility_status,
    {{ var('simulation_year') }} as simulation_year
  FROM {{ ref('int_baseline_workforce') }}
  WHERE employment_status = 'active'
),

-- Calculate eligibility determination
eligibility_calculation AS (
  SELECT
    employee_id,
    employee_ssn,
    employee_hire_date,
    employment_status,
    current_age,
    current_tenure,
    level_id,
    current_compensation,
    waiting_period_days,
    employee_eligibility_date,
    current_eligibility_status,
    simulation_year,
    -- Calculate days since hire as of the evaluation date (end of simulation year)
    DATEDIFF('day', employee_hire_date, CAST(simulation_year || '-12-31' AS DATE)) as days_since_hire,
    -- Use end of year as evaluation date for consistency
    CAST(simulation_year || '-12-31' AS DATE) as eligibility_evaluation_date
  FROM employee_eligibility_base
)

-- Final eligibility determination
SELECT
  employee_id,
  employee_ssn,
  employee_hire_date,
  employment_status,
  current_age,
  current_tenure,
  level_id,
  current_compensation,
  waiting_period_days,
  simulation_year,
  days_since_hire,
  -- Determine if eligible based on eligibility date vs evaluation date
  CASE
    WHEN employee_eligibility_date <= eligibility_evaluation_date THEN true
    ELSE false
  END as is_eligible,
  -- Provide eligibility reason
  CASE
    WHEN employee_eligibility_date <= eligibility_evaluation_date THEN 'eligible_service_met'
    ELSE 'pending_service_requirement'
  END as eligibility_reason,
  -- Include evaluation date and eligibility date for reference
  eligibility_evaluation_date,
  employee_eligibility_date,
  -- Include original status from baseline (for validation)
  current_eligibility_status as baseline_eligibility_status
FROM eligibility_calculation
ORDER BY simulation_year, employee_id
