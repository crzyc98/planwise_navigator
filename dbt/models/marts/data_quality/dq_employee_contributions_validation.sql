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
  Employee Contributions Data Quality Validation - Story S025-02

  Comprehensive zero-tolerance data quality validation for employee contribution calculations.
  This model implements rigorous validation rules to ensure:

  - IRS 402(g) limit compliance with zero violations
  - Contributions never exceed compensation
  - Enrollment status consistency
  - Mathematical accuracy of time-weighted calculations
  - Age-based catch-up rule application
  - Period overlap logic validation

  Severity Levels:
  - CRITICAL: Zero tolerance - pipeline fails (IRS violations, data corruption)
  - ERROR: High priority - requires immediate attention (business rule violations)
  - WARNING: Medium priority - investigate and monitor (edge cases, anomalies)
  - INFO: Low priority - informational (metrics, statistics)
*/

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH base_contribution_data AS (
    SELECT *
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
    SELECT *
    FROM {{ ref('irs_contribution_limits') }}
    WHERE plan_year = {{ simulation_year }}
        AND limit_type = 'employee_deferral'
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
            MAX(il.base_limit), ' (under age 50)'
        ) AS validation_message,
        ARRAY_AGG(
            CONCAT('Employee: ', cd.employee_id,
                   ', Age: ', cd.age_as_of_december_31,
                   ', Contributions: $', ROUND(cd.prorated_annual_contributions, 2),
                   ', Limit: $', il.base_limit)
        ) AS violation_details
    FROM base_contribution_data cd
    CROSS JOIN irs_limits il
    WHERE cd.age_as_of_december_31 < il.age_threshold
        AND cd.prorated_annual_contributions > il.base_limit
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
            MAX(il.total_limit)
        ) AS validation_message,
        ARRAY_AGG(
            CONCAT('Employee: ', cd.employee_id,
                   ', Age: ', cd.age_as_of_december_31,
                   ', Contributions: $', ROUND(cd.prorated_annual_contributions, 2),
                   ', Limit: $', il.total_limit)
        ) AS violation_details
    FROM base_contribution_data cd
    CROSS JOIN irs_limits il
    WHERE cd.age_as_of_december_31 >= il.age_threshold
        AND cd.prorated_annual_contributions > il.total_limit
    GROUP BY il.total_limit
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
        ) AS validation_message,
        ARRAY_AGG(
            CONCAT('Employee: ', cd.employee_id,
                   ', Contributions: $', ROUND(cd.prorated_annual_contributions, 2),
                   ', Compensation: $', ROUND(wd.prorated_annual_compensation, 2))
        ) AS violation_details
    FROM base_contribution_data cd
    INNER JOIN workforce_data wd ON cd.employee_id = wd.employee_id
    WHERE cd.prorated_annual_contributions > (wd.prorated_annual_compensation + 100)  -- $100 tolerance for rounding
    GROUP BY 1, 2, 3, 4
    HAVING COUNT(*) > 0

    UNION ALL

    -- Rule C04: Invalid Deferral Rates
    SELECT
        'C04' AS validation_rule,
        'INVALID_DEFERRAL_RATE' AS validation_source,
        'CRITICAL' AS severity,
        1 AS severity_rank,
        COUNT(*) AS violation_count,
        'Invalid deferral rates detected: rates < 0% or > 100%' AS validation_message,
        ARRAY_AGG(
            CONCAT('Employee: ', cd.employee_id,
                   ', Effective Rate: ', ROUND(cd.effective_deferral_rate * 100, 2), '%')
        ) AS violation_details
    FROM base_contribution_data cd
    WHERE cd.effective_deferral_rate < 0
        OR cd.effective_deferral_rate > 1.0
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
        'Contributions detected for non-enrolled employees' AS validation_message,
        ARRAY_AGG(
            CONCAT('Employee: ', cd.employee_id,
                   ', Enrolled: ', cd.is_enrolled,
                   ', Contributions: $', ROUND(cd.prorated_annual_contributions, 2))
        ) AS violation_details
    FROM base_contribution_data cd
    WHERE cd.is_enrolled = false
        AND cd.prorated_annual_contributions > 10  -- $10 minimum threshold
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
        'IRS limit enforcement logic inconsistency detected' AS validation_message,
        ARRAY_AGG(
            CONCAT('Employee: ', cd.employee_id,
                   ', Prorated: $', ROUND(cd.prorated_annual_contributions, 2),
                   ', IRS Limited: $', ROUND(cd.irs_limited_annual_contributions, 2),
                   ', Flag: ', cd.irs_limit_reached)
        ) AS violation_details
    FROM base_contribution_data cd
    WHERE (cd.irs_limited_annual_contributions != cd.prorated_annual_contributions AND cd.irs_limit_reached = false)
        OR (cd.irs_limited_annual_contributions = cd.prorated_annual_contributions AND cd.irs_limit_reached = true)
        OR (cd.excess_contributions > 0 AND cd.irs_limit_reached = false)
        OR (cd.excess_contributions = 0 AND cd.irs_limit_reached = true)
    GROUP BY 1, 2, 3, 4
    HAVING COUNT(*) > 0

    UNION ALL

    -- Rule E03: Age Determination Inconsistency
    SELECT
        'E03' AS validation_rule,
        'AGE_DETERMINATION_INCONSISTENCY' AS validation_source,
        'ERROR' AS severity,
        2 AS severity_rank,
        COUNT(*) AS violation_count,
        'Age determination inconsistency detected between models' AS validation_message,
        ARRAY_AGG(
            CONCAT('Employee: ', cd.employee_id,
                   ', Contrib Age: ', cd.age_as_of_december_31,
                   ', Workforce Age: ', wd.current_age,
                   ', Limit Applied: $', cd.applicable_irs_limit)
        ) AS violation_details
    FROM base_contribution_data cd
    INNER JOIN workforce_data wd ON cd.employee_id = wd.employee_id
    WHERE ABS(cd.age_as_of_december_31 - wd.current_age) > 1  -- Allow 1 year tolerance
    GROUP BY 1, 2, 3, 4
    HAVING COUNT(*) > 0

    UNION ALL

    -- Rule E04: Missing Employee Data
    SELECT
        'E04' AS validation_rule,
        'MISSING_EMPLOYEE_DATA' AS validation_source,
        'ERROR' AS severity,
        2 AS severity_rank,
        COUNT(*) AS violation_count,
        'Enrolled employees missing from contribution calculations' AS validation_message,
        ARRAY_AGG(
            CONCAT('Employee: ', wd.employee_id,
                   ', Enrolled: ', wd.is_enrolled_flag,
                   ', Status: ', wd.employment_status)
        ) AS violation_details
    FROM workforce_data wd
    LEFT JOIN base_contribution_data cd ON wd.employee_id = cd.employee_id
    WHERE wd.is_enrolled_flag = true
        AND wd.employment_status = 'active'
        AND cd.employee_id IS NULL
    GROUP BY 1, 2, 3, 4
    HAVING COUNT(*) > 0
),

