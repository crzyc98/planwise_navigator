{% set sample = {
  'current': {
    'match': {'cap_percent': 0.03, 'tiers': [
      {'employee_min': 0.0, 'employee_max': 0.06, 'match_rate': 0.5}
    ]},
    'employer_core': {'contribution_rate': 0.03, 'graded_schedule': []},
    'auto_enrollment': {
      'default_deferral_rate': 0.06, 'window_days': 30,
      'scope': 'new_hires_only'
    },
    'deferral_escalation': {'increment': 0.02, 'cap': 0.08},
    'eligibility': {'waiting_period_days': 90}
  }
} %}

{% set formula_family_sample = {
  'age_design': {
    'match': {'family': 'deferral_based', 'match_template': 'tiered', 'cap_percent': 0.04, 'tiers': []},
    'employer_core': {
      'family': 'age_banded', 'contribution_rate': 0.02,
      'integration_enabled': true, 'integration_level_mode': 'ss_wage_base',
      'integration_level_value': none, 'integration_disparity_rate': 0.0054,
      'age_schedule': [
        {'min_age': 0, 'max_age': 40, 'rate': 2.0},
        {'min_age': 40, 'max_age': none, 'rate': 4.0}
      ]
    },
    'auto_enrollment': {'default_deferral_rate': 0.04, 'window_days': 45, 'scope': 'all_eligible_employees'},
    'deferral_escalation': {'increment': 0.01, 'cap': 0.06},
    'eligibility': {'waiting_period_days': 0}
  },
  'points_design': {
    'match': {'family': 'points_based', 'match_template': 'points', 'cap_percent': 0.04, 'tiers': []},
    'employer_core': {
      'family': 'points_based', 'contribution_rate': 0.03,
      'integration_enabled': false, 'integration_level_mode': 'ss_wage_base',
      'integration_level_value': none, 'integration_disparity_rate': 0.0,
      'points_schedule': [{'min_points': 0, 'max_points': none, 'rate': 3.0}]
    },
    'auto_enrollment': {'default_deferral_rate': 0.06, 'window_days': 30, 'scope': 'new_hires_only'},
    'deferral_escalation': {'increment': 0.02, 'cap': 0.08},
    'eligibility': {'waiting_period_days': 90}
  }
} %}

WITH empty_scalars AS (
  {{ get_plan_design_parameters({}) }}
),
empty_match AS (
  {{ get_plan_design_match_tiers({}) }}
),
empty_core AS (
  {{ get_plan_design_core_graded_schedule({}) }}
),
sample_scalars AS (
  {{ get_plan_design_parameters(sample) }}
),
sample_match AS (
  {{ get_plan_design_match_tiers(sample) }}
),
family_parameters AS (
  {{ get_plan_design_parameters(formula_family_sample) }}
),
age_schedule AS (
  {{ get_plan_design_core_age_schedule(formula_family_sample) }}
),
points_schedule AS (
  {{ get_plan_design_core_points_schedule(formula_family_sample) }}
),
violations AS (
  SELECT 'empty_scalars' AS violation WHERE (SELECT COUNT(*) FROM empty_scalars) <> 0
  UNION ALL
  SELECT 'empty_match' WHERE (SELECT COUNT(*) FROM empty_match) <> 0
  UNION ALL
  SELECT 'empty_core' WHERE (SELECT COUNT(*) FROM empty_core) <> 0
  UNION ALL
  SELECT 'scalar_cardinality' WHERE (SELECT COUNT(*) FROM sample_scalars) <> 1
  UNION ALL
  SELECT 'match_cardinality' WHERE (SELECT COUNT(*) FROM sample_match) <> 1
  UNION ALL
  SELECT 'scalar_values'
  WHERE NOT EXISTS (
    SELECT 1 FROM sample_scalars
    WHERE plan_design_id = 'current'
      AND auto_enrollment_window_days = 30
      AND eligibility_waiting_period_days = 90
  )
  UNION ALL
  SELECT 'family_cardinality' WHERE (SELECT COUNT(*) FROM family_parameters) <> 2
  UNION ALL
  SELECT 'family_scalar_values'
  WHERE NOT EXISTS (
    SELECT 1 FROM family_parameters
    WHERE plan_design_id = 'age_design'
      AND match_formula_family = 'deferral_based'
      AND core_formula_family = 'age_banded'
      AND core_integration_enabled
      AND core_integration_disparity_rate = 0.0054
  )
  UNION ALL
  SELECT 'age_decimal_conversion'
  WHERE NOT EXISTS (
    SELECT 1 FROM age_schedule
    WHERE plan_design_id = 'age_design' AND min_age = 0 AND max_age = 40 AND rate = 0.02
  )
  UNION ALL
  SELECT 'points_decimal_conversion'
  WHERE NOT EXISTS (
    SELECT 1 FROM points_schedule
    WHERE plan_design_id = 'points_design' AND min_points = 0
      AND max_points IS NULL AND rate = 0.03
  )
)
SELECT * FROM violations
