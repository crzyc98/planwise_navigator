{{ config(
    materialized='table',
    tags=['data_quality', 'event_validation', 'critical']
) }}

-- Data Quality Check: Detect Duplicate Events
-- Monitors for duplicate events that should be unique per employee/year/type/date
--
-- **Critical Alert Thresholds:**
-- - 0 duplicates: PASS
-- - 1-10 duplicates: WARNING (investigate)
-- - 11+ duplicates: CRITICAL (event generation bug detected)

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
),

duplicate_summary AS (
  SELECT
    simulation_year,
    event_type,
    COUNT(*) as duplicate_groups,
    SUM(event_count - 1) as total_duplicate_events,
    SUM(event_count) as total_events_in_duplicates
  FROM event_duplicates
  GROUP BY simulation_year, event_type
),

overall_summary AS (
  SELECT
    COUNT(DISTINCT simulation_year) as affected_years,
    COUNT(DISTINCT employee_id) as affected_employees,
    SUM(event_count - 1) as total_duplicate_events,
    CASE
      WHEN SUM(event_count - 1) = 0 THEN 'PASS'
      WHEN SUM(event_count - 1) <= 10 THEN 'WARNING'
      ELSE 'CRITICAL'
    END as data_quality_status
  FROM event_duplicates
)

-- Final output with duplicate details
SELECT
  ed.simulation_year,
  ed.scenario_id,
  ed.plan_design_id,
  ed.employee_id,
  ed.event_type,
  ed.effective_date,
  ed.compensation_key,
  ed.event_count as duplicate_count,
  ed.unique_event_ids as distinct_event_ids_count,
  ed.duplicate_event_ids,
  ds.duplicate_groups as year_type_duplicate_groups,
  ds.total_duplicate_events as year_type_total_duplicates,
  os.total_duplicate_events as overall_duplicate_events,
  os.affected_employees as overall_affected_employees,
  os.data_quality_status,
  CURRENT_TIMESTAMP as validation_timestamp,
  'duplicate_event_detection_v1' as validation_rule
FROM event_duplicates ed
LEFT JOIN duplicate_summary ds
  ON ed.simulation_year = ds.simulation_year
  AND ed.event_type = ds.event_type
CROSS JOIN overall_summary os
ORDER BY
  ed.simulation_year,
  ed.event_type,
  ed.employee_id,
  ed.effective_date
