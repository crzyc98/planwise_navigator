-- Converted from validation model to test
-- Added simulation_year filter for performance

/*
  Data Quality Validation: Enrollment Continuity Audit

  This test validates that enrollment dates are properly tracked across simulation years
  and detects potential issues with duplicate enrollment events.

  Key validations:
  1. Employees with enrollment events should have enrollment dates in workforce snapshots
  2. Enrollment dates should not regress (become NULL after being set)
  3. Employees should not have multiple enrollment events across years
  4. New hires should get proper enrollment date tracking

  Returns only failing records (0 rows = all validations pass)
*/

WITH enrollment_events_summary AS (
  -- Get all enrollment events by employee and year
  SELECT
    employee_id,
    simulation_year,
    COUNT(*) AS enrollment_events_count,
    MIN(effective_date) AS first_enrollment_date,
    MAX(effective_date) AS last_enrollment_date
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'enrollment'
    AND simulation_year = {{ var('simulation_year') }}
  GROUP BY employee_id, simulation_year
),

workforce_enrollment_status AS (
  -- Get enrollment status from workforce snapshots
  SELECT
    employee_id,
    simulation_year,
    employee_enrollment_date,
    CASE WHEN employee_enrollment_date IS NOT NULL THEN 1 ELSE 0 END AS has_enrollment_date
  FROM {{ ref('fct_workforce_snapshot') }}
  WHERE employment_status = 'active'
    AND simulation_year = {{ var('simulation_year') }}
),

enrollment_validation AS (
  SELECT
    COALESCE(ee.employee_id, ws.employee_id) AS employee_id,
    COALESCE(ee.simulation_year, ws.simulation_year) AS simulation_year,

    -- Event data
    ee.enrollment_events_count,
    ee.first_enrollment_date AS event_enrollment_date,

    -- Workforce snapshot data
    ws.employee_enrollment_date AS snapshot_enrollment_date,
    ws.has_enrollment_date,

    -- Validation flags
    CASE
      WHEN ee.enrollment_events_count > 0 AND ws.employee_enrollment_date IS NULL
      THEN 'ENROLLMENT_EVENT_NOT_REFLECTED_IN_SNAPSHOT'

      WHEN ee.enrollment_events_count > 1
      THEN 'MULTIPLE_ENROLLMENT_EVENTS_IN_YEAR'

      WHEN ee.enrollment_events_count IS NULL AND ws.employee_enrollment_date IS NOT NULL
      THEN 'ENROLLMENT_DATE_WITHOUT_EVENT'

      ELSE 'VALID'
    END AS validation_status,

    -- Additional context
    CASE
      WHEN ee.enrollment_events_count > 0 THEN 'HAS_ENROLLMENT_EVENT'
      ELSE 'NO_ENROLLMENT_EVENT'
    END AS event_status,

    CASE
      WHEN ws.has_enrollment_date = 1 THEN 'HAS_ENROLLMENT_DATE'
      ELSE 'NO_ENROLLMENT_DATE'
    END AS snapshot_status

  FROM enrollment_events_summary ee
  FULL OUTER JOIN workforce_enrollment_status ws
    ON ee.employee_id = ws.employee_id
    AND ee.simulation_year = ws.simulation_year
),

-- Check for enrollment date regression (losing enrollment status over time)
enrollment_regression_check AS (
  SELECT
    employee_id,
    simulation_year,
    employee_enrollment_date,
    LAG(employee_enrollment_date) OVER (
      PARTITION BY employee_id
      ORDER BY simulation_year
    ) AS previous_year_enrollment_date,

    CASE
      WHEN LAG(employee_enrollment_date) OVER (
        PARTITION BY employee_id
        ORDER BY simulation_year
      ) IS NOT NULL
      AND employee_enrollment_date IS NULL
      THEN 'ENROLLMENT_DATE_REGRESSION'
      ELSE 'NO_REGRESSION'
    END AS regression_status

  FROM {{ ref('fct_workforce_snapshot') }}
  WHERE employment_status = 'active'
    AND simulation_year <= {{ var('simulation_year') }}
),

-- Check for multiple enrollment events across years (duplicate enrollments)
duplicate_enrollment_check AS (
  SELECT
    employee_id,
    COUNT(DISTINCT simulation_year) AS years_with_enrollment_events,
    MIN(simulation_year) AS first_enrollment_year,
    MAX(simulation_year) AS last_enrollment_year,
    SUM(enrollment_events_count) AS total_enrollment_events,

    CASE
      WHEN COUNT(DISTINCT simulation_year) > 1
      THEN 'DUPLICATE_ENROLLMENT_ACROSS_YEARS'
      ELSE 'SINGLE_ENROLLMENT_ONLY'
    END AS duplicate_status

  FROM enrollment_events_summary
  GROUP BY employee_id
)

-- Return only records with data quality issues (0 rows = all validations pass)
SELECT
  ev.employee_id,
  ev.simulation_year,
  ev.enrollment_events_count,
  ev.event_enrollment_date,
  ev.snapshot_enrollment_date,
  ev.validation_status,
  ev.event_status,
  ev.snapshot_status,

  -- Regression check
  rc.regression_status,
  rc.previous_year_enrollment_date,

  -- Duplicate enrollment check
  dec.duplicate_status,
  dec.years_with_enrollment_events,
  dec.total_enrollment_events,

  -- Overall data quality flag
  CASE
    WHEN ev.validation_status != 'VALID'
      OR rc.regression_status = 'ENROLLMENT_DATE_REGRESSION'
      OR dec.duplicate_status = 'DUPLICATE_ENROLLMENT_ACROSS_YEARS'
    THEN 'DATA_QUALITY_ISSUE'
    ELSE 'VALID'
  END AS overall_data_quality,

  -- Issue description
  CASE
    WHEN ev.validation_status = 'ENROLLMENT_EVENT_NOT_REFLECTED_IN_SNAPSHOT'
    THEN 'Enrollment event occurred but not reflected in workforce snapshot'

    WHEN ev.validation_status = 'MULTIPLE_ENROLLMENT_EVENTS_IN_YEAR'
    THEN 'Multiple enrollment events in the same year'

    WHEN rc.regression_status = 'ENROLLMENT_DATE_REGRESSION'
    THEN 'Enrollment date was lost between years (regression)'

    WHEN dec.duplicate_status = 'DUPLICATE_ENROLLMENT_ACROSS_YEARS'
    THEN 'Employee has enrollment events in multiple years (duplicate enrollments)'

    ELSE 'No data quality issues detected'
  END AS issue_description,

  CURRENT_TIMESTAMP AS validation_timestamp

FROM enrollment_validation ev
LEFT JOIN enrollment_regression_check rc
  ON ev.employee_id = rc.employee_id
  AND ev.simulation_year = rc.simulation_year
LEFT JOIN duplicate_enrollment_check dec
  ON ev.employee_id = dec.employee_id

WHERE overall_data_quality = 'DATA_QUALITY_ISSUE'

ORDER BY
  ev.employee_id,
  ev.simulation_year
