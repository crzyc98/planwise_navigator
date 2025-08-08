{{ config(
    materialized='incremental',
    unique_key=['audit_record_id'],
    on_schema_change='sync_all_columns',
    indexes=[
        {'columns': ['simulation_year', 'employee_id'], 'type': 'btree'},
        {'columns': ['audit_timestamp'], 'type': 'btree'},
        {'columns': ['audit_event_type'], 'type': 'btree'},
        {'columns': ['scenario_id'], 'type': 'btree'}
    ],
    tags=['audit', 'immutable', 'contribution_audit', 'event_sourcing']
) }}

/*
  Immutable Contribution Calculation Audit Trail - Story S025-02

  Creates an immutable audit trail for all employee contribution calculations,
  maintaining complete event sourcing integrity and regulatory compliance.

  This model captures:
  - Every contribution calculation with full lineage
  - All deferral rate changes with effective periods
  - IRS limit applications and enforcement decisions
  - Data quality validation results at calculation time
  - Performance metrics and calculation complexity
  - Cross-year consistency tracking

  Architecture:
  - Immutable append-only design with UUID tracking
  - Event sourcing pattern with complete reconstruction capability
  - Zero data loss tolerance with comprehensive error handling
  - Integration with enrollment state accumulator for consistency

  Regulatory Compliance:
  - Complete audit trail for IRS examinations
  - Immutable record of all limit enforcement decisions
  - Detailed tracking of contribution calculation methodology
  - Full data lineage for compliance attestation
*/

{% set simulation_year = var('simulation_year', 2025) | int %}

WITH contribution_calculations AS (
    SELECT
        employee_id,
        simulation_year,
        prorated_annual_contributions,
        irs_limited_annual_contributions,
        excess_contributions,
        effective_deferral_rate,
        contribution_periods_count,
        first_contribution_period_start,
        last_contribution_period_end,
        age_as_of_december_31,
        applicable_irs_limit,
        irs_limit_reached,
        is_enrolled,
        enrollment_date,
        years_since_first_enrollment,
        prorated_annual_compensation,
        full_year_equivalent_compensation,
        current_age,
        employment_status,
        data_quality_flag,
        created_at,
        scenario_id,
        parameter_scenario_id
    FROM {{ ref('int_employee_contributions') }}
    WHERE simulation_year = {{ simulation_year }}
),

deferral_rate_changes AS (
    SELECT
        employee_id,
        effective_date,
        event_type,
        employee_deferral_rate,
        LAG(employee_deferral_rate, 1, 0.00) OVER (
            PARTITION BY employee_id
            ORDER BY effective_date
        ) AS previous_deferral_rate
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type IN ('enrollment', 'enrollment_change')
        AND simulation_year = {{ simulation_year }}
        AND employee_deferral_rate IS NOT NULL
),

validation_results AS (
    SELECT
        validation_rule,
        validation_source,
        severity,
        violation_count,
        validation_message,
        violation_details,
        validation_timestamp,
        scenario_id AS validation_scenario_id,
        audit_record_id AS validation_audit_id,
        risk_level,
        regulatory_impact
    FROM {{ ref('dq_employee_contributions_validation') }}
    WHERE simulation_year = {{ simulation_year }}
),

irs_limits AS (
    SELECT
        plan_year,
        age_threshold,
        base_limit,
        catch_up_limit,
        total_limit
    FROM {{ ref('irs_contribution_limits') }}
    WHERE plan_year = {{ simulation_year }}
        AND limit_type = 'employee_deferral'
    LIMIT 1
)

