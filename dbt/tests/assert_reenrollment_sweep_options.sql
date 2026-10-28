{{ config(severity='error', tags=['enrollment_validation']) }}

-- Declines produce no sweep; accepted contributors publish exactly the audited
-- rate election. Group flags are strict comparisons evaluated at the sweep date.
WITH parameter_rows AS (
{% if var('plan_design_parameters', none) %}
  {{ get_plan_design_parameters(var('plan_design_parameters')) }}
{% else %}
  SELECT '{{ var("plan_design_id", "default") }}' AS plan_design_id,
    '{{ var("reenrollment_sweep_method", "enroll_at_default") }}' AS reenrollment_sweep_method,
    {{ var('reenrollment_sweep_include_non_contributors', true) }} AS reenrollment_sweep_include_non_contributors,
    {{ var('reenrollment_sweep_include_below_default', false) }} AS reenrollment_sweep_include_below_default,
    {{ var('reenrollment_sweep_include_below_aip_cap', false) }} AS reenrollment_sweep_include_below_aip_cap,
    {{ var('auto_enrollment_default_deferral_rate', 0.02) }} AS auto_enrollment_default_deferral_rate,
    {{ var('deferral_escalation_increment', 0.01) }} AS deferral_escalation_increment,
    {{ var('deferral_escalation_cap', 0.10) }} AS deferral_escalation_cap
{% endif %}
), contributor_events AS (
  SELECT employee_id, scenario_id, plan_design_id, simulation_year, effective_date,
    employee_deferral_rate, prev_employee_deferral_rate, event_type
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_category = 'reenrollment_sweep'
    AND simulation_year = {{ var('simulation_year') }}
    AND scenario_id = '{{ var('scenario_id', 'default') }}'
), candidates AS (
  SELECT employee_id, scenario_id, plan_design_id, simulation_year, effective_date,
    rate_at_sweep, sweep_rate, method, declined, decline_draw, decline_probability,
    below_default, below_aip_cap
  FROM {{ ref('int_reenrollment_sweep_candidates') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND scenario_id = '{{ var('scenario_id', 'default') }}'
), contributor_violations AS (
  SELECT COALESCE(c.employee_id, e.employee_id) AS employee_id,
    COALESCE(c.simulation_year, e.simulation_year) AS simulation_year
  FROM candidates c FULL OUTER JOIN contributor_events e
    USING (employee_id, scenario_id, plan_design_id, simulation_year)
  LEFT JOIN parameter_rows p ON c.plan_design_id = p.plan_design_id
  WHERE c.employee_id IS NULL
    OR (c.declined AND e.employee_id IS NOT NULL)
    OR (NOT c.declined AND (e.employee_id IS NULL
      OR e.event_type <> 'deferral_change'
      OR e.effective_date IS DISTINCT FROM c.effective_date
      OR e.prev_employee_deferral_rate IS DISTINCT FROM c.rate_at_sweep::DECIMAL(5,4)
      OR e.employee_deferral_rate IS DISTINCT FROM c.sweep_rate))
    OR c.declined IS DISTINCT FROM (c.decline_draw < c.decline_probability)
    OR NOT {{ reenrollment_contributor_group('p', 'c.rate_at_sweep') }}
    OR c.below_default IS DISTINCT FROM (c.rate_at_sweep < p.auto_enrollment_default_deferral_rate)
    OR c.below_aip_cap IS DISTINCT FROM (c.rate_at_sweep < p.deferral_escalation_cap)
    OR c.method IS DISTINCT FROM p.reenrollment_sweep_method
    OR c.sweep_rate IS DISTINCT FROM CAST({{ reenrollment_contributor_rate('p', 'c.rate_at_sweep') }} AS DECIMAL(5,4))
    OR (c.method = 'into_aip' AND c.sweep_rate IS DISTINCT FROM c.rate_at_sweep::DECIMAL(5,4))
    OR (c.method = 'enroll_at_default' AND c.sweep_rate < c.rate_at_sweep)
), membership_violations AS (
  SELECT c.employee_id, c.simulation_year
  FROM candidates c
  LEFT JOIN {{ ref('int_deferral_rate_state_accumulator') }} s
    USING (employee_id, scenario_id, plan_design_id, simulation_year)
  WHERE NOT c.declined
    AND ({{ var('deferral_escalation_enabled', true) }} OR c.method = 'into_aip')
    AND NOT COALESCE(s.aip_participant, FALSE)
    {% if var('deferral_rate_changes_enabled', true) and var('deferral_rate_changes_post_escalation_decrease_leaves_escalation', false) %}
    AND NOT EXISTS (
      SELECT 1 FROM {{ ref('fct_yearly_events') }} exit
      WHERE exit.employee_id = c.employee_id AND exit.scenario_id = c.scenario_id
        AND exit.simulation_year = c.simulation_year AND exit.effective_date > c.effective_date
        AND exit.event_category = 'aip_response_decrease'
    )
    {% endif %}
), enrollment_violations AS (
  SELECT e.employee_id, e.simulation_year
  FROM {{ ref('fct_yearly_events') }} e
  INNER JOIN parameter_rows p USING (plan_design_id)
  WHERE e.event_type = 'enrollment' AND e.event_details LIKE 'Re-enrollment sweep - %'
    AND e.simulation_year = {{ var('simulation_year') }}
    AND e.scenario_id = '{{ var('scenario_id', 'default') }}'
    AND (NOT p.reenrollment_sweep_include_non_contributors
      OR e.employee_deferral_rate IS DISTINCT FROM CAST(CASE
        WHEN p.reenrollment_sweep_method = 'into_aip' THEN p.deferral_escalation_increment
        ELSE p.auto_enrollment_default_deferral_rate END AS DECIMAL(5,4)))
)
SELECT employee_id, simulation_year FROM contributor_violations
UNION ALL
SELECT employee_id, simulation_year FROM enrollment_violations

UNION ALL
SELECT employee_id, simulation_year FROM membership_violations
