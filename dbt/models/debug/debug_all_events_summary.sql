{{ config(
  materialized='table' if var('enable_debug_models', false) else 'ephemeral',
  tags=['DEBUG', 'EVENT_SUMMARY'],
  enabled=var('enable_debug_models', false)
) }}

{% if var('enable_debug_models', false) %}

-- Debug All Events Summary: Comprehensive overview of all event generation
-- This model provides a unified view of hire, termination, and promotion events
-- with aggregate statistics and data quality validation.

WITH hire_events AS (
  SELECT
    'hire' AS event_category,
    COUNT(*) AS event_count,
    COUNT(DISTINCT employee_id) AS unique_employees,
    MIN(event_date) AS earliest_date,
    MAX(event_date) AS latest_date,
    AVG(starting_salary) AS avg_starting_salary,
    AVG(hire_rng) AS avg_rng_value,
    STDDEV(hire_rng) AS rng_stddev,
    COUNT(CASE WHEN hire_decision = 'HIRED' THEN 1 END) AS hired_count,
    COUNT(*) - COUNT(CASE WHEN hire_decision = 'HIRED' THEN 1 END) AS not_hired_count
  FROM {{ ref('debug_hire_events') }}
  WHERE {{ var('enable_debug_models', false) }}
),

termination_events AS (
  SELECT
    'termination' AS event_category,
    COUNT(*) AS event_count,
    COUNT(DISTINCT employee_id) AS unique_employees,
    MIN(event_date) AS earliest_date,
    MAX(event_date) AS latest_date,
    AVG(current_compensation) AS avg_final_compensation,
    AVG(term_rng) AS avg_rng_value,
    STDDEV(term_rng) AS rng_stddev,
    COUNT(CASE WHEN termination_decision = 'TERMINATED' THEN 1 END) AS terminated_count,
    COUNT(*) - COUNT(CASE WHEN termination_decision = 'TERMINATED' THEN 1 END) AS retained_count
  FROM {{ ref('debug_termination_events') }}
  WHERE {{ var('enable_debug_models', false) }}
),

promotion_events AS (
  SELECT
    'promotion' AS event_category,
    COUNT(*) AS event_count,
    COUNT(DISTINCT employee_id) AS unique_employees,
    MIN(event_date) AS earliest_date,
    MAX(event_date) AS latest_date,
    AVG(new_compensation) AS avg_new_compensation,
    AVG(promotion_rng) AS avg_rng_value,
    STDDEV(promotion_rng) AS rng_stddev,
    COUNT(CASE WHEN promotion_decision = 'PROMOTED' THEN 1 END) AS promoted_count,
    COUNT(*) - COUNT(CASE WHEN promotion_decision = 'PROMOTED' THEN 1 END) AS not_promoted_count
  FROM {{ ref('debug_promotion_events') }}
  WHERE {{ var('enable_debug_models', false) }}
),

unified_summary AS (
  SELECT
    he.event_category,
    he.event_count,
    he.unique_employees,
    he.earliest_date,
    he.latest_date,
    he.avg_starting_salary AS avg_compensation,
    he.avg_rng_value,
    he.rng_stddev,
    he.hired_count AS positive_events,
    he.not_hired_count AS negative_events
  FROM hire_events he

  UNION ALL

  SELECT
    te.event_category,
    te.event_count,
    te.unique_employees,
    te.earliest_date,
    te.latest_date,
    te.avg_final_compensation AS avg_compensation,
    te.avg_rng_value,
    te.rng_stddev,
    te.terminated_count AS positive_events,
    te.retained_count AS negative_events
  FROM termination_events te

  UNION ALL

  SELECT
    pe.event_category,
    pe.event_count,
    pe.unique_employees,
    pe.earliest_date,
    pe.latest_date,
    pe.avg_new_compensation AS avg_compensation,
    pe.avg_rng_value,
    pe.rng_stddev,
    pe.promoted_count AS positive_events,
    pe.not_promoted_count AS negative_events
  FROM promotion_events pe
),

rng_quality_analysis AS (
  SELECT
    event_category,
    -- Check if RNG mean is close to 0.5 (good uniform distribution)
    CASE
      WHEN ABS(avg_rng_value - 0.5) < 0.05 THEN 'GOOD ✅'
      WHEN ABS(avg_rng_value - 0.5) < 0.1 THEN 'ACCEPTABLE ⚠️'
      ELSE 'POOR ❌'
    END AS rng_mean_quality,

    -- Check if RNG standard deviation is close to ~0.289 (expected for uniform distribution)
    CASE
      WHEN ABS(rng_stddev - 0.289) < 0.05 THEN 'GOOD ✅'
      WHEN ABS(rng_stddev - 0.289) < 0.1 THEN 'ACCEPTABLE ⚠️'
      ELSE 'POOR ❌'
    END AS rng_stddev_quality,

    avg_rng_value,
    rng_stddev

  FROM unified_summary
),

