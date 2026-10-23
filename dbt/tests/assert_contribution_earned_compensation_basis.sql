{{ config(severity='error', tags=['contribution', 'data_quality']) }}

-- Contributions are scenario-local; scenario_id exists only on the snapshot.
-- Match consumes this same earned-pay base, with Feature 101 windowing retained.
SELECT
  snapshot.employee_id,
  snapshot.scenario_id,
  snapshot.plan_design_id,
  snapshot.simulation_year
FROM {{ ref('fct_workforce_snapshot') }} snapshot
LEFT JOIN {{ ref('int_employee_contributions') }} contributions
  ON snapshot.employee_id = contributions.employee_id
  AND snapshot.plan_design_id = contributions.plan_design_id
  AND snapshot.simulation_year = contributions.simulation_year
WHERE snapshot.simulation_year = {{ var('simulation_year', 2025) }}
  AND snapshot.scenario_id = '{{ var("scenario_id", "default") }}'
  AND (
    contributions.employee_id IS NULL
    OR snapshot.prorated_annual_compensation IS NULL
    OR contributions.prorated_annual_compensation IS NULL
    OR contributions.total_contribution_base_compensation IS NULL
    OR ABS(contributions.prorated_annual_compensation
      - snapshot.prorated_annual_compensation) > 0.01
    OR (
      contributions.contribution_window_category IS DISTINCT FROM 'enroll_optout_window'
      AND ABS(contributions.total_contribution_base_compensation
        - contributions.prorated_annual_compensation) > 0.01
    )
  )
