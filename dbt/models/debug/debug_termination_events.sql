{{ config(
  materialized='table' if var('debug_event') == 'termination' else 'ephemeral',
  tags=['DEBUG', 'EVENT_GENERATION'],
  enabled=var('enable_debug_models', false)
) }}

{% if var('debug_event', '') == 'termination' or var('enable_debug_models', false) %}

-- Debug Termination Events: Detailed analysis of termination event generation
-- This model provides step-by-step visibility into the termination event generation process
-- including hazard-based probability calculations and demographic factors.

{{ log_dev_subset_status() }}

WITH baseline_workforce AS (
  {{ apply_dev_subset("
    SELECT
      employee_id,
      employee_ssn,
      employee_hire_date,
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
      AND employee_hire_date < CAST('" ~ var('simulation_year') ~ "-01-01' AS DATE)
  ") }}
),

termination_probability_calculation AS (
  SELECT
    bw.*,
    -- Generate deterministic random number for termination probability
    {{ hash_rng('bw.employee_id', var('simulation_year'), 'termination') }} AS term_rng,

    -- Age-based termination rates (hazard modeling)
    CASE
      WHEN bw.current_age < 25 THEN {{ var('term_rate_young', 0.18) }}    -- High turnover for young workers
      WHEN bw.current_age < 35 THEN {{ var('term_rate_early_career', 0.12) }} -- Career building phase
      WHEN bw.current_age < 45 THEN {{ var('term_rate_mid_career', 0.08) }}   -- Stable career phase
      WHEN bw.current_age < 55 THEN {{ var('term_rate_mature', 0.06) }}        -- Pre-retirement stability
      WHEN bw.current_age < 65 THEN {{ var('term_rate_pre_retirement', 0.15) }} -- Some early retirement
      ELSE {{ var('term_rate_retirement', 0.25) }}                            -- Retirement age
    END AS age_based_term_rate,

    -- Tenure-based adjustments (newer employees more likely to leave)
    CASE
      WHEN bw.current_tenure < 1 THEN 2.0   -- Very high first-year turnover
      WHEN bw.current_tenure < 2 THEN 1.5   -- High second-year turnover
      WHEN bw.current_tenure < 5 THEN 1.0   -- Baseline turnover
      WHEN bw.current_tenure < 10 THEN 0.7  -- Lower turnover with experience
      WHEN bw.current_tenure < 20 THEN 0.5  -- Very low turnover for veterans
      ELSE 0.3                              -- Minimal voluntary turnover for long-term employees
    END AS tenure_adjustment_factor,

    -- Compensation-based adjustments (higher paid employees more likely to stay)
    CASE
      WHEN bw.current_compensation < 40000 THEN 1.3   -- Higher turnover for low pay
      WHEN bw.current_compensation < 60000 THEN 1.0   -- Baseline
      WHEN bw.current_compensation < 100000 THEN 0.8  -- Lower turnover for good pay
      ELSE 0.6                                        -- Lowest turnover for high earners
    END AS compensation_adjustment_factor,

    -- Performance tier simulation (based on employee characteristics)
    CASE
      WHEN {{ hash_rng('bw.employee_id', var('simulation_year'), 'performance') }} < 0.15 THEN 'low'
      WHEN {{ hash_rng('bw.employee_id', var('simulation_year'), 'performance') }} < 0.85 THEN 'average'
      ELSE 'high'
    END AS simulated_performance_tier

  FROM baseline_workforce bw
),

termination_decision_logic AS (
  SELECT
    tpc.*,
    -- Calculate final termination probability with all adjustments
    GREATEST(
      0.01,  -- Minimum 1% termination rate
      LEAST(
        0.50,  -- Maximum 50% termination rate cap
        tpc.age_based_term_rate *
        tpc.tenure_adjustment_factor *
        tpc.compensation_adjustment_factor *
        CASE
          WHEN tpc.simulated_performance_tier = 'low' THEN 1.8     -- Higher termination for low performers
          WHEN tpc.simulated_performance_tier = 'high' THEN 0.5    -- Lower termination for high performers
          ELSE 1.0                                                 -- Baseline for average performers
        END
      )
    ) AS final_termination_probability,

    -- Make termination decision
    CASE
      WHEN tpc.term_rng < GREATEST(
        0.01,
        LEAST(
          0.50,
          tpc.age_based_term_rate *
          tpc.tenure_adjustment_factor *
          tpc.compensation_adjustment_factor *
          CASE
            WHEN tpc.simulated_performance_tier = 'low' THEN 1.8
            WHEN tpc.simulated_performance_tier = 'high' THEN 0.5
            ELSE 1.0
          END
        )
      )
      THEN 'TERMINATED'
      ELSE 'RETAINED'
    END AS termination_decision,

    -- Generate termination reason based on demographics and random factors
    CASE
      WHEN tpc.current_age >= 65 THEN 'retirement'
      WHEN tpc.current_age >= 62 AND {{ hash_rng('tpc.employee_id', var('simulation_year'), 'retirement') }} < 0.3 THEN 'early_retirement'
      WHEN tpc.current_tenure < 1 AND {{ hash_rng('tpc.employee_id', var('simulation_year'), 'reason') }} < 0.6 THEN 'voluntary_early'
      WHEN {{ hash_rng('tpc.employee_id', var('simulation_year'), 'reason') }} < 0.8 THEN 'voluntary'
      ELSE 'involuntary'
    END AS termination_reason,

    -- Generate deterministic termination date within the simulation year
    DATE('{{ var("simulation_year") }}-01-01') +
      INTERVAL (FLOOR({{ hash_rng('tpc.employee_id', var('simulation_year'), 'term_date') }} * 365)) DAY AS termination_date

  FROM termination_probability_calculation tpc
),

termination_events_with_debug AS (
  SELECT
    'default' AS scenario_id,
    'default' AS plan_design_id,
    tdl.employee_id,
    'termination' AS event_type,
    tdl.termination_date AS event_date,
    JSON_OBJECT(
      'reason', tdl.termination_reason,
      'level_id', tdl.level_id,
      'tenure_months', tdl.current_tenure * 12,
      'final_compensation', tdl.current_compensation,
      'age_at_termination', tdl.current_age,
      'performance_tier', tdl.simulated_performance_tier
    ) AS event_payload,
    {{ var('simulation_year') }} AS simulation_year,
    CURRENT_TIMESTAMP AS created_at,

    -- Debug information fields
    tdl.term_rng,
    tdl.age_based_term_rate,
    tdl.tenure_adjustment_factor,
    tdl.compensation_adjustment_factor,
    tdl.simulated_performance_tier,
    tdl.final_termination_probability,
    tdl.termination_decision,
    tdl.termination_reason,
    tdl.current_age,
    tdl.current_tenure,
    tdl.current_compensation,

    -- Comprehensive debug message
    CONCAT(
      'DEBUG: emp_id=', tdl.employee_id,
      ', rng=', ROUND(tdl.term_rng, 4),
      ', age_rate=', ROUND(tdl.age_based_term_rate, 4),
      ', tenure_adj=', tdl.tenure_adjustment_factor,
      ', comp_adj=', tdl.compensation_adjustment_factor,
      ', perf=', tdl.simulated_performance_tier,
      ', final_prob=', ROUND(tdl.final_termination_probability, 4),
      ', decision=', tdl.termination_decision,
      ', reason=', tdl.termination_reason,
      ', term_date=', tdl.termination_date
    ) AS debug_info

  FROM termination_decision_logic tdl
  WHERE tdl.termination_decision = 'TERMINATED'  -- Only return actual termination events
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
  term_rng,
  age_based_term_rate,
  tenure_adjustment_factor,
  compensation_adjustment_factor,
  simulated_performance_tier,
  final_termination_probability,
  termination_decision,
  termination_reason,
  current_age,
  current_tenure,
  current_compensation,
  debug_info

FROM termination_events_with_debug
{{ deterministic_order_by(['employee_id'], ['termination_date']) }}

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
  NULL::DOUBLE AS term_rng,
  NULL::DOUBLE AS age_based_term_rate,
  NULL::DOUBLE AS tenure_adjustment_factor,
  NULL::DOUBLE AS compensation_adjustment_factor,
  NULL::VARCHAR AS simulated_performance_tier,
  NULL::DOUBLE AS final_termination_probability,
  NULL::VARCHAR AS termination_decision,
  NULL::VARCHAR AS termination_reason,
  NULL::INTEGER AS current_age,
  NULL::INTEGER AS current_tenure,
  NULL::INTEGER AS current_compensation,
  NULL::VARCHAR AS debug_info
WHERE 1=0

{% endif %}
