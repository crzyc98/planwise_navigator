{{ config(severity='error', tags=['core_contributions']) }}

-- Actual earned compensation is the common basis for base and integrated core.
SELECT
  snapshot.employee_id,
  snapshot.scenario_id,
  snapshot.plan_design_id,
  snapshot.simulation_year
FROM {{ ref('fct_workforce_snapshot') }} snapshot
LEFT JOIN {{ ref('int_employer_core_contributions') }} core
  ON snapshot.employee_id = core.employee_id
  AND snapshot.scenario_id = core.scenario_id
  AND snapshot.plan_design_id = core.plan_design_id
  AND snapshot.simulation_year = core.simulation_year
LEFT JOIN {{ ref('config_irs_limits') }} limits
  ON snapshot.simulation_year = limits.limit_year
WHERE snapshot.simulation_year = {{ var('simulation_year', 2025) }}
  AND snapshot.scenario_id = '{{ var("scenario_id", "default") }}'
  AND (
    snapshot.employer_core_amount > 0
    OR core.core_contribution_rate > 0
    OR core.employer_core_amount > 0
  )
  AND (
    core.employee_id IS NULL
    OR limits.compensation_limit IS NULL
    OR snapshot.prorated_annual_compensation IS NULL
    OR core.base_core_amount IS NULL
    OR core.disparity_core_amount IS NULL
    OR core.employer_core_amount IS NULL
    OR snapshot.employer_core_amount IS NULL
    OR ABS(core.base_core_amount - ROUND(
      LEAST(snapshot.prorated_annual_compensation, limits.compensation_limit)
        * core.core_contribution_rate, 2
    )) > 0.01
    OR ABS(core.employer_core_amount
      - core.base_core_amount - core.disparity_core_amount) > 0.01
    OR ABS(snapshot.employer_core_amount - core.employer_core_amount) > 0.01
  )