-- WARNING VALIDATION RULES (Medium Priority)
warning_validations AS (
    -- Rule W01: High Deferral Rates
    SELECT
        'W01' AS validation_rule,
        'HIGH_DEFERRAL_RATES' AS validation_source,
        'WARNING' AS severity,
        3 AS severity_rank,
        COUNT(*) AS violation_count,
        'High deferral rates detected (>50% of compensation)' AS validation_message,
        ARRAY_AGG(
            CONCAT('Employee: ', cd.employee_id,
                   ', Rate: ', ROUND(cd.effective_deferral_rate * 100, 2), '%',
                   ', Contributions: $', ROUND(cd.prorated_annual_contributions, 2))
        ) AS violation_details
    FROM base_contribution_data cd
    WHERE cd.effective_deferral_rate > 0.50
    GROUP BY 1, 2, 3, 4
    HAVING COUNT(*) > 0

    UNION ALL

    -- Rule W02: Catch-up Eligible Near Limit
    SELECT
        'W02' AS validation_rule,
        'CATCHUP_ELIGIBLE_NEAR_LIMIT' AS validation_source,
        'WARNING' AS severity,
        3 AS severity_rank,
        COUNT(*) AS violation_count,
        'Catch-up eligible employees near contribution limits' AS validation_message,
        ARRAY_AGG(
            CONCAT('Employee: ', cd.employee_id,
                   ', Age: ', cd.age_as_of_december_31,
                   ', Contributions: $', ROUND(cd.prorated_annual_contributions, 2),
                   ', Limit: $', cd.applicable_irs_limit,
                   ', Remaining: $', ROUND(cd.applicable_irs_limit - cd.prorated_annual_contributions, 2))
        ) AS violation_details
    FROM base_contribution_data cd
    CROSS JOIN irs_limits il
    WHERE cd.age_as_of_december_31 >= il.age_threshold
        AND cd.prorated_annual_contributions > (cd.applicable_irs_limit * 0.90)  -- Within 90% of limit
        AND cd.prorated_annual_contributions <= cd.applicable_irs_limit
    GROUP BY 1, 2, 3, 4
    HAVING COUNT(*) > 0

    UNION ALL

    -- Rule W03: Unusual Contribution Patterns
    SELECT
        'W03' AS validation_rule,
        'UNUSUAL_CONTRIBUTION_PATTERNS' AS validation_source,
        'WARNING' AS severity,
        3 AS severity_rank,
        COUNT(*) AS violation_count,
        'Unusual contribution patterns detected (very small amounts)' AS validation_message,
        ARRAY_AGG(
            CONCAT('Employee: ', cd.employee_id,
                   ', Contributions: $', ROUND(cd.prorated_annual_contributions, 2),
                   ', Periods: ', cd.contribution_periods_count)
        ) AS violation_details
    FROM base_contribution_data cd
    WHERE cd.prorated_annual_contributions > 0
        AND cd.prorated_annual_contributions < 100  -- Less than $100 annually
        AND cd.is_enrolled = true
    GROUP BY 1, 2, 3, 4
    HAVING COUNT(*) > 0
),

