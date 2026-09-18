{{ config(severity='error', tags=['data_quality']) }}

{#
  Contributions must use the canonical workforce age for the same employee-year.
  Age selects IRS catch-up limits here and points-based match tiers downstream,
  so deriving it independently can change employee and employer contribution amounts.

  Returns one row per mismatch; the test passes when empty.
#}

SELECT
    workforce.scenario_id,
    contributions.employee_id,
    contributions.plan_design_id,
    contributions.simulation_year,
    contributions.current_age AS contribution_current_age,
    workforce.current_age AS workforce_current_age
FROM {{ ref('int_employee_contributions') }} contributions
INNER JOIN {{ ref('int_workforce_state_accumulator') }} workforce
    ON contributions.plan_design_id = workforce.plan_design_id
   AND contributions.employee_id = workforce.employee_id
   AND contributions.simulation_year = workforce.simulation_year
WHERE workforce.scenario_id = '{{ var('scenario_id', 'default') }}'
  AND contributions.current_age IS DISTINCT FROM workforce.current_age
