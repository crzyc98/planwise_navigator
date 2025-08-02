{{
  config(
    materialized='table',
    contract={'enforced': false}
  )
}}

/*
Weekly Participant Balance Snapshots - S072-06

SIMPLIFIED VERSION: This model is temporarily simplified to work with current event structure.
The original version expected DC plan events with payload_json structure that isn't yet implemented.

TODO: Re-implement when DC plan events are fully integrated into fct_yearly_events
*/

WITH enrollment_events AS (
  SELECT DISTINCT
    employee_id AS participant_id,
    'default_plan' AS plan_id,
    simulation_year,
    effective_date,
    event_type
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type IN ('enrollment', 'enrollment_change')
),

simplified_snapshots AS (
  SELECT
    participant_id,
    plan_id,
    simulation_year,
    effective_date AS snapshot_date,

    -- Simplified metrics from current event structure
    CASE WHEN event_type = 'enrollment' THEN TRUE ELSE FALSE END AS is_enrolled,
    'simplified_snapshot' AS participation_status,
    'valid' AS data_quality_flag,
    FALSE AS is_current_week,
    CURRENT_TIMESTAMP AS snapshot_created_at

  FROM enrollment_events
)

SELECT
  participant_id,
  plan_id,
  simulation_year,
  snapshot_date,
  is_enrolled,
  participation_status,
  data_quality_flag,
  is_current_week,
  snapshot_created_at

FROM simplified_snapshots

ORDER BY
  participant_id,
  plan_id,
  snapshot_date
