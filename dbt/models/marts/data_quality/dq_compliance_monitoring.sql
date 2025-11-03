{{config(enabled=false)}}

{{ config(
    materialized='table',
    indexes=[
        {'columns': ['simulation_year'], 'type': 'btree'},
        {'columns': ['compliance_category'], 'type': 'btree'},
        {'columns': ['risk_level'], 'type': 'btree'},
        {'columns': ['regulatory_deadline'], 'type': 'btree'}
    ],
    tags=['compliance', 'regulatory', 'irs_monitoring', 'critical']
) }}

/*
  Comprehensive Compliance Monitoring Framework - Story S025-02

  Implements enterprise-grade regulatory compliance monitoring for DC plan
  contribution calculations with specific focus on IRS requirements.

  Compliance Areas Monitored:
  - IRS 402(g) Employee Deferral Limits (Zero Tolerance)
  - IRS 401(a)(17) Compensation Limits
  - Age-based Catch-up Contribution Rules
  - Plan Document Compliance Requirements
  - Anti-Discrimination Testing Preparation
  - Excess Contribution Detection and Remediation

  Regulatory Framework:
  - SOX Section 404 Internal Controls
  - ERISA Fiduciary Responsibilities
  - IRS Plan Administration Requirements
  - DOL Reporting and Disclosure Rules

  Risk Management:
  - Automated violation detection with immediate alerting
  - Trend analysis for proactive compliance management
  - Regulatory deadline tracking with advance warnings
  - Audit trail maintenance for regulatory examinations
*/

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH irs_contribution_limits AS (
    SELECT
        limit_year,
        catch_up_age_threshold,
        base_limit,
        catch_up_limit,
        -- For reporting, treat total_limit as catch_up_limit for eligible employees
        catch_up_limit AS total_limit
    FROM {{ ref('irs_contribution_limits') }}
    WHERE limit_year = {{ simulation_year }}
    LIMIT 1
),

contribution_data AS (
    SELECT
        employee_id,
        simulation_year,
        -- Map to expected names
        annual_contribution_amount AS prorated_annual_contributions,
        annual_contribution_amount AS irs_limited_annual_contributions,
        GREATEST(0, requested_contribution_amount - annual_contribution_amount) AS excess_contributions,
        effective_annual_deferral_rate AS effective_deferral_rate,
        current_age AS age_as_of_december_31,
        applicable_irs_limit,
        irs_limit_applied AS irs_limit_reached,
        is_enrolled_flag AS is_enrolled,
        prorated_annual_compensation,
        employment_status,
        data_quality_flag
    FROM {{ ref('int_employee_contributions') }}
    WHERE simulation_year = {{ simulation_year }}
),

validation_results AS (
    SELECT
        validation_rule,
        validation_source,
        severity,
        violation_count,
        validation_message,
        risk_level,
        regulatory_impact
    FROM {{ ref('dq_employee_contributions_validation') }}
    WHERE simulation_year = {{ simulation_year }}
),

