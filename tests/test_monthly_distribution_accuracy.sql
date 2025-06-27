-- Test: Monthly distribution accuracy for realistic timing mode
-- Validates that actual raise timing distribution matches configured percentages within tolerance
-- Expected: All monthly variances within ±2% tolerance

{{ config(severity='error') }}

WITH actual_distribution AS (
  SELECT
    EXTRACT(month FROM effective_date) as month,
    COUNT(*) as raise_count,
    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as actual_percentage
  FROM {{ ref('fct_yearly_events') }}
  WHERE event_type = 'RAISE'
    AND simulation_year = {{ var('simulation_year') }}
    -- Only test when realistic timing is enabled
    AND {{ var('raise_timing_methodology', 'legacy') }} = 'realistic'
  GROUP BY month
),
expected_distribution AS (
  SELECT
    month,
    percentage * 100 as expected_percentage
  FROM {{ ref('config_raise_timing_distribution') }}
  WHERE industry_profile = '{{ var("raise_timing_profile", "general_corporate") }}'
),
variance_analysis AS (
  SELECT
    a.month,
    a.actual_percentage,
    e.expected_percentage,
    ABS(a.actual_percentage - e.expected_percentage) as variance,
    {{ var('timing_tolerance', 2.0) }} as tolerance_threshold
  FROM actual_distribution a
  JOIN expected_distribution e ON a.month = e.month
)
SELECT
  month,
  actual_percentage,
  expected_percentage,
  variance,
  tolerance_threshold,
  'DISTRIBUTION_VARIANCE_EXCEEDS_TOLERANCE' as error_type
FROM variance_analysis
WHERE variance > tolerance_threshold
