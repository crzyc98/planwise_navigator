{% macro match_family_arm_graded_by_service() %}
SELECT
  ec.employee_id, ec.plan_design_id, ec.simulation_year,
  ec.eligible_compensation, ec.deferral_rate, ec.annual_deferrals,
  ec.years_of_service, lim.irs_401a17_limit,
  tier.match_rate * LEAST(ec.deferral_rate, tier.max_deferral_pct)
    * LEAST(ec.eligible_compensation, lim.irs_401a17_limit) AS match_amount,
  'graded_by_service'::VARCHAR AS formula_type,
  'graded_by_service'::VARCHAR AS formula_family,
  NULL::INT AS applied_points,
  1::INTEGER AS resolution_count
FROM employee_contributions ec
CROSS JOIN irs_compensation_limits lim
INNER JOIN plan_design_parameters pdp
  ON pdp.plan_design_id = ec.plan_design_id
 AND pdp.match_formula_family = 'graded_by_service'
INNER JOIN plan_design_match_tiers tier
  ON tier.plan_design_id = ec.plan_design_id
 AND tier.formula_family = 'graded_by_service'
 AND ec.years_of_service >= tier.band_min_value
 AND (tier.band_max_value IS NULL OR ec.years_of_service < tier.band_max_value)
{% endmacro %}
