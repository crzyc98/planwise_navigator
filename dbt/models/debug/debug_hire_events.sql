{{ config(
  materialized='table' if var('debug_event') == 'hire' else 'ephemeral',
  tags=['DEBUG', 'EVENT_GENERATION'],
  enabled=var('enable_debug_models', false)
) }}

{% if var('debug_event', '') == 'hire' or var('enable_debug_models', false) %}

-- Debug Hire Events: Detailed analysis of hire event generation
-- This model provides step-by-step visibility into the hire event generation process
-- for development and debugging purposes.

{{ log_dev_subset_status() }}

WITH baseline_workforce AS (
  {{ apply_dev_subset("
    SELECT
      employee_id,
      current_compensation,
      current_age,
      current_tenure,
      level_id,
      age_band,
      tenure_band,
      employment_status
    FROM " ~ ref('int_baseline_workforce') ~ "
    WHERE simulation_year = " ~ var('simulation_year') ~ "
      AND employment_status = 'active'
  ") }}
),

hire_probability_calculation AS (
  SELECT
    bw.*,
    -- Generate deterministic random number for hire probability
    (ABS(HASH(CONCAT(bw.employee_id, '|', '{{ var("simulation_year") }}', '|hire'))) % 2147483647) / 2147483647.0 AS hire_rng,

    -- Simplified hire rate logic for debug (replace with actual business logic)
    CASE
      WHEN bw.level_id = 1 THEN {{ var('hire_rate_level_1', 0.15) }}
      WHEN bw.level_id = 2 THEN {{ var('hire_rate_level_2', 0.12) }}
      WHEN bw.level_id = 3 THEN {{ var('hire_rate_level_3', 0.08) }}
      ELSE {{ var('hire_rate_default', 0.10) }}
    END AS hire_threshold,

    -- Age-based adjustments (younger employees more likely to move/create openings)
    CASE
      WHEN bw.current_age < 30 THEN 1.2
      WHEN bw.current_age < 40 THEN 1.0
      WHEN bw.current_age < 50 THEN 0.8
      ELSE 0.6
    END AS age_adjustment_factor,

    -- Tenure-based adjustments (newer employees more likely to create turnover)
    CASE
      WHEN bw.current_tenure < 2 THEN 1.3
      WHEN bw.current_tenure < 5 THEN 1.0
      WHEN bw.current_tenure < 10 THEN 0.7
      ELSE 0.5
    END AS tenure_adjustment_factor

  FROM baseline_workforce bw
),

hire_decision_logic AS (
  SELECT
    hpc.*,
    -- Calculate adjusted hire threshold
    hpc.hire_threshold * hpc.age_adjustment_factor * hpc.tenure_adjustment_factor AS adjusted_hire_threshold,

    -- Make hire decision
    CASE
      WHEN hpc.hire_rng < (hpc.hire_threshold * hpc.age_adjustment_factor * hpc.tenure_adjustment_factor)
      THEN 'HIRED'
      ELSE 'NO_HIRE'
    END AS hire_decision,

    -- Generate deterministic hire date within the simulation year
    '{{ var("simulation_year") }}-01-01'::DATE +
      INTERVAL (FLOOR((ABS(HASH(CONCAT(hpc.employee_id, '|', '{{ var("simulation_year") }}', '|hire_date'))) % 2147483647) / 2147483647.0 * 365)) DAY AS hire_date,

    -- Generate starting salary with some variation
    ROUND(
      hpc.current_compensation * (0.95 + 0.10 * (ABS(HASH(CONCAT(hpc.employee_id, '|', '{{ var("simulation_year") }}', '|salary'))) % 2147483647) / 2147483647.0)
    ) AS starting_salary

  FROM hire_probability_calculation hpc
),

hire_events_with_debug AS (
  SELECT
    'default' AS scenario_id,
    'default' AS plan_design_id,
    -- Generate new employee ID for hired employee
    CASE
      WHEN hdl.hire_decision = 'HIRED'
      THEN 'NH_' || CAST({{ var('simulation_year') }} AS VARCHAR) || '_' || hdl.employee_id
      ELSE hdl.employee_id
    END AS employee_id,
    'hire' AS event_type,
    hdl.hire_date AS event_date,
    JSON_OBJECT(
      'original_employee_id', hdl.employee_id,
      'level_id', hdl.level_id,
      'starting_salary', hdl.starting_salary,
      'hire_source', 'replacement_hire',
      'department', 'general'
    ) AS event_payload,
    {{ var('simulation_year') }} AS simulation_year,
    CURRENT_TIMESTAMP AS created_at,

    -- Debug information fields
    hdl.hire_rng,
    hdl.hire_threshold,
    hdl.age_adjustment_factor,
    hdl.tenure_adjustment_factor,
    hdl.adjusted_hire_threshold,
    hdl.hire_decision,
    hdl.starting_salary,
    hdl.current_age,
    hdl.current_tenure,

    -- Comprehensive debug message
    CONCAT(
      'DEBUG: emp_id=', hdl.employee_id,
      ', rng=', ROUND(hdl.hire_rng, 4),
      ', base_threshold=', hdl.hire_threshold,
      ', age_adj=', hdl.age_adjustment_factor,
      ', tenure_adj=', hdl.tenure_adjustment_factor,
      ', final_threshold=', ROUND(hdl.adjusted_hire_threshold, 4),
      ', decision=', hdl.hire_decision,
      ', hire_date=', hdl.hire_date,
      ', salary=', hdl.starting_salary
    ) AS debug_info

  FROM hire_decision_logic hdl
  WHERE hdl.hire_decision = 'HIRED'  -- Only return actual hire events
)

SELECT
  {{ generate_event_uuid() }} AS event_id,
  scenario_id,
  plan_design_id,
  employee_id,
  event_type,
  event_date,
  event_payload,
  simulation_year,
  created_at,

  -- Debug fields (these would not be included in production models)
  hire_rng,
  hire_threshold,
  age_adjustment_factor,
  tenure_adjustment_factor,
  adjusted_hire_threshold,
  hire_decision,
  starting_salary,
  current_age,
  current_tenure,
  debug_info

FROM hire_events_with_debug
{{ deterministic_order_by(['employee_id'], ['event_date']) }}

{% else %}

-- Placeholder when debug not enabled - returns empty result set with correct schema
SELECT
  NULL::VARCHAR AS event_id,
  NULL::VARCHAR AS scenario_id,
  NULL::VARCHAR AS plan_design_id,
  NULL::VARCHAR AS employee_id,
  NULL::VARCHAR AS event_type,
  NULL::DATE AS event_date,
  NULL::JSON AS event_payload,
  NULL::INTEGER AS simulation_year,
  NULL::TIMESTAMP AS created_at,
  -- Debug fields
  NULL::DOUBLE AS hire_rng,
  NULL::DOUBLE AS hire_threshold,
  NULL::DOUBLE AS age_adjustment_factor,
  NULL::DOUBLE AS tenure_adjustment_factor,
  NULL::DOUBLE AS adjusted_hire_threshold,
  NULL::VARCHAR AS hire_decision,
  NULL::INTEGER AS starting_salary,
  NULL::INTEGER AS current_age,
  NULL::INTEGER AS current_tenure,
  NULL::VARCHAR AS debug_info
WHERE 1=0

{% endif %}
