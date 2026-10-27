{{ config(materialized='incremental', incremental_strategy='replace_simulation_year',
  on_schema_change='sync_all_columns', tags=['EVENT_GENERATION']) }}

-- Preserve declined candidates and the rate at the sweep for an auditable denominator.
WITH {{ reenrollment_sweep_inputs() }},
irs_limits AS (
  SELECT base_limit, catch_up_limit, catch_up_age_threshold,
    super_catch_up_limit, super_catch_up_age_min, super_catch_up_age_max
  FROM {{ ref('config_irs_limits') }}
  ORDER BY CASE WHEN limit_year = {{ var('simulation_year') }} THEN 0 ELSE 1 END,
    ABS(limit_year - {{ var('simulation_year') }})
  LIMIT 1
),
rate_inputs AS (
  SELECT
    aw.employee_id,
    aw.employee_ssn,
    aw.plan_design_id,
    aw.simulation_year,
    aw.current_compensation,
    aw.current_age,
    aw.current_tenure,
    aw.level_id,
    aw.age_band,
    aw.tenure_band,
    aw.reenrollment_sweep_method,
    aw.reenrollment_sweep_decline_probability,
    aw.reenrollment_sweep_include_below_default,
    aw.reenrollment_sweep_include_below_aip_cap,
    aw.auto_enrollment_default_deferral_rate,
    aw.deferral_escalation_cap,
    {{ reenrollment_sweep_date('aw') }} AS sweep_date,
    pe.latest_opt_out_date,
    pe.prior_aip_participant,
    CAST({{ rate_before_voluntary_change(
      'FALSE', 'TRUE', 'pe.sweep_deferral_rate, 0',
      'ce.new_deferral_rate', 'mr.employee_deferral_rate', 'ce.escalation_rate',
      'ce.max_escalation_rate', 'aw.current_compensation', 'aw.current_age'
    ) }} AS DECIMAL(5,4)) AS rate_at_sweep,
    {{ enrollment_behavior_draw('aw.employee_id', 'aw.simulation_year', '-reenrollment-decline-') }} AS decline_draw
  FROM active_workforce aw
  LEFT JOIN previous_enrollment_state pe ON aw.employee_id = pe.employee_id
  LEFT JOIN {{ ref('int_deferral_rate_escalation_events') }} ce
    ON aw.employee_id = ce.employee_id AND aw.simulation_year = ce.simulation_year
    AND ce.effective_date <= ({{ reenrollment_sweep_date('aw') }})
  LEFT JOIN {{ ref('int_deferral_match_response_events') }} mr
    ON aw.employee_id = mr.employee_id AND aw.simulation_year = mr.simulation_year
    AND mr.effective_date <= ({{ reenrollment_sweep_date('aw') }})
  CROSS JOIN irs_limits il
  WHERE {{ var('auto_enrollment_enabled', true) }}
    AND {{ is_reenrollment_sweep_year('aw.simulation_year', 'aw.reenrollment_sweep_enabled', 'aw.reenrollment_sweep_interval_years', 'aw.reenrollment_sweep_first_year') }}
    AND aw.employment_status = 'active' AND aw.is_plan_eligible
    AND NOT aw.is_plan_ineligible_override
    AND aw.plan_eligibility_date <= MAKE_DATE(aw.simulation_year, 12, 31)
    -- 0% participants use the enrollment path and its AE opt-out model.
    AND pe.sweep_deferral_rate > 0
),
candidates AS (
  SELECT
    r.employee_id,
    r.employee_ssn,
    r.plan_design_id,
    r.simulation_year,
    r.current_compensation,
    r.current_age,
    r.current_tenure,
    r.level_id,
    r.age_band,
    r.tenure_band,
    r.reenrollment_sweep_method,
    r.reenrollment_sweep_decline_probability,
    r.reenrollment_sweep_include_below_default,
    r.reenrollment_sweep_include_below_aip_cap,
    r.auto_enrollment_default_deferral_rate,
    r.deferral_escalation_cap,
    r.sweep_date,
    r.latest_opt_out_date,
    r.rate_at_sweep,
    r.decline_draw
  FROM rate_inputs r
  LEFT JOIN {{ ref('int_employee_termination_dates') }} t
    ON r.employee_id = t.employee_id AND r.simulation_year = t.simulation_year
  WHERE {{ reenrollment_contributor_group('r', 'r.rate_at_sweep') }}
    -- Sweep only contributors it changes: a higher rate, or joining automatic
    -- increases they aren't already in. Otherwise the event would be a no-op.
    AND ({{ reenrollment_contributor_rate('r', 'r.rate_at_sweep') }} > r.rate_at_sweep
      OR (NOT COALESCE(r.prior_aip_participant, FALSE)
        AND (r.reenrollment_sweep_method = 'into_aip'
          OR {{ var('deferral_escalation_enabled', true) }})))
    AND (r.latest_opt_out_date IS NULL OR r.latest_opt_out_date < r.sweep_date)
    AND (t.termination_date IS NULL OR r.sweep_date <= t.termination_date)
)
SELECT
  '{{ var("scenario_id", "default") }}' AS scenario_id,
  plan_design_id, employee_id, employee_ssn, simulation_year,
  sweep_date AS effective_date, current_compensation, current_age, current_tenure,
  level_id, age_band, tenure_band, rate_at_sweep,
  rate_at_sweep < auto_enrollment_default_deferral_rate AS below_default,
  rate_at_sweep < deferral_escalation_cap AS below_aip_cap,
  reenrollment_sweep_method AS method,
  reenrollment_sweep_decline_probability AS decline_probability,
  decline_draw,
  decline_draw < reenrollment_sweep_decline_probability AS declined,
  {{ reenrollment_contributor_rate('candidates', 'rate_at_sweep') }}::DECIMAL(5,4) AS sweep_rate
FROM candidates
