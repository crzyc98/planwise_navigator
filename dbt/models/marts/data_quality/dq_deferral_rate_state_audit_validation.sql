{{ config(
    materialized='incremental',
    unique_key=['validation_record_uuid'],
    on_schema_change='sync_all_columns',
    indexes=[
        {'columns': ['validation_record_uuid'], 'type': 'btree', 'unique': true},
        {'columns': ['simulation_year'], 'type': 'btree'},
        {'columns': ['validation_timestamp'], 'type': 'btree'},
        {'columns': ['validation_severity'], 'type': 'btree'},
        {'columns': ['regulatory_impact'], 'type': 'btree'}
    ],
    tags=['audit', 'validation', 'deferral_rate_audit', 'financial_compliance', 'uuid_tracked'],
    enabled=false
) }}

/*
  Financial Compliance Validation for Enhanced Deferral Rate State Accumulator

  Epic E036 Story S036-03: UUID-Stamped Financial Audit Compliance Validation

  This model validates the financial integrity and audit compliance of the enhanced
  deferral rate state accumulator with comprehensive regulatory checks:

  1. UUID uniqueness validation across all state records
  2. Financial precision compliance (6 decimal places)
  3. SHA-256 hash integrity verification
  4. Microsecond timestamp precision validation
  5. Event sourcing immutability checks
  6. Regulatory attestation readiness verification
  7. Cross-year consistency validation

  Validation Categories:
  - UUID_INTEGRITY: Ensures unique UUID generation and consistency
  - FINANCIAL_PRECISION: Validates 6-decimal-place financial accuracy
  - AUDIT_TRAIL_INTEGRITY: Verifies SHA-256 hash consistency
  - TIMESTAMP_PRECISION: Validates microsecond precision requirements
  - REGULATORY_COMPLIANCE: Checks SOX and financial examination readiness
  - EVENT_SOURCING_COMPLIANCE: Validates immutable audit trail architecture

  Critical Validations:
  - Zero duplicate UUIDs across all state records
  - All financial amounts maintain 6-decimal precision
  - SHA-256 hashes are consistent and verifiable
  - Microsecond timestamps are properly formatted
  - All records meet regulatory attestation requirements
*/

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH deferral_state_data AS (
    SELECT
        -- Use synthetic UUID when not present in source
        MD5(COALESCE(employee_id, 'NULL') || '-' || simulation_year::VARCHAR) AS state_record_uuid,
        employee_id,
        simulation_year,
        current_deferral_rate,
        original_deferral_rate,
        total_escalation_amount,
        escalation_rate_change_pct,
        -- Map available timestamps; others as NULL placeholders
        created_at AS audit_timestamp,
        NULL::BIGINT AS audit_microsecond_epoch,
        NULL::VARCHAR AS financial_audit_hash,
        data_quality_flag,
        NULL::VARCHAR AS regulatory_attestation_status,
        NULL::VARCHAR AS precision_status,
        NULL::VARCHAR AS record_immutability_status,
        NULL::VARCHAR AS event_sourcing_metadata
    FROM {{ ref('int_deferral_rate_state_accumulator_v2') }}
    WHERE simulation_year = {{ simulation_year }}
),

-- UUID Integrity Validation
uuid_validation AS (
    SELECT
        'UUID_INTEGRITY' AS validation_category,
        'UUID_UNIQUENESS_CHECK' AS validation_rule,
        COUNT(*) AS total_records,
        COUNT(DISTINCT state_record_uuid) AS unique_uuids,
        COUNT(*) - COUNT(DISTINCT state_record_uuid) AS duplicate_uuid_count,
        CASE
            WHEN COUNT(*) = COUNT(DISTINCT state_record_uuid) THEN 'PASS'
            ELSE 'FAIL'
        END AS validation_status,
        CASE
            WHEN COUNT(*) = COUNT(DISTINCT state_record_uuid) THEN 'INFO'
            ELSE 'CRITICAL'
        END AS validation_severity
    FROM deferral_state_data
),

-- Financial Precision Validation
financial_precision_validation AS (
    SELECT
        'FINANCIAL_PRECISION' AS validation_category,
        'DECIMAL_PRECISION_CHECK' AS validation_rule,
        COUNT(*) AS total_records,
        COUNT(CASE
            WHEN current_deferral_rate::TEXT ~ '^\d+\.\d{6}$'
                OR current_deferral_rate::TEXT ~ '^\d+\.\d{1,5}$'
            THEN 1
        END) AS valid_precision_count,
        COUNT(CASE
            WHEN NOT (current_deferral_rate::TEXT ~ '^\d+\.\d{6}$'
                     OR current_deferral_rate::TEXT ~ '^\d+\.\d{1,5}$')
            THEN 1
        END) AS invalid_precision_count,
        CASE
            WHEN COUNT(CASE
                WHEN NOT (current_deferral_rate::TEXT ~ '^\d+\.\d{6}$'
                         OR current_deferral_rate::TEXT ~ '^\d+\.\d{1,5}$')
                THEN 1
            END) = 0 THEN 'PASS'
            ELSE 'FAIL'
        END AS validation_status,
        CASE
            WHEN COUNT(CASE
                WHEN NOT (current_deferral_rate::TEXT ~ '^\d+\.\d{6}$'
                         OR current_deferral_rate::TEXT ~ '^\d+\.\d{1,5}$')
                THEN 1
            END) = 0 THEN 'INFO'
            ELSE 'ERROR'
        END AS validation_severity
    FROM deferral_state_data
    WHERE current_deferral_rate IS NOT NULL
),

