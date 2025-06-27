-- Test: Configuration parameter validation
-- Validates that timing distribution configuration is valid
-- Expected: Distribution percentages sum to 1.0, all values within valid ranges

{{ config(severity='error') }}

WITH distribution_validation AS (
  SELECT
    SUM(percentage) as total_percentage,
    COUNT(*) as month_count,
    MIN(percentage) as min_percentage,
    MAX(percentage) as max_percentage,
    industry_profile
  FROM {{ ref('config_raise_timing_distribution') }}
  WHERE industry_profile = '{{ var("raise_timing_profile", "general_corporate") }}'
  GROUP BY industry_profile
),
validation_rules AS (
  SELECT
    rule_name,
    target_value,
    tolerance,
    enforcement_level
  FROM {{ ref('config_timing_validation_rules') }}
),
validation_checks AS (
  SELECT
    d.industry_profile,
    d.total_percentage,
    d.month_count,
    d.min_percentage,
    d.max_percentage,
    CASE
      WHEN ABS(d.total_percentage - 1.0) > (SELECT tolerance FROM validation_rules WHERE rule_name = 'monthly_distribution_sum')
      THEN 'DISTRIBUTION_SUM_INVALID'
      WHEN d.month_count != 12
      THEN 'MONTH_COUNT_INVALID'
      WHEN d.min_percentage < (SELECT target_value FROM validation_rules WHERE rule_name = 'minimum_month_percentage')
      THEN 'MINIMUM_PERCENTAGE_INVALID'
      WHEN d.max_percentage > (SELECT target_value FROM validation_rules WHERE rule_name = 'maximum_month_percentage')
      THEN 'MAXIMUM_PERCENTAGE_INVALID'
      ELSE 'VALID'
    END as validation_status
  FROM distribution_validation d
)
SELECT
  industry_profile,
  total_percentage,
  month_count,
  min_percentage,
  max_percentage,
  validation_status as error_type
FROM validation_checks
WHERE validation_status != 'VALID'
