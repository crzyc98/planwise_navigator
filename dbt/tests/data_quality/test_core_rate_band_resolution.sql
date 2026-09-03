-- Second-net check for core output grain and absence of unresolved eligible rates.
-- Detailed gap, overlap, fallback, and schedule diagnostics remain in the model's
-- pre-dedup guard so invalid rows cannot be published for this test to normalize.
WITH published AS (
  SELECT
    employee_id,
    plan_design_id,
    simulation_year,
    COUNT(*) AS row_count,
    COUNT(*) FILTER (
      WHERE eligible_for_core AND core_contribution_rate IS NULL
    ) AS unresolved_count,
    -- Ineligible employees must receive nothing, including permitted-disparity
    -- amounts: integration is gated on a resolved non-zero core rate.
    COUNT(*) FILTER (
      WHERE NOT COALESCE(eligible_for_core, FALSE)
        AND (
          COALESCE(employer_core_amount, 0) <> 0
          OR COALESCE(disparity_core_amount, 0) <> 0
        )
    ) AS ineligible_paid_count
  FROM {{ ref('int_employer_core_contributions') }}
  WHERE simulation_year = {{ var('simulation_year') }}
  GROUP BY employee_id, plan_design_id, simulation_year
)
SELECT
  employee_id,
  plan_design_id,
  simulation_year,
  row_count,
  unresolved_count,
  ineligible_paid_count
FROM published
WHERE row_count <> 1 OR unresolved_count <> 0 OR ineligible_paid_count <> 0
