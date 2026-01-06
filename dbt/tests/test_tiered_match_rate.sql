/*
  Test: Service-Based Match Rate Macro (get_tiered_match_rate)

  This test verifies that the get_tiered_match_rate and get_tiered_match_max_deferral
  macros correctly compute rates based on years of service.

  Configuration tested:
    - employer_match_status: 'graded_by_service'
    - employer_match_graded_schedule:
      - 0-5 years: 50% rate, 6% max deferral
      - 5+ years: 100% rate, 6% max deferral

  Test Cases:
    1. Employee with 0 years tenure should get 50% rate (0.50)
    2. Employee with 4 years tenure should get 50% rate (0.50)
    3. Employee with 5 years tenure should get 100% rate (1.00) - boundary test
    4. Employee with 10 years tenure should get 100% rate (1.00)
    5. All tiers should return 6% max deferral (0.06)

  Expected: No rows returned (all assertions pass)

  Feature: E010 - Service-Based Match Contribution Tiers
*/

{% set test_schedule = [
    {'min_years': 0, 'max_years': 5, 'rate': 50, 'max_deferral_pct': 6},
    {'min_years': 5, 'max_years': none, 'rate': 100, 'max_deferral_pct': 6}
] %}

WITH test_cases AS (
    -- Generate test cases with known years of service
    SELECT 0 AS years_of_service, 0.50 AS expected_rate, 0.06 AS expected_max_deferral, '0 years - tier 1' AS test_name
    UNION ALL
    SELECT 1, 0.50, 0.06, '1 year - tier 1'
    UNION ALL
    SELECT 4, 0.50, 0.06, '4 years - tier 1 (boundary-1)'
    UNION ALL
    SELECT 5, 1.00, 0.06, '5 years - tier 2 (boundary, inclusive)'
    UNION ALL
    SELECT 6, 1.00, 0.06, '6 years - tier 2'
    UNION ALL
    SELECT 10, 1.00, 0.06, '10 years - tier 2'
    UNION ALL
    SELECT 20, 1.00, 0.06, '20 years - tier 2'
),

macro_results AS (
    SELECT
        tc.years_of_service,
        tc.expected_rate,
        tc.expected_max_deferral,
        tc.test_name,
        -- Invoke the macros with the test schedule
        {{ get_tiered_match_rate('tc.years_of_service', test_schedule, 0.50) }} AS actual_rate,
        {{ get_tiered_match_max_deferral('tc.years_of_service', test_schedule, 0.06) }} AS actual_max_deferral
    FROM test_cases tc
),

assertions AS (
    SELECT
        test_name,
        years_of_service,
        expected_rate,
        actual_rate,
        expected_max_deferral,
        actual_max_deferral,
        ABS(actual_rate - expected_rate) AS rate_diff,
        ABS(actual_max_deferral - expected_max_deferral) AS deferral_diff
    FROM macro_results
)

-- Return rows where macro output doesn't match expected (test fails if any rows)
SELECT *
FROM assertions
WHERE rate_diff > 0.0001  -- Floating point tolerance
   OR deferral_diff > 0.0001
