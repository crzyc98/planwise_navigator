/*
  Test: Service Tier Core Contributions (2-Tier Schedule)

  This test verifies that employees receive different core contribution rates
  based on their years of service when graded_by_service is configured.

  Configuration:
    - employer_core_status: 'graded_by_service'
    - employer_core_graded_schedule:
      - 0-9 years: 6%
      - 10+ years: 8%

  Test Cases:
    1. Employee with 5 years tenure should get 6% rate (0.06)
    2. Employee with 15 years tenure should get 8% rate (0.08)
    3. Employee with exactly 10 years tenure should get 8% rate (0.08)

  Expected: No rows returned (all assertions pass)
*/

WITH service_tier_check AS (
    SELECT
        ec.employee_id,
        snap.years_of_service,
        ec.core_contribution_rate,
        -- Expected rate based on years of service
        CASE
            WHEN COALESCE(snap.years_of_service, 0) >= 10 THEN 0.08
            ELSE 0.06
        END AS expected_rate,
        -- Calculate difference
        ABS(ec.core_contribution_rate -
            CASE
                WHEN COALESCE(snap.years_of_service, 0) >= 10 THEN 0.08
                ELSE 0.06
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
      -- Only run this test when graded_by_service is configured
      AND '{{ var("employer_core_status", "flat") }}' = 'graded_by_service'
)

-- Return rows where the rate doesn't match expected (test fails if any rows)
SELECT *
FROM service_tier_check
WHERE rate_difference > 0.0001  -- Allow for floating point tolerance
