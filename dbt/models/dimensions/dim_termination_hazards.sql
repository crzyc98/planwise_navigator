{{ config(
  materialized='table',
  tags=['HAZARD_CACHE']
) }}

-- Cached termination hazards dimension table
-- Pre-computed turnover rates with hazard ratios and survival probabilities
-- Rebuilt only when hazard parameters change to optimize performance

WITH termination_base_parameters AS (
  SELECT
    base_rate_for_new_hire AS base_termination_rate
  FROM {{ ref('stg_config_termination_hazard_base') }}
),

termination_multipliers AS (
  SELECT
    tm.tenure_band,
    tm.multiplier AS tenure_adjustment,
    am.age_band,
    am.multiplier AS age_adjustment
  FROM {{ ref('stg_config_termination_hazard_tenure_multipliers') }} tm
  CROSS JOIN {{ ref('stg_config_termination_hazard_age_multipliers') }} am
),

job_levels AS (
  SELECT level_id
  FROM {{ ref('stg_config_job_levels') }}
),

-- Load effective parameters for termination rates by level if available
effective_params AS (
  SELECT
    job_level,
    parameter_value AS level_adjustment
  FROM {{ ref('int_effective_parameters') }}
  WHERE event_type = 'termination'
    AND parameter_name = 'level_adjustment'
    AND fiscal_year = {{ var('simulation_year', 2025) }}
),

-- Add economic and seasonal factors (placeholder for future enhancement)
economic_factors AS (
  SELECT
    1.0 AS economic_factor,  -- Neutral baseline
    1.0 AS seasonal_adjustment  -- Neutral baseline
),

hazard_calculations AS (
  SELECT
    jl.level_id,
    tm.tenure_band,
    tm.age_band,
    -- Add department dimension (placeholder for future enhancement)
    'ALL' AS department,
    -- Add performance tier dimension (placeholder for future enhancement)
    'STANDARD' AS performance_tier,

    -- Calculate base termination probability using existing logic
    tb.base_termination_rate *
    tm.tenure_adjustment *
    tm.age_adjustment *
    ef.economic_factor *
    ef.seasonal_adjustment *
    COALESCE(ep.level_adjustment, 1.0) AS base_termination_probability,

    -- Apply ceiling to ensure probability doesn't exceed 1.0
    LEAST(1.0,
      tb.base_termination_rate *
      tm.tenure_adjustment *
      tm.age_adjustment *
      ef.economic_factor *
      ef.seasonal_adjustment *
      COALESCE(ep.level_adjustment, 1.0)
    ) AS termination_probability,

    -- Expected tenure in months (inverse of monthly termination rate)
    CASE
      WHEN tb.base_termination_rate * tm.tenure_adjustment * tm.age_adjustment *
           ef.economic_factor * ef.seasonal_adjustment > 0
      THEN 1.0 / (tb.base_termination_rate * tm.tenure_adjustment * tm.age_adjustment *
                  ef.economic_factor * ef.seasonal_adjustment)
      ELSE NULL
    END AS expected_tenure_months,

    -- Hazard ratio (relative to baseline new hire rate)
    CASE
      WHEN tb.base_termination_rate > 0
      THEN (tb.base_termination_rate * tm.tenure_adjustment * tm.age_adjustment *
            ef.economic_factor * ef.seasonal_adjustment) / tb.base_termination_rate
      ELSE 1.0
    END AS hazard_ratio,

    -- 12-month survival probability
    POWER(
      1.0 - LEAST(1.0,
        tb.base_termination_rate *
        tm.tenure_adjustment *
        tm.age_adjustment *
        ef.economic_factor *
        ef.seasonal_adjustment *
        COALESCE(ep.level_adjustment, 1.0)
      ),
      12
    ) AS survival_probability_12mo

  FROM job_levels jl
  CROSS JOIN termination_multipliers tm
  CROSS JOIN termination_base_parameters tb
  CROSS JOIN economic_factors ef
  LEFT JOIN effective_params ep ON ep.job_level = jl.level_id
)

SELECT
  level_id,
  tenure_band,
  age_band,
  department,
  performance_tier,
  termination_probability,
  expected_tenure_months,
  hazard_ratio,
  survival_probability_12mo,

  -- Audit fields
  CURRENT_TIMESTAMP AS cache_built_at,
  '{{ var("hazard_params_hash", "default") }}' AS params_hash

FROM hazard_calculations
ORDER BY level_id, tenure_band, age_band