-- IRS 402(g) Compliance Monitoring
irs_402g_compliance AS (
    SELECT
        'IRS_402G_COMPLIANCE' AS compliance_category,
        'IRS Section 402(g) Employee Deferral Limits' AS compliance_description,

        -- Critical metrics
        COUNT(*) AS total_employees,
        SUM(CASE WHEN cd.is_enrolled THEN 1 ELSE 0 END) AS enrolled_employees,
        SUM(CASE WHEN cd.irs_limit_reached THEN 1 ELSE 0 END) AS employees_at_limit,
        SUM(CASE WHEN cd.excess_contributions > 0 THEN 1 ELSE 0 END) AS employees_with_excess,

        -- Violation tracking
        SUM(CASE WHEN cd.prorated_annual_contributions > cd.applicable_irs_limit THEN 1 ELSE 0 END) AS limit_violations,
        SUM(cd.excess_contributions) AS total_excess_contributions,

        -- Age-based analysis
        SUM(CASE WHEN cd.age_as_of_december_31 >= 50 THEN 1 ELSE 0 END) AS catch_up_eligible_count,
        SUM(CASE WHEN cd.age_as_of_december_31 >= 50 AND cd.irs_limit_reached THEN 1 ELSE 0 END) AS catch_up_at_limit,

        -- Risk indicators
        MAX(cd.excess_contributions) AS max_individual_excess,
        AVG(CASE WHEN cd.is_enrolled THEN cd.effective_deferral_rate ELSE NULL END) AS avg_deferral_rate,

        -- Compliance status
        CASE
            WHEN SUM(CASE WHEN cd.prorated_annual_contributions > cd.applicable_irs_limit THEN 1 ELSE 0 END) = 0
            THEN 'COMPLIANT'
            ELSE 'VIOLATIONS_DETECTED'
        END AS compliance_status,

        CASE
            WHEN SUM(CASE WHEN cd.prorated_annual_contributions > cd.applicable_irs_limit THEN 1 ELSE 0 END) = 0
            THEN 'LOW'
            WHEN SUM(cd.excess_contributions) > 50000
            THEN 'HIGH'
            ELSE 'MEDIUM'
        END AS risk_level,

        -- Regulatory deadlines (IRS correction deadlines)
        MAKE_DATE({{ simulation_year }}, 4, 15) AS primary_correction_deadline,
        MAKE_DATE({{ simulation_year }}, 12, 31) AS plan_year_end_deadline,

        il.base_limit,
        il.catch_up_limit,
        il.total_limit

    FROM contribution_data cd
    CROSS JOIN irs_contribution_limits il
    GROUP BY il.base_limit, il.catch_up_limit, il.total_limit
),

-- Compensation Limit Compliance (IRS 401(a)(17))
compensation_limit_compliance AS (
    SELECT
        'COMPENSATION_LIMIT_COMPLIANCE' AS compliance_category,
        'IRS Section 401(a)(17) Compensation Limits' AS compliance_description,

        -- Metrics (placeholder - would need IRS 401(a)(17) limits)
        COUNT(*) AS total_employees,
        SUM(CASE WHEN cd.prorated_annual_compensation > 350000 THEN 1 ELSE 0 END) AS high_compensation_count,
        MAX(cd.prorated_annual_compensation) AS max_compensation,
        AVG(cd.prorated_annual_compensation) AS avg_compensation,

        -- Compliance indicators
        SUM(CASE WHEN cd.prorated_annual_compensation > 350000 THEN 1 ELSE 0 END) AS potential_violations,
        0 AS total_excess_contributions,  -- Placeholder

        0 AS catch_up_eligible_count,  -- Not applicable
        0 AS catch_up_at_limit,  -- Not applicable
        0 AS max_individual_excess,  -- Not applicable
        NULL AS avg_deferral_rate,  -- Not applicable for compensation limits

        'REQUIRES_MANUAL_REVIEW' AS compliance_status,
        'MEDIUM' AS risk_level,

        MAKE_DATE({{ simulation_year }}, 4, 15) AS primary_correction_deadline,
        MAKE_DATE({{ simulation_year }}, 12, 31) AS plan_year_end_deadline,

        -- Placeholder limits
        350000 AS base_limit,
        0 AS catch_up_limit,
        350000 AS total_limit

    FROM contribution_data cd
),

