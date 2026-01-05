/*
  Test: Multi-Tier Core Contributions (4-Tier Schedule)

  This test verifies that complex service tier configurations (3+ tiers)
  work correctly with the graded_by_service feature.

  Configuration:
    - employer_core_status: 'graded_by_service'
    - employer_core_graded_schedule:
      - 0-2 years: 4%
      - 3-5 years: 5%
      - 6-10 years: 6%
      - 11+ years: 8%

  Test Cases:
    1. Employee with 1 year tenure should get 4% rate
    2. Employee with 4 years tenure should get 5% rate
    3. Employee with 8 years tenure should get 6% rate
    4. Employee with 15 years tenure should get 8% rate

  Expected: No rows returned (all assertions pass)
*/

WITH multi_tier_check AS (
    SELECT
        ec.employee_id,
        snap.years_of_service,
        ec.core_contribution_rate,
        -- Expected rate based on 4-tier schedule
        CASE
            WHEN COALESCE(snap.years_of_service, 0) >= 11 THEN 0.08
            WHEN COALESCE(snap.years_of_service, 0) >= 6 THEN 0.06
            WHEN COALESCE(snap.years_of_service, 0) >= 3 THEN 0.05
            ELSE 0.04
        END AS expected_rate,
        -- Calculate difference
        ABS(ec.core_contribution_rate -
            CASE
                WHEN COALESCE(snap.years_of_service, 0) >= 11 THEN 0.08
                WHEN COALESCE(snap.years_of_service, 0) >= 6 THEN 0.06
                WHEN COALESCE(snap.years_of_service, 0) >= 3 THEN 0.05
                ELSE 0.04
            END
        ) AS rate_difference
    FROM {{ ref('int_employer_core_contributions') }} ec
    INNER JOIN (
        SELECT
            employee_id,
            FLOOR(COALESCE(current_tenure, 0))::INT AS years_of_service
        FROM {{ ref('int_workforce_snapshot_optimized') }}
        WHERE simulation_year = {{ var('simulation_year', 2025) }}
    ) snap ON ec.employee_id = snap.employee_id
    WHERE ec.simulation_year = {{ var('simulation_year', 2025) }}
      AND ec.eligible_for_core = TRUE
      AND ec.employer_core_amount > 0
      -- Only run this test when graded_by_service with 4 tiers is configured
      AND '{{ var("employer_core_status", "flat") }}' = 'graded_by_service'
      AND {{ var("employer_core_graded_schedule", []) | length }} >= 4
)

-- Return rows where the rate doesn't match expected (test fails if any rows)
SELECT *
FROM multi_tier_check
WHERE rate_difference > 0.0001  -- Allow for floating point tolerance
