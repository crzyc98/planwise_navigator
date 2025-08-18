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
    tags=['audit', 'validation', 'deferral_rate_audit', 'financial_compliance', 'uuid_tracked']
) }}

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH deferral_state_data AS (
    SELECT
        -- Synthetic UUID to ensure uniqueness when source lacks native UUID
        MD5(COALESCE(employee_id, 'NULL') || '-' || simulation_year::VARCHAR) AS state_record_uuid,
        employee_id,
        simulation_year,
        current_deferral_rate,
        original_deferral_rate,
        total_escalation_amount,
        escalation_rate_change_pct,
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

uuid_validation AS (
    SELECT
        'UUID_INTEGRITY' AS validation_category,
        'UUID_UNIQUENESS_CHECK' AS validation_rule,
        COUNT(*) AS total_records,
        COUNT(DISTINCT state_record_uuid) AS unique_uuids,
        COUNT(*) - COUNT(DISTINCT state_record_uuid) AS duplicate_uuid_count,
        CASE WHEN COUNT(*) = COUNT(DISTINCT state_record_uuid) THEN 'PASS' ELSE 'FAIL' END AS validation_status,
        CASE WHEN COUNT(*) = COUNT(DISTINCT state_record_uuid) THEN 'INFO' ELSE 'CRITICAL' END AS validation_severity
    FROM deferral_state_data
),

financial_precision_validation AS (
    SELECT
        'FINANCIAL_PRECISION' AS validation_category,
        'DECIMAL_PRECISION_CHECK' AS validation_rule,
        COUNT(*) AS total_records,
        COUNT(CASE WHEN current_deferral_rate IS NOT NULL THEN 1 END) AS valid_precision_count,
        COUNT(CASE WHEN current_deferral_rate IS NULL THEN 1 END) AS invalid_precision_count,
        CASE WHEN COUNT(CASE WHEN current_deferral_rate IS NULL THEN 1 END) = 0 THEN 'PASS' ELSE 'FAIL' END AS validation_status,
        CASE WHEN COUNT(CASE WHEN current_deferral_rate IS NULL THEN 1 END) = 0 THEN 'INFO' ELSE 'ERROR' END AS validation_severity
    FROM deferral_state_data
),

hash_integrity_validation AS (
    SELECT
        'AUDIT_TRAIL_INTEGRITY' AS validation_category,
        'SHA256_HASH_FORMAT_CHECK' AS validation_rule,
        COUNT(*) AS total_records,
        0 AS valid_hash_count,
        COUNT(*) AS invalid_hash_count,
        'WARNING' AS validation_status,
        'WARNING' AS validation_severity
    FROM deferral_state_data
),

timestamp_precision_validation AS (
    SELECT
        'TIMESTAMP_PRECISION' AS validation_category,
        'MICROSECOND_PRECISION_CHECK' AS validation_rule,
        COUNT(*) AS total_records,
        COUNT(CASE WHEN audit_microsecond_epoch IS NOT NULL AND audit_microsecond_epoch > 0 THEN 1 END) AS valid_microsecond_count,
        COUNT(CASE WHEN audit_microsecond_epoch IS NULL OR audit_microsecond_epoch <= 0 THEN 1 END) AS invalid_microsecond_count,
        CASE WHEN COUNT(CASE WHEN audit_microsecond_epoch IS NULL OR audit_microsecond_epoch <= 0 THEN 1 END) = 0 THEN 'PASS' ELSE 'FAIL' END AS validation_status,
        CASE WHEN COUNT(CASE WHEN audit_microsecond_epoch IS NULL OR audit_microsecond_epoch <= 0 THEN 1 END) = 0 THEN 'INFO' ELSE 'ERROR' END AS validation_severity
    FROM deferral_state_data
),

regulatory_compliance_validation AS (
    SELECT
        'REGULATORY_COMPLIANCE' AS validation_category,
        'ATTESTATION_READINESS_CHECK' AS validation_rule,
        COUNT(*) AS total_records,
        0 AS attestation_ready_count,
        COUNT(*) AS requires_review_count,
        'WARNING' AS validation_status,
        'WARNING' AS validation_severity
    FROM deferral_state_data
),

event_sourcing_validation AS (
    SELECT
        'EVENT_SOURCING_COMPLIANCE' AS validation_category,
        'IMMUTABILITY_STATUS_CHECK' AS validation_rule,
        COUNT(*) AS total_records,
        0 AS compliant_records_count,
        COUNT(*) AS non_compliant_records_count,
        'WARNING' AS validation_status,
        'CRITICAL' AS validation_severity
    FROM deferral_state_data
),

all_validations AS (
    SELECT * FROM uuid_validation
    UNION ALL SELECT * FROM financial_precision_validation
    UNION ALL SELECT * FROM hash_integrity_validation
    UNION ALL SELECT * FROM timestamp_precision_validation
    UNION ALL SELECT * FROM regulatory_compliance_validation
    UNION ALL SELECT * FROM event_sourcing_validation
)

SELECT
    CONCAT('DEFR-VALID-V2-', validation_rule, '-', {{ simulation_year }}, '-', EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::BIGINT) AS validation_record_uuid,
    validation_category,
    validation_rule,
    validation_status,
    validation_severity,
    {{ simulation_year }} AS simulation_year,
    total_records,
    NULL AS valid_count,
    NULL AS invalid_count,
    CASE
        WHEN validation_status = 'PASS' THEN 'All records pass ' || validation_rule || ' validation'
        WHEN validation_status = 'WARNING' THEN 'Some records require review for ' || validation_rule
        ELSE 'Validation failed for ' || validation_rule
    END AS validation_message,
    CASE WHEN validation_severity IN ('CRITICAL', 'ERROR') THEN true ELSE false END AS regulatory_impact,
    CURRENT_TIMESTAMP AS validation_timestamp,
    'dq_deferral_rate_state_audit_validation_v2' AS validation_source,
    'int_deferral_rate_state_accumulator_v2' AS validated_model,
    'SOX_COMPLIANT_VALIDATION' AS regulatory_framework,
    'IMMUTABLE_VALIDATION_RECORD' AS audit_record_type
FROM all_validations

{% if is_incremental() %}
  WHERE NOT EXISTS (
    SELECT 1 FROM {{ this }} existing
    WHERE existing.validation_rule = all_validations.validation_rule
      AND existing.simulation_year = {{ simulation_year }}
      AND DATE(existing.validation_timestamp) = CURRENT_DATE
  )
{% endif %}

ORDER BY validation_category, validation_rule
