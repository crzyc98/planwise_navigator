{{ config(
  materialized='table',
  tags=['HAZARD_CACHE']
) }}

-- Cached enrollment hazards dimension table
-- Pre-computed DC plan enrollment probabilities by age, income, and tenure
-- Rebuilt only when hazard parameters change to optimize performance

WITH job_levels AS (
  SELECT level_id
  FROM {{ ref('stg_config_job_levels') }}
),

-- Load default deferral rates which drive enrollment probabilities
deferral_rates AS (
  SELECT
    age_segment,
    income_segment,
    default_rate,
    auto_escalate,
    auto_escalate_rate,
    max_rate
  FROM {{ ref('default_deferral_rates') }}
  WHERE scenario_id = '{{ var("scenario_id", "default") }}'
),

-- Load effective parameters for enrollment rates if available
enrollment_params AS (
  SELECT
    job_level,
    parameter_value AS enrollment_adjustment
  FROM {{ ref('int_effective_parameters') }}
  WHERE event_type = 'enrollment'
    AND parameter_name = 'enrollment_adjustment'
    AND fiscal_year = {{ var('simulation_year', 2025) }}
),

-- Create tenure bands for enrollment analysis
tenure_bands AS (
  SELECT DISTINCT tenure_band
  FROM {{ ref('stg_config_termination_hazard_tenure_multipliers') }}
),

-- Create comprehensive enrollment hazard matrix
hazard_calculations AS (
  SELECT
    jl.level_id,
    tb.tenure_band,
    dr.age_segment,
    dr.income_segment,

    -- Base enrollment probability logic
    -- Higher deferral rates correlate with higher enrollment likelihood
    LEAST(1.0,
      CASE
        -- New hires have lower initial enrollment (opt-in burden)
        WHEN tb.tenure_band = '0-1' THEN dr.default_rate * 2.0
        -- Tenured employees more likely to participate
        WHEN tb.tenure_band IN ('1-3', '3-5') THEN dr.default_rate * 3.0
        -- Long tenure employees very likely enrolled
        ELSE dr.default_rate * 4.0
      END * COALESCE(ep.enrollment_adjustment, 1.0)
    ) AS enrollment_probability,

    -- Auto-enrollment eligibility probability
    CASE
      WHEN tb.tenure_band = '0-1' THEN 0.95  -- Most new hires eligible
      WHEN tb.tenure_band IN ('1-3', '3-5') THEN 0.80  -- Some already enrolled
      ELSE 0.30  -- Long tenure likely already enrolled
    END AS auto_enrollment_eligibility_probability,

    -- Voluntary enrollment probability (for non-auto-enrolled)
    LEAST(1.0,
      CASE
        WHEN dr.income_segment = 'executive' THEN 0.70
        WHEN dr.income_segment = 'high' THEN 0.55
        WHEN dr.income_segment = 'moderate' THEN 0.35
        ELSE 0.20  -- low_income
      END *
      CASE
        WHEN dr.age_segment = 'senior' THEN 1.3
        WHEN dr.age_segment = 'mature' THEN 1.2
        WHEN dr.age_segment = 'mid_career' THEN 1.0
        ELSE 0.8  -- young
      END
    ) AS voluntary_enrollment_probability,

    -- Expected deferral rate upon enrollment
    dr.default_rate AS expected_initial_deferral_rate,

    -- Auto-escalation characteristics
    dr.auto_escalate AS has_auto_escalation,
    COALESCE(dr.auto_escalate_rate, 0.0) AS auto_escalation_rate,
    dr.max_rate AS maximum_deferral_rate,

    -- Expected months to enrollment for eligible non-enrolled employees
    CASE
      WHEN dr.default_rate > 0 AND tb.tenure_band != '0-1'
      THEN 12.0 / (dr.default_rate * 2.0)  -- Simplified model
      ELSE 24.0  -- Longer for new hires
    END AS expected_months_to_voluntary_enrollment

  FROM job_levels jl
  CROSS JOIN tenure_bands tb
  CROSS JOIN deferral_rates dr
  LEFT JOIN enrollment_params ep ON ep.job_level = jl.level_id
)

SELECT
  level_id,
  tenure_band,
  age_segment,
  income_segment,
  enrollment_probability,
  auto_enrollment_eligibility_probability,
  voluntary_enrollment_probability,
  expected_initial_deferral_rate,
  has_auto_escalation,
  auto_escalation_rate,
  maximum_deferral_rate,
  expected_months_to_voluntary_enrollment,

  -- Composite metrics for analysis
  enrollment_probability * auto_enrollment_eligibility_probability AS auto_enrollment_net_probability,
  enrollment_probability * (1.0 - auto_enrollment_eligibility_probability) * voluntary_enrollment_probability AS voluntary_enrollment_net_probability,

  -- Audit fields
  CURRENT_TIMESTAMP AS cache_built_at,
  '{{ var("hazard_params_hash", "default") }}' AS params_hash

FROM hazard_calculations
ORDER BY level_id, tenure_band, age_segment, income_segment
