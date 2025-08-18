{{ config(
    materialized='table',
    indexes=[
        {'columns': ['orphaned_state_type', 'simulation_year'], 'type': 'btree'},
        {'columns': ['employee_id'], 'type': 'btree'},
        {'columns': ['severity_level'], 'type': 'btree'},
        {'columns': ['data_quality_flag'], 'type': 'btree'}
    ]
) }}

/*
  Specialized Orphaned State Detection for Deferral Rate System

  Epic E036: Temporal State Tracking Implementation
  Story S036-03: Orphaned State Detection Patterns

  This model implements enterprise-grade orphaned state detection patterns
  specifically designed for financial data audit compliance. It identifies:

  1. Escalations without corresponding enrollment records
  2. Rate changes without supporting event history
  3. Employee state inconsistencies across systems
  4. Temporal state corruption indicators
  5. Data integrity violations requiring immediate attention

  Regulatory compliance: Ensures all deferral rate state changes have
  complete audit trails and data lineage validation.
*/

{% set current_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}

WITH

    -- 1. ESCALATIONS WITHOUT ENROLLMENT RECORDS
    escalations_without_enrollment AS (
        SELECT
            'ESCALATIONS_WITHOUT_ENROLLMENT' AS orphaned_state_type,
            acc.employee_id,
            acc.simulation_year,
            acc.current_deferral_rate,
            acc.escalations_received,
            acc.has_escalations,
            acc.is_enrolled_flag,
            acc.last_escalation_date,

            -- Context data
            ws.employment_status,
            ws.employee_hire_date,
            NULL AS enrollment_date,

            -- Severity assessment
            CASE
                WHEN acc.escalations_received >= 3 THEN 'CRITICAL'
                WHEN acc.escalations_received >= 2 THEN 'HIGH'
                ELSE 'MEDIUM'
            END AS severity_level,

            -- Root cause analysis
            CASE
                WHEN ws.employment_status = 'terminated' THEN 'Employee terminated after escalations'
                WHEN ws.employee_id IS NULL THEN 'Employee not found in workforce'
                WHEN acc.is_enrolled_flag = false THEN 'Enrollment status inconsistent'
                ELSE 'Unknown enrollment state issue'
            END AS root_cause_analysis,

            -- Financial impact estimate
            acc.escalations_received * 0.01 * COALESCE(ws.employee_gross_compensation, 0) * 0.15 AS estimated_financial_impact,

            'Employees with deferral rate escalations but no valid enrollment records' AS issue_description

        FROM {{ ref('int_deferral_rate_state_accumulator_v2') }} acc
        LEFT JOIN {{ ref('fct_workforce_snapshot') }} ws
            ON acc.employee_id = ws.employee_id
            AND acc.simulation_year = ws.simulation_year
        LEFT JOIN {{ ref('int_enrollment_state_accumulator') }} enroll
            ON acc.employee_id = enroll.employee_id
            AND acc.simulation_year = enroll.simulation_year
            AND enroll.enrollment_status = true
        WHERE acc.simulation_year = {{ current_year }}
            AND acc.has_escalations = true
            AND (acc.is_enrolled_flag = false OR enroll.employee_id IS NULL)
            AND acc.employee_id IS NOT NULL
    ),

    -- 2. RATE INCREASES WITHOUT ESCALATION EVENTS
    rate_increases_without_events AS (
        SELECT
            'RATE_INCREASE_WITHOUT_EVENTS' AS orphaned_state_type,
            acc.employee_id,
            acc.simulation_year,
            acc.current_deferral_rate,
            acc.escalations_received,
            acc.has_escalations,
            acc.is_enrolled_flag,
            acc.last_escalation_date,

            -- Context data
            ws.employment_status,
            ws.employee_hire_date,
            enroll.enrollment_date,

            -- Severity based on rate deviation
            CASE
                WHEN (acc.current_deferral_rate - acc.original_deferral_rate) >= 0.05 THEN 'CRITICAL'
                WHEN (acc.current_deferral_rate - acc.original_deferral_rate) >= 0.03 THEN 'HIGH'
                WHEN (acc.current_deferral_rate - acc.original_deferral_rate) >= 0.01 THEN 'MEDIUM'
                ELSE 'LOW'
            END AS severity_level,

            -- Root cause analysis
            CASE
                WHEN acc.escalations_received = 0 AND acc.current_deferral_rate > acc.original_deferral_rate THEN 'Rate increased without escalation count'
                WHEN acc.has_escalations = false AND acc.escalations_received > 0 THEN 'Escalation flag inconsistent with count'
                WHEN acc.last_escalation_date IS NULL AND acc.escalations_received > 0 THEN 'Missing escalation date with positive count'
                ELSE 'Rate/event history mismatch'
            END AS root_cause_analysis,

            -- Financial impact of unexplained rate increases
            (acc.current_deferral_rate - acc.original_deferral_rate) * COALESCE(ws.employee_gross_compensation, 0) * 0.15 AS estimated_financial_impact,

            'Employees with deferral rate increases not supported by escalation event history' AS issue_description

        FROM {{ ref('int_deferral_rate_state_accumulator_v2') }} acc
        LEFT JOIN {{ ref('fct_workforce_snapshot') }} ws
            ON acc.employee_id = ws.employee_id
            AND acc.simulation_year = ws.simulation_year
        LEFT JOIN {{ ref('int_enrollment_state_accumulator') }} enroll
            ON acc.employee_id = enroll.employee_id
            AND acc.simulation_year = enroll.simulation_year
        WHERE acc.simulation_year = {{ current_year }}
            AND acc.current_deferral_rate > acc.original_deferral_rate
            AND (
                acc.escalations_received = 0
                OR (acc.has_escalations = false AND acc.escalations_received > 0)
                OR (acc.last_escalation_date IS NULL AND acc.escalations_received > 0)
            )
            AND acc.employee_id IS NOT NULL
    ),

    -- 3. TERMINATED EMPLOYEES WITH ACTIVE ESCALATIONS
    terminated_with_escalations AS (
        SELECT
            'TERMINATED_WITH_ACTIVE_ESCALATIONS' AS orphaned_state_type,
            acc.employee_id,
            acc.simulation_year,
            acc.current_deferral_rate,
            acc.escalations_received,
            acc.has_escalations,
            acc.is_enrolled_flag,
            acc.last_escalation_date,

            -- Context data
            ws.employment_status,
            ws.employee_hire_date,
            enroll.enrollment_date,

            -- All terminated employees with escalations are high priority
            'HIGH' AS severity_level,

            -- Root cause analysis
            CASE
                WHEN ws.employment_status = 'terminated' AND acc.escalation_events_this_year > 0 THEN 'New escalations for terminated employee'
                WHEN ws.employment_status = 'terminated' AND acc.has_escalations = true THEN 'Historical escalations not cleaned up'
                ELSE 'Termination/escalation data inconsistency'
            END AS root_cause_analysis,

            -- Financial impact - terminated employees shouldn't have active escalations
            acc.current_deferral_rate * COALESCE(ws.employee_gross_compensation, 0) * 0.15 AS estimated_financial_impact,

            'Terminated employees should not have active deferral rate escalations' AS issue_description

        FROM {{ ref('int_deferral_rate_state_accumulator_v2') }} acc
        INNER JOIN {{ ref('fct_workforce_snapshot') }} ws
            ON acc.employee_id = ws.employee_id
            AND acc.simulation_year = ws.simulation_year
            AND ws.employment_status = 'terminated'
        LEFT JOIN {{ ref('int_enrollment_state_accumulator') }} enroll
            ON acc.employee_id = enroll.employee_id
            AND acc.simulation_year = enroll.simulation_year
        WHERE acc.simulation_year = {{ current_year }}
            AND acc.has_escalations = true
            AND acc.employee_id IS NOT NULL
    ),

    -- 4. NEW HIRES WITH HISTORICAL ESCALATIONS
    new_hires_with_escalations AS (
        SELECT
            'NEW_HIRE_WITH_HISTORICAL_ESCALATIONS' AS orphaned_state_type,
            acc.employee_id,
            acc.simulation_year,
            acc.current_deferral_rate,
            acc.escalations_received,
            acc.has_escalations,
            acc.is_enrolled_flag,
            acc.last_escalation_date,

            -- Context data
            ws.employment_status,
            ws.employee_hire_date,
            enroll.enrollment_date,

            -- New hires with escalations are suspicious
            'MEDIUM' AS severity_level,

            -- Root cause analysis
            CASE
                WHEN hire_events.employee_id IS NOT NULL AND acc.escalations_received > 0 THEN 'New hire has pre-existing escalation history'
                WHEN EXTRACT('year' FROM ws.employee_hire_date) = acc.simulation_year AND acc.years_since_first_escalation > 0 THEN 'Hire year mismatch with escalation history'
                ELSE 'New hire escalation data inconsistency'
            END AS root_cause_analysis,

            -- Financial impact - new hires shouldn't have escalation history
            acc.escalations_received * 0.01 * COALESCE(ws.employee_gross_compensation, 0) * 0.15 AS estimated_financial_impact,

            'New hires should not have pre-existing deferral rate escalation history' AS issue_description

        FROM {{ ref('int_deferral_rate_state_accumulator_v2') }} acc
        INNER JOIN {{ ref('fct_workforce_snapshot') }} ws
            ON acc.employee_id = ws.employee_id
            AND acc.simulation_year = ws.simulation_year
        LEFT JOIN {{ ref('fct_yearly_events') }} hire_events
            ON acc.employee_id = hire_events.employee_id
            AND acc.simulation_year = hire_events.simulation_year
            AND hire_events.event_type = 'hire'
        LEFT JOIN {{ ref('int_enrollment_state_accumulator') }} enroll
            ON acc.employee_id = enroll.employee_id
            AND acc.simulation_year = enroll.simulation_year
        WHERE acc.simulation_year = {{ current_year }}
            AND (
                hire_events.employee_id IS NOT NULL
                OR EXTRACT('year' FROM ws.employee_hire_date) = acc.simulation_year
            )
            AND acc.escalations_received > 0
            AND acc.employee_id IS NOT NULL
    ),

    -- 5. ESCALATION AMOUNTS WITHOUT EVENT SUPPORT
    escalation_amounts_without_events AS (
        SELECT
            'ESCALATION_AMOUNTS_WITHOUT_EVENTS' AS orphaned_state_type,
            acc.employee_id,
            acc.simulation_year,
            acc.current_deferral_rate,
            acc.escalations_received,
            acc.has_escalations,
            acc.is_enrolled_flag,
            acc.last_escalation_date,

            -- Context data
            ws.employment_status,
            ws.employee_hire_date,
            enroll.enrollment_date,

            -- Severity based on amount discrepancy
            CASE
                WHEN ABS(acc.total_escalation_amount - COALESCE(events.total_escalation_amount, 0)) >= 0.05 THEN 'CRITICAL'
                WHEN ABS(acc.total_escalation_amount - COALESCE(events.total_escalation_amount, 0)) >= 0.03 THEN 'HIGH'
                ELSE 'MEDIUM'
            END AS severity_level,

            -- Root cause analysis with actual vs expected amounts
            'Escalation amount mismatch: Accumulator=' || acc.total_escalation_amount ||
            ', Events=' || COALESCE(events.total_escalation_amount, 0) AS root_cause_analysis,

            -- Financial impact of amount discrepancy
            ABS(acc.total_escalation_amount - COALESCE(events.total_escalation_amount, 0)) * COALESCE(ws.employee_gross_compensation, 0) * 0.15 AS estimated_financial_impact,

            'Escalation amounts in accumulator do not match supporting event records' AS issue_description

        FROM {{ ref('int_deferral_rate_state_accumulator_v2') }} acc
        LEFT JOIN {{ ref('fct_workforce_snapshot') }} ws
            ON acc.employee_id = ws.employee_id
            AND acc.simulation_year = ws.simulation_year
        LEFT JOIN (
            SELECT
                employee_id,
                SUM(escalation_rate) AS total_escalation_amount,
                COUNT(*) AS event_count
            FROM {{ ref('int_deferral_rate_escalation_events') }}
            WHERE simulation_year <= {{ current_year }}
            GROUP BY employee_id
        ) events ON acc.employee_id = events.employee_id
        LEFT JOIN {{ ref('int_enrollment_state_accumulator') }} enroll
            ON acc.employee_id = enroll.employee_id
            AND acc.simulation_year = enroll.simulation_year
        WHERE acc.simulation_year = {{ current_year }}
            AND acc.total_escalation_amount > 0
            AND ABS(acc.total_escalation_amount - COALESCE(events.total_escalation_amount, 0)) >= 0.01
            AND acc.employee_id IS NOT NULL
    ),

    orphaned_state_detection AS (
        -- CONSOLIDATE ALL ORPHANED STATE DETECTIONS
        SELECT * FROM escalations_without_enrollment
        UNION ALL
        SELECT * FROM rate_increases_without_events
        UNION ALL
        SELECT * FROM terminated_with_escalations
        UNION ALL
        SELECT * FROM new_hires_with_escalations
        UNION ALL
        SELECT * FROM escalation_amounts_without_events
    )

