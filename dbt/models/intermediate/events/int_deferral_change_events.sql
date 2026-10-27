-- D2/D3: one proactive choice, strictly after every earlier rate event.
{{ config(materialized='ephemeral', tags=['EVENT_GENERATION']) }}
{% set simulation_year = var('simulation_year') | int %}
{% set start_year = var('start_year', 2025) | int %}
{% set scenario_id = var('scenario_id', 'default') %}

{% if not var('deferral_rate_changes_enabled', false) %}
SELECT
  CAST(NULL AS VARCHAR) AS employee_id,
  CAST(NULL AS VARCHAR) AS employee_ssn,
  CAST(NULL AS VARCHAR) AS event_type,
  CAST(NULL AS INTEGER) AS simulation_year,
  CAST(NULL AS DATE) AS effective_date,
  CAST(NULL AS VARCHAR) AS event_details,
  CAST(NULL AS DECIMAL(15,2)) AS compensation_amount,
  CAST(NULL AS DECIMAL(15,2)) AS previous_compensation,
  CAST(NULL AS DECIMAL(5,4)) AS employee_deferral_rate,
  CAST(NULL AS DECIMAL(5,4)) AS prev_employee_deferral_rate,
  CAST(NULL AS SMALLINT) AS employee_age,
  CAST(NULL AS DECIMAL(10,2)) AS employee_tenure,
  CAST(NULL AS SMALLINT) AS level_id,
  CAST(NULL AS VARCHAR) AS age_band,
  CAST(NULL AS VARCHAR) AS tenure_band,
  CAST(NULL AS DECIMAL(5,4)) AS event_probability,
  CAST(NULL AS VARCHAR) AS event_category
