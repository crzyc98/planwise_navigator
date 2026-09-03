{% macro match_family_arm_tenure_graded() %}
SELECT
  ec.employee_id, ec.plan_design_id, ec.simulation_year,
  ec.eligible_compensation, ec.deferral_rate, ec.annual_deferrals,
  ec.years_of_service, lim.irs_401a17_limit,
  SUM(CASE WHEN ec.deferral_rate > tier.employee_min
      THEN LEAST(ec.deferral_rate - tier.employee_min,
                 tier.employee_max - tier.employee_min)
           * tier.match_rate
           * LEAST(ec.eligible_compensation, lim.irs_401a17_limit)
      ELSE 0 END) AS match_amount,
  'tenure_graded'::VARCHAR AS formula_type,
  'tenure_graded'::VARCHAR AS formula_family,
  NULL::INT AS applied_points,
  COUNT(DISTINCT (tier.band_min_value, tier.band_max_value))::INTEGER
    AS resolution_count
FROM employee_contributions ec
CROSS JOIN irs_compensation_limits lim
INNER JOIN plan_design_parameters pdp
  ON pdp.plan_design_id = ec.plan_design_id
 AND pdp.match_formula_family = 'tenure_graded'
INNER JOIN plan_design_match_tiers tier
  ON tier.plan_design_id = ec.plan_design_id
 AND tier.formula_family = 'tenure_graded'
 AND ec.years_of_service >= tier.band_min_value
 AND (tier.band_max_value IS NULL OR ec.years_of_service < tier.band_max_value)
GROUP BY ec.employee_id, ec.plan_design_id, ec.simulation_year,
         ec.eligible_compensation, ec.deferral_rate, ec.annual_deferrals,
         ec.years_of_service, lim.irs_401a17_limit
{% endmacro %}
