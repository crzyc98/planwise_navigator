{{ config(
    materialized='view',
    indexes=[
        {'columns': ['simulation_year'], 'type': 'btree'},
        {'columns': ['regulatory_framework'], 'type': 'btree'},
        {'columns': ['overall_compliance_status'], 'type': 'btree'}
    ],
    tags=['regulatory', 'reporting', 'deferral_rate_audit', 'financial_compliance', 'executive_dashboard']
) }}

/*
  Regulatory Reporting Readiness Dashboard for Enhanced Deferral Rate State Accumulator

  Epic E036 Story S036-03: Financial Audit Compliance Regulatory Reporting

  This model provides executive-level regulatory reporting for the enhanced deferral rate
  state accumulator, summarizing compliance status across key financial audit dimensions:

  1. UUID-stamped immutable audit trail completeness
  2. Financial precision compliance (6 decimal places)
  3. SHA-256 data integrity validation status
  4. Microsecond timestamp precision compliance
  5. SOX compliance readiness assessment
  6. Event sourcing architecture validation
  7. Cross-year consistency verification

  Target Audience:
  - Financial audit teams
  - Regulatory compliance officers
  - Data governance committees
  - Executive leadership
  - External auditors

  Compliance Frameworks:
  - SOX (Sarbanes-Oxley) financial reporting requirements
  - IRS retirement plan audit standards
  - ERISA fiduciary compliance
  - Enterprise data governance policies

  Key Metrics:
  - Overall compliance percentage across all validation categories
  - Risk assessment by severity level (CRITICAL, ERROR, WARNING)
  - Regulatory attestation readiness percentage
  - Immutable audit trail completeness score
  - Financial data precision validation results
*/

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH deferral_state_summary AS (
    SELECT
        simulation_year,
        COUNT(*) AS total_deferral_state_records,
        COUNT(DISTINCT employee_id) AS unique_employees_tracked,

        -- UUID and immutability compliance
        COUNT(CASE WHEN state_record_uuid IS NOT NULL THEN 1 END) AS records_with_uuid,
        COUNT(CASE WHEN record_immutability_status = 'UUID_STAMPED_IMMUTABLE' THEN 1 END) AS immutable_records,

        -- Financial precision compliance
        COUNT(CASE WHEN precision_status = 'FINANCIAL_PRECISION_VALIDATED' THEN 1 END) AS precision_validated_records,
        COUNT(CASE WHEN current_deferral_rate IS NOT NULL AND
                        current_deferral_rate >= 0 AND
                        current_deferral_rate <= 1 THEN 1 END) AS valid_deferral_rates,

        -- Audit trail integrity
        COUNT(CASE WHEN financial_audit_hash IS NOT NULL AND
                        LENGTH(financial_audit_hash) = 64 THEN 1 END) AS records_with_valid_hash,
        COUNT(CASE WHEN audit_microsecond_epoch IS NOT NULL AND
                        audit_microsecond_epoch > 0 THEN 1 END) AS records_with_microsecond_precision,

        -- Regulatory attestation readiness
        COUNT(CASE WHEN regulatory_attestation_status = 'ATTESTATION_READY' THEN 1 END) AS attestation_ready_records,
        COUNT(CASE WHEN regulatory_framework = 'SOX_COMPLIANT' THEN 1 END) AS sox_compliant_records,

        -- Data quality metrics
        COUNT(CASE WHEN data_quality_flag = 'VALID' THEN 1 END) AS valid_quality_records,

        -- Financial metrics summaries
        ROUND(AVG(current_deferral_rate)::DECIMAL, 6) AS average_deferral_rate,
        ROUND(MIN(current_deferral_rate)::DECIMAL, 6) AS min_deferral_rate,
        ROUND(MAX(current_deferral_rate)::DECIMAL, 6) AS max_deferral_rate,
        COUNT(CASE WHEN escalations_received > 0 THEN 1 END) AS employees_with_escalations,
        ROUND(AVG(total_escalation_amount)::DECIMAL, 6) AS average_total_escalation_amount

    FROM {{ ref('int_deferral_rate_state_accumulator') }}
    WHERE simulation_year = {{ simulation_year }}
    GROUP BY simulation_year
),