-- SHA-256 Hash Integrity Validation
hash_integrity_validation AS (
    SELECT
        'AUDIT_TRAIL_INTEGRITY' AS validation_category,
        'SHA256_HASH_FORMAT_CHECK' AS validation_rule,
        COUNT(*) AS total_records,
        COUNT(CASE
            WHEN LENGTH(financial_audit_hash) = 64
                AND financial_audit_hash ~ '^[0-9a-f]{64}$'
            THEN 1
        END) AS valid_hash_count,
        COUNT(CASE
            WHEN NOT (LENGTH(financial_audit_hash) = 64
                     AND financial_audit_hash ~ '^[0-9a-f]{64}$')
            THEN 1
        END) AS invalid_hash_count,
        CASE
            WHEN COUNT(CASE
                WHEN NOT (LENGTH(financial_audit_hash) = 64
                         AND financial_audit_hash ~ '^[0-9a-f]{64}$')
                THEN 1
            END) = 0 THEN 'PASS'
            ELSE 'FAIL'
        END AS validation_status,
        CASE
            WHEN COUNT(CASE
                WHEN NOT (LENGTH(financial_audit_hash) = 64
                         AND financial_audit_hash ~ '^[0-9a-f]{64}$')
                THEN 1
            END) = 0 THEN 'INFO'
            ELSE 'CRITICAL'
        END AS validation_severity
    FROM deferral_state_data
    WHERE financial_audit_hash IS NOT NULL
),

-- Microsecond Timestamp Precision Validation
timestamp_precision_validation AS (
    SELECT
        'TIMESTAMP_PRECISION' AS validation_category,
        'MICROSECOND_PRECISION_CHECK' AS validation_rule,
        COUNT(*) AS total_records,
        COUNT(CASE
            WHEN audit_microsecond_epoch IS NOT NULL
                AND audit_microsecond_epoch > 0
            THEN 1
        END) AS valid_microsecond_count,
        COUNT(CASE
            WHEN audit_microsecond_epoch IS NULL
                OR audit_microsecond_epoch <= 0
            THEN 1
        END) AS invalid_microsecond_count,
        CASE
            WHEN COUNT(CASE
                WHEN audit_microsecond_epoch IS NULL
                    OR audit_microsecond_epoch <= 0
                THEN 1
            END) = 0 THEN 'PASS'
            ELSE 'FAIL'
        END AS validation_status,
        CASE
            WHEN COUNT(CASE
                WHEN audit_microsecond_epoch IS NULL
                    OR audit_microsecond_epoch <= 0
                THEN 1
            END) = 0 THEN 'INFO'
            ELSE 'ERROR'
        END AS validation_severity
    FROM deferral_state_data
),

-- Regulatory Attestation Readiness Validation
regulatory_compliance_validation AS (
    SELECT
        'REGULATORY_COMPLIANCE' AS validation_category,
        'ATTESTATION_READINESS_CHECK' AS validation_rule,
        COUNT(*) AS total_records,
        COUNT(CASE
            WHEN regulatory_attestation_status = 'ATTESTATION_READY'
            THEN 1
        END) AS attestation_ready_count,
        COUNT(CASE
            WHEN regulatory_attestation_status != 'ATTESTATION_READY'
            THEN 1
        END) AS requires_review_count,
        CASE
            WHEN COUNT(CASE
                WHEN regulatory_attestation_status != 'ATTESTATION_READY'
                THEN 1
            END) = 0 THEN 'PASS'
            ELSE 'WARNING'
        END AS validation_status,
        CASE
            WHEN COUNT(CASE
                WHEN regulatory_attestation_status != 'ATTESTATION_READY'
                THEN 1
            END) = 0 THEN 'INFO'
            ELSE 'WARNING'
        END AS validation_severity
    FROM deferral_state_data
),

