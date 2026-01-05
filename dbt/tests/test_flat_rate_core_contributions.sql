/*
  Test: Flat Rate Core Contributions (Regression Test)

  This test verifies that when employer_core_status is 'flat',
  all eligible employees receive the same flat rate regardless of tenure.

  Configuration:
    - employer_core_status: 'flat' (or not graded_by_service)
    - employer_core_contribution_rate: The flat rate to apply

  Expected: No rows returned (all employees have the same rate)
*/

WITH flat_rate_check AS (
    SELECT
        employee_id,
        core_contribution_rate,
        {{ var('employer_core_contribution_rate', 0.02) }} AS expected_flat_rate,
        ABS(core_contribution_rate - {{ var('employer_core_contribution_rate', 0.02) }}) AS rate_difference
    FROM {{ ref('int_employer_core_contributions') }}
    WHERE simulation_year = {{ var('simulation_year', 2025) }}
      AND eligible_for_core = TRUE
      AND employer_core_amount > 0
      -- Only run this test when NOT using graded_by_service
      AND '{{ var("employer_core_status", "flat") }}' != 'graded_by_service'
)

-- Return rows where the rate doesn't match the flat rate (test fails if any rows)
SELECT *
FROM flat_rate_check
WHERE rate_difference > 0.0001  -- Allow for floating point tolerance
