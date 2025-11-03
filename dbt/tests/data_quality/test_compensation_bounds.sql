{{
  config(
    severity='error',
    tags=['data_quality', 'compensation', 'bounds_check']
  )
}}

/*
  Data Quality Test: Comprehensive Compensation Bounds Check

  Flags compensation values that exceed reasonable bounds and calculates inflation factors.

  Purpose:
  - Identify compensation values > $10M (CRITICAL)
  - Identify compensation values > $5M (WARNING)
  - Identify compensation values < $10K (WARNING)
  - Calculate inflation factors from baseline workforce
  - Flag >2x increases as suspicious

  Returns rows where compensation bounds are violated.
*/

WITH baseline_compensation AS (
  SELECT
    employee_id,
    current_compensation as baseline_compensation,
    simulation_year as baseline_year
  FROM {{ ref('int_baseline_workforce') }}
  WHERE simulation_year = {{ var('simulation_year') }}
),

current_compensation AS (
  SELECT
    employee_id,
    current_compensation,
    prorated_annual_compensation,
    full_year_equivalent_compensation,
    simulation_year,
    employment_status
  FROM {{ ref('fct_workforce_snapshot') }}
  WHERE simulation_year = {{ var('simulation_year') }}
    AND employment_status = 'active'
),

compensation_with_inflation AS (
  SELECT
    c.employee_id,
    c.current_compensation,
    c.prorated_annual_compensation,
    c.full_year_equivalent_compensation,
    c.simulation_year,
    b.baseline_compensation,
    b.baseline_year,
    CASE
      WHEN b.baseline_compensation > 0
      THEN c.current_compensation / b.baseline_compensation
      ELSE NULL
    END as inflation_factor,
    COALESCE(c.current_compensation, 0) - COALESCE(b.baseline_compensation, 0) as absolute_increase,
    CASE
      WHEN b.baseline_compensation > 0
      THEN ((c.current_compensation - b.baseline_compensation) / b.baseline_compensation) * 100
      ELSE NULL
    END as percentage_increase
  FROM current_compensation c
  LEFT JOIN baseline_compensation b
    ON c.employee_id = b.employee_id
)

SELECT
  employee_id,
  current_compensation,
  prorated_annual_compensation,
  simulation_year,
  baseline_compensation,
  inflation_factor,
  absolute_increase,
  percentage_increase,
  CASE
    WHEN current_compensation > 10000000 THEN 'CRITICAL'
    WHEN current_compensation > 5000000 THEN 'WARNING'
    WHEN current_compensation < 10000 THEN 'WARNING'
    WHEN inflation_factor > 10.0 THEN 'CRITICAL'
    WHEN inflation_factor > 5.0 THEN 'SEVERE'
    WHEN inflation_factor > 2.0 THEN 'WARNING'
    WHEN inflation_factor < 0.8 AND baseline_compensation IS NOT NULL THEN 'WARNING'
    WHEN percentage_increase > 1000 THEN 'CRITICAL'
    WHEN percentage_increase > 500 THEN 'SEVERE'
    WHEN percentage_increase > 100 THEN 'WARNING'
    WHEN percentage_increase < -20 AND baseline_compensation IS NOT NULL THEN 'WARNING'
    ELSE 'OK'
  END as severity,
  CONCAT_WS('; ',
    CASE WHEN current_compensation > 10000000 THEN 'Compensation exceeds $10M' END,
    CASE WHEN current_compensation > 5000000 AND current_compensation <= 10000000 THEN 'Compensation exceeds $5M' END,
    CASE WHEN current_compensation < 10000 THEN 'Compensation below $10K' END,
    CASE WHEN inflation_factor > 10.0 THEN CONCAT('Extreme inflation: ', ROUND(inflation_factor, 2), 'x baseline') END,
    CASE WHEN inflation_factor > 5.0 AND inflation_factor <= 10.0 THEN CONCAT('Severe inflation: ', ROUND(inflation_factor, 2), 'x baseline') END,
    CASE WHEN inflation_factor > 2.0 AND inflation_factor <= 5.0 THEN CONCAT('High inflation: ', ROUND(inflation_factor, 2), 'x baseline') END,
    CASE WHEN inflation_factor < 0.8 AND baseline_compensation IS NOT NULL THEN CONCAT('Compensation decrease: ', ROUND(inflation_factor, 2), 'x baseline') END
  ) as issue_description
FROM compensation_with_inflation
WHERE
  current_compensation > 10000000
  OR current_compensation > 5000000
  OR current_compensation < 10000
  OR inflation_factor > 2.0
  OR (inflation_factor < 0.8 AND baseline_compensation IS NOT NULL)
  OR percentage_increase > 100
  OR (percentage_increase < -20 AND baseline_compensation IS NOT NULL)
ORDER BY
  CASE
    WHEN severity = 'CRITICAL' THEN 1
    WHEN severity = 'SEVERE' THEN 2
    WHEN severity = 'WARNING' THEN 3
    ELSE 4
  END,
  current_compensation DESC
