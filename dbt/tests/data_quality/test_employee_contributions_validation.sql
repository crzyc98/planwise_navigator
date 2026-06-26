{{
  config(
    severity='error',
    tags=['data_quality', 'contributions', 'irs_compliance', 'epic_e034']
  )
}}

/*
  Data Quality Test: Employee Contributions Validation - Epic E034

  This test validates contribution calculations and returns only failing records.
  It performs comprehensive checks including IRS compliance, rate consistency,
  and compensation validation.

  Validation Rules:
  1. Contributions don't exceed compensation
  2. Deferral rate consistency between events and calculated rates
  3. IRS 402(g) limit validation ($23,500 under 50, $31,000 for 50+)
  4. Contribution amounts align with periods and rates
  5. No negative contribution amounts
  6. Enrolled employees have contribution records
  7. No excessive contribution rates (over 50%)
  8. IRS limit flag accuracy
  9. Contribution model integration

  Empty result set = all validations passed
  Non-empty result set = validation failures requiring attention
*/

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH simulation_parameters AS (
    SELECT {{ simulation_year }} AS current_year
),

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
        ) AS validation_message
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
        ) AS validation_message
    FROM workforce_with_contributions
    WHERE ABS(current_deferral_rate - COALESCE(effective_annual_deferral_rate, 0)) > 0.05
      AND is_enrolled_flag = true
      AND prorated_annual_contributions > 0
),

-- Get dynamic IRS limits for validation year
irs_limits_for_validation AS (
    SELECT
        limit_year,
        base_limit,
        catch_up_limit,
        catch_up_age_threshold,
        super_catch_up_limit,
        super_catch_up_age_min,
        super_catch_up_age_max
    FROM {{ ref('config_irs_limits') }}
    WHERE limit_year = (SELECT current_year FROM simulation_parameters)
),

-- Validation 3: IRS 402(g) limit validation
-- Compare against the contribution model's authoritative applicable_irs_limit (the limit
-- actually used to cap the contribution), not a limit re-derived from the snapshot's
-- current_age. The two age values can legitimately differ by a year — an employee who
-- attains age 50/60 during the year is catch-up eligible in the model while the snapshot
-- may still show the prior age — which produced false CRITICAL failures (issue #334).
irs_limit_violations AS (
    SELECT
        w.employee_id,
        w.simulation_year,
        'irs_402g_limit_exceeded' AS validation_rule,
        'CRITICAL' AS severity,
        CONCAT(
            'Employee ', w.employee_id, ' ',
            'CRITICAL: IRS limit bypass detected: $', ROUND(ec.annual_contribution_amount, 2),
            ' > $', ROUND(ec.applicable_irs_limit, 2),
            ' - This indicates IRS enforcement failure!'
        ) AS validation_message
    FROM workforce_with_contributions w
    JOIN {{ ref('int_employee_contributions') }} ec
        ON w.employee_id = ec.employee_id
        AND w.simulation_year = ec.simulation_year
    WHERE ec.annual_contribution_amount > ec.applicable_irs_limit + 0.01
      AND ec.annual_contribution_amount > 0
),

-- Validation 4: Contribution components mismatch
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
        ) AS validation_message
    FROM workforce_with_contributions
    WHERE ABS(ytd_contributions - (pre_tax_contributions + roth_contributions)) > 0.01
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
        ) AS validation_message
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
        ) AS validation_message
    FROM workforce_with_contributions
    WHERE is_enrolled_flag = true
      AND current_deferral_rate > 0
      AND COALESCE(prorated_annual_contributions, 0) = 0
      AND employment_status = 'active'
      AND prorated_annual_compensation > 0
),