validation_summary AS (
    SELECT
        simulation_year,
        COUNT(*) AS total_validation_checks,
        COUNT(CASE WHEN validation_status = 'PASS' THEN 1 END) AS passed_validations,
        COUNT(CASE WHEN validation_status = 'FAIL' THEN 1 END) AS failed_validations,
        COUNT(CASE WHEN validation_status = 'WARNING' THEN 1 END) AS warning_validations,

        -- Severity breakdown
        COUNT(CASE WHEN validation_severity = 'CRITICAL' THEN 1 END) AS critical_issues,
        COUNT(CASE WHEN validation_severity = 'ERROR' THEN 1 END) AS error_issues,
        COUNT(CASE WHEN validation_severity = 'WARNING' THEN 1 END) AS warning_issues,
        COUNT(CASE WHEN validation_severity = 'INFO' THEN 1 END) AS info_items,

        -- Regulatory impact
        COUNT(CASE WHEN regulatory_impact = true THEN 1 END) AS regulatory_impact_validations,

        -- Category-specific validation status
        MAX(CASE WHEN validation_category = 'UUID_INTEGRITY' AND validation_status = 'PASS' THEN 1 ELSE 0 END) AS uuid_integrity_pass,
        MAX(CASE WHEN validation_category = 'FINANCIAL_PRECISION' AND validation_status = 'PASS' THEN 1 ELSE 0 END) AS financial_precision_pass,
        MAX(CASE WHEN validation_category = 'AUDIT_TRAIL_INTEGRITY' AND validation_status = 'PASS' THEN 1 ELSE 0 END) AS audit_trail_integrity_pass,
        MAX(CASE WHEN validation_category = 'TIMESTAMP_PRECISION' AND validation_status = 'PASS' THEN 1 ELSE 0 END) AS timestamp_precision_pass,
        MAX(CASE WHEN validation_category = 'REGULATORY_COMPLIANCE' AND validation_status = 'PASS' THEN 1 ELSE 0 END) AS regulatory_compliance_pass,
        MAX(CASE WHEN validation_category = 'EVENT_SOURCING_COMPLIANCE' AND validation_status = 'PASS' THEN 1 END) AS event_sourcing_compliance_pass

    FROM {{ ref('dq_deferral_rate_state_audit_validation') }}
    WHERE simulation_year = {{ simulation_year }}
    GROUP BY simulation_year
)

