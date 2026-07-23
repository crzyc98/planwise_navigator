{{ config(
    materialized='ephemeral',
    tags=['FOUNDATION', 'critical', 'temporal_projection']
) }}

{% set simulation_year = var('simulation_year') | int %}
{% set scenario_id = var('scenario_id', 'default') %}
{% set plan_design_id = var('plan_design_id', 'default') %}

-- Decision-year-ready view over the orchestrator's strict N-1 projection.
SELECT
  workforce.employee_id,
  workforce.employee_ssn,
  workforce.employee_birth_date,
  workforce.employee_hire_date,
  CASE
    WHEN full_year_equivalent_compensation IS NULL
      OR full_year_equivalent_compensation <= 0 THEN 50000
    ELSE full_year_equivalent_compensation
  END AS employee_gross_compensation,
  current_age + 1 AS current_age,
  current_tenure + 1 AS current_tenure,
  level_id,
  'active' AS employment_status,
  CAST(NULL AS DATE) AS termination_date,
  {{ assign_age_band('current_age + 1') }} AS age_band,
  {{ assign_tenure_band('current_tenure + 1') }} AS tenure_band,
  COALESCE(
    enrollment.authoritative_enrollment_date,
    enrollment.enrollment_date
  ) AS employee_enrollment_date,
  workforce.scheduled_hours_per_week,
  CASE
    WHEN COALESCE(
      enrollment.authoritative_enrollment_date,
      enrollment.enrollment_date
    ) IS NOT NULL THEN TRUE
    ELSE FALSE
  END AS is_enrolled_flag,
  {{ simulation_year }} AS simulation_year,
  'workforce_state_projection' AS data_source,
  TRUE AS data_quality_valid
FROM {{ source('orchestrator_state', 'workforce_state_projection') }} workforce
LEFT JOIN {{ source('orchestrator_state', 'enrollment_decision_projection') }} enrollment
  ON workforce.employee_id = enrollment.employee_id
 AND enrollment.decision_year = {{ simulation_year }}
 AND enrollment.scenario_id = '{{ scenario_id }}'
 AND enrollment.plan_design_id = '{{ plan_design_id }}'
WHERE workforce.decision_year = {{ simulation_year }}
  AND workforce.source_simulation_year = {{ simulation_year - 1 }}
  AND workforce.scenario_id = '{{ scenario_id }}'
  AND workforce.plan_design_id = '{{ plan_design_id }}'
  AND workforce.employment_status = 'active'
  AND workforce.employee_id IS NOT NULL
  AND workforce.employee_ssn IS NOT NULL
  AND workforce.employee_birth_date IS NOT NULL
  AND workforce.employee_hire_date IS NOT NULL
  AND workforce.current_compensation > 0
  AND workforce.current_age BETWEEN 0 AND 100
  AND workforce.current_tenure >= 0
