{{ config(
    materialized='table',
    indexes=[
        {'columns': ['validation_category', 'simulation_year'], 'type': 'btree'},
        {'columns': ['employee_id', 'simulation_year'], 'type': 'btree'},
        {'columns': ['data_quality_flag'], 'type': 'btree'}
    ]
) }}

/*
  Comprehensive Deferral Rate State Continuity Validator

  Epic E036: Temporal State Tracking Implementation
  Story S036-03: Multi-Year Continuity Validation

  This validation model ensures enterprise-grade data quality for the deferral
  rate state accumulator across multi-year simulations. It implements:

  1. Cross-year state transition validation
  2. Orphaned state detection
  3. Employee lifecycle integration validation
  4. Escalation continuity checks
  5. Data integrity auditing

  Financial audit compliance: Tracks all state changes with UUID-based audit trails
*/

{% set current_year = var('simulation_year', 2025) | int %}
{% set start_year = var('start_year', 2025) | int %}

-- Generate comprehensive cross-year validation dataset
WITH validation_base AS (
    SELECT
        {{ current_year }} AS validation_year,
        {{ start_year }} AS start_year_reference,
        'deferral_rate_state_continuity' AS validation_scope,
        CURRENT_TIMESTAMP AS validation_timestamp
),

-- 1. CROSS-YEAR STATE TRANSITION VALIDATION
state_transition_analysis AS (
    {% if current_year > start_year %}
    SELECT
        'STATE_TRANSITION' AS validation_category,
        curr.employee_id,
        curr.simulation_year,
        prev.simulation_year AS previous_year,

        -- Current year state
        curr.current_deferral_rate,
        curr.escalations_received,
        curr.has_escalations,

        -- Previous year state
        prev.current_deferral_rate AS prev_deferral_rate,
        prev.escalations_received AS prev_escalations_received,
        prev.has_escalations AS prev_has_escalations,

        -- Validation logic
        CASE
            WHEN curr.escalations_received < prev.escalations_received THEN 'ESCALATION_COUNT_DECREASED'
            WHEN curr.current_deferral_rate < prev.current_deferral_rate AND curr.escalations_received = prev.escalations_received THEN 'DEFERRAL_RATE_DECREASED_WITHOUT_RESET'
            WHEN curr.has_escalations = false AND prev.has_escalations = true AND curr.escalations_received > 0 THEN 'ESCALATION_FLAG_INCONSISTENT'
            WHEN curr.is_enrolled_flag = false AND curr.has_escalations = true THEN 'UNENROLLED_WITH_ESCALATIONS'
            ELSE 'VALID_TRANSITION'
        END AS transition_validation_result,

        -- Rate change analysis
        curr.current_deferral_rate - prev.current_deferral_rate AS rate_change,
        curr.escalations_received - prev.escalations_received AS escalation_count_change,

        -- Temporal metrics
        EXTRACT('days' FROM (curr.last_escalation_date - prev.last_escalation_date)) AS days_between_escalations,

        -- Employee lifecycle context
        emp_curr.employment_status AS current_employment_status,
        emp_prev.employment_status AS previous_employment_status

    FROM {{ ref('int_deferral_rate_state_accumulator_v2') }} curr
    LEFT JOIN {{ ref('int_deferral_rate_state_accumulator_v2') }} prev
        ON curr.employee_id = prev.employee_id
        AND prev.simulation_year = curr.simulation_year - 1
    LEFT JOIN {{ ref('fct_workforce_snapshot') }} emp_curr
        ON curr.employee_id = emp_curr.employee_id
        AND curr.simulation_year = emp_curr.simulation_year
    LEFT JOIN {{ ref('fct_workforce_snapshot') }} emp_prev
        ON prev.employee_id = emp_prev.employee_id
        AND prev.simulation_year = emp_prev.simulation_year
    WHERE curr.simulation_year = {{ current_year }}
        AND curr.employee_id IS NOT NULL
    {% else %}
    -- Base year: No previous state to validate
    SELECT
        'STATE_TRANSITION' AS validation_category,
        curr.employee_id,
        curr.simulation_year,
        NULL AS previous_year,
        curr.current_deferral_rate,
        curr.escalations_received,
        curr.has_escalations,
        NULL AS prev_deferral_rate,
        NULL AS prev_escalations_received,
        NULL AS prev_has_escalations,
        CASE
            WHEN curr.escalations_received > 0 AND curr.simulation_year = {{ start_year }} THEN 'BASE_YEAR_WITH_ESCALATIONS'
            WHEN curr.is_enrolled_flag = false AND curr.has_escalations = true THEN 'UNENROLLED_WITH_ESCALATIONS'
            ELSE 'VALID_BASE_STATE'
        END AS transition_validation_result,
        NULL AS rate_change,
        NULL AS escalation_count_change,
        NULL AS days_between_escalations,
        emp.employment_status AS current_employment_status,
        NULL AS previous_employment_status
    FROM {{ ref('int_deferral_rate_state_accumulator_v2') }} curr
    LEFT JOIN {{ ref('fct_workforce_snapshot') }} emp
        ON curr.employee_id = emp.employee_id
        AND curr.simulation_year = emp.simulation_year
    WHERE curr.simulation_year = {{ current_year }}
        AND curr.employee_id IS NOT NULL
    {% endif %}
),