-- INFORMATIONAL VALIDATION RULES (Low Priority)
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
            ', Enrolled: ', SUM(CASE WHEN cd.is_enrolled THEN 1 ELSE 0 END),
            ', Avg Contribution: $', ROUND(AVG(CASE WHEN cd.is_enrolled THEN cd.prorated_annual_contributions ELSE NULL END), 2),
            ', Total Contributions: $', ROUND(SUM(cd.prorated_annual_contributions), 2)
        ) AS validation_message,
        ARRAY[CONCAT(
            'Age 50+ Count: ', SUM(CASE WHEN cd.age_as_of_december_31 >= 50 THEN 1 ELSE 0 END),
            ', At Limit Count: ', SUM(CASE WHEN cd.irs_limit_reached THEN 1 ELSE 0 END),
            ', Avg Effective Rate: ', ROUND(AVG(CASE WHEN cd.is_enrolled THEN cd.effective_deferral_rate ELSE NULL END) * 100, 2), '%'
        )] AS violation_details
    FROM base_contribution_data cd
    GROUP BY 1, 2, 3, 4
),

-- Additional CRITICAL validation rules for enhanced compliance
critical_validations_extended AS (
    -- Rule C05: Data Corruption Detection
    SELECT
        'C05' AS validation_rule,
        'DATA_CORRUPTION_DETECTION' AS validation_source,
        'CRITICAL' AS severity,
        1 AS severity_rank,
        COUNT(*) AS violation_count,
        'Critical data corruption detected in contribution calculations' AS validation_message,
        ARRAY_AGG(
            CONCAT('Employee: ', cd.employee_id,
                   ', Issue: ', cd.data_quality_flag,
                   ', Contributions: $', ROUND(cd.prorated_annual_contributions, 2))
        ) AS violation_details
    FROM base_contribution_data cd
    WHERE cd.data_quality_flag != 'VALID'
        AND cd.data_quality_flag IN ('INVALID_EMPLOYEE_ID', 'CONTRIBUTIONS_EXCEED_COMPENSATION', 'IRS_LIMIT_MISMATCH')
    GROUP BY 1, 2, 3, 4
    HAVING COUNT(*) > 0

    UNION ALL

    -- Rule C06: Event Sourcing Integrity Violation
    SELECT
        'C06' AS validation_rule,
        'EVENT_SOURCING_INTEGRITY_VIOLATION' AS validation_source,
        'CRITICAL' AS severity,
        1 AS severity_rank,
        COUNT(*) AS violation_count,
        'Event sourcing integrity violations detected - contribution data without supporting events' AS validation_message,
        ARRAY_AGG(
            CONCAT('Employee: ', cd.employee_id,
                   ', Contributions: $', ROUND(cd.prorated_annual_contributions, 2),
                   ', Periods: ', cd.contribution_periods_count)
        ) AS violation_details
    FROM base_contribution_data cd
    LEFT JOIN {{ ref('fct_yearly_events') }} ye
        ON cd.employee_id = ye.employee_id
        AND ye.simulation_year = {{ simulation_year }}
        AND ye.event_type IN ('enrollment', 'enrollment_change')
    WHERE cd.prorated_annual_contributions > 100
        AND ye.employee_id IS NULL
        AND cd.is_enrolled = true
    GROUP BY 1, 2, 3, 4
    HAVING COUNT(*) > 0
),