WHERE FALSE
{% else %}
WITH irs_limits AS (
  SELECT base_limit, catch_up_limit, catch_up_age_threshold,
    super_catch_up_limit, super_catch_up_age_min, super_catch_up_age_max
  FROM {{ ref('config_irs_limits') }}
  ORDER BY CASE WHEN limit_year = {{ simulation_year }} THEN 0 ELSE 1 END,
    ABS(limit_year - {{ simulation_year }})
  LIMIT 1
),
continuous_participants AS (
  {% if simulation_year == start_year %}
  SELECT b.employee_id, b.employee_deferral_rate AS previous_deferral_rate,
    {{ aip_initial_membership(var('deferral_escalation_mode', 'automatic'),
      'census.auto_escalation_opt_out', 'b.employee_id') }} AS aip_participant
  FROM {{ ref('int_baseline_workforce') }} b
  LEFT JOIN {{ ref('stg_census_data') }} census ON b.employee_id = census.employee_id
  WHERE b.simulation_year = {{ simulation_year }}
    AND b.employee_enrollment_date < DATE '{{ simulation_year }}-01-01'
    AND b.employee_deferral_rate > 0
  {% else %}
  -- Temporal read, like escalation: ref() would create a dependency cycle.
  SELECT employee_id, current_deferral_rate AS previous_deferral_rate, aip_participant
  FROM {{ target.schema }}.int_deferral_rate_state_accumulator
  WHERE simulation_year = {{ simulation_year - 1 }}
    AND scenario_id = '{{ scenario_id }}'
    AND is_enrolled_flag AND current_deferral_rate > 0
  {% endif %}
),
enrollments AS (
  SELECT employee_id, {{ enrollment_payload_deferral_rate() }} AS initial_deferral_rate, effective_date,
    event_details LIKE 'Re-enrollment sweep - %' AS is_reenrollment_sweep
  FROM {{ ref('int_enrollment_events') }}
  WHERE scenario_id = '{{ scenario_id }}'
    AND LOWER(event_type) IN ('enrollment', 'benefit_enrollment')
    AND simulation_year {{ '<=' if simulation_year == start_year else '=' }} {{ simulation_year }}
  QUALIFY ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY effective_date) = 1
),
opt_outs AS (
  SELECT DISTINCT employee_id
  FROM {{ ref('int_enrollment_events') }}
  WHERE scenario_id = '{{ scenario_id }}' AND simulation_year = {{ simulation_year }}
    AND LOWER(event_type) = 'enrollment_change'
    AND COALESCE(employee_deferral_rate, 0) = 0
),
escalations AS (
  SELECT employee_id, effective_date, new_deferral_rate, escalation_rate, max_escalation_rate
  FROM {{ ref('int_deferral_rate_escalation_events') }}
  WHERE simulation_year = {{ simulation_year }} AND new_deferral_rate IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY effective_date DESC) = 1
),
match_responses AS (
  SELECT employee_id, effective_date, employee_deferral_rate AS match_responsive_rate
  FROM {{ ref('int_deferral_match_response_events') }}
  WHERE simulation_year = {{ simulation_year }} AND employee_deferral_rate IS NOT NULL
  QUALIFY ROW_NUMBER() OVER (PARTITION BY employee_id ORDER BY effective_date DESC) = 1
),
rate_inputs AS (
  SELECT w.employee_id, w.employee_ssn, w.employee_compensation,
    w.current_age, w.current_tenure, w.level_id, p.aip_participant,
    {{ rate_before_voluntary_change(
      'oo.employee_id IS NOT NULL', 'TRUE',
      'ne.initial_deferral_rate, p.previous_deferral_rate, 0.03::DECIMAL(5,4)',
      'ce.new_deferral_rate', 'mr.match_responsive_rate', 'ce.escalation_rate',
      'ce.max_escalation_rate', 'w.employee_compensation',
      'COALESCE(' ~ simulation_year ~ ' - YEAR(w.employee_birth_date), w.current_age)'
    ) }} AS previous_rate,
    {{ deferral_change_cap('w.employee_compensation',
      'COALESCE(' ~ simulation_year ~ ' - YEAR(w.employee_birth_date), w.current_age)') }} AS rate_cap,
    -- Include enrollment defensively: opt-outs retain precedence and are excluded.
    CAST(GREATEST(DATE '{{ simulation_year }}-01-01', ce.effective_date,
      mr.effective_date, ne.effective_date) AS DATE) + 1 AS window_start,
    LEAST(DATE '{{ simulation_year }}-12-31', t.termination_date) AS window_end,
    CASE WHEN p.aip_participant
      THEN {{ var('deferral_rate_changes_with_escalation_increase_probability', 0.03) }}
      ELSE {{ var('deferral_rate_changes_without_escalation_increase_probability', 0.25) }}
    END AS increase_probability,
    CASE WHEN p.aip_participant
      THEN {{ var('deferral_rate_changes_with_escalation_decrease_probability', 0.15) }}
      ELSE {{ var('deferral_rate_changes_without_escalation_decrease_probability', 0.075) }}
    END AS decrease_probability,
    {{ enrollment_behavior_draw('w.employee_id', simulation_year, '-deferral-change-') }} AS choice_draw,
    {{ enrollment_behavior_draw('w.employee_id', simulation_year, '-deferral-change-step-') }} AS step_draw,
    {{ enrollment_behavior_draw('w.employee_id', simulation_year, '-deferral-change-timing-') }} AS timing_draw
  FROM continuous_participants p
  INNER JOIN {{ ref('int_employee_compensation_by_year') }} w ON p.employee_id = w.employee_id
    AND w.simulation_year = {{ simulation_year }} AND w.employment_status = 'active'
  INNER JOIN {{ ref('int_plan_design_assignment_accumulator') }} assignment
    ON w.employee_id = assignment.employee_id AND assignment.simulation_year = {{ simulation_year }}
    AND assignment.scenario_id = '{{ scenario_id }}'
  LEFT JOIN enrollments ne ON w.employee_id = ne.employee_id
  LEFT JOIN escalations ce ON w.employee_id = ce.employee_id
    AND {{ rate_event_survives_sweep('ne.is_reenrollment_sweep', 'ne.effective_date', 'ce.effective_date') }}
  LEFT JOIN match_responses mr ON w.employee_id = mr.employee_id
    AND {{ rate_event_survives_sweep('ne.is_reenrollment_sweep', 'ne.effective_date', 'mr.effective_date') }}
  LEFT JOIN opt_outs oo ON w.employee_id = oo.employee_id
  LEFT JOIN {{ ref('int_employee_termination_dates') }} t ON w.employee_id = t.employee_id
    AND t.simulation_year = {{ simulation_year }}
  CROSS JOIN irs_limits il
  WHERE oo.employee_id IS NULL
),
choices AS (
  SELECT employee_id, employee_ssn, employee_compensation, current_age,
    current_tenure, level_id, previous_rate, rate_cap, increase_probability,
    decrease_probability, step_draw,
    {{ deferral_change_category('choice_draw', 'increase_probability', 'decrease_probability') }} AS category,
    {{ deferral_change_date('window_start', 'window_end', 'timing_draw') }} AS change_date
  FROM rate_inputs
  WHERE previous_rate > 0
),
steps AS (
  SELECT employee_id, employee_ssn, employee_compensation, current_age,
    current_tenure, level_id, previous_rate, rate_cap, increase_probability,
    decrease_probability, category, change_date,
    CASE WHEN category = 'proactive_increase'
      THEN {{ deferral_change_step('step_draw', 'increase') }}
      ELSE {{ deferral_change_step('step_draw', 'decrease') }} END AS step_pp
  FROM choices
  WHERE category IS NOT NULL AND change_date IS NOT NULL
),
changes AS (
  SELECT employee_id, employee_ssn, employee_compensation, current_age,
    current_tenure, level_id, previous_rate, increase_probability,
    decrease_probability, category, change_date, step_pp,
    {{ deferral_change_rate('previous_rate', 'category', 'step_pp', 'rate_cap') }} AS new_rate
  FROM steps
)
SELECT
  employee_id::VARCHAR AS employee_id,
  employee_ssn::VARCHAR AS employee_ssn,
  {{ evt_deferral_change() }}::VARCHAR AS event_type,
  {{ simulation_year }}::INTEGER AS simulation_year,
  change_date::DATE AS effective_date,
  (REPLACE(category, '_', ' ') || ': ' || ROUND(previous_rate * 100, 2)
    || '% -> ' || ROUND(new_rate * 100, 2) || '% (drawn step ' || step_pp || 'pp)')::VARCHAR AS event_details,
  employee_compensation::DECIMAL(15,2) AS compensation_amount,
  employee_compensation::DECIMAL(15,2) AS previous_compensation,
  new_rate::DECIMAL(5,4) AS employee_deferral_rate,
  previous_rate::DECIMAL(5,4) AS prev_employee_deferral_rate,
  current_age::SMALLINT AS employee_age,
  current_tenure::DECIMAL(10,2) AS employee_tenure,
  level_id::SMALLINT AS level_id,
  {{ assign_age_band('current_age') }}::VARCHAR AS age_band,
  {{ assign_tenure_band('current_tenure') }}::VARCHAR AS tenure_band,
  (CASE WHEN category = 'proactive_increase' THEN increase_probability
    ELSE decrease_probability END)::DECIMAL(5,4) AS event_probability,
  category::VARCHAR AS event_category
FROM changes
WHERE new_rate <> previous_rate
{% endif %}
