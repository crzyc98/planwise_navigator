{{ config(
    materialized='table',
    indexes=[
        {'columns': ['simulation_year'], 'type': 'btree'},
        {'columns': ['severity'], 'type': 'btree'},
        {'columns': ['validation_rule'], 'type': 'btree'}
    ],
    tags=['data_quality', 'critical', 'contribution_validation']
) }}

/*
  Simplified Employee Contributions Data Quality Validation - Story S025-02 Testing

  Simplified version for comprehensive testing that works with current data model.
  Focuses on core validation rules for IRS compliance and data integrity.
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
    FROM {{ ref('irs_contribution_limits') }}
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
        COUNT(*) AS violation_count,
        CONCAT(
            'IRS 402(g) base limit violations detected: ',
            COUNT(*), ' employees with contributions exceeding $',
            MAX(il.base_limit), ' (under age threshold)'
        ) AS validation_message
    FROM base_contribution_data cd
    CROSS JOIN irs_limits il
    WHERE cd.current_age < il.catch_up_age_threshold
        AND cd.annual_contribution_amount > il.base_limit
    GROUP BY il.base_limit
    HAVING COUNT(*) > 0

    UNION ALL

    -- Rule C02: IRS 402(g) Total Limit Violations (50+ with catch-up)
    SELECT
        'C02' AS validation_rule,
        'IRS_402G_TOTAL_LIMIT_VIOLATION' AS validation_source,
        'CRITICAL' AS severity,
        1 AS severity_rank,
        COUNT(*) AS violation_count,
        CONCAT(
            'IRS 402(g) total limit violations detected: ',
            COUNT(*), ' employees age 50+ with contributions exceeding $',
            MAX(il.catch_up_limit)
        ) AS validation_message
    FROM base_contribution_data cd
    CROSS JOIN irs_limits il
    WHERE cd.current_age >= il.catch_up_age_threshold
        AND cd.annual_contribution_amount > il.catch_up_limit
    GROUP BY il.catch_up_limit
    HAVING COUNT(*) > 0

    UNION ALL

    -- Rule C03: Contributions Exceed Compensation
    SELECT
        'C03' AS validation_rule,
        'CONTRIBUTIONS_EXCEED_COMPENSATION' AS validation_source,
        'CRITICAL' AS severity,
        1 AS severity_rank,
        COUNT(*) AS violation_count,
        CONCAT(
            'Contributions exceeding compensation detected: ',
            COUNT(*), ' employees with contributions > prorated compensation'
        ) AS validation_message
    FROM base_contribution_data cd
    INNER JOIN workforce_data wd ON cd.employee_id = wd.employee_id
    WHERE cd.annual_contribution_amount > (wd.prorated_annual_compensation + 100)  -- $100 tolerance for rounding
    GROUP BY 1, 2, 3, 4
    HAVING COUNT(*) > 0
),

-- ERROR VALIDATION RULES (High Priority)
error_validations AS (
    -- Rule E01: Contributions Without Enrollment
    SELECT
        'E01' AS validation_rule,
        'CONTRIBUTIONS_WITHOUT_ENROLLMENT' AS validation_source,
        'ERROR' AS severity,
        2 AS severity_rank,
        COUNT(*) AS violation_count,
        'Contributions detected for non-enrolled employees' AS validation_message
    FROM base_contribution_data cd
    WHERE cd.is_enrolled_flag = false
        AND cd.annual_contribution_amount > 10  -- $10 minimum threshold
    GROUP BY 1, 2, 3, 4
    HAVING COUNT(*) > 0

    UNION ALL

    -- Rule E02: IRS Limit Enforcement Mismatch
    SELECT
        'E02' AS validation_rule,
        'IRS_LIMIT_ENFORCEMENT_MISMATCH' AS validation_source,
        'ERROR' AS severity,
        2 AS severity_rank,
        COUNT(*) AS violation_count,
        'IRS limit enforcement logic inconsistency detected' AS validation_message
    FROM base_contribution_data cd
    WHERE (cd.irs_limit_applied = true AND cd.amount_capped_by_irs_limit <= 0)
        OR (cd.irs_limit_applied = false AND cd.amount_capped_by_irs_limit > 0)
    GROUP BY 1, 2, 3, 4
    HAVING COUNT(*) > 0
),

-- INFORMATIONAL VALIDATION RULES (Statistics)
info_validations AS (
    -- Rule I01: Contribution Statistics
    SELECT
        'I01' AS validation_rule,
        'CONTRIBUTION_STATISTICS' AS validation_source,
        'INFO' AS severity,
        4 AS severity_rank,
        1 AS violation_count,  -- Always 1 record for stats
        CONCAT(
            'Contribution Statistics - ',
            'Total Employees: ', COUNT(*),
            ', Enrolled: ', SUM(CASE WHEN cd.is_enrolled_flag THEN 1 ELSE 0 END),
            ', Avg Contribution: $', ROUND(AVG(CASE WHEN cd.is_enrolled_flag THEN cd.annual_contribution_amount ELSE NULL END), 2),
            ', Total Contributions: $', ROUND(SUM(cd.annual_contribution_amount), 2)
        ) AS validation_message
    FROM base_contribution_data cd
    GROUP BY 1, 2, 3, 4
),

-- Combine all validation results
all_validations AS (
    SELECT * FROM critical_validations
    UNION ALL
    SELECT * FROM error_validations
    UNION ALL
    SELECT * FROM info_validations
)

-- Final result with enhanced metadata
SELECT
    {{ simulation_year }} AS simulation_year,
    validation_rule,
    validation_source,
    severity,
    severity_rank,
    violation_count,
    validation_message,
    -- Enhanced metadata for audit trail
    CURRENT_TIMESTAMP AS validation_timestamp,
    '{{ var("scenario_id", "default") }}' AS scenario_id,
    '{{ var("parameter_scenario_id", "default") }}' AS parameter_scenario_id,
    -- Audit trail fields
    CONCAT('DQ-', validation_rule, '-', {{ simulation_year }}, '-', EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::BIGINT) AS audit_record_id,
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
FROM all_validations
ORDER BY severity_rank, validation_rule
