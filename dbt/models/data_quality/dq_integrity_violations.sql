{{ config(
    materialized='table',
    tags=['data_quality', 'monitoring'],
    enabled=false
) }}

/*
  DEPRECATED: This model has been converted to a dbt test.
  Use: dbt test --select test_integrity_violations

  This model is kept for backward compatibility with dependent models.
  It now simply references the test to maintain the same interface.

  To migrate:
  1. Update dependent models to use dbt tests instead
  2. Remove this model once all dependencies are updated
*/

-- Return empty result set to satisfy dependencies
-- Actual validation is now performed by dbt test: test_integrity_violations
SELECT
    'deprecated' as check_name,
    0 as violation_count,
    CURRENT_TIMESTAMP as check_timestamp,
    'INFO' as severity,
    'This model has been deprecated. Use dbt test --select test_integrity_violations' as description
WHERE 1 = 0  -- Always return empty result