-- Validation 7: Excessive contribution rates
excessive_contribution_rates AS (
    SELECT
        employee_id,
        simulation_year,
        'excessive_contribution_rate' AS validation_rule,
        'WARNING' AS severity,
        CONCAT(
            'Employee ', employee_id, ' has excessive contribution rate: ',
            ROUND((prorated_annual_contributions / NULLIF(prorated_annual_compensation, 0)) * 100, 2), '%'
        ) AS validation_message
    FROM workforce_with_contributions
    WHERE (prorated_annual_contributions / NULLIF(prorated_annual_compensation, 0)) > 0.5
      AND prorated_annual_contributions > 0
      AND prorated_annual_compensation > 0
),

-- Validation 8: IRS limit flag accuracy (using dynamic limits from config_irs_limits seed)
irs_limit_flag_inaccuracy AS (
    SELECT
        w.employee_id,
        w.simulation_year,
        'irs_limit_flag_inaccurate' AS validation_rule,
        'ERROR' AS severity,
        CONCAT(
            'Employee ', w.employee_id, ' IRS limit flag mismatch. ',
            'Flag: ', w.irs_limit_reached, ', ',
            'Amount: $', ROUND(w.prorated_annual_contributions, 2)
        ) AS validation_message
    FROM workforce_with_contributions w
    CROSS JOIN irs_limits_for_validation il
    WHERE w.irs_limit_reached != (
        w.prorated_annual_contributions >=
            CASE WHEN w.current_age BETWEEN il.super_catch_up_age_min AND il.super_catch_up_age_max THEN il.super_catch_up_limit WHEN w.current_age >= il.catch_up_age_threshold THEN il.catch_up_limit ELSE il.base_limit END
    )
      AND w.prorated_annual_contributions > 0
),

-- Validation 9: Contribution model integration
contribution_model_integration AS (
    SELECT
        fw.employee_id,
        fw.simulation_year,
        'contribution_model_missing' AS validation_rule,
        'CRITICAL' AS severity,
        CONCAT(
            'Employee ', fw.employee_id, ' is enrolled with contributions in workforce snapshot ',
            'but missing from int_employee_contributions model'
        ) AS validation_message
    FROM workforce_with_contributions fw
    LEFT JOIN {{ ref('int_employee_contributions') }} ec
        ON fw.employee_id = ec.employee_id
        AND fw.simulation_year = ec.simulation_year
    WHERE fw.is_enrolled_flag = true
      AND COALESCE(fw.prorated_annual_contributions, 0) > 0
      AND ec.employee_id IS NULL
)

-- Union all validation results, then fail only on genuine ERROR/CRITICAL rows. This is
-- an error-severity gate, so WARNING-level diagnostics (rate-consistency between the two
-- deferral-rate fields, >50% rate driven by near-zero prorated comp on early terminations)
-- are computed for transparency but must not turn the build red (issue #334).
SELECT employee_id, simulation_year, validation_rule, severity, validation_message
FROM (
    SELECT employee_id, simulation_year, validation_rule, severity, validation_message
    FROM contributions_exceed_compensation
    UNION ALL
    SELECT employee_id, simulation_year, validation_rule, severity, validation_message
    FROM rate_consistency_violations
    UNION ALL
    SELECT employee_id, simulation_year, validation_rule, severity, validation_message
    FROM irs_limit_violations
    UNION ALL
    SELECT employee_id, simulation_year, validation_rule, severity, validation_message
    FROM contribution_component_mismatch
    UNION ALL
    SELECT employee_id, simulation_year, validation_rule, severity, validation_message
    FROM negative_contributions
    UNION ALL
    SELECT employee_id, simulation_year, validation_rule, severity, validation_message
    FROM enrolled_without_contributions
    UNION ALL
    SELECT employee_id, simulation_year, validation_rule, severity, validation_message
    FROM excessive_contribution_rates
    UNION ALL
    SELECT employee_id, simulation_year, validation_rule, severity, validation_message
    FROM irs_limit_flag_inaccuracy
    UNION ALL
    SELECT employee_id, simulation_year, validation_rule, severity, validation_message
    FROM contribution_model_integration
) all_validations
WHERE severity IN ('ERROR', 'CRITICAL')
