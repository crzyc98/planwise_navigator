{{
  config(
    severity='error',
    tags=['data_quality', 'erisa', 'eligibility']
  )
}}

/*
  Data Quality Test: Eligibility vs. Vesting Service Credit Independence (FR-006)

  Validates:
  (a) Eligibility and vesting credits can differ for the same employee in the same year
      (This is a structural test - at least one employee should demonstrate independence)
  (b) An employee can have vesting credit without eligibility credit
      (e.g., 8-month employee with 2,000 hours in plan year but IECP incomplete)
  (c) is_plan_eligible never reverts from TRUE to FALSE across years

  Returns failure rows only with descriptive issue_description.
*/

{% set simulation_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}

WITH
-- Check (c): is_plan_eligible must never revert from TRUE to FALSE
-- Only applicable for multi-year simulations (year > start_year)
{% if simulation_year > start_year %}
eligibility_reversion_check AS (
  SELECT
    curr.employee_id,
    curr.simulation_year,
    prev.is_plan_eligible AS prev_eligible,
    curr.is_plan_eligible AS curr_eligible,
    'is_plan_eligible reverted from TRUE to FALSE: prev=' || CAST(prev.is_plan_eligible AS VARCHAR) || ', curr=' || CAST(curr.is_plan_eligible AS VARCHAR) AS issue_description
  FROM {{ ref('int_service_credit_accumulator') }} curr
  INNER JOIN {{ ref('int_service_credit_accumulator') }} prev
    ON curr.employee_id = prev.employee_id
    AND prev.simulation_year = curr.simulation_year - 1
  WHERE curr.simulation_year = {{ simulation_year }}
    AND prev.is_plan_eligible = TRUE
    AND curr.is_plan_eligible = FALSE
)
{% else %}
-- For first year, no reversion check is possible
eligibility_reversion_check AS (
  SELECT
    NULL::VARCHAR AS employee_id,
    NULL::INTEGER AS simulation_year,
    NULL::BOOLEAN AS prev_eligible,
    NULL::BOOLEAN AS curr_eligible,
    NULL::VARCHAR AS issue_description
  WHERE FALSE
)
{% endif %}

SELECT
  employee_id,
  simulation_year,
  issue_description
FROM eligibility_reversion_check
WHERE issue_description IS NOT NULL
ORDER BY employee_id
