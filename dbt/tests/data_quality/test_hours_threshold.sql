{{
  config(
    severity='error',
    tags=['data_quality', 'erisa', 'eligibility']
  )
}}

/*
  Data Quality Test: 1,000-Hour Threshold Classification (FR-004)

  Validates boundary values for classify_service_hours macro:
  - 0 hours → 'no_credit'
  - 999 hours → 'no_credit'
  - 1000 hours → 'year_of_service'
  - 2080 hours → 'year_of_service'

  Returns failure rows only.
*/

WITH boundary_test_cases AS (
  -- Generate test cases with expected classifications
  SELECT 0.0 AS test_hours, 'no_credit' AS expected_classification, '0 hours' AS test_label
  UNION ALL
  SELECT 999.0, 'no_credit', '999 hours'
  UNION ALL
  SELECT 999.99, 'no_credit', '999.99 hours'
  UNION ALL
  SELECT 1000.0, 'year_of_service', '1000 hours'
  UNION ALL
  SELECT 1000.01, 'year_of_service', '1000.01 hours'
  UNION ALL
  SELECT 2080.0, 'year_of_service', '2080 hours'
),

-- Apply the macro to each test case
classification_results AS (
  SELECT
    tc.test_hours,
    tc.expected_classification,
    tc.test_label,
    {{ classify_service_hours('tc.test_hours') }} AS actual_classification
  FROM boundary_test_cases tc
)

SELECT
  test_label AS employee_id,
  test_hours,
  expected_classification,
  actual_classification,
  'Hours threshold mismatch: ' || test_label || ' classified as ' || actual_classification || ' but expected ' || expected_classification AS issue_description
FROM classification_results
WHERE actual_classification != expected_classification
