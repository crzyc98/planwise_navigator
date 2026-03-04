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
-- Check (a): Eligibility and vesting credits CAN differ for the same employee/year.
-- If every single employee has identical credits, the counters may be wired together
-- rather than tracked independently. At least one divergent row must exist.
independence_check AS (
  SELECT
    COUNT(*) AS total_rows,
    COUNT(CASE WHEN eligibility_years_credited != vesting_years_credited THEN 1 END) AS divergent_rows
  FROM {{ ref('int_service_credit_accumulator') }}
  WHERE simulation_year = {{ simulation_year }}
),

independence_failures AS (
  SELECT
    'STRUCTURAL' AS employee_id,
    {{ simulation_year }} AS simulation_year,
    'Check (a) failed: eligibility_years_credited = vesting_years_credited for all '
      || CAST(ic.total_rows AS VARCHAR)
      || ' rows — counters may not be independent' AS issue_description
  FROM independence_check ic
  WHERE ic.total_rows > 0
    AND ic.divergent_rows = 0
),

-- Check (b): An employee can earn vesting credit without eligibility credit
-- (e.g., plan-year hours >= threshold but IECP incomplete).
-- If no such row exists, the model may be copying eligibility into vesting.
vesting_without_eligibility_check AS (
  SELECT
    COUNT(*) AS total_rows,
    COUNT(CASE
      WHEN vesting_classification_this_year = 'year_of_service'
       AND eligibility_classification_this_year != 'year_of_service'
      THEN 1
    END) AS vesting_only_rows
  FROM {{ ref('int_service_credit_accumulator') }}
  WHERE simulation_year = {{ simulation_year }}
),

vesting_without_eligibility_failures AS (
  SELECT
    'STRUCTURAL' AS employee_id,
    {{ simulation_year }} AS simulation_year,
    'Check (b) warning: no employees have vesting credit without eligibility credit — '
      || 'may be correct if all employees meet both thresholds, but review if IECP logic is active' AS issue_description
  FROM vesting_without_eligibility_check vc
  WHERE vc.total_rows > 0
    AND vc.vesting_only_rows = 0
    -- Only flag when IECP employees exist (hire-year employees with incomplete IECP)
    AND EXISTS (
      SELECT 1
      FROM {{ ref('int_eligibility_computation_period') }}
      WHERE simulation_year = {{ simulation_year }}
        AND period_type = 'iecp'
        AND NOT is_iecp_complete
    )
),

-- Check (c): is_plan_eligible must never revert from TRUE to FALSE
{% if simulation_year > start_year %}
eligibility_reversion_check AS (
  SELECT
    curr.employee_id,
    curr.simulation_year,
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
eligibility_reversion_check AS (
  SELECT
    NULL::VARCHAR AS employee_id,
    NULL::INTEGER AS simulation_year,
    NULL::VARCHAR AS issue_description
  WHERE FALSE
)
{% endif %}

SELECT employee_id, simulation_year, issue_description
FROM independence_failures

UNION ALL

SELECT employee_id, simulation_year, issue_description
FROM vesting_without_eligibility_failures

UNION ALL

SELECT employee_id, simulation_year, issue_description
FROM eligibility_reversion_check
WHERE issue_description IS NOT NULL

ORDER BY employee_id