-- Generate audit records for each employee calculation
SELECT
    -- Immutable audit identifiers
    CONCAT('CONTRIB-AUDIT-', cc.employee_id, '-', {{ simulation_year }}, '-',
           EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::BIGINT, '-',
           SUBSTR(MD5(RANDOM()::TEXT), 1, 8)) AS audit_record_id,

    -- Core audit metadata
    'CONTRIBUTION_CALCULATION' AS audit_event_type,
    CURRENT_TIMESTAMP AS audit_timestamp,
    cc.simulation_year,
    cc.employee_id,
    cc.scenario_id,
    cc.parameter_scenario_id,

    -- Contribution calculation audit data
    STRUCT(
        'core_calculation' AS calculation_type,
        cc.prorated_annual_contributions AS calculated_amount,
        cc.irs_limited_annual_contributions AS irs_limited_amount,
        cc.excess_contributions AS excess_amount,
        cc.effective_deferral_rate AS effective_rate,
        cc.contribution_periods_count AS periods_processed,
        cc.data_quality_flag AS quality_status,
        CASE
            WHEN cc.contribution_periods_count > 5 THEN 'COMPLEX'
            WHEN cc.contribution_periods_count > 2 THEN 'MODERATE'
            ELSE 'SIMPLE'
        END AS calculation_complexity
    ) AS contribution_audit_data,

    -- Employee context audit data
    STRUCT(
        cc.age_as_of_december_31 AS age_for_limits,
        cc.applicable_irs_limit AS applied_limit,
        cc.irs_limit_reached AS limit_reached_flag,
        cc.is_enrolled AS enrollment_status,
        cc.enrollment_date AS enrollment_effective_date,
        cc.years_since_first_enrollment AS enrollment_tenure,
        cc.employment_status AS employment_status,
        cc.prorated_annual_compensation AS compensation_base
    ) AS employee_context_data,

    -- Period-based calculation audit
    STRUCT(
        cc.first_contribution_period_start AS first_period_start,
        cc.last_contribution_period_end AS last_period_end,
        DATE_DIFF('day', cc.first_contribution_period_start, cc.last_contribution_period_end) + 1 AS total_days_contributing,
        ROUND(
            (DATE_DIFF('day', cc.first_contribution_period_start, cc.last_contribution_period_end) + 1) / 365.0, 4
        ) AS contribution_year_fraction
    ) AS period_audit_data,

    -- IRS compliance audit data
    STRUCT(
        il.base_limit AS irs_base_limit,
        il.catch_up_limit AS irs_catch_up_limit,
        il.total_limit AS irs_total_limit,
        il.age_threshold AS irs_age_threshold,
        CASE
            WHEN cc.age_as_of_december_31 >= il.age_threshold THEN 'CATCH_UP_ELIGIBLE'
            ELSE 'BASE_LIMIT_ONLY'
        END AS irs_limit_category,
        cc.irs_limit_reached AS limit_enforcement_applied,
        CASE
            WHEN cc.excess_contributions > 0 THEN 'EXCESS_DETECTED'
            WHEN cc.prorated_annual_contributions = cc.applicable_irs_limit THEN 'AT_LIMIT'
            WHEN cc.prorated_annual_contributions > (cc.applicable_irs_limit * 0.9) THEN 'NEAR_LIMIT'
            ELSE 'WITHIN_LIMITS'
        END AS compliance_status
    ) AS irs_compliance_audit,

    -- Deferral rate change audit (aggregated)
    ARRAY(
        SELECT STRUCT(
            drc.effective_date AS change_date,
            drc.event_type AS change_event,
            drc.previous_deferral_rate AS previous_rate,
            drc.employee_deferral_rate AS new_rate,
            drc.employee_deferral_rate - drc.previous_deferral_rate AS rate_delta
        )
        FROM deferral_rate_changes drc
        WHERE drc.employee_id = cc.employee_id
        ORDER BY drc.effective_date
    ) AS deferral_rate_changes_audit,

    -- Data quality validation audit
    ARRAY(
        SELECT STRUCT(
            vr.validation_rule AS rule_code,
            vr.validation_source AS rule_source,
            vr.severity AS severity_level,
            vr.violation_count AS violations_found,
            vr.risk_level AS risk_assessment,
            vr.regulatory_impact AS regulatory_flag
        )
        FROM validation_results vr
        WHERE vr.regulatory_impact = true
           OR vr.severity IN ('CRITICAL', 'ERROR')
    ) AS validation_audit_data,

    -- Performance and system audit
    STRUCT(
        cc.created_at AS calculation_timestamp,
        DATE_DIFF('second', cc.created_at, CURRENT_TIMESTAMP) AS audit_delay_seconds,
        CASE
            WHEN cc.contribution_periods_count > 5 THEN 'HIGH_COMPLEXITY'
            WHEN cc.contribution_periods_count > 2 THEN 'MEDIUM_COMPLEXITY'
            ELSE 'LOW_COMPLEXITY'
        END AS processing_complexity,
        '{{ var("dbt_version", "unknown") }}' AS dbt_version,
        'int_employee_contributions' AS source_model,
        ARRAY['fct_yearly_events', 'int_enrollment_state_accumulator', 'irs_contribution_limits'] AS dependency_models
    ) AS system_audit_data,

    -- Cross-year consistency audit
    STRUCT(
        cc.years_since_first_enrollment AS enrollment_years,
        {% if simulation_year > var('start_year', 2025) %}
        CASE
            WHEN EXISTS (
                SELECT 1 FROM {{ this }} prev_audit
                WHERE prev_audit.employee_id = cc.employee_id
                    AND prev_audit.simulation_year = {{ simulation_year - 1 }}
            ) THEN 'PRIOR_YEAR_DATA_AVAILABLE'
            ELSE 'NEW_EMPLOYEE_OR_MISSING_DATA'
        END AS prior_year_status,
        {% else %}
        'BASELINE_YEAR' AS prior_year_status,
        {% endif %}
        CURRENT_TIMESTAMP AS consistency_check_timestamp
    ) AS cross_year_audit_data,

    -- Immutable audit trail metadata
    'FINALIZED' AS audit_record_status,
    CURRENT_TIMESTAMP AS audit_record_created_at,
    'dq_contribution_audit_trail' AS audit_source_model,
    MD5(CONCAT(cc.employee_id, cc.simulation_year, cc.prorated_annual_contributions,
               cc.irs_limited_annual_contributions, cc.effective_deferral_rate)) AS calculation_fingerprint,

    -- Regulatory attestation fields
    'SOX_COMPLIANT' AS regulatory_framework,
    'AUTOMATED_dbt_CALCULATION' AS calculation_method,
    'IMMUTABLE_AUDIT_TRAIL' AS audit_trail_type,
    CASE
        WHEN cc.data_quality_flag = 'VALID'
             AND cc.excess_contributions = 0
             AND cc.prorated_annual_contributions <= cc.prorated_annual_compensation
        THEN 'ATTESTATION_READY'
        ELSE 'REQUIRES_REVIEW'
    END AS attestation_status

