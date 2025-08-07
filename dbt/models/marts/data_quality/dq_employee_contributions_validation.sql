{{ config(
    materialized='table',
    indexes=[
        {'columns': ['employee_id', 'simulation_year'], 'type': 'btree'},
        {'columns': ['validation_rule'], 'type': 'btree'},
        {'columns': ['severity'], 'type': 'btree'}
    ]
) }}

{% set simulation_year = var('simulation_year', 2025) | int %}

/*
  Data Quality Validation for Employee Contributions - Epic E034

  This model validates contribution calculations and returns only failing records
  for review. It performs comprehensive checks including IRS compliance, rate
  consistency, and compensation validation.

  Validation Rules:
  1. Contributions don't exceed compensation
  2. Deferral rate consistency between events and calculated rates
  3. IRS 402(g) limit validation ($23,500 under 50, $31,000 for 50+)
  4. Contribution amounts align with periods and rates
  5. No negative contribution amounts
  6. Enrolled employees have contribution records

  Only returns failing records - empty result set indicates all validations passed.
*/

WITH simulation_parameters AS (
    SELECT {{ simulation_year }} AS current_year
),

-- Get workforce data with contributions
workforce_with_contributions AS (
    SELECT
        fw.employee_id,
        fw.simulation_year,
        fw.current_compensation,
        fw.prorated_annual_compensation,
        fw.current_age,
        fw.is_enrolled_flag,
        fw.current_deferral_rate,
        fw.employment_status,
        -- Contribution data from the updated workforce snapshot
        fw.prorated_annual_contributions,
        fw.pre_tax_contributions,
        fw.roth_contributions,
        fw.ytd_contributions,
        fw.irs_limit_reached,
        fw.effective_annual_deferral_rate,
        fw.total_contribution_base_compensation,
        fw.contribution_quality_flag
    FROM {{ ref('fct_workforce_snapshot') }} fw
    WHERE fw.simulation_year = (SELECT current_year FROM simulation_parameters)
),

-- Validation 1: Contributions exceed compensation
contributions_exceed_compensation AS (
    SELECT
        employee_id,
        simulation_year,
        'contributions_exceed_compensation' AS validation_rule,
        'ERROR' AS severity,
        CONCAT(
            'Employee ', employee_id, ' has contributions ($',
            ROUND(prorated_annual_contributions, 2),
            ') exceeding prorated compensation ($',
            ROUND(prorated_annual_compensation, 2), ')'
        ) AS validation_message,
        prorated_annual_contributions AS actual_value,
        prorated_annual_compensation AS expected_max_value,
        prorated_annual_contributions - prorated_annual_compensation AS variance
    FROM workforce_with_contributions
    WHERE prorated_annual_contributions > prorated_annual_compensation
      AND prorated_annual_contributions > 0
      AND prorated_annual_compensation > 0
),

-- Validation 2: Rate consistency check
rate_consistency_violations AS (
    SELECT
        employee_id,
        simulation_year,
        'deferral_rate_inconsistency' AS validation_rule,
        'WARNING' AS severity,
        CONCAT(
            'Employee ', employee_id, ' has deferral rate mismatch. ',
            'Current rate: ', ROUND(current_deferral_rate * 100, 2), '%, ',
            'Effective rate: ', ROUND(COALESCE(effective_annual_deferral_rate, 0) * 100, 2), '%'
        ) AS validation_message,
        current_deferral_rate AS actual_value,
        effective_annual_deferral_rate AS expected_max_value,
        ABS(current_deferral_rate - COALESCE(effective_annual_deferral_rate, 0)) AS variance
    FROM workforce_with_contributions
    WHERE ABS(current_deferral_rate - COALESCE(effective_annual_deferral_rate, 0)) > 0.05  -- 5% tolerance
      AND is_enrolled_flag = true
      AND prorated_annual_contributions > 0
),

-- Validation 3: IRS 402(g) limit validation - Should be ZERO with new enforcement
irs_limit_violations AS (
    SELECT
        employee_id,
        simulation_year,
        'irs_402g_limit_exceeded' AS validation_rule,
        'CRITICAL' AS severity,
        CONCAT(
            'Employee ', employee_id, ' (age ', current_age, ') ',
            'CRITICAL: IRS limit bypass detected: $', ROUND(prorated_annual_contributions, 2),
            ' > $',
            CASE WHEN current_age >= 50 THEN '31,000' ELSE '23,500' END,
            ' - This indicates IRS enforcement failure!'
        ) AS validation_message,
        prorated_annual_contributions AS actual_value,
        CASE WHEN current_age >= 50 THEN 31000 ELSE 23500 END AS expected_max_value,
        prorated_annual_contributions -
            CASE WHEN current_age >= 50 THEN 31000 ELSE 23500 END AS variance
    FROM workforce_with_contributions
    WHERE prorated_annual_contributions >
        CASE WHEN current_age >= 50 THEN 31000 ELSE 23500 END
      AND prorated_annual_contributions > 0
),

