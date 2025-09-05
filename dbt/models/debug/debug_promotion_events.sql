{{ config(
  materialized='table' if var('debug_event') == 'promotion' else 'ephemeral',
  tags=['DEBUG', 'EVENT_GENERATION'],
  enabled=var('enable_debug_models', false)
) }}

{% if var('debug_event', '') == 'promotion' or var('enable_debug_models', false) %}

-- Debug Promotion Events: Detailed analysis of promotion event generation
-- This model provides step-by-step visibility into the promotion event generation process
-- including career progression logic and performance-based promotion decisions.

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
  ") }}
),

promotion_eligibility_calculation AS (
  SELECT
    bw.*,
    -- Generate deterministic random number for promotion probability
    {{ hash_rng('bw.employee_id', var('simulation_year'), 'promotion') }} AS promotion_rng,

    -- Base promotion rates by level (higher levels have lower promotion rates)
    CASE
      WHEN bw.level_id = 1 THEN {{ var('promotion_rate_level_1', 0.20) }}  -- Entry level, higher promotion rate
      WHEN bw.level_id = 2 THEN {{ var('promotion_rate_level_2', 0.15) }}  -- Mid-level
      WHEN bw.level_id = 3 THEN {{ var('promotion_rate_level_3', 0.10) }}  -- Senior level
      WHEN bw.level_id = 4 THEN {{ var('promotion_rate_level_4', 0.08) }}  -- Management level
      WHEN bw.level_id = 5 THEN {{ var('promotion_rate_level_5', 0.05) }}  -- Executive level
      ELSE {{ var('promotion_rate_default', 0.03) }}                       -- Top levels (rare promotions)
    END AS base_promotion_rate,

    -- Tenure-based eligibility (need minimum tenure for promotion)
    CASE
      WHEN bw.current_tenure < 1 THEN 0.0    -- No promotions in first year
      WHEN bw.current_tenure < 2 THEN 0.5    -- Reduced rate in second year
      WHEN bw.current_tenure < 5 THEN 1.0    -- Normal rate for experienced
      WHEN bw.current_tenure < 10 THEN 1.2   -- Peak promotion years
      WHEN bw.current_tenure < 15 THEN 0.8   -- Declining promotion rate
      ELSE 0.3                               -- Minimal promotions for long-tenured
    END AS tenure_promotion_factor,

    -- Age-based career stage adjustments
    CASE
      WHEN bw.current_age < 25 THEN 0.8   -- Learning phase
      WHEN bw.current_age < 35 THEN 1.3   -- Career building phase
      WHEN bw.current_age < 45 THEN 1.1   -- Prime career years
      WHEN bw.current_age < 55 THEN 0.9   -- Senior contributor phase
      ELSE 0.4                            -- Pre-retirement phase
    END AS age_promotion_factor,

    -- Simulated performance rating (based on deterministic factors)
    CASE
      WHEN {{ hash_rng('bw.employee_id', var('simulation_year'), 'performance') }} < 0.10 THEN 'exceeds'
      WHEN {{ hash_rng('bw.employee_id', var('simulation_year'), 'performance') }} < 0.80 THEN 'meets'
      ELSE 'below'
    END AS performance_rating,

    -- Calculate next level information
    CASE
      WHEN bw.level_id < 6 THEN bw.level_id + 1
      ELSE bw.level_id  -- Already at max level
    END AS promotion_target_level

  FROM baseline_workforce bw
),

promotion_decision_logic AS (
  SELECT
    pec.*,
    -- Performance-based promotion multipliers
    CASE
      WHEN pec.performance_rating = 'exceeds' THEN 2.0   -- High performers get promoted more
      WHEN pec.performance_rating = 'meets' THEN 1.0     -- Standard promotion rate
      ELSE 0.1                                           -- Low performers rarely promoted
    END AS performance_promotion_factor,

    -- Calculate final promotion probability
    LEAST(
      0.40,  -- Cap at 40% maximum promotion rate
      pec.base_promotion_rate *
      pec.tenure_promotion_factor *
      pec.age_promotion_factor *
      CASE
        WHEN pec.performance_rating = 'exceeds' THEN 2.0
        WHEN pec.performance_rating = 'meets' THEN 1.0
        ELSE 0.1
      END
    ) AS final_promotion_probability,

    -- Make promotion decision
    CASE
      WHEN pec.level_id >= 6 THEN 'MAX_LEVEL'  -- Already at maximum level
      WHEN pec.promotion_rng < LEAST(
        0.40,
        pec.base_promotion_rate *
        pec.tenure_promotion_factor *
        pec.age_promotion_factor *
        CASE
          WHEN pec.performance_rating = 'exceeds' THEN 2.0
          WHEN pec.performance_rating = 'meets' THEN 1.0
          ELSE 0.1
        END
      )
      THEN 'PROMOTED'
      ELSE 'NO_PROMOTION'
    END AS promotion_decision,

    -- Calculate salary increase for promotion (typically 8-15%)
    ROUND(
      pec.current_compensation * (
        1.08 + 0.07 * {{ hash_rng('pec.employee_id', var('simulation_year'), 'salary_increase') }}
      )
    ) AS new_compensation,

    -- Generate promotion effective date (typically mid-year performance reviews)
    CASE
      WHEN {{ hash_rng('pec.employee_id', var('simulation_year'), 'promotion_timing') }} < 0.6
      THEN DATE('{{ var("simulation_year") }}-07-01')  -- July promotions (60%)
      WHEN {{ hash_rng('pec.employee_id', var('simulation_year'), 'promotion_timing') }} < 0.9
      THEN DATE('{{ var("simulation_year") }}-01-01')  -- January promotions (30%)
      ELSE DATE('{{ var("simulation_year") }}-10-01')  -- October promotions (10%)
    END AS promotion_date

  FROM promotion_eligibility_calculation pec
),

