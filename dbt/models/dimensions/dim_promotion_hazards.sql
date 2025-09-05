{{ config(
  materialized='table',
  tags=['HAZARD_CACHE']
) }}

-- Cached promotion hazards dimension table
-- Pre-computed promotion probabilities by level, tenure, age, and department
-- Rebuilt only when hazard parameters change to optimize performance

WITH promotion_base_parameters AS (
  SELECT
    base_rate,
    level_dampener_factor
  FROM {{ ref('stg_config_promotion_hazard_base') }}
),

promotion_multipliers AS (
  SELECT
    tm.tenure_band,
    tm.multiplier AS tenure_multiplier,
    am.age_band,
    am.multiplier AS age_multiplier
  FROM {{ ref('stg_config_promotion_hazard_tenure_multipliers') }} tm
  CROSS JOIN {{ ref('stg_config_promotion_hazard_age_multipliers') }} am
),

job_levels AS (
  SELECT level_id
  FROM {{ ref('stg_config_job_levels') }}
),

-- Load effective parameters for promotion rates by level if available
effective_params AS (
  SELECT
    job_level,
    parameter_value AS level_adjustment
  FROM {{ ref('int_effective_parameters') }}
  WHERE event_type = 'promotion'
    AND parameter_name = 'level_adjustment'
    AND fiscal_year = {{ var('simulation_year', 2025) }}
),

hazard_calculations AS (
  SELECT
    jl.level_id,
    pm.tenure_band,
    pm.age_band,
    -- Add department dimension (placeholder for future enhancement)
    'ALL' AS department,
    -- Add performance tier dimension (placeholder for future enhancement)
    'STANDARD' AS performance_tier,

    -- Calculate base promotion probability using existing logic
    pb.base_rate *
    pm.tenure_multiplier *
    pm.age_multiplier *
    GREATEST(0, 1 - pb.level_dampener_factor * (jl.level_id - 1)) *
    COALESCE(ep.level_adjustment, 1.0) AS base_promotion_probability,

    -- Apply ceiling to ensure probability doesn't exceed 1.0
    LEAST(1.0,
      pb.base_rate *
      pm.tenure_multiplier *
      pm.age_multiplier *
      GREATEST(0, 1 - pb.level_dampener_factor * (jl.level_id - 1)) *
      COALESCE(ep.level_adjustment, 1.0)
    ) AS promotion_probability,

    -- Additional hazard metrics for analytical purposes
    CASE
      WHEN pb.base_rate * pm.tenure_multiplier * pm.age_multiplier *
           GREATEST(0, 1 - pb.level_dampener_factor * (jl.level_id - 1)) > 0
      THEN 1.0 / (pb.base_rate * pm.tenure_multiplier * pm.age_multiplier *
                  GREATEST(0, 1 - pb.level_dampener_factor * (jl.level_id - 1)))
      ELSE NULL
    END AS expected_months_to_promotion,

    -- Confidence intervals (simplified implementation)
    LEAST(1.0,
      GREATEST(0,
        pb.base_rate * pm.tenure_multiplier * pm.age_multiplier *
        GREATEST(0, 1 - pb.level_dampener_factor * (jl.level_id - 1)) * 0.8
      )
    ) AS confidence_interval_lower,

    LEAST(1.0,
      pb.base_rate * pm.tenure_multiplier * pm.age_multiplier *
      GREATEST(0, 1 - pb.level_dampener_factor * (jl.level_id - 1)) * 1.2
    ) AS confidence_interval_upper

  FROM job_levels jl
  CROSS JOIN promotion_multipliers pm
  CROSS JOIN promotion_base_parameters pb
  LEFT JOIN effective_params ep ON ep.job_level = jl.level_id
)

SELECT
  level_id,
  tenure_band,
  age_band,
  department,
  performance_tier,
  promotion_probability,
  expected_months_to_promotion,
  confidence_interval_lower,
  confidence_interval_upper,

  -- Audit fields
  CURRENT_TIMESTAMP AS cache_built_at,
  '{{ var("hazard_params_hash", "default") }}' AS params_hash

FROM hazard_calculations
ORDER BY level_id, tenure_band, age_band