-- Data Quality Compliance Monitoring
data_quality_compliance AS (
    SELECT
        'DATA_QUALITY_COMPLIANCE' AS compliance_category,
        'Data Integrity and Calculation Accuracy' AS compliance_description,

        (SELECT COUNT(*) FROM contribution_data) AS total_employees,
        (SELECT COUNT(*) FROM contribution_data WHERE is_enrolled = true) AS enrolled_employees,
        0 AS employees_at_limit,  -- Not applicable

        -- Critical data quality metrics
        SUM(CASE WHEN vr.severity = 'CRITICAL' THEN vr.violation_count ELSE 0 END) AS limit_violations,
        SUM(CASE WHEN vr.severity = 'ERROR' THEN vr.violation_count ELSE 0 END) AS total_excess_contributions,

        0 AS catch_up_eligible_count,  -- Not applicable
        0 AS catch_up_at_limit,  -- Not applicable
        MAX(CASE WHEN vr.severity = 'CRITICAL' THEN vr.violation_count ELSE 0 END) AS max_individual_excess,
        NULL AS avg_deferral_rate,  -- Not applicable

        CASE
            WHEN SUM(CASE WHEN vr.severity = 'CRITICAL' AND vr.violation_count > 0 THEN 1 ELSE 0 END) = 0
            THEN 'COMPLIANT'
            ELSE 'VIOLATIONS_DETECTED'
        END AS compliance_status,

        CASE
            WHEN SUM(CASE WHEN vr.severity = 'CRITICAL' AND vr.violation_count > 0 THEN 1 ELSE 0 END) = 0
            THEN 'LOW'
            WHEN SUM(CASE WHEN vr.severity IN ('CRITICAL', 'ERROR') AND vr.violation_count > 0 THEN 1 ELSE 0 END) > 3
            THEN 'HIGH'
            ELSE 'MEDIUM'
        END AS risk_level,

        CURRENT_DATE AS primary_correction_deadline,  -- Immediate for data quality
        MAKE_DATE({{ simulation_year }}, 12, 31) AS plan_year_end_deadline,

        0 AS base_limit,  -- Not applicable
        0 AS catch_up_limit,  -- Not applicable
        0 AS total_limit  -- Not applicable

    FROM validation_results vr
    WHERE vr.regulatory_impact = true
),

-- Plan Administration Compliance
plan_administration_compliance AS (
    SELECT
        'PLAN_ADMINISTRATION_COMPLIANCE' AS compliance_category,
        'Plan Document and Administrative Compliance' AS compliance_description,

        COUNT(*) AS total_employees,
        SUM(CASE WHEN cd.is_enrolled THEN 1 ELSE 0 END) AS enrolled_employees,
        0 AS employees_at_limit,  -- Calculated below

        -- Administrative compliance metrics
        SUM(CASE WHEN cd.data_quality_flag != 'VALID' THEN 1 ELSE 0 END) AS limit_violations,
        0 AS total_excess_contributions,  -- Not applicable

        0 AS catch_up_eligible_count,  -- Not applicable here
        0 AS catch_up_at_limit,  -- Not applicable here
        0 AS max_individual_excess,  -- Not applicable
        AVG(CASE WHEN cd.is_enrolled THEN cd.effective_deferral_rate ELSE NULL END) AS avg_deferral_rate,

        CASE
            WHEN SUM(CASE WHEN cd.data_quality_flag != 'VALID' THEN 1 ELSE 0 END) = 0
            THEN 'COMPLIANT'
            ELSE 'ADMINISTRATIVE_ISSUES'
        END AS compliance_status,

        CASE
            WHEN SUM(CASE WHEN cd.data_quality_flag != 'VALID' THEN 1 ELSE 0 END) = 0
            THEN 'LOW'
            WHEN SUM(CASE WHEN cd.data_quality_flag != 'VALID' THEN 1 ELSE 0 END) > 10
            THEN 'HIGH'
            ELSE 'MEDIUM'
        END AS risk_level,

        MAKE_DATE({{ simulation_year }}, 3, 31) AS primary_correction_deadline,  -- Form 5500 deadline
        MAKE_DATE({{ simulation_year }}, 12, 31) AS plan_year_end_deadline,

        0 AS base_limit,  -- Not applicable
        0 AS catch_up_limit,  -- Not applicable
        0 AS total_limit  -- Not applicable

    FROM contribution_data cd
),

-- Combined compliance monitoring results
combined_compliance AS (
    SELECT * FROM irs_402g_compliance
    UNION ALL
    SELECT * FROM compensation_limit_compliance
    UNION ALL
    SELECT * FROM data_quality_compliance
    UNION ALL
    SELECT * FROM plan_administration_compliance
)

