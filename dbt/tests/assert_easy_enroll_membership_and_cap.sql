{{ config(severity='error', tags=['enrollment', 'easy_enroll']) }}

WITH package_enrollments AS (
  SELECT scenario_id, employee_id, MIN(simulation_year) AS enrollment_year,
    -- A late-year hire's election can take effect next January; the escalation
    -- model counts its delay from the effective date, so this guard must too.
    MIN(EXTRACT('year' FROM effective_date)) AS effective_year
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'enrollment' AND event_category = 'easy_enroll'
  GROUP BY scenario_id, employee_id
),
escalation_parameters AS (
  {% if var('plan_design_parameters', none) %}
  {{ get_plan_design_parameters(var('plan_design_parameters')) }}
  {% else %}
  SELECT
    '{{ var('plan_design_id', 'default') }}'::VARCHAR AS plan_design_id,
    {{ var('deferral_escalation_increment', 0.01) }}::DECIMAL(10,6) AS deferral_escalation_increment
  {% endif %}
)
SELECT ee.employee_id, ee.enrollment_year AS simulation_year, 'missing_initial_state' AS violation
FROM package_enrollments ee
LEFT JOIN {{ ref('int_deferral_rate_state_accumulator') }} s
  ON s.scenario_id = ee.scenario_id AND s.employee_id = ee.employee_id
  AND s.simulation_year = ee.enrollment_year
WHERE s.employee_id IS NULL

UNION ALL

SELECT s.employee_id, s.simulation_year, 'missing_membership' AS violation
FROM {{ ref('int_deferral_rate_state_accumulator') }} s
INNER JOIN package_enrollments ee
  ON s.scenario_id = ee.scenario_id AND s.employee_id = ee.employee_id
  AND s.simulation_year >= ee.enrollment_year
WHERE (NOT s.aip_participant OR s.aip_participant IS NULL)
  {% if var('deferral_rate_changes_enabled', true) and var('deferral_rate_changes_post_escalation_decrease_leaves_escalation', false) %}
  AND NOT EXISTS (
    SELECT 1 FROM {{ ref('fct_yearly_events') }} response
    WHERE response.scenario_id = s.scenario_id AND response.employee_id = s.employee_id
      AND response.simulation_year <= s.simulation_year
      AND response.event_type = 'deferral_change'
      AND response.event_category = 'aip_response_decrease'
      AND NOT EXISTS (
        SELECT 1 FROM {{ ref('fct_yearly_events') }} rejoin
        WHERE rejoin.scenario_id = s.scenario_id AND rejoin.employee_id = s.employee_id
          AND rejoin.simulation_year > response.simulation_year
          AND rejoin.simulation_year <= s.simulation_year
          AND rejoin.event_type = 'enrollment' AND rejoin.event_category = 'easy_enroll'
      )
  )
  {% endif %}

UNION ALL

SELECT s.employee_id, s.simulation_year, 'unexpected_membership' AS violation
FROM {{ ref('int_deferral_rate_state_accumulator') }} s
LEFT JOIN package_enrollments ee
  ON s.scenario_id = ee.scenario_id AND s.employee_id = ee.employee_id
  AND s.simulation_year >= ee.enrollment_year
WHERE s.aip_participant AND ee.employee_id IS NULL
  AND (
    NOT {{ var('deferral_escalation_enabled', true) }}
    OR ('{{ var('deferral_escalation_mode', 'automatic') }}' = 'participant_elected'
      AND {{ var('deferral_escalation_participant_elected_signup_probability', 0.01) }} = 0)
  )

{% if var('easy_enroll_enabled', true) %}
UNION ALL

-- Start from prior-year members eligible on the escalation date, rather than
-- the escalation rows: suppressing all EE escalations must fail this test.
SELECT p.employee_id, w.simulation_year, 'missing_escalation' AS violation
FROM {{ ref('int_deferral_rate_state_accumulator') }} p
INNER JOIN package_enrollments ee
  ON p.scenario_id = ee.scenario_id AND p.employee_id = ee.employee_id
  AND p.simulation_year >= ee.enrollment_year
INNER JOIN {{ ref('int_employee_compensation_by_year') }} w
  ON w.employee_id = p.employee_id AND w.simulation_year = p.simulation_year + 1
INNER JOIN {{ ref('int_plan_design_assignment_accumulator') }} assignment
  ON assignment.employee_id = w.employee_id
  AND assignment.scenario_id = p.scenario_id
  AND assignment.simulation_year = w.simulation_year
INNER JOIN escalation_parameters parameters
  ON parameters.plan_design_id = assignment.plan_design_id
WHERE w.simulation_year = {{ var('simulation_year') }}
  AND p.scenario_id = '{{ var('scenario_id', 'default') }}'
  AND p.aip_participant
  AND w.employment_status = 'active'
  {% if var('deferral_escalation_require_enrollment', true) %}
  AND w.is_enrolled_flag
  {% endif %}
  {% if var('deferral_escalation_hire_date_cutoff', none) is not none %}
  AND w.employee_hire_date >= '{{ var('deferral_escalation_hire_date_cutoff') }}'::DATE
  {% endif %}
  AND w.simulation_year - ee.effective_year >= {{ var('deferral_escalation_first_delay_years', 1) }}
  AND (p.last_escalation_date IS NULL
    OR EXTRACT('year' FROM p.last_escalation_date) < w.simulation_year)
  AND p.current_deferral_rate > 0
  AND LEAST({{ var('easy_enroll_escalation_cap', 0.10) }},
    p.current_deferral_rate + parameters.deferral_escalation_increment
  ) - p.current_deferral_rate >= 0.001
  AND NOT EXISTS (
    SELECT 1 FROM {{ ref('fct_yearly_events') }} t
    WHERE t.scenario_id = p.scenario_id AND t.employee_id = p.employee_id
      AND t.simulation_year = w.simulation_year
      AND t.event_type = 'termination'
      AND t.effective_date < CAST(w.simulation_year || '-{{ var('deferral_escalation_effective_mmdd', '01-01') }}' AS DATE)
  )
  AND NOT EXISTS (
    SELECT 1 FROM {{ ref('fct_yearly_events') }} e
    WHERE e.scenario_id = p.scenario_id AND e.employee_id = p.employee_id
      AND e.simulation_year = w.simulation_year
      AND e.event_type = 'deferral_escalation'
  )
{% endif %}

UNION ALL

SELECT e.employee_id, e.simulation_year, 'invalid_escalation' AS violation
FROM {{ ref('fct_yearly_events') }} e
LEFT JOIN package_enrollments ee
  ON e.scenario_id = ee.scenario_id AND e.employee_id = ee.employee_id
  AND e.simulation_year >= ee.enrollment_year
WHERE e.event_type = 'deferral_escalation'
  AND (
    (ee.employee_id IS NOT NULL
      AND e.employee_deferral_rate > {{ var('easy_enroll_escalation_cap', 0.10) }})
    OR (NOT {{ var('deferral_escalation_enabled', true) }} AND ee.employee_id IS NULL)
  )