event_rate_analysis AS (
  SELECT
    us.event_category,
    us.positive_events,
    us.negative_events,
    us.positive_events + us.negative_events AS total_evaluations,
    ROUND(100.0 * us.positive_events / (us.positive_events + us.negative_events), 2) AS event_rate_pct,

    -- Expected event rates for validation
    CASE
      WHEN us.event_category = 'hire' THEN 15.0        -- ~15% hire rate expected
      WHEN us.event_category = 'termination' THEN 10.0 -- ~10% termination rate expected
      WHEN us.event_category = 'promotion' THEN 12.0   -- ~12% promotion rate expected
      ELSE 0.0
    END AS expected_rate_pct,

    -- Quality assessment
    CASE
      WHEN us.event_category = 'hire' AND
           ABS(100.0 * us.positive_events / (us.positive_events + us.negative_events) - 15.0) < 3.0
      THEN 'GOOD ✅'
      WHEN us.event_category = 'termination' AND
           ABS(100.0 * us.positive_events / (us.positive_events + us.negative_events) - 10.0) < 3.0
      THEN 'GOOD ✅'
      WHEN us.event_category = 'promotion' AND
           ABS(100.0 * us.positive_events / (us.positive_events + us.negative_events) - 12.0) < 3.0
      THEN 'GOOD ✅'
      ELSE 'CHECK NEEDED ⚠️'
    END AS rate_quality_assessment

  FROM unified_summary us
)

SELECT
  us.event_category,
  us.event_count,
  us.unique_employees,
  us.earliest_date,
  us.latest_date,
  ROUND(us.avg_compensation, 0) AS avg_compensation,
  era.event_rate_pct,
  era.expected_rate_pct,
  era.rate_quality_assessment,
  ROUND(rqa.avg_rng_value, 4) AS avg_rng_value,
  rqa.rng_mean_quality,
  ROUND(rqa.rng_stddev, 4) AS rng_stddev,
  rqa.rng_stddev_quality,

  -- Overall quality score
  CASE
    WHEN rqa.rng_mean_quality = 'GOOD ✅' AND
         rqa.rng_stddev_quality = 'GOOD ✅' AND
         era.rate_quality_assessment = 'GOOD ✅'
    THEN 'EXCELLENT ✅'
    WHEN rqa.rng_mean_quality IN ('GOOD ✅', 'ACCEPTABLE ⚠️') AND
         rqa.rng_stddev_quality IN ('GOOD ✅', 'ACCEPTABLE ⚠️') AND
         era.rate_quality_assessment IN ('GOOD ✅', 'CHECK NEEDED ⚠️')
    THEN 'ACCEPTABLE ⚠️'
    ELSE 'NEEDS ATTENTION ❌'
  END AS overall_quality,

  -- Debug configuration info
  '{{ var("debug_event", "all") }}' AS debug_event_filter,
  {{ var('random_seed', 42) }} AS random_seed,
  {{ var('simulation_year') }} AS simulation_year,
  '{{ var("enable_dev_subset", false) }}' AS dev_subset_enabled,
  CURRENT_TIMESTAMP AS analysis_timestamp

FROM unified_summary us
LEFT JOIN rng_quality_analysis rqa ON us.event_category = rqa.event_category
LEFT JOIN event_rate_analysis era ON us.event_category = era.event_category
ORDER BY us.event_category

{% else %}

-- Placeholder when debug not enabled
SELECT
  NULL::VARCHAR AS event_category,
  NULL::INTEGER AS event_count,
  NULL::INTEGER AS unique_employees,
  NULL::DATE AS earliest_date,
  NULL::DATE AS latest_date,
  NULL::INTEGER AS avg_compensation,
  NULL::DOUBLE AS event_rate_pct,
  NULL::DOUBLE AS expected_rate_pct,
  NULL::VARCHAR AS rate_quality_assessment,
  NULL::DOUBLE AS avg_rng_value,
  NULL::VARCHAR AS rng_mean_quality,
  NULL::DOUBLE AS rng_stddev,
  NULL::VARCHAR AS rng_stddev_quality,
  NULL::VARCHAR AS overall_quality,
  NULL::VARCHAR AS debug_event_filter,
  NULL::INTEGER AS random_seed,
  NULL::INTEGER AS simulation_year,
  NULL::VARCHAR AS dev_subset_enabled,
  NULL::TIMESTAMP AS analysis_timestamp
WHERE 1=0

{% endif %}