-- Enhanced ERROR validation rules
error_validations_extended AS (
    -- Rule E05: Cross-Year Consistency Validation
    SELECT
        'E05' AS validation_rule,
        'CROSS_YEAR_CONSISTENCY_VIOLATION' AS validation_source,
        'ERROR' AS severity,
        2 AS severity_rank,
        COUNT(*) AS violation_count,
        'Cross-year contribution consistency violations detected' AS validation_message,
        ARRAY_AGG(
            CONCAT('Employee: ', cd.employee_id,
                   ', Current: $', ROUND(cd.prorated_annual_contributions, 2),
                   ', YTD Flag: ', cd.years_since_first_enrollment)
        ) AS violation_details
    FROM base_contribution_data cd
    WHERE cd.years_since_first_enrollment > 0
        AND cd.prorated_annual_contributions > 0
        AND cd.enrollment_date IS NULL  -- Missing enrollment tracking
    GROUP BY 1, 2, 3, 4
    HAVING COUNT(*) > 0

    UNION ALL

    -- Rule E06: Enrollment State Accumulator Mismatch
    SELECT
        'E06' AS validation_rule,
        'ENROLLMENT_ACCUMULATOR_MISMATCH' AS validation_source,
        'ERROR' AS severity,
        2 AS severity_rank,
        COUNT(*) AS violation_count,
        'Enrollment state accumulator consistency violations' AS validation_message,
        ARRAY_AGG(
            CONCAT('Employee: ', cd.employee_id,
                   ', Contrib Enrolled: ', cd.is_enrolled,
                   ', Accum Enrolled: ', esa.enrollment_status,
                   ', Contributions: $', ROUND(cd.prorated_annual_contributions, 2))
        ) AS violation_details
    FROM base_contribution_data cd
    LEFT JOIN {{ ref('int_enrollment_state_accumulator') }} esa
        ON cd.employee_id = esa.employee_id
        AND esa.simulation_year = {{ simulation_year }}
    WHERE (cd.is_enrolled != esa.enrollment_status)
        AND cd.prorated_annual_contributions > 10
    GROUP BY 1, 2, 3, 4
    HAVING COUNT(*) > 0
),

-- Enhanced WARNING validation rules
warning_validations_extended AS (
    -- Rule W04: Performance Anomaly Detection
    SELECT
        'W04' AS validation_rule,
        'PERFORMANCE_ANOMALY_DETECTION' AS validation_source,
        'WARNING' AS severity,
        3 AS severity_rank,
        1 AS violation_count,
        CONCAT(
            'Performance anomalies detected - ',
            'Avg calc time per employee may be excessive, ',
            'Total records processed: ', COUNT(*)
        ) AS validation_message,
        ARRAY[
            CONCAT(
                'Complex periods detected: ',
                SUM(CASE WHEN cd.contribution_periods_count > 5 THEN 1 ELSE 0 END),
                ' employees with >5 periods'
            )
        ] AS violation_details
    FROM base_contribution_data cd
    GROUP BY 1, 2, 3, 4
    HAVING COUNT(*) > 10000  -- Flag for large datasets

    UNION ALL

    -- Rule W05: Regulatory Compliance Risk
    SELECT
        'W05' AS validation_rule,
        'REGULATORY_COMPLIANCE_RISK' AS validation_source,
        'WARNING' AS severity,
        3 AS severity_rank,
        COUNT(*) AS violation_count,
        'Employees approaching IRS limits requiring compliance monitoring' AS validation_message,
        ARRAY_AGG(
            CONCAT('Employee: ', cd.employee_id,
                   ', Utilization: ', ROUND((cd.prorated_annual_contributions / cd.applicable_irs_limit) * 100, 1), '%',
                   ', Remaining: $', ROUND(cd.applicable_irs_limit - cd.prorated_annual_contributions, 2))
        ) AS violation_details
    FROM base_contribution_data cd
    WHERE cd.prorated_annual_contributions > (cd.applicable_irs_limit * 0.85)  -- Within 85% of limit
        AND NOT cd.irs_limit_reached
    GROUP BY 1, 2, 3, 4
    HAVING COUNT(*) > 0
),