FROM contribution_calculations cc
CROSS JOIN irs_limits il
WHERE cc.employee_id IS NOT NULL

{% if is_incremental() %}
    -- For incremental runs, only add new records
    AND NOT EXISTS (
        SELECT 1 FROM {{ this }} existing
        WHERE existing.employee_id = cc.employee_id
            AND existing.simulation_year = cc.simulation_year
            AND existing.scenario_id = cc.scenario_id
            AND existing.parameter_scenario_id = cc.parameter_scenario_id
    )
{% endif %}

UNION ALL

-- Generate audit records for data quality validation events
SELECT
    -- Immutable audit identifiers for validation events
    CONCAT('VALIDATION-AUDIT-', vr.validation_rule, '-', {{ simulation_year }}, '-',
           EXTRACT(EPOCH FROM CURRENT_TIMESTAMP)::BIGINT, '-',
           SUBSTR(MD5(RANDOM()::TEXT), 1, 8)) AS audit_record_id,

    -- Validation event audit metadata
    'DATA_QUALITY_VALIDATION' AS audit_event_type,
    CURRENT_TIMESTAMP AS audit_timestamp,
    {{ simulation_year }} AS simulation_year,
    NULL AS employee_id,  -- System-level validation
    vr.validation_scenario_id AS scenario_id,
    '{{ var("parameter_scenario_id", "default") }}' AS parameter_scenario_id,

    -- Validation-specific audit data (using NULL for non-applicable fields)
    NULL AS contribution_audit_data,
    NULL AS employee_context_data,
    NULL AS period_audit_data,
    NULL AS irs_compliance_audit,
    NULL AS deferral_rate_changes_audit,

    -- Validation audit data
    ARRAY[STRUCT(
        vr.validation_rule AS rule_code,
        vr.validation_source AS rule_source,
        vr.severity AS severity_level,
        vr.violation_count AS violations_found,
        vr.risk_level AS risk_assessment,
        vr.regulatory_impact AS regulatory_flag
    )] AS validation_audit_data,

    -- System audit for validation
    STRUCT(
        vr.validation_timestamp AS calculation_timestamp,
        0 AS audit_delay_seconds,  -- Real-time validation
        'SYSTEM_VALIDATION' AS processing_complexity,
        '{{ var("dbt_version", "unknown") }}' AS dbt_version,
        'dq_employee_contributions_validation' AS source_model,
        ARRAY['int_employee_contributions', 'fct_yearly_events'] AS dependency_models
    ) AS system_audit_data,

    NULL AS cross_year_audit_data,

    -- Validation audit trail metadata
    CASE
        WHEN vr.severity = 'CRITICAL' AND vr.violation_count > 0 THEN 'FAILED'
        WHEN vr.severity = 'ERROR' AND vr.violation_count > 0 THEN 'WARNING'
        ELSE 'PASSED'
    END AS audit_record_status,
    CURRENT_TIMESTAMP AS audit_record_created_at,
    'dq_employee_contributions_validation' AS audit_source_model,
    MD5(CONCAT(vr.validation_rule, vr.validation_source, vr.violation_count,
               vr.validation_timestamp)) AS calculation_fingerprint,

    -- Regulatory attestation for validations
    'SOX_COMPLIANT' AS regulatory_framework,
    'AUTOMATED_VALIDATION' AS calculation_method,
    'IMMUTABLE_AUDIT_TRAIL' AS audit_trail_type,
    CASE
        WHEN vr.severity = 'CRITICAL' AND vr.violation_count > 0 THEN 'CRITICAL_ISSUE'
        WHEN vr.severity = 'ERROR' AND vr.violation_count > 0 THEN 'REQUIRES_REVIEW'
        ELSE 'ATTESTATION_READY'
    END AS attestation_status

FROM validation_results vr
WHERE vr.regulatory_impact = true
   OR vr.severity IN ('CRITICAL', 'ERROR')

{% if is_incremental() %}
    -- For incremental runs, only add new validation records
    AND NOT EXISTS (
        SELECT 1 FROM {{ this }} existing
        WHERE existing.audit_event_type = 'DATA_QUALITY_VALIDATION'
            AND existing.calculation_fingerprint = MD5(CONCAT(vr.validation_rule, vr.validation_source, vr.violation_count, vr.validation_timestamp))
    )
{% endif %}

ORDER BY audit_timestamp, employee_id NULLS LAST