promotion_events_with_debug AS (
  SELECT
    'default' AS scenario_id,
    'default' AS plan_design_id,
    pdl.employee_id,
    'promotion' AS event_type,
    pdl.promotion_date AS event_date,
    JSON_OBJECT(
      'from_level_id', pdl.level_id,
      'to_level_id', pdl.promotion_target_level,
      'old_compensation', pdl.current_compensation,
      'new_compensation', pdl.new_compensation,
      'salary_increase_pct', ROUND(100.0 * (pdl.new_compensation - pdl.current_compensation) / pdl.current_compensation, 2),
      'performance_rating', pdl.performance_rating,
      'promotion_reason', 'performance_based'
    ) AS event_payload,
    {{ var('simulation_year') }} AS simulation_year,
    CURRENT_TIMESTAMP AS created_at,

    -- Debug information fields
    pdl.promotion_rng,
    pdl.base_promotion_rate,
    pdl.tenure_promotion_factor,
    pdl.age_promotion_factor,
    pdl.performance_rating,
    pdl.performance_promotion_factor,
    pdl.final_promotion_probability,
    pdl.promotion_decision,
    pdl.promotion_target_level,
    pdl.new_compensation,
    pdl.current_age,
    pdl.current_tenure,
    pdl.current_compensation,

    -- Comprehensive debug message
    CONCAT(
      'DEBUG: emp_id=', pdl.employee_id,
      ', rng=', ROUND(pdl.promotion_rng, 4),
      ', base_rate=', ROUND(pdl.base_promotion_rate, 4),
      ', tenure_factor=', pdl.tenure_promotion_factor,
      ', age_factor=', pdl.age_promotion_factor,
      ', perf=', pdl.performance_rating,
      ', perf_factor=', pdl.performance_promotion_factor,
      ', final_prob=', ROUND(pdl.final_promotion_probability, 4),
      ', decision=', pdl.promotion_decision,
      ', from_level=', pdl.level_id,
      ', to_level=', pdl.promotion_target_level,
      ', salary_change=', (pdl.new_compensation - pdl.current_compensation),
      ', promo_date=', pdl.promotion_date
    ) AS debug_info

  FROM promotion_decision_logic pdl
  WHERE pdl.promotion_decision = 'PROMOTED'  -- Only return actual promotion events
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
  promotion_rng,
  base_promotion_rate,
  tenure_promotion_factor,
  age_promotion_factor,
  performance_rating,
  performance_promotion_factor,
  final_promotion_probability,
  promotion_decision,
  promotion_target_level,
  new_compensation,
  current_age,
  current_tenure,
  current_compensation,
  debug_info

FROM promotion_events_with_debug
{{ deterministic_order_by(['employee_id'], ['promotion_date']) }}

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
  NULL::DOUBLE AS promotion_rng,
  NULL::DOUBLE AS base_promotion_rate,
  NULL::DOUBLE AS tenure_promotion_factor,
  NULL::DOUBLE AS age_promotion_factor,
  NULL::VARCHAR AS performance_rating,
  NULL::DOUBLE AS performance_promotion_factor,
  NULL::DOUBLE AS final_promotion_probability,
  NULL::VARCHAR AS promotion_decision,
  NULL::INTEGER AS promotion_target_level,
  NULL::INTEGER AS new_compensation,
  NULL::INTEGER AS current_age,
  NULL::INTEGER AS current_tenure,
  NULL::INTEGER AS current_compensation,
  NULL::VARCHAR AS debug_info
WHERE 1=0

{% endif %}
