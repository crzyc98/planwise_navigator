-- D1: enrolled at zero because of a stop, including years waiting to restart.
{{ config(severity='error') }}
{% if var('deferral_rate_changes_enabled', true) %}
WITH expected AS (
  SELECT s.employee_id, s.scenario_id, s.plan_design_id, s.simulation_year,
    s.current_deferral_rate = 0 AND s.is_enrolled_flag
      AND {{ has_unreversed_stop(ref('fct_yearly_events'), 's.employee_id',
        's.scenario_id', 's.simulation_year + 1') }} AS stopped
  FROM {{ ref('int_deferral_rate_state_accumulator') }} s
  -- Rate state retains past leavers; snapshots only publish this year's workforce.
  INNER JOIN {{ ref('int_workforce_state_accumulator') }} workforce
    ON workforce.employee_id = s.employee_id AND workforce.scenario_id = s.scenario_id
    AND workforce.plan_design_id = s.plan_design_id AND workforce.simulation_year = s.simulation_year
  WHERE s.simulation_year = {{ var('simulation_year') }}
    AND s.scenario_id = '{{ var("scenario_id", "default") }}'
)
SELECT e.employee_id, e.simulation_year
FROM expected e
LEFT JOIN {{ ref('fct_workforce_snapshot') }} snapshot
  ON snapshot.employee_id = e.employee_id AND snapshot.scenario_id = e.scenario_id
  AND snapshot.plan_design_id = e.plan_design_id AND snapshot.simulation_year = e.simulation_year
WHERE (e.stopped AND (
    snapshot.participation_status IS DISTINCT FROM 'not_participating'
    OR snapshot.participation_status_detail IS DISTINCT FROM 'not_participating - stopped contributions'
    OR snapshot.is_enrolled_flag IS DISTINCT FROM TRUE))
  OR (NOT e.stopped AND snapshot.participation_status_detail = 'not_participating - stopped contributions')
{% else %}
SELECT NULL::VARCHAR AS employee_id, NULL::INTEGER AS simulation_year WHERE FALSE
{% endif %}