-- 2. ORPHANED STATE DETECTION
orphaned_state_analysis AS (
    SELECT
        'ORPHANED_STATE' AS validation_category,
        acc.employee_id,
        acc.simulation_year,
        NULL AS previous_year,
        acc.current_deferral_rate,
        acc.escalations_received,
        acc.has_escalations,
        NULL AS prev_deferral_rate,
        NULL AS prev_escalations_received,
        NULL AS prev_has_escalations,

        -- Orphaned state validation
        CASE
            WHEN acc.has_escalations = true AND acc.is_enrolled_flag = false THEN 'ESCALATIONS_WITHOUT_ENROLLMENT'
            WHEN acc.escalations_received > 0 AND acc.last_escalation_date IS NULL THEN 'ESCALATION_COUNT_WITHOUT_DATE'
            WHEN acc.current_deferral_rate > acc.original_deferral_rate AND acc.escalations_received = 0 THEN 'RATE_INCREASE_WITHOUT_ESCALATIONS'
            WHEN acc.has_escalations = true AND ws.employee_id IS NULL THEN 'ESCALATIONS_WITHOUT_WORKFORCE_RECORD'
            WHEN acc.is_enrolled_flag = true AND enrollment.employee_id IS NULL THEN 'ENROLLED_WITHOUT_ENROLLMENT_RECORD'
            ELSE 'NO_ORPHANED_STATE'
        END AS transition_validation_result,

        NULL AS rate_change,
        NULL AS escalation_count_change,
        NULL AS days_between_escalations,
        ws.employment_status AS current_employment_status,
        NULL AS previous_employment_status

    FROM {{ ref('int_deferral_rate_state_accumulator_v2') }} acc
    LEFT JOIN {{ ref('fct_workforce_snapshot') }} ws
        ON acc.employee_id = ws.employee_id
        AND acc.simulation_year = ws.simulation_year
    LEFT JOIN {{ ref('int_enrollment_state_accumulator') }} enrollment
        ON acc.employee_id = enrollment.employee_id
        AND acc.simulation_year = enrollment.simulation_year
        AND enrollment.enrollment_status = true
    WHERE acc.simulation_year = {{ current_year }}
        AND acc.employee_id IS NOT NULL
),

-- 3. EMPLOYEE LIFECYCLE INTEGRATION VALIDATION
lifecycle_integration_analysis AS (
    SELECT
        'LIFECYCLE_INTEGRATION' AS validation_category,
        acc.employee_id,
        acc.simulation_year,
        NULL AS previous_year,
        acc.current_deferral_rate,
        acc.escalations_received,
        acc.has_escalations,
        NULL AS prev_deferral_rate,
        NULL AS prev_escalations_received,
        NULL AS prev_has_escalations,

        -- Lifecycle integration validation
        CASE
            WHEN ws.employment_status = 'terminated' AND acc.has_escalations = true THEN 'TERMINATED_EMPLOYEE_WITH_ESCALATIONS'
            WHEN hire_events.employee_id IS NOT NULL AND acc.escalations_received > 0 AND acc.simulation_year = hire_events.simulation_year THEN 'NEW_HIRE_WITH_ESCALATIONS'
            WHEN term_events.employee_id IS NOT NULL AND acc.simulation_year = term_events.simulation_year AND acc.escalation_events_this_year > 0 THEN 'TERMINATED_WITH_NEW_ESCALATIONS'
            WHEN ws.employee_id IS NULL AND acc.is_enrolled_flag = true THEN 'ENROLLED_WITHOUT_ACTIVE_EMPLOYMENT'
            ELSE 'VALID_LIFECYCLE_INTEGRATION'
        END AS transition_validation_result,

        NULL AS rate_change,
        NULL AS escalation_count_change,
        NULL AS days_between_escalations,
        ws.employment_status AS current_employment_status,
        NULL AS previous_employment_status

    FROM {{ ref('int_deferral_rate_state_accumulator_v2') }} acc
    LEFT JOIN {{ ref('fct_workforce_snapshot') }} ws
        ON acc.employee_id = ws.employee_id
        AND acc.simulation_year = ws.simulation_year
    LEFT JOIN {{ ref('fct_yearly_events') }} hire_events
        ON acc.employee_id = hire_events.employee_id
        AND acc.simulation_year = hire_events.simulation_year
        AND hire_events.event_type = 'hire'
    LEFT JOIN {{ ref('fct_yearly_events') }} term_events
        ON acc.employee_id = term_events.employee_id
        AND acc.simulation_year = term_events.simulation_year
        AND term_events.event_type = 'termination'
    WHERE acc.simulation_year = {{ current_year }}
        AND acc.employee_id IS NOT NULL
),