-- Final compliance monitoring output
SELECT
    {{ simulation_year }} AS simulation_year,
    cc.compliance_category,
    cc.compliance_description,

    -- Employee and participation metrics
    cc.total_employees,
    cc.enrolled_employees,
    ROUND((cc.enrolled_employees::DECIMAL / NULLIF(cc.total_employees, 0)) * 100, 2) AS participation_rate,

    -- Compliance violation metrics
    cc.limit_violations AS violation_count,
    cc.employees_at_limit,
    cc.employees_with_excess,
    cc.total_excess_contributions,

    -- Risk assessment
    cc.compliance_status,
    cc.risk_level,
    CASE cc.risk_level
        WHEN 'HIGH' THEN 1
        WHEN 'MEDIUM' THEN 2
        WHEN 'LOW' THEN 3
        ELSE 4
    END AS risk_priority,

    -- Age-based analysis (where applicable)
    cc.catch_up_eligible_count,
    cc.catch_up_at_limit,
    CASE
        WHEN cc.catch_up_eligible_count > 0
        THEN ROUND((cc.catch_up_at_limit::DECIMAL / cc.catch_up_eligible_count) * 100, 2)
        ELSE NULL
    END AS catch_up_utilization_rate,

    -- Financial impact
    cc.max_individual_excess,
    cc.avg_deferral_rate,

    -- IRS limits (where applicable)
    CASE WHEN cc.base_limit > 0 THEN cc.base_limit ELSE NULL END AS irs_base_limit,
    CASE WHEN cc.catch_up_limit > 0 THEN cc.catch_up_limit ELSE NULL END AS irs_catch_up_limit,
    CASE WHEN cc.total_limit > 0 THEN cc.total_limit ELSE NULL END AS irs_total_limit,

    -- Regulatory deadlines and timeline management
    cc.primary_correction_deadline,
    cc.plan_year_end_deadline,
    DATE_DIFF('day', CURRENT_DATE, cc.primary_correction_deadline) AS days_to_primary_deadline,
    DATE_DIFF('day', CURRENT_DATE, cc.plan_year_end_deadline) AS days_to_year_end,

    -- Action required flags
    CASE
        WHEN cc.compliance_status IN ('VIOLATIONS_DETECTED', 'ADMINISTRATIVE_ISSUES')
        THEN 'IMMEDIATE_ACTION_REQUIRED'
        WHEN cc.risk_level = 'HIGH'
        THEN 'HIGH_PRIORITY_REVIEW'
        WHEN DATE_DIFF('day', CURRENT_DATE, cc.primary_correction_deadline) <= 30
        THEN 'DEADLINE_APPROACHING'
        ELSE 'MONITORING_REQUIRED'
    END AS action_required,

    -- Attestation and audit trail
    'AUTOMATED_COMPLIANCE_MONITORING' AS monitoring_method,
    CURRENT_TIMESTAMP AS compliance_check_timestamp,
    '{{ var("scenario_id", "default") }}' AS scenario_id,
    CONCAT('COMPLIANCE-', cc.compliance_category, '-', {{ simulation_year }}, '-',
           EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::BIGINT) AS compliance_record_id,

    -- Documentation and regulatory framework
    'SOX_404_INTERNAL_CONTROLS' AS regulatory_framework,
    ARRAY[
        'IRS_SECTION_401_402',
        'ERISA_FIDUCIARY_RESPONSIBILITY',
        'DOL_REPORTING_DISCLOSURE',
        'PLAN_DOCUMENT_COMPLIANCE'
    ] AS applicable_regulations,

    -- Executive summary metrics
    CASE
        WHEN cc.compliance_status = 'COMPLIANT' AND cc.risk_level = 'LOW'
        THEN 'GREEN'
        WHEN cc.compliance_status IN ('VIOLATIONS_DETECTED', 'ADMINISTRATIVE_ISSUES')
        THEN 'RED'
        ELSE 'YELLOW'
    END AS executive_status_indicator

FROM combined_compliance cc
ORDER BY
    CASE cc.risk_level
        WHEN 'HIGH' THEN 1
        WHEN 'MEDIUM' THEN 2
        WHEN 'LOW' THEN 3
        ELSE 4
    END,
    cc.compliance_category
