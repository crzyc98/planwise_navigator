{% macro match_family_arm_points_based() %}
SELECT
  ec.employee_id, ec.plan_design_id, ec.simulation_year,
  ec.eligible_compensation, ec.deferral_rate, ec.annual_deferrals,
  ec.years_of_service, lim.irs_401a17_limit,
  tier.match_rate * LEAST(ec.deferral_rate, tier.max_deferral_pct)
    * LEAST(ec.eligible_compensation, lim.irs_401a17_limit) AS match_amount,
  'points_based'::VARCHAR AS formula_type,
  'points_based'::VARCHAR AS formula_family,
  (FLOOR(ec.age_as_of_december_31)::INT + ec.years_of_service) AS applied_points,
  1::INTEGER AS resolution_count
FROM employee_contributions ec
CROSS JOIN irs_compensation_limits lim
INNER JOIN plan_design_parameters pdp
  ON pdp.plan_design_id = ec.plan_design_id
 AND pdp.match_formula_family = 'points_based'
INNER JOIN plan_design_match_tiers tier
  ON tier.plan_design_id = ec.plan_design_id
 AND tier.formula_family = 'points_based'
 AND (FLOOR(ec.age_as_of_december_31)::INT + ec.years_of_service)
     >= tier.band_min_value
 AND (tier.band_max_value IS NULL
      OR (FLOOR(ec.age_as_of_december_31)::INT + ec.years_of_service)
         < tier.band_max_value)
{% endmacro %}