-- 4. ESCALATION CONTINUITY VALIDATION
escalation_continuity_analysis AS (
    SELECT
        'ESCALATION_CONTINUITY' AS validation_category,
        acc.employee_id,
        acc.simulation_year,
        NULL AS previous_year,
        acc.current_deferral_rate,
        acc.escalations_received,
        acc.has_escalations,
        NULL AS prev_deferral_rate,
        NULL AS prev_escalations_received,
        NULL AS prev_has_escalations,

        -- Escalation continuity validation
        CASE
            WHEN acc.escalations_received > 0 AND escalation_events.employee_id IS NULL THEN 'ESCALATION_COUNT_WITHOUT_EVENTS'
            WHEN escalation_events.employee_id IS NOT NULL AND acc.escalations_received = 0 THEN 'ESCALATION_EVENTS_WITHOUT_COUNT'
            WHEN acc.last_escalation_date IS NOT NULL AND escalation_events.max_effective_date != acc.last_escalation_date THEN 'ESCALATION_DATE_MISMATCH'
            WHEN acc.total_escalation_amount != COALESCE(escalation_events.total_escalation_amount, 0) THEN 'ESCALATION_AMOUNT_MISMATCH'
            ELSE 'VALID_ESCALATION_CONTINUITY'
        END AS transition_validation_result,

        NULL AS rate_change,
        NULL AS escalation_count_change,
        NULL AS days_between_escalations,
        NULL AS current_employment_status,
        NULL AS previous_employment_status

    FROM {{ ref('int_deferral_rate_state_accumulator_v2') }} acc
    LEFT JOIN (
        SELECT
            employee_id,
            COUNT(*) AS event_count,
            MAX(effective_date) AS max_effective_date,
            SUM(escalation_rate) AS total_escalation_amount
        FROM {{ ref('int_deferral_rate_escalation_events') }}
        WHERE simulation_year <= {{ current_year }}
        GROUP BY employee_id
    ) escalation_events ON acc.employee_id = escalation_events.employee_id
    WHERE acc.simulation_year = {{ current_year }}
        AND acc.employee_id IS NOT NULL
),

-- 5. CONSOLIDATED VALIDATION RESULTS
validation_summary AS (
    SELECT * FROM state_transition_analysis
    UNION ALL
    SELECT * FROM orphaned_state_analysis
    UNION ALL
    SELECT * FROM lifecycle_integration_analysis
    UNION ALL
    SELECT * FROM escalation_continuity_analysis
)

-- FINAL OUTPUT WITH METADATA
SELECT
    v.validation_category,
    v.employee_id,
    v.simulation_year,
    v.previous_year,
    v.transition_validation_result,
    v.current_deferral_rate,
    v.escalations_received,
    v.rate_change,
    v.escalation_count_change,
    v.days_between_escalations,
    v.current_employment_status,
    v.previous_employment_status,

    -- Data quality classification
    CASE
        WHEN v.transition_validation_result LIKE '%VALID%' THEN 'PASS'
        WHEN v.transition_validation_result LIKE '%NO_%' THEN 'PASS'
        ELSE 'FAIL'
    END AS data_quality_flag,

    -- Severity classification for audit priorities
    CASE
        WHEN v.transition_validation_result IN ('ESCALATION_COUNT_DECREASED', 'ESCALATIONS_WITHOUT_ENROLLMENT', 'TERMINATED_EMPLOYEE_WITH_ESCALATIONS') THEN 'HIGH'
        WHEN v.transition_validation_result IN ('DEFERRAL_RATE_DECREASED_WITHOUT_RESET', 'ESCALATION_FLAG_INCONSISTENT', 'NEW_HIRE_WITH_ESCALATIONS') THEN 'MEDIUM'
        ELSE 'LOW'
    END AS severity_level,

    -- Audit metadata
    vb.validation_timestamp,
    vb.validation_scope,
    {{ dbt_utils.generate_surrogate_key(['v.employee_id', 'v.simulation_year', 'v.validation_category']) }} AS validation_id,
    '{{ var("scenario_id", "default") }}' AS scenario_id

FROM validation_summary v
CROSS JOIN validation_base vb
WHERE v.employee_id IS NOT NULL
ORDER BY v.validation_category, v.employee_id, v.simulation_year