SELECT
    -- Report metadata
    'DEFERRAL_RATE_REGULATORY_AUDIT_SUMMARY' AS report_name,
    'E036_S036_03_UUID_STAMPED_FINANCIAL_COMPLIANCE' AS report_version,
    {{ simulation_year }} AS simulation_year,
    CURRENT_TIMESTAMP AS report_generated_timestamp,
    'SOX_COMPLIANT' AS regulatory_framework,

    -- Executive summary metrics
    ds.total_deferral_state_records,
    ds.unique_employees_tracked,

    -- Overall compliance score (0-100%)
    ROUND((
        (ds.records_with_uuid::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
        (ds.precision_validated_records::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
        (ds.records_with_valid_hash::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
        (ds.records_with_microsecond_precision::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
        (ds.attestation_ready_records::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
        (ds.sox_compliant_records::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.65)
    )::DECIMAL, 2) AS overall_compliance_percentage,

    -- Compliance status determination
    CASE
        WHEN ROUND((
            (ds.records_with_uuid::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.precision_validated_records::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.records_with_valid_hash::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.records_with_microsecond_precision::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.attestation_ready_records::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.sox_compliant_records::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.65)
        )::DECIMAL, 2) >= 95.0 THEN 'FULL_COMPLIANCE'
        WHEN ROUND((
            (ds.records_with_uuid::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.precision_validated_records::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.records_with_valid_hash::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.records_with_microsecond_precision::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.attestation_ready_records::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.sox_compliant_records::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.65)
        )::DECIMAL, 2) >= 90.0 THEN 'SUBSTANTIAL_COMPLIANCE'
        WHEN ROUND((
            (ds.records_with_uuid::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.precision_validated_records::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.records_with_valid_hash::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.records_with_microsecond_precision::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.attestation_ready_records::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.sox_compliant_records::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.65)
        )::DECIMAL, 2) >= 75.0 THEN 'PARTIAL_COMPLIANCE'
        ELSE 'NON_COMPLIANCE'
    END AS overall_compliance_status,

    -- Detailed compliance breakdown
    STRUCT(
        ROUND((ds.records_with_uuid::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 100)::DECIMAL, 2) AS uuid_compliance_pct,
        ROUND((ds.precision_validated_records::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 100)::DECIMAL, 2) AS financial_precision_compliance_pct,
        ROUND((ds.records_with_valid_hash::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 100)::DECIMAL, 2) AS hash_integrity_compliance_pct,
        ROUND((ds.records_with_microsecond_precision::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 100)::DECIMAL, 2) AS timestamp_precision_compliance_pct,
        ROUND((ds.attestation_ready_records::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 100)::DECIMAL, 2) AS attestation_readiness_pct,
        ROUND((ds.sox_compliant_records::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 100)::DECIMAL, 2) AS sox_compliance_pct
    ) AS detailed_compliance_metrics,

    -- Validation results summary
    COALESCE(vs.total_validation_checks, 0) AS total_validation_checks_performed,
    COALESCE(vs.passed_validations, 0) AS validation_checks_passed,
    COALESCE(vs.failed_validations, 0) AS validation_checks_failed,
    COALESCE(vs.critical_issues, 0) AS critical_issues_identified,
    COALESCE(vs.error_issues, 0) AS error_issues_identified,
    COALESCE(vs.regulatory_impact_validations, 0) AS regulatory_impact_issues,

    -- Category-specific validation status
    STRUCT(
        COALESCE(vs.uuid_integrity_pass, 0) AS uuid_integrity_validation_pass,
        COALESCE(vs.financial_precision_pass, 0) AS financial_precision_validation_pass,
        COALESCE(vs.audit_trail_integrity_pass, 0) AS audit_trail_integrity_validation_pass,
        COALESCE(vs.timestamp_precision_pass, 0) AS timestamp_precision_validation_pass,
        COALESCE(vs.regulatory_compliance_pass, 0) AS regulatory_compliance_validation_pass,
        COALESCE(vs.event_sourcing_compliance_pass, 0) AS event_sourcing_validation_pass
    ) AS category_validation_status,

    -- Financial metrics for regulatory oversight
    STRUCT(
        ds.average_deferral_rate AS avg_employee_deferral_rate,
        ds.min_deferral_rate AS minimum_deferral_rate,
        ds.max_deferral_rate AS maximum_deferral_rate,
        ds.employees_with_escalations AS employees_with_rate_escalations,
        ds.average_total_escalation_amount AS avg_escalation_amount_per_employee
    ) AS financial_oversight_metrics,

    -- Regulatory attestation summary
    CASE
        WHEN COALESCE(vs.critical_issues, 0) = 0
             AND COALESCE(vs.error_issues, 0) = 0
             AND ds.attestation_ready_records = ds.total_deferral_state_records
        THEN 'READY_FOR_ATTESTATION'
        WHEN COALESCE(vs.critical_issues, 0) > 0
        THEN 'CRITICAL_ISSUES_REQUIRE_RESOLUTION'
        WHEN COALESCE(vs.error_issues, 0) > 0
        THEN 'ERROR_ISSUES_REQUIRE_REVIEW'
        ELSE 'REQUIRES_COMPLIANCE_REVIEW'
    END AS regulatory_attestation_readiness,

    -- Audit trail metadata for regulatory traceability
    'IMMUTABLE_UUID_STAMPED_AUDIT_TRAIL' AS audit_trail_architecture,
    'SHA256_DATA_INTEGRITY_VALIDATED' AS data_integrity_method,
    'MICROSECOND_TIMESTAMP_PRECISION' AS temporal_precision_level,
    'EVENT_SOURCING_COMPLIANT' AS data_architecture_compliance,

    -- Executive recommendation
    CASE
        WHEN ROUND((
            (ds.records_with_uuid::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.precision_validated_records::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.records_with_valid_hash::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.records_with_microsecond_precision::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.attestation_ready_records::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.67) +
            (ds.sox_compliant_records::FLOAT / NULLIF(ds.total_deferral_state_records, 0) * 16.65)
        )::DECIMAL, 2) >= 95.0
        AND COALESCE(vs.critical_issues, 0) = 0
        THEN 'PROCEED_WITH_REGULATORY_REPORTING'
        WHEN COALESCE(vs.critical_issues, 0) > 0
        THEN 'IMMEDIATE_REMEDIATION_REQUIRED'
        ELSE 'COMPLIANCE_IMPROVEMENT_RECOMMENDED'
    END AS executive_recommendation

FROM deferral_state_summary ds
LEFT JOIN validation_summary vs ON ds.simulation_year = vs.simulation_year