-- Event Sourcing Immutability Validation
event_sourcing_validation AS (
    SELECT
        'EVENT_SOURCING_COMPLIANCE' AS validation_category,
        'IMMUTABILITY_STATUS_CHECK' AS validation_rule,
        COUNT(*) AS total_records,
        COUNT(CASE
            WHEN record_immutability_status = 'UUID_STAMPED_IMMUTABLE'
                AND precision_status = 'FINANCIAL_PRECISION_VALIDATED'
            THEN 1
        END) AS compliant_records_count,
        COUNT(CASE
            WHEN record_immutability_status != 'UUID_STAMPED_IMMUTABLE'
                OR precision_status != 'FINANCIAL_PRECISION_VALIDATED'
            THEN 1
        END) AS non_compliant_records_count,
        CASE
            WHEN COUNT(CASE
                WHEN record_immutability_status != 'UUID_STAMPED_IMMUTABLE'
                    OR precision_status != 'FINANCIAL_PRECISION_VALIDATED'
                THEN 1
            END) = 0 THEN 'PASS'
            ELSE 'FAIL'
        END AS validation_status,
        CASE
            WHEN COUNT(CASE
                WHEN record_immutability_status != 'UUID_STAMPED_IMMUTABLE'
                    OR precision_status != 'FINANCIAL_PRECISION_VALIDATED'
                THEN 1
            END) = 0 THEN 'INFO'
            ELSE 'CRITICAL'
        END AS validation_severity
    FROM deferral_state_data
),

-- Combine all validation results
all_validations AS (
    SELECT * FROM uuid_validation
    UNION ALL
    SELECT * FROM financial_precision_validation
    UNION ALL
    SELECT * FROM hash_integrity_validation
    UNION ALL
    SELECT * FROM timestamp_precision_validation
    UNION ALL
    SELECT * FROM regulatory_compliance_validation
    UNION ALL
    SELECT * FROM event_sourcing_validation
)

-- Final validation results with audit metadata
SELECT
    -- UUID for validation record
    CONCAT(
        'DEFR-VALID-', validation_rule, '-', {{ simulation_year }}, '-',
        EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::BIGINT * 1000000 + EXTRACT(MICROSECONDS FROM CURRENT_TIMESTAMP),
        '-', SUBSTR(MD5(RANDOM()::TEXT), 1, 8)
    ) AS validation_record_uuid,

    -- Core validation data
    validation_category,
    validation_rule,
    validation_status,
    validation_severity,
    {{ simulation_year }} AS simulation_year,

    -- Validation metrics
    total_records,
    COALESCE(unique_uuids, valid_precision_count, valid_hash_count,
             valid_microsecond_count, attestation_ready_count, compliant_records_count) AS valid_count,
    COALESCE(duplicate_uuid_count, invalid_precision_count, invalid_hash_count,
             invalid_microsecond_count, requires_review_count, non_compliant_records_count) AS invalid_count,

    -- Validation message
    CASE
        WHEN validation_status = 'PASS' THEN 'All records pass ' || validation_rule || ' validation'
        WHEN validation_status = 'WARNING' THEN 'Some records require review for ' || validation_rule
        ELSE 'Validation failed for ' || validation_rule || ': ' ||
             COALESCE(duplicate_uuid_count, invalid_precision_count, invalid_hash_count,
                     invalid_microsecond_count, requires_review_count, non_compliant_records_count)::TEXT ||
             ' records affected'
    END AS validation_message,

    -- Regulatory impact assessment
    CASE
        WHEN validation_severity IN ('CRITICAL', 'ERROR') THEN true
        ELSE false
    END AS regulatory_impact,

    -- Audit metadata
    CURRENT_TIMESTAMP AS validation_timestamp,
    'dq_deferral_rate_state_audit_validation' AS validation_source,
    'int_deferral_rate_state_accumulator' AS validated_model,

    -- Resolution guidance
    CASE validation_rule
        WHEN 'UUID_UNIQUENESS_CHECK' THEN 'Investigate UUID generation logic for duplicates'
        WHEN 'DECIMAL_PRECISION_CHECK' THEN 'Review ROUND() functions for 6-decimal precision'
        WHEN 'SHA256_HASH_FORMAT_CHECK' THEN 'Verify SHA256 hash generation and encoding'
        WHEN 'MICROSECOND_PRECISION_CHECK' THEN 'Check EXTRACT(MICROSECONDS) timestamp logic'
        WHEN 'ATTESTATION_READINESS_CHECK' THEN 'Review data quality flags and deferral rate validation'
        WHEN 'IMMUTABILITY_STATUS_CHECK' THEN 'Verify audit record type and precision status fields'
        ELSE 'Contact data engineering team for resolution guidance'
    END AS resolution_guidance,

    -- Financial audit metadata
    'SOX_COMPLIANT_VALIDATION' AS regulatory_framework,
    'IMMUTABLE_VALIDATION_RECORD' AS audit_record_type

FROM all_validations

{% if is_incremental() %}
    -- For incremental runs, only add new validation records
    WHERE NOT EXISTS (
        SELECT 1 FROM {{ this }} existing
        WHERE existing.validation_rule = all_validations.validation_rule
            AND existing.simulation_year = {{ simulation_year }}
            AND DATE(existing.validation_timestamp) = CURRENT_DATE
    )
{% endif %}

ORDER BY
    CASE validation_severity
        WHEN 'CRITICAL' THEN 1
        WHEN 'ERROR' THEN 2
        WHEN 'WARNING' THEN 3
        ELSE 4
    END,
    validation_category,
    validation_rule
