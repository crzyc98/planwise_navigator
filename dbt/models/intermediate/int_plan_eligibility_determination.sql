{{ config(
    materialized='table',
    tags=['eligibility', 'enrollment', 'EVENT_GENERATION', 'E023']
) }}

{% set simulation_year = var('simulation_year') | int %}
{% set scenario_id = var('scenario_id', 'default') %}
{% set minimum_age = var('plan_eligibility_minimum_age', var('minimum_age', 21)) | int %}
{% set plan_design_parameters_config = var('plan_design_parameters', none) %}

WITH parameter_rows AS (
{% if plan_design_parameters_config %}
  {{ get_plan_design_parameters(plan_design_parameters_config) }}
{% else %}
  SELECT
    '{{ var('plan_design_id', 'default') }}'::VARCHAR AS plan_design_id,
    {{ var('plan_eligibility_waiting_period_days', 0) }}::INTEGER
      AS eligibility_waiting_period_days
{% endif %}
),

employee_candidates AS (
  SELECT
    employee_id,
    employee_ssn,
    employee_hire_date::DATE AS employee_hire_date,
    current_age,
    current_tenure,
    level_id,
    employee_compensation AS current_compensation,
    age_band,
    tenure_band,
    simulation_year,
    1 AS source_priority
  FROM {{ ref('int_employee_compensation_by_year') }}
  WHERE simulation_year = {{ simulation_year }}
    AND employment_status = 'active'
    AND employee_id IS NOT NULL

  UNION ALL

  SELECT
    employee_id,
    employee_ssn,
    effective_date::DATE AS employee_hire_date,
    employee_age AS current_age,
    0::DECIMAL(10,2) AS current_tenure,
    level_id,
    compensation_amount AS current_compensation,
    age_band,
    tenure_band,
    simulation_year,
    2 AS source_priority
  FROM {{ ref('int_hiring_events') }}
  WHERE simulation_year = {{ simulation_year }}
    AND employee_id IS NOT NULL
),

employees AS (
  SELECT * EXCLUDE (source_priority, candidate_rank)
  FROM (
    SELECT
      candidate.*,
      ROW_NUMBER() OVER (
        PARTITION BY candidate.employee_id, candidate.simulation_year
        ORDER BY candidate.source_priority
      ) AS candidate_rank
    FROM employee_candidates candidate
  ) ranked
  WHERE candidate_rank = 1
),

eligibility_calculation AS (
  SELECT
    '{{ scenario_id }}'::VARCHAR AS scenario_id,
    assignment.plan_design_id,
    employee.*,
    parameters.eligibility_waiting_period_days AS waiting_period_days,
    {{ minimum_age }}::INTEGER AS minimum_age,
    employee.employee_hire_date
      + INTERVAL (parameters.eligibility_waiting_period_days) DAY
      AS plan_eligibility_date,
    employee.current_age >= {{ minimum_age }} AS meets_age_requirement,
    CASE
      WHEN parameters.eligibility_waiting_period_days = 0 THEN TRUE
      ELSE DATE_DIFF(
        'day', employee.employee_hire_date,
        MAKE_DATE(employee.simulation_year, 12, 31)
      ) >= parameters.eligibility_waiting_period_days
    END AS meets_tenure_requirement
  FROM employees employee
  INNER JOIN {{ ref('int_plan_design_assignment_accumulator') }} assignment
    ON employee.employee_id = assignment.employee_id
   AND employee.simulation_year = assignment.simulation_year
   AND assignment.scenario_id = '{{ scenario_id }}'
  INNER JOIN parameter_rows parameters
    ON assignment.plan_design_id = parameters.plan_design_id
)

SELECT
  scenario_id,
  plan_design_id,
  employee_id,
  employee_ssn,
  simulation_year,
  employee_hire_date,
  current_age,
  current_tenure,
  level_id,
  current_compensation,
  age_band,
  tenure_band,
  waiting_period_days,
  minimum_age,
  plan_eligibility_date,
  meets_age_requirement,
  meets_tenure_requirement,
  meets_age_requirement AND meets_tenure_requirement AS is_plan_eligible,
  CASE
    WHEN meets_age_requirement AND meets_tenure_requirement THEN 'eligible'
    WHEN NOT meets_age_requirement THEN 'not_eligible_age'
    WHEN NOT meets_tenure_requirement THEN 'not_eligible_tenure'
    ELSE 'not_eligible_other'
  END AS eligibility_status,
  CASE
    WHEN current_age < minimum_age THEN (minimum_age - current_age) * 365
    WHEN DATE_DIFF('day', employee_hire_date, MAKE_DATE(simulation_year, 12, 31))
      < waiting_period_days
    THEN waiting_period_days
      - DATE_DIFF('day', employee_hire_date, MAKE_DATE(simulation_year, 12, 31))
    ELSE 0
  END AS days_until_eligible,
  CASE
    WHEN meets_age_requirement AND meets_tenure_requirement
    THEN GREATEST(
      plan_eligibility_date,
      MAKE_DATE(simulation_year - current_age + minimum_age, 1, 1)
    )
    ELSE NULL
  END AS eligibility_effective_date,
  CURRENT_TIMESTAMP AS determination_timestamp,
  'plan_eligibility' AS eligibility_type,
  'assignment_aware_rule_based' AS determination_method
FROM eligibility_calculation
ORDER BY employee_id
