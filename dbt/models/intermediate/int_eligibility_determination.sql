{{ config(materialized='table') }}

/*
  Eligibility Determination Model (Epic E022: Story S022-01) - EVENT-BASED VERSION

  Determines employee eligibility for DC plan participation based on eligibility events
  generated at hire time. This approach provides a complete audit trail and simplifies
  eligibility tracking.

  Business Logic:
  - Eligibility is determined from events created when employees are hired
  - Each employee has an eligibility_date calculated as hire_date + waiting_period_days
  - Current eligibility status is derived by comparing eligibility_date to the evaluation date
  - Supports immediate eligibility (0 days) and various waiting periods

  Event Structure:
  - Event type: 'eligibility'
  - Event details contains: eligibility_date, waiting_period_days, determination_type
  - Events are immutable - changes would create new events (future enhancement)

  Performance:
  - Leverages existing event infrastructure
  - JSON extraction is optimized in DuckDB
  - Materialized as table for optimal query performance

  Usage:
    This model is consumed by:
    - Enrollment models for filtering eligible employees
    - Contribution models for participation validation
    - Reporting and analytics
*/

WITH eligibility_events AS (
  -- Get all eligibility events from the event stream
  SELECT
    employee_id,
    employee_ssn,
    simulation_year,
    effective_date as determination_date,
    JSON_EXTRACT_STRING(event_details, '$.eligibility_date')::DATE AS eligibility_date,
    JSON_EXTRACT(event_details, '$.waiting_period_days')::INT AS waiting_period_days,
    JSON_EXTRACT_STRING(event_details, '$.determination_type') AS determination_type,
    created_at
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'eligibility'
    AND JSON_EXTRACT_STRING(event_details, '$.determination_type') = 'initial'
),

-- Get the most recent eligibility determination for each employee
latest_eligibility AS (
  SELECT
    employee_id,
    employee_ssn,
    eligibility_date,
    waiting_period_days,
    determination_date,
    MAX(simulation_year) as last_determination_year
  FROM eligibility_events
  GROUP BY employee_id, employee_ssn, eligibility_date, waiting_period_days, determination_date
),

-- Get employee details from workforce snapshot
employee_details AS (
  SELECT DISTINCT
    employee_id,
    employee_ssn,
    employee_hire_date,
    employment_status,
    current_age,
    current_tenure,
    level_id,
    current_compensation,
    simulation_year
  FROM {{ ref('fct_workforce_snapshot') }}
)

-- Join eligibility events with employee details for each simulation year
SELECT
  ed.employee_id,
  ed.employee_ssn,
  ed.employee_hire_date,
  ed.employment_status,
  ed.current_age,
  ed.current_tenure,
  ed.level_id,
  ed.current_compensation,
  le.waiting_period_days,
  ed.simulation_year,
  -- Calculate days since hire as of the evaluation date (end of simulation year)
  DATEDIFF('day', ed.employee_hire_date, CAST(ed.simulation_year || '-12-31' AS DATE)) as days_since_hire,
  -- Determine if eligible based on eligibility date
  CASE
    WHEN le.eligibility_date <= CAST(ed.simulation_year || '-12-31' AS DATE) THEN true
    ELSE false
  END as is_eligible,
  -- Provide eligibility reason
  CASE
    WHEN le.eligibility_date <= CAST(ed.simulation_year || '-12-31' AS DATE) THEN 'eligible_service_met'
    ELSE 'pending_service_requirement'
  END as eligibility_reason,
  -- Use end of year as evaluation date for consistency
  CAST(ed.simulation_year || '-12-31' AS DATE) as eligibility_evaluation_date,
  le.eligibility_date as employee_eligibility_date
FROM employee_details ed
LEFT JOIN latest_eligibility le ON ed.employee_id = le.employee_id
WHERE ed.employment_status = 'active'
ORDER BY ed.simulation_year, ed.employee_id
