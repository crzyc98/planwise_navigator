-- Second-net check for the published match-calculation grain and eligible coverage.
-- The model's pre-publication guard owns detailed family/band diagnostics; this
-- assertion protects against a future refactor bypassing that guard.
WITH eligible AS (
  SELECT
    contributions.employee_id,
    contributions.plan_design_id,
    contributions.simulation_year
  FROM {{ ref('int_employee_contributions') }} contributions
  INNER JOIN {{ ref('int_employer_eligibility') }} eligibility
    ON eligibility.employee_id = contributions.employee_id
   AND eligibility.plan_design_id = contributions.plan_design_id
   AND eligibility.simulation_year = contributions.simulation_year
   AND eligibility.scenario_id = '{{ var("scenario_id", "default") }}'
  WHERE contributions.simulation_year = {{ var('simulation_year') }}
    AND eligibility.eligible_for_match
),
published AS (
  SELECT
    employee_id,
    plan_design_id,
    simulation_year,
    COUNT(*) AS row_count
  FROM {{ ref('int_employee_match_calculations') }}
  WHERE simulation_year = {{ var('simulation_year') }}
  GROUP BY employee_id, plan_design_id, simulation_year
),
violations AS (
  SELECT
    eligible.employee_id,
    eligible.plan_design_id,
    eligible.simulation_year,
    COALESCE(published.row_count, 0) AS row_count
  FROM eligible
  LEFT JOIN published
    USING (employee_id, plan_design_id, simulation_year)
  WHERE COALESCE(published.row_count, 0) <> 1

  UNION ALL

  SELECT employee_id, plan_design_id, simulation_year, row_count
  FROM published
  WHERE row_count <> 1
)
SELECT * FROM violations
