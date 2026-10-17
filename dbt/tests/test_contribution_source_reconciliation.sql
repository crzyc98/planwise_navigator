-- Only supported allocations reconcile. A blocked allocation must expose no sources.
SELECT scenario_id, plan_design_id, employee_id, simulation_year
FROM {{ ref('fct_workforce_snapshot') }}
WHERE simulation_year = {{ var('simulation_year') }}
  AND (
    (mandatory_roth_status NOT IN ('blocked_no_roth', 'ineligible_catch_up', 'exceeds_modeled_limit')
      AND (pre_tax_contributions IS NULL OR roth_contributions IS NULL
        OR pre_tax_contributions + roth_contributions != ROUND(ytd_contributions, 2)))
    OR (mandatory_roth_status IN ('blocked_no_roth', 'ineligible_catch_up', 'exceeds_modeled_limit')
      AND (pre_tax_contributions IS NOT NULL OR roth_contributions IS NOT NULL))
    OR (mandatory_roth_status IN ('required', 'required_under_assumptions')
      AND (mandatory_roth_required IS NULL OR roth_contributions < mandatory_roth_required))
    OR pre_tax_contributions < 0 OR roth_contributions < 0
  )
