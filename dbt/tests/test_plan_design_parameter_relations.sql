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
)
SELECT * FROM violations
