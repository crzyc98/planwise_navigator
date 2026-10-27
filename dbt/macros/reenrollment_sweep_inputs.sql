{# Shared eligibility, prior rate and pending opt-out inputs for both sweep paths. #}
{% macro reenrollment_sweep_inputs() %}
{% set plan_design_parameters_config = var("plan_design_parameters", none) %}
parameter_rows AS (
{% if plan_design_parameters_config %}
  {{ get_plan_design_parameters(plan_design_parameters_config) }}
{% else %}
  SELECT
    '{{ var('plan_design_id', 'default') }}'::VARCHAR AS plan_design_id,
    {{ var('auto_enrollment_default_deferral_rate', 0.02) }}::DECIMAL(10,6)
      AS auto_enrollment_default_deferral_rate,
    {{ var('auto_enrollment_window_days', 45) }}::INTEGER
      AS auto_enrollment_window_days,
    '{{ var('auto_enrollment_scope', 'all_eligible_employees') }}'::VARCHAR
      AS auto_enrollment_scope,
    {{ var('reenrollment_sweep_enabled', false) }}::BOOLEAN AS reenrollment_sweep_enabled,
    {{ var('reenrollment_sweep_interval_years', 3) }}::INTEGER AS reenrollment_sweep_interval_years,
    {{ var('reenrollment_sweep_first_year', none) if var('reenrollment_sweep_first_year', none) is not none else 'NULL' }}::INTEGER AS reenrollment_sweep_first_year,
    '{{ var('reenrollment_sweep_method', 'enroll_at_default') }}'::VARCHAR AS reenrollment_sweep_method,
    {{ var('reenrollment_sweep_include_non_contributors', true) }}::BOOLEAN AS reenrollment_sweep_include_non_contributors,
    {{ var('reenrollment_sweep_include_below_default', false) }}::BOOLEAN AS reenrollment_sweep_include_below_default,
    {{ var('reenrollment_sweep_include_below_aip_cap', false) }}::BOOLEAN AS reenrollment_sweep_include_below_aip_cap,
    {{ var('reenrollment_sweep_decline_probability', 0.10) }}::DECIMAL(10,6) AS reenrollment_sweep_decline_probability,
    {{ var('deferral_escalation_increment', 0.01) }}::DECIMAL(10,6) AS deferral_escalation_increment,
    {{ var('deferral_escalation_cap', 0.10) }}::DECIMAL(10,6) AS deferral_escalation_cap
{% endif %}
),

active_workforce_base AS (
  -- Base active employees with compensation (excludes current-year new hires in first year)
  SELECT DISTINCT
    employee_id,
    employee_ssn,
    employee_hire_date,
    {{ var('simulation_year') }} as simulation_year,
    current_age,
    current_tenure,
    level_id,
    employee_compensation AS current_compensation,
    {{ assign_age_band('current_age') }} AS age_band,
    {{ assign_tenure_band('current_tenure') }} AS tenure_band,
    employment_status
  FROM {{ ref('int_employee_compensation_by_year') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND employment_status = 'active'
),

new_hires_current_year AS (
  -- Ensure current-year new hires are considered for enrollment attempts in their hire year
  SELECT DISTINCT
    he.employee_id,
    he.employee_ssn,
    he.effective_date::DATE AS employee_hire_date,
    he.simulation_year,
    he.employee_age AS current_age,
    0.0 AS current_tenure,
    he.level_id,
    he.compensation_amount AS current_compensation,
    {{ assign_age_band('he.employee_age') }} AS age_band,
    {{ assign_tenure_band('0') }} AS tenure_band,
    'active' AS employment_status
  FROM {{ ref('int_hiring_events') }} he
  WHERE he.simulation_year = {{ var('simulation_year') }}
),

active_workforce AS (
  -- Feature 103: fold the resolved plan-eligibility override into the population
  -- once, so every eligibility flag below gates on `NOT is_plan_ineligible_override`.
  SELECT
    base.employee_id,
    base.employee_ssn,
    base.employee_hire_date,
    base.simulation_year,
    base.current_age,
    base.current_tenure,
    base.level_id,
    base.current_compensation,
    base.age_band,
    base.tenure_band,
    base.employment_status,
    assignment.plan_design_id,
    parameters.auto_enrollment_default_deferral_rate,
    parameters.auto_enrollment_window_days,
    parameters.auto_enrollment_scope,
    parameters.reenrollment_sweep_enabled,
    parameters.reenrollment_sweep_interval_years,
    parameters.reenrollment_sweep_first_year,
    parameters.reenrollment_sweep_method,
    parameters.reenrollment_sweep_include_non_contributors,
    parameters.reenrollment_sweep_include_below_default,
    parameters.reenrollment_sweep_include_below_aip_cap,
    parameters.reenrollment_sweep_decline_probability,
    parameters.deferral_escalation_increment,
    parameters.deferral_escalation_cap,
    eligibility.plan_eligibility_date,
    eligibility.is_plan_eligible,
    COALESCE(ov.is_plan_ineligible_override, false) AS is_plan_ineligible_override
  FROM (
    SELECT employee_id, employee_ssn, employee_hire_date, simulation_year, current_age, current_tenure, level_id, current_compensation, age_band, tenure_band, employment_status FROM active_workforce_base
    UNION ALL
    SELECT employee_id, employee_ssn, employee_hire_date, simulation_year, current_age, current_tenure, level_id, current_compensation, age_band, tenure_band, employment_status FROM new_hires_current_year
  ) base
  INNER JOIN {{ ref('int_plan_design_assignment_accumulator') }} assignment
    ON base.employee_id = assignment.employee_id
   AND base.simulation_year = assignment.simulation_year
   AND assignment.scenario_id = '{{ var('scenario_id', 'default') }}'
  INNER JOIN parameter_rows parameters
    ON assignment.plan_design_id = parameters.plan_design_id
  INNER JOIN {{ ref('int_plan_eligibility_determination') }} eligibility
    ON base.employee_id = eligibility.employee_id
   AND base.simulation_year = eligibility.simulation_year
   AND assignment.plan_design_id = eligibility.plan_design_id
   AND eligibility.scenario_id = '{{ var('scenario_id', 'default') }}'
  LEFT JOIN {{ ref('int_plan_eligibility_override') }} ov
    ON base.employee_id = ov.employee_id
    AND base.simulation_year = ov.simulation_year
),

-- Temporal inputs: only published prior simulation years are available here.
-- Direct relation reads avoid a cycle through this year's event publication.
prior_sweep_events AS (
  {% if var('simulation_year') | int > var('start_year', 2025) | int %}
  SELECT employee_id, effective_date, event_type, event_details,
    employee_deferral_rate, event_sequence, event_id
  FROM {{ target.schema }}.fct_yearly_events
  WHERE simulation_year < {{ var('simulation_year') }}
    AND scenario_id = '{{ var('scenario_id', 'default') }}'
    AND event_type IN ('enrollment', 'benefit_enrollment', 'enrollment_change',
      'deferral_escalation', 'deferral_match_response', 'deferral_change')
  {% else %}
  SELECT NULL::VARCHAR AS employee_id, NULL::TIMESTAMP AS effective_date,
    NULL::VARCHAR AS event_type, NULL::VARCHAR AS event_details,
    NULL::DECIMAL(5,4) AS employee_deferral_rate, NULL::INTEGER AS event_sequence,
    NULL::VARCHAR AS event_id
  WHERE FALSE
  {% endif %}
),
sweep_history AS (
  SELECT aw.employee_id,
    MAX(e.effective_date) FILTER (WHERE e.event_type = 'enrollment_change'
      AND LOWER(e.event_details) LIKE '%opt-out%') AS latest_opt_out_date,
    -- Prior-year events can take effect this year. Apply those already effective
    -- at the sweep date on top of the prior-year deferral accumulator.
    ARG_MAX(e.employee_deferral_rate,
      STRUCT_PACK(date := e.effective_date, sequence := e.event_sequence, id := e.event_id))
      FILTER (WHERE e.effective_date >= MAKE_DATE(aw.simulation_year, 1, 1)
        AND e.effective_date <= ({{ reenrollment_sweep_date('aw') }})) AS pending_deferral_rate
  FROM active_workforce aw
  LEFT JOIN prior_sweep_events e ON aw.employee_id = e.employee_id
  GROUP BY aw.employee_id
),
previous_enrollment_state AS (
  SELECT
    pe.employee_id,
    pe.enrollment_date AS previous_enrollment_date,
    pe.is_enrolled AS was_enrolled_previously,
    pe.ever_opted_out,
    pe.current_deferral_rate,
    history.latest_opt_out_date,
    COALESCE(history.pending_deferral_rate,
      {% if var('simulation_year') | int > var('start_year', 2025) | int %}
      deferral.current_deferral_rate,
      {% endif %}
      pe.current_deferral_rate, 0) AS sweep_deferral_rate,
    {% if var('simulation_year') | int > var('start_year', 2025) | int %}
    deferral.aip_participant AS prior_aip_participant,
    {% else %}
    NULL::BOOLEAN AS prior_aip_participant,
    {% endif %}
    pe.enrollment_source,
    CASE WHEN pe.enrollment_date IS NULL THEN 0
         ELSE {{ var('simulation_year') }} - EXTRACT(YEAR FROM pe.enrollment_date)
    END AS years_since_first_enrollment
  FROM {{ ref('stg_prior_enrollment_state') }} pe
  LEFT JOIN sweep_history history ON pe.employee_id = history.employee_id
  {% if var('simulation_year') | int > var('start_year', 2025) | int %}
  LEFT JOIN {{ target.schema }}.int_deferral_rate_state_accumulator deferral
    ON pe.employee_id = deferral.employee_id
    AND deferral.simulation_year = {{ var('simulation_year') }} - 1
    AND deferral.scenario_id = '{{ var('scenario_id', 'default') }}'
  {% endif %}
)
{% endmacro %}
