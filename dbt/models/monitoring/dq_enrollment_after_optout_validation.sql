{{ config(
  materialized='table',
  tags=['data_quality', 'enrollment_validation']
) }}

/*
  Data Quality Validation: Enrollment After Opt-Out Detection

  This model detects employees who have enrollment events AFTER opt-out events
  without an explicit voluntary enrollment decision between the opt-out and re-enrollment.

  Business Rule:
  - Once an employee opts out, they should remain opted-out unless they make a new voluntary enrollment decision
  - Automatic re-enrollment (auto-enrollment, year-over-year) should NOT occur for employees who opted out

  Test Logic:
  1. Find all employees with opt-out events
  2. For each employee, find enrollment events AFTER their opt-out
  3. Flag cases where re-enrollment occurs without explicit voluntary decision

  Expected Result: 0 rows (no invalid re-enrollments)
*/

WITH opt_out_events AS (
  -- Get all opt-out events with their timing
  SELECT
    employee_id,
    simulation_year as opt_out_year,
    effective_date as opt_out_date,
    event_details,
    ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY effective_date DESC) as opt_out_rank
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'enrollment_change'
    AND LOWER(event_details) LIKE '%opt-out%'
    AND employee_id IS NOT NULL
),

enrollment_events_after_optout AS (
  -- Find enrollment events that occur AFTER an employee's most recent opt-out
  SELECT
    ee.employee_id,
    oo.opt_out_year,
    oo.opt_out_date,
    oo.event_details as opt_out_details,
    ee.simulation_year as enrollment_year,
    ee.effective_date as enrollment_date,
    ee.event_category,
    ee.event_details as enrollment_details,
    -- Calculate time between opt-out and re-enrollment
    EXTRACT(DAY FROM ee.effective_date - oo.opt_out_date) as days_since_optout
  FROM {{ ref('fct_yearly_events') }} ee
  INNER JOIN opt_out_events oo
    ON ee.employee_id = oo.employee_id
    AND oo.opt_out_rank = 1  -- Only consider most recent opt-out
    AND ee.effective_date > oo.opt_out_date  -- Enrollment after opt-out
  WHERE ee.event_type = 'enrollment'
    AND ee.employee_id IS NOT NULL
),

invalid_reenrollments AS (
  -- Flag re-enrollments that are NOT explicit voluntary decisions
  -- Valid re-enrollments: voluntary_enrollment, proactive_voluntary
  -- Invalid re-enrollments: auto_enrollment, year_over_year_voluntary
  SELECT
    employee_id,
    opt_out_year,
    opt_out_date,
    opt_out_details,
    enrollment_year,
    enrollment_date,
    event_category,
    enrollment_details,
    days_since_optout,
    CASE
      WHEN event_category IN ('voluntary_enrollment', 'proactive_voluntary', 'proactive_voluntary_enrollment') THEN 'VALID'
      WHEN event_category IN ('auto_enrollment', 'year_over_year_voluntary') THEN 'INVALID'
      ELSE 'UNKNOWN'
    END as validation_status,
    CASE
      WHEN event_category IN ('voluntary_enrollment', 'proactive_voluntary', 'proactive_voluntary_enrollment')
        THEN 'Employee made explicit voluntary enrollment decision after opt-out'
      WHEN event_category = 'auto_enrollment'
        THEN 'ISSUE: Auto-enrollment should not re-enroll employees who opted out'
      WHEN event_category = 'year_over_year_voluntary'
        THEN 'ISSUE: Year-over-year enrollment should not re-enroll employees who opted out'
      ELSE 'ISSUE: Unknown enrollment category - needs investigation'
    END as validation_message
  FROM enrollment_events_after_optout
)

-- Return only INVALID cases for monitoring and alerting
SELECT
  employee_id,
  opt_out_year,
  opt_out_date,
  opt_out_details,
  enrollment_year,
  enrollment_date,
  event_category,
  enrollment_details,
  days_since_optout,
  validation_status,
  validation_message,
  -- Add severity for alerting
  CASE
    WHEN validation_status = 'INVALID' THEN 'HIGH'
    WHEN validation_status = 'UNKNOWN' THEN 'MEDIUM'
    ELSE 'LOW'
  END as severity,
  CURRENT_TIMESTAMP as validation_timestamp
FROM invalid_reenrollments
WHERE validation_status != 'VALID'  -- Only return problematic cases
ORDER BY enrollment_year, employee_id

/*
  Usage:
  - Run after multi-year simulation to check for invalid re-enrollments
  - Expected result: 0 rows
  - If rows are returned, investigate the event_category and enrollment logic

  Example query to check results:
  SELECT
    COUNT(*) as total_invalid_reenrollments,
    COUNT(DISTINCT employee_id) as affected_employees,
    event_category,
    validation_message
  FROM {{ this }}
  GROUP BY event_category, validation_message
  ORDER BY total_invalid_reenrollments DESC
*/
