{{ config(materialized='view', tags=['EVENT_GENERATION', 'enrollment']) }}

-- Disposable input rebuilt by the orchestrator before each event-generation year.
SELECT
  employee_id,
  decision_year,
  enrollment_date,
  is_enrolled,
  ever_opted_out,
  enrollment_source,
  current_deferral_rate,
  latest_event_id,
  latest_event_year,
  latest_event_effective_date
FROM {{ source('orchestrator_state', 'enrollment_decision_projection') }}
WHERE decision_year = {{ var('simulation_year') }}
  AND scenario_id = '{{ var('scenario_id', 'default') }}'
  AND plan_design_id = '{{ var('plan_design_id', 'default') }}'