-- Validation 4: Contribution components don't sum correctly
contribution_component_mismatch AS (
    SELECT
        employee_id,
        simulation_year,
        'contribution_components_mismatch' AS validation_rule,
        'ERROR' AS severity,
        CONCAT(
            'Employee ', employee_id, ' contribution components mismatch. ',
            'Total: $', ROUND(ytd_contributions, 2), ', ',
            'Pre-tax + Roth: $', ROUND(pre_tax_contributions + roth_contributions, 2)
        ) AS validation_message,
        ytd_contributions AS actual_value,
        pre_tax_contributions + roth_contributions AS expected_max_value,
        ABS(ytd_contributions - (pre_tax_contributions + roth_contributions)) AS variance
    FROM workforce_with_contributions
    WHERE ABS(ytd_contributions - (pre_tax_contributions + roth_contributions)) > 0.01  -- $0.01 tolerance
      AND ytd_contributions > 0
),

-- Validation 5: Negative contribution amounts
negative_contributions AS (
    SELECT
        employee_id,
        simulation_year,
        'negative_contribution_amount' AS validation_rule,
        'ERROR' AS severity,
        CONCAT(
            'Employee ', employee_id, ' has negative contribution amount: $',
            ROUND(prorated_annual_contributions, 2)
        ) AS validation_message,
        prorated_annual_contributions AS actual_value,
        0.0 AS expected_max_value,
        prorated_annual_contributions AS variance
    FROM workforce_with_contributions
    WHERE prorated_annual_contributions < 0
),

-- Validation 6: Enrolled employees without contributions
enrolled_without_contributions AS (
    SELECT
        employee_id,
        simulation_year,
        'enrolled_without_contributions' AS validation_rule,
        'WARNING' AS severity,
        CONCAT(
            'Employee ', employee_id, ' is enrolled (deferral rate: ',
            ROUND(current_deferral_rate * 100, 2), '%) but has no contributions'
        ) AS validation_message,
        0.0 AS actual_value,
        current_deferral_rate * prorated_annual_compensation AS expected_max_value,
        current_deferral_rate * prorated_annual_compensation AS variance
    FROM workforce_with_contributions
    WHERE is_enrolled_flag = true
      AND current_deferral_rate > 0
      AND COALESCE(prorated_annual_contributions, 0) = 0
      AND employment_status = 'active'
      AND prorated_annual_compensation > 0
),

-- Validation 7: Excessive contribution rates (over 50%)
excessive_contribution_rates AS (
    SELECT
        employee_id,
        simulation_year,
        'excessive_contribution_rate' AS validation_rule,
        'WARNING' AS severity,
        CONCAT(
            'Employee ', employee_id, ' has excessive contribution rate: ',
            ROUND((prorated_annual_contributions / NULLIF(prorated_annual_compensation, 0)) * 100, 2), '%'
        ) AS validation_message,
        prorated_annual_contributions / NULLIF(prorated_annual_compensation, 0) AS actual_value,
        0.5 AS expected_max_value,
        (prorated_annual_contributions / NULLIF(prorated_annual_compensation, 0)) - 0.5 AS variance
    FROM workforce_with_contributions
    WHERE (prorated_annual_contributions / NULLIF(prorated_annual_compensation, 0)) > 0.5
      AND prorated_annual_contributions > 0
      AND prorated_annual_compensation > 0
),

