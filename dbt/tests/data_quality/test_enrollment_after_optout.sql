{{
  config(
    severity='error',
    tags=['data_quality', 'enrollment_validation', 'opt_out']
  )
}}

/*
  Data Quality Test: Enrollment After Opt-Out Detection

  Detects employees who have enrollment events AFTER opt-out events
  without an explicit voluntary enrollment decision between the opt-out and re-enrollment.

  Business Rule:
  - Once an employee opts out, they should remain opted-out unless they make a new voluntary enrollment decision
  - Automatic re-enrollment (auto-enrollment, year-over-year) should NOT occur for employees who opted out

  Expected Result: 0 rows (no invalid re-enrollments)
*/

WITH opt_out_events AS (
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
  SELECT
    ee.employee_id,
    oo.opt_out_year,
    oo.opt_out_date,
    oo.event_details as opt_out_details,
    ee.simulation_year as enrollment_year,
    ee.effective_date as enrollment_date,
    ee.event_category,
    ee.event_details as enrollment_details,
    EXTRACT(DAY FROM ee.effective_date - oo.opt_out_date) as days_since_optout
  FROM {{ ref('fct_yearly_events') }} ee
  INNER JOIN opt_out_events oo
    ON ee.employee_id = oo.employee_id
    AND oo.opt_out_rank = 1
    AND ee.effective_date > oo.opt_out_date
  WHERE ee.event_type = 'enrollment'
    AND ee.employee_id IS NOT NULL
),

invalid_reenrollments AS (
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
      WHEN event_category = 'auto_enrollment'
        THEN 'ISSUE: Auto-enrollment should not re-enroll employees who opted out'
      WHEN event_category = 'year_over_year_voluntary'
        THEN 'ISSUE: Year-over-year enrollment should not re-enroll employees who opted out'
      ELSE 'ISSUE: Unknown enrollment category - needs investigation'
    END as validation_message,
    CASE
      WHEN validation_status = 'INVALID' THEN 'HIGH'
      WHEN validation_status = 'UNKNOWN' THEN 'MEDIUM'
      ELSE 'LOW'
    END as severity
  FROM (
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
      END as validation_status
    FROM enrollment_events_after_optout
  ) sub
)

-- Return only INVALID and UNKNOWN cases
SELECT
  employee_id,
  opt_out_year,
  opt_out_date,
  enrollment_year,
  enrollment_date,
  event_category,
  days_since_optout,
  validation_status,
  validation_message,
  severity
FROM invalid_reenrollments
WHERE validation_status != 'VALID'
ORDER BY enrollment_year, employee_id
