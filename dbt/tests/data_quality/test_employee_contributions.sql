-- Converted from validation model to test
-- Added simulation_year filter for performance

/*
  Simplified Employee Contributions Data Quality Validation - Story S025-02 Testing

  Simplified version for comprehensive testing that works with current data model.
  Focuses on core validation rules for IRS compliance and data integrity.

  Returns only failing records for dbt test.
*/

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH base_contribution_data AS (
    SELECT
        employee_id,
        simulation_year,
        current_age,
        employment_status,
        -- Map to names used in validations
        annual_contribution_amount,
        requested_contribution_amount,
        amount_capped_by_irs_limit,
        applicable_irs_limit,
        irs_limit_applied,
        is_enrolled_flag,
        prorated_annual_compensation,
        effective_annual_deferral_rate as effective_deferral_rate
    FROM {{ ref('int_employee_contributions') }}
    WHERE simulation_year = {{ simulation_year }}
),

workforce_data AS (
    SELECT
        *,
        employee_compensation AS prorated_annual_compensation  -- Map to expected name
    FROM {{ ref('int_employee_compensation_by_year') }}
    WHERE simulation_year = {{ simulation_year }}
),

irs_limits AS (
    SELECT
        limit_year,
        base_limit,
        catch_up_limit,
        catch_up_age_threshold
    FROM {{ ref('config_irs_limits') }}
    WHERE limit_year = {{ simulation_year }}
    LIMIT 1
),

-- CRITICAL VALIDATION RULES (Zero Tolerance)
critical_validations AS (
    -- Rule C01: IRS 402(g) Base Limit Violations
    SELECT
        'C01' AS validation_rule,
        'IRS_402G_BASE_LIMIT_VIOLATION' AS validation_source,
        'CRITICAL' AS severity,
        1 AS severity_rank,
        cd.employee_id,
        cd.annual_contribution_amount,
        il.base_limit,
        CONCAT(
            'IRS 402(g) base limit violation: contribution $',
            cd.annual_contribution_amount, ' exceeds base limit $',
            il.base_limit, ' for employee under age ', il.catch_up_age_threshold
        ) AS validation_message
    FROM base_contribution_data cd
    CROSS JOIN irs_limits il
    WHERE cd.current_age < il.catch_up_age_threshold
        AND cd.annual_contribution_amount > il.base_limit

    UNION ALL

    -- Rule C02: IRS 402(g) Total Limit Violations (50+ with catch-up)
    SELECT
        'C02' AS validation_rule,
        'IRS_402G_TOTAL_LIMIT_VIOLATION' AS validation_source,
        'CRITICAL' AS severity,
        1 AS severity_rank,
        cd.employee_id,
        cd.annual_contribution_amount,
        il.catch_up_limit,
        CONCAT(
            'IRS 402(g) total limit violation: contribution $',
            cd.annual_contribution_amount, ' exceeds catch-up limit $',
            il.catch_up_limit, ' for employee age 50+'
        ) AS validation_message
    FROM base_contribution_data cd
    CROSS JOIN irs_limits il
    WHERE cd.current_age >= il.catch_up_age_threshold
        AND cd.annual_contribution_amount > il.catch_up_limit

    UNION ALL

    -- Rule C03: Contributions Exceed Compensation
    SELECT
        'C03' AS validation_rule,
        'CONTRIBUTIONS_EXCEED_COMPENSATION' AS validation_source,
        'CRITICAL' AS severity,
        1 AS severity_rank,
        cd.employee_id,
        cd.annual_contribution_amount,
        wd.prorated_annual_compensation,
        CONCAT(
            'Contribution exceeds compensation: contribution $',
            cd.annual_contribution_amount, ' > prorated compensation $',
            wd.prorated_annual_compensation
        ) AS validation_message
    FROM base_contribution_data cd
    INNER JOIN workforce_data wd ON cd.employee_id = wd.employee_id
    WHERE cd.annual_contribution_amount > (wd.prorated_annual_compensation + 100)  -- $100 tolerance for rounding
),

-- ERROR VALIDATION RULES (High Priority)
error_validations AS (
    -- Rule E01: Contributions Without Enrollment
    SELECT
        'E01' AS validation_rule,
        'CONTRIBUTIONS_WITHOUT_ENROLLMENT' AS validation_source,
        'ERROR' AS severity,
        2 AS severity_rank,
        cd.employee_id,
        cd.annual_contribution_amount,
        0.0 AS expected_value,
        'Contribution detected for non-enrolled employee' AS validation_message
    FROM base_contribution_data cd
    WHERE cd.is_enrolled_flag = false
        AND cd.annual_contribution_amount > 10  -- $10 minimum threshold

    UNION ALL

    -- Rule E02: IRS Limit Enforcement Mismatch
    SELECT
        'E02' AS validation_rule,
        'IRS_LIMIT_ENFORCEMENT_MISMATCH' AS validation_source,
        'ERROR' AS severity,
        2 AS severity_rank,
        cd.employee_id,
        cd.amount_capped_by_irs_limit,
        NULL AS expected_value,
        'IRS limit enforcement logic inconsistency: irs_limit_applied flag does not match capped amount' AS validation_message
    FROM base_contribution_data cd
    WHERE (cd.irs_limit_applied = true AND cd.amount_capped_by_irs_limit <= 0)
        OR (cd.irs_limit_applied = false AND cd.amount_capped_by_irs_limit > 0)
)

-- Combine all validation failures and return for dbt test
SELECT
    {{ simulation_year }} AS simulation_year,
    validation_rule,
    validation_source,
    severity,
    severity_rank,
    employee_id,
    validation_message,
    -- Enhanced metadata for audit trail
    CURRENT_TIMESTAMP AS validation_timestamp,
    '{{ var("scenario_id", "default") }}' AS scenario_id,
    '{{ var("parameter_scenario_id", "default") }}' AS parameter_scenario_id,
    -- Audit trail fields
    CONCAT('DQ-', validation_rule, '-', {{ simulation_year }}, '-', employee_id) AS audit_record_id,
    'dbt_test' AS validation_engine_version,
    -- Risk assessment
    CASE severity
        WHEN 'CRITICAL' THEN 'IMMEDIATE_ACTION_REQUIRED'
        WHEN 'ERROR' THEN 'HIGH_PRIORITY_REVIEW'
        WHEN 'WARNING' THEN 'MONITORING_REQUIRED'
        ELSE 'INFORMATIONAL_ONLY'
    END AS risk_level,
    -- Compliance flags
    CASE
        WHEN validation_source LIKE 'IRS%' THEN true
        WHEN validation_source LIKE '%COMPLIANCE%' THEN true
        ELSE false
    END AS regulatory_impact
FROM (
    SELECT * FROM critical_validations
    UNION ALL
    SELECT * FROM error_validations
) all_failures
ORDER BY severity_rank, validation_rule, employee_id