-- Validation 8: IRS limit flag accuracy
irs_limit_flag_inaccuracy AS (
    SELECT
        employee_id,
        simulation_year,
        'irs_limit_flag_inaccurate' AS validation_rule,
        'ERROR' AS severity,
        CONCAT(
            'Employee ', employee_id, ' IRS limit flag mismatch. ',
            'Flag: ', irs_limit_reached, ', ',
            'Amount: $', ROUND(prorated_annual_contributions, 2), ', ',
            'Limit: $', CASE WHEN current_age >= 50 THEN '31,000' ELSE '23,500' END
        ) AS validation_message,
        CASE WHEN irs_limit_reached THEN 1.0 ELSE 0.0 END AS actual_value,
        CASE WHEN prorated_annual_contributions >=
            CASE WHEN current_age >= 50 THEN 31000 ELSE 23500 END
        THEN 1.0 ELSE 0.0 END AS expected_max_value,
        0 AS variance
    FROM workforce_with_contributions
    WHERE irs_limit_reached != (
        prorated_annual_contributions >=
            CASE WHEN current_age >= 50 THEN 31000 ELSE 23500 END
    )
      AND prorated_annual_contributions > 0
),

-- Validation 9: NEW - Contribution model integration validation
contribution_model_integration AS (
    SELECT
        fw.employee_id,
        fw.simulation_year,
        'contribution_model_missing' AS validation_rule,
        'CRITICAL' AS severity,
        CONCAT(
            'Employee ', fw.employee_id, ' is enrolled with contributions in workforce snapshot ',
            'but missing from int_employee_contributions model'
        ) AS validation_message,
        1.0 AS actual_value,
        0.0 AS expected_max_value,
        1.0 AS variance
    FROM workforce_with_contributions fw
    LEFT JOIN {{ ref('int_employee_contributions') }} ec
        ON fw.employee_id = ec.employee_id
        AND fw.simulation_year = ec.simulation_year
    WHERE fw.is_enrolled_flag = true
      AND COALESCE(fw.prorated_annual_contributions, 0) > 0
      AND ec.employee_id IS NULL
),

-- Union all validation results
all_validation_failures AS (
    SELECT * FROM contributions_exceed_compensation
    UNION ALL
    SELECT * FROM rate_consistency_violations
    UNION ALL
    SELECT * FROM irs_limit_violations
    UNION ALL
    SELECT * FROM contribution_component_mismatch
    UNION ALL
    SELECT * FROM negative_contributions
    UNION ALL
    SELECT * FROM enrolled_without_contributions
    UNION ALL
    SELECT * FROM excessive_contribution_rates
    UNION ALL
    SELECT * FROM irs_limit_flag_inaccuracy
    UNION ALL
    SELECT * FROM contribution_model_integration
)

-- Final output: Only failing records with metadata
SELECT
    employee_id,
    simulation_year,
    validation_rule,
    severity,
    validation_message,
    actual_value,
    expected_max_value,
    variance,
    -- Add severity ranking for prioritization
    CASE severity
        WHEN 'CRITICAL' THEN 0
        WHEN 'ERROR' THEN 1
        WHEN 'WARNING' THEN 2
        ELSE 3
    END AS severity_rank,
    -- Add validation category grouping
    CASE
        WHEN validation_rule IN ('contributions_exceed_compensation', 'negative_contribution_amount')
            THEN 'CONTRIBUTION_AMOUNTS'
        WHEN validation_rule IN ('deferral_rate_inconsistency', 'excessive_contribution_rate')
            THEN 'RATE_VALIDATION'
        WHEN validation_rule IN ('irs_402g_limit_exceeded', 'irs_limit_flag_inaccurate')
            THEN 'IRS_COMPLIANCE'
        WHEN validation_rule IN ('contribution_components_mismatch')
            THEN 'DATA_INTEGRITY'
        WHEN validation_rule IN ('enrolled_without_contributions')
            THEN 'ENROLLMENT_CONSISTENCY'
        WHEN validation_rule IN ('contribution_model_missing')
            THEN 'MODEL_INTEGRATION'
        ELSE 'OTHER'
    END AS validation_category,
    -- Metadata
    CURRENT_TIMESTAMP AS validation_timestamp,
    'Epic_E034_contribution_validation' AS validation_source
FROM all_validation_failures
ORDER BY
    severity_rank ASC,  -- Errors first
    validation_category ASC,
    ABS(variance) DESC,  -- Largest variances first within category
    employee_id ASC

/*
  Usage Notes:
  - Empty result set = all validations passed
  - Non-empty result set = review failing records by severity
  - ERROR severity requires immediate attention
  - WARNING severity should be investigated but may be acceptable
  - Use validation_category to group similar issues for bulk resolution
  - variance column shows magnitude of the validation failure

  Performance Notes:
  - Uses CTEs for clarity and maintainability
  - Indexed on employee_id, simulation_year, validation_rule, severity
  - Returns only failing records to minimize result set size
  - Should complete in <1 second for 10,000+ employee workforce
*/
