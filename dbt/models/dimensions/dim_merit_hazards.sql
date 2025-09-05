{{ config(
  materialized='table',
  tags=['HAZARD_CACHE']
) }}

-- Cached merit hazards dimension table
-- Pre-computed merit increase probabilities and amounts by level and department
-- Rebuilt only when hazard parameters change to optimize performance

WITH job_levels AS (
  SELECT level_id
  FROM {{ ref('stg_config_job_levels') }}
),

-- Load effective parameters for merit rates by level
merit_base_params AS (
  SELECT
    job_level,
    parameter_value AS merit_base_rate
  FROM {{ ref('int_effective_parameters') }}
  WHERE event_type = 'raise'
    AND parameter_name = 'merit_base'
    AND fiscal_year = {{ var('simulation_year', 2025) }}
),

-- Load merit multipliers from configuration if they exist
merit_multipliers AS (
  SELECT
    level_id,
    -- Default multipliers by level (can be enhanced with more sophisticated logic)
    CASE
      WHEN level_id <= 2 THEN 1.0   -- Entry level
      WHEN level_id <= 4 THEN 1.1   -- Mid level
      WHEN level_id <= 6 THEN 1.2   -- Senior level
      ELSE 1.3                      -- Executive level
    END AS level_multiplier,

    -- Performance tier adjustments (placeholder for future enhancement)
    1.0 AS performance_multiplier,

    -- Department adjustments (placeholder for future enhancement)
    1.0 AS department_multiplier
  FROM {{ ref('stg_config_job_levels') }}
),

-- Additional dimensions for future expansion
dimension_combinations AS (
  SELECT
    jl.level_id,
    'ALL' AS department,  -- Placeholder for future department-specific logic
    'STANDARD' AS performance_tier  -- Placeholder for performance-based differentiation
  FROM job_levels jl
),

hazard_calculations AS (
  SELECT
    dc.level_id,
    dc.department,
    dc.performance_tier,

    -- Base merit rate from parameters
    COALESCE(mbp.merit_base_rate, 0.03) AS base_merit_rate,  -- Default 3%

    -- Calculate merit probability (likelihood of receiving merit increase)
    -- This is a simplified model - can be enhanced with tenure, performance factors
    LEAST(1.0,
      CASE
        WHEN dc.level_id <= 2 THEN 0.70  -- 70% for entry level
        WHEN dc.level_id <= 4 THEN 0.80  -- 80% for mid level
        WHEN dc.level_id <= 6 THEN 0.85  -- 85% for senior level
        ELSE 0.90                        -- 90% for executive level
      END
    ) AS merit_probability,

    -- Calculate expected merit increase percentage
    COALESCE(mbp.merit_base_rate, 0.03) *
    mm.level_multiplier *
    mm.performance_multiplier *
    mm.department_multiplier AS expected_merit_increase,

    -- Merit amount distribution parameters
    COALESCE(mbp.merit_base_rate, 0.03) *
    mm.level_multiplier * 0.5 AS merit_min_increase,  -- 50% of expected

    COALESCE(mbp.merit_base_rate, 0.03) *
    mm.level_multiplier * 1.5 AS merit_max_increase,  -- 150% of expected

    -- Standard deviation for merit distribution
    COALESCE(mbp.merit_base_rate, 0.03) *
    mm.level_multiplier * 0.3 AS merit_std_dev  -- 30% of expected

  FROM dimension_combinations dc
  LEFT JOIN merit_base_params mbp ON mbp.job_level = dc.level_id
  LEFT JOIN merit_multipliers mm ON mm.level_id = dc.level_id
)

SELECT
  level_id,
  department,
  performance_tier,
  merit_probability,
  expected_merit_increase,
  merit_min_increase,
  merit_max_increase,
  merit_std_dev,

  -- Additional metrics for analytics
  CASE
    WHEN merit_probability > 0
    THEN 1.0 / merit_probability  -- Expected years between merit increases
    ELSE NULL
  END AS expected_years_between_merits,

  -- Audit fields
  CURRENT_TIMESTAMP AS cache_built_at,
  '{{ var("hazard_params_hash", "default") }}' AS params_hash

FROM hazard_calculations
ORDER BY level_id, department, performance_tier
