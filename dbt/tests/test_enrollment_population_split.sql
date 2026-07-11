-- depends_on: {{ ref('int_voluntary_enrollment_decision') }}
{{ config(severity='error', tags=['enrollment', 'data_quality']) }}

-- Projected already-enrolled or opted-out employees are not eligible for a
-- voluntary decision in the current context.
{% set projection = adapter.get_relation(database=target.database, schema=target.schema, identifier='enrollment_decision_projection') %}
{% if projection is none %}
SELECT CAST(NULL AS VARCHAR) AS employee_id WHERE FALSE
{% else %}
SELECT
  decision.employee_id,
  state.is_enrolled,
  state.ever_opted_out
FROM {{ ref('int_voluntary_enrollment_decision') }} decision
JOIN {{ source('orchestrator_state', 'enrollment_decision_projection') }} state
  ON decision.employee_id = state.employee_id
WHERE state.decision_year = {{ var('simulation_year') }}
  AND state.scenario_id = '{{ var('scenario_id', 'default') }}'
  AND state.plan_design_id = '{{ var('plan_design_id', 'default') }}'
  AND (state.is_enrolled OR state.ever_opted_out)
{% endif %}