-- Enhanced INFO validation rules for comprehensive reporting
info_validations_extended AS (
    -- Rule I02: Detailed Performance Metrics
    SELECT
        'I02' AS validation_rule,
        'DETAILED_PERFORMANCE_METRICS' AS validation_source,
        'INFO' AS severity,
        4 AS severity_rank,
        1 AS violation_count,
        CONCAT(
            'Performance Metrics - ',
            'Complex Calculations: ', SUM(CASE WHEN cd.contribution_periods_count > 3 THEN 1 ELSE 0 END),
            ', Simple Calculations: ', SUM(CASE WHEN cd.contribution_periods_count <= 3 THEN 1 ELSE 0 END),
            ', Processing Time Category: ',
            CASE
                WHEN COUNT(*) > 50000 THEN 'LARGE_BATCH'
                WHEN COUNT(*) > 10000 THEN 'MEDIUM_BATCH'
                ELSE 'SMALL_BATCH'
            END
        ) AS validation_message,
        ARRAY[
            CONCAT(
                'Memory Usage Indicator: ',
                CASE
                    WHEN AVG(cd.contribution_periods_count) > 4 THEN 'HIGH'
                    WHEN AVG(cd.contribution_periods_count) > 2 THEN 'MEDIUM'
                    ELSE 'LOW'
                END,
                ', Avg Periods: ', ROUND(AVG(cd.contribution_periods_count), 2)
            )
        ] AS violation_details
    FROM base_contribution_data cd
    GROUP BY 1, 2, 3, 4

    UNION ALL

    -- Rule I03: Regulatory Compliance Summary
    SELECT
        'I03' AS validation_rule,
        'REGULATORY_COMPLIANCE_SUMMARY' AS validation_source,
        'INFO' AS severity,
        4 AS severity_rank,
        1 AS violation_count,
        CONCAT(
            'Compliance Summary - ',
            'HCE Count: ', SUM(CASE WHEN cd.prorated_annual_contributions > 15000 THEN 1 ELSE 0 END),
            ', At Limit: ', SUM(CASE WHEN cd.irs_limit_reached THEN 1 ELSE 0 END),
            ', Catch-up Eligible: ', SUM(CASE WHEN cd.age_as_of_december_31 >= 50 THEN 1 ELSE 0 END),
            ', Total Plan Assets: $', ROUND(SUM(cd.prorated_annual_contributions), 0)
        ) AS validation_message,
        ARRAY[
            CONCAT(
                'Plan Health Indicators - ',
                'Participation Rate: ', ROUND((SUM(CASE WHEN cd.is_enrolled THEN 1 ELSE 0 END)::DECIMAL / COUNT(*)) * 100, 1), '%, ',
                'Avg Deferral Rate: ', ROUND(AVG(CASE WHEN cd.is_enrolled THEN cd.effective_deferral_rate ELSE NULL END) * 100, 2), '%, ',
                'Diversification Score: ',
                CASE
                    WHEN STDDEV(cd.prorated_annual_contributions) > 5000 THEN 'HIGH'
                    WHEN STDDEV(cd.prorated_annual_contributions) > 2000 THEN 'MEDIUM'
                    ELSE 'LOW'
                END
            )
        ] AS violation_details
    FROM base_contribution_data cd
    GROUP BY 1, 2, 3, 4
),

-- Combine all validation results
all_validations AS (
    SELECT * FROM critical_validations
    UNION ALL
    SELECT * FROM critical_validations_extended
    UNION ALL
    SELECT * FROM error_validations
    UNION ALL
    SELECT * FROM error_validations_extended
    UNION ALL
    SELECT * FROM warning_validations
    UNION ALL
    SELECT * FROM warning_validations_extended
    UNION ALL
    SELECT * FROM info_validations
    UNION ALL
    SELECT * FROM info_validations_extended
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
    violation_details,
    -- Enhanced metadata for audit trail
    CURRENT_TIMESTAMP AS validation_timestamp,
    '{{ var("scenario_id", "default") }}' AS scenario_id,
    '{{ var("parameter_scenario_id", "default") }}' AS parameter_scenario_id,
    -- Audit trail fields
    CONCAT('DQ-', validation_rule, '-', {{ simulation_year }}, '-', EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::BIGINT) AS audit_record_id,
    'dbt_' || '{{ var("dbt_version", "unknown") }}' AS validation_engine_version,
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
    END AS regulatory_impact,
    -- Data lineage tracking
    'int_employee_contributions' AS primary_source_model,
    ARRAY['fct_yearly_events', 'int_enrollment_state_accumulator', 'irs_contribution_limits'] AS dependency_models
FROM all_validations
ORDER BY severity_rank, validation_rule
