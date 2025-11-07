{{
  config(
    severity='error',
    tags=['data_quality', 'event_validation', 'critical']
  )
}}

/*
  Data Quality Test: Detect Duplicate Events

  Monitors for duplicate events that should be unique per employee/year/type/date

  **Critical Alert Thresholds:**
  - 0 duplicates: PASS (empty result set)
  - 1-10 duplicates: WARNING (investigate)
  - 11+ duplicates: CRITICAL (event generation bug detected)

  Returns rows where duplicate events are detected.
*/

WITH event_duplicates AS (
  SELECT
    scenario_id,
    plan_design_id,
    employee_id,
    simulation_year,
    event_type,
    effective_date,
    COALESCE(compensation_amount, -999) as compensation_key,
    COUNT(*) as event_count,
    COUNT(DISTINCT event_id) as unique_event_ids,
    STRING_AGG(DISTINCT event_id, ', ') as duplicate_event_ids
  FROM {{ ref('fct_yearly_events') }}
  GROUP BY
    scenario_id,
    plan_design_id,
    employee_id,
    simulation_year,
    event_type,
    effective_date,
    COALESCE(compensation_amount, -999)
  HAVING COUNT(*) > 1
)

SELECT
  simulation_year,
  scenario_id,
  plan_design_id,
  employee_id,
  event_type,
  effective_date,
  event_count as duplicate_count,
  unique_event_ids as distinct_event_ids_count,
  duplicate_event_ids,
  CASE
    WHEN event_count <= 2 THEN 'WARNING'
    ELSE 'CRITICAL'
  END as severity
FROM event_duplicates
ORDER BY
  simulation_year,
  event_type,
  employee_id,
  effective_date
