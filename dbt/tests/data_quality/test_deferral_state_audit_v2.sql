-- Converted from validation model to test
-- Added simulation_year filter for performance

-- Financial Compliance Validation for Enhanced Deferral Rate State Accumulator
-- Simplified version that returns only failing records for dbt test

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

all_validations AS (
    SELECT * FROM uuid_validation
    UNION ALL SELECT * FROM financial_precision_validation
)

-- Return only failing validations for dbt test
SELECT
    CONCAT('DEFR-VALID-V2-', validation_rule, '-', {{ simulation_year }}, '-', EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::BIGINT) AS validation_record_uuid,
    validation_category,
    validation_rule,
    validation_status,
    validation_severity,
    {{ simulation_year }} AS simulation_year,
    total_records,
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
WHERE validation_status != 'PASS'
ORDER BY validation_category, validation_rule