-- FINAL OUTPUT WITH AUDIT METADATA
SELECT
    orphaned_state_type,
    employee_id,
    simulation_year,
    current_deferral_rate,
    escalations_received,
    has_escalations,
    is_enrolled_flag,
    last_escalation_date,
    employment_status,
    employee_hire_date,
    enrollment_date,
    severity_level,
    root_cause_analysis,
    estimated_financial_impact,
    issue_description,

    -- Data quality classification
    CASE
        WHEN severity_level IN ('CRITICAL', 'HIGH') THEN 'FAIL'
        WHEN severity_level = 'MEDIUM' THEN 'WARNING'
        ELSE 'REVIEW'
    END AS data_quality_flag,

    -- Audit trail metadata
    CURRENT_TIMESTAMP AS detection_timestamp,
    {{ dbt_utils.generate_surrogate_key(['employee_id', 'simulation_year', 'orphaned_state_type']) }} AS detection_id,
    '{{ var("scenario_id", "default") }}' AS scenario_id,
    'validate_deferral_rate_orphaned_states' AS detection_source

FROM orphaned_state_detection
WHERE employee_id IS NOT NULL
ORDER BY
    CASE severity_level
        WHEN 'CRITICAL' THEN 1
        WHEN 'HIGH' THEN 2
        WHEN 'MEDIUM' THEN 3
        ELSE 4
    END,
    orphaned_state_type,
    employee_id
