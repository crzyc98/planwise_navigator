{{ config(
    materialized='table',
    indexes=[
        {'columns': ['simulation_year'], 'type': 'btree'},
        {'columns': ['data_quality_status'], 'type': 'btree'},
        {'columns': ['employee_id', 'simulation_year'], 'type': 'btree'}
    ],
    tags=['data_quality', 'monitoring', 'promotion_validation']
) }}

-- Real-time data quality validation for promotion compensation integrity
-- Validates that promotion events use correct previous compensation from
-- the end-of-year workforce snapshot instead of stale baseline data

WITH promotion_events AS (
    SELECT
        employee_id,
        simulation_year,
        effective_date,
        previous_compensation as promotion_previous_salary,
        compensation_amount as promotion_new_salary,
        event_details
    FROM {{ ref('fct_yearly_events') }}
    WHERE event_type = 'promotion'
        AND simulation_year > 2025  -- Skip baseline year
),

previous_year_compensation AS (
    SELECT
        employee_id,
        simulation_year,
        current_compensation as snapshot_current_compensation,
        prorated_annual_compensation,
        full_year_equivalent_compensation,
        employment_status
    FROM {{ ref('fct_workforce_snapshot') }}
    WHERE employment_status = 'active'
),

compensation_validation AS (
    SELECT
        p.employee_id,
        p.simulation_year,
        p.effective_date,
        p.promotion_previous_salary,
        p.promotion_new_salary,
        p.event_details,

        -- Previous year compensation state
        ws.snapshot_current_compensation,
        ws.prorated_annual_compensation as prev_year_prorated,
        ws.full_year_equivalent_compensation as prev_year_full_year,

        -- Calculate compensation gaps
        p.promotion_previous_salary - ws.snapshot_current_compensation as compensation_gap,
        ROUND(
            (p.promotion_previous_salary - ws.snapshot_current_compensation) /
            NULLIF(ws.snapshot_current_compensation, 0) * 100, 2
        ) as gap_percentage,

        -- Validate promotion increase reasonableness (15-30% typical range)
        (p.promotion_new_salary - p.promotion_previous_salary) /
        NULLIF(p.promotion_previous_salary, 0) * 100 as promotion_increase_percentage,

        -- Data quality assessment
        CASE
            -- Critical violations: Major compensation gaps indicating stale data
            WHEN abs(p.promotion_previous_salary - ws.snapshot_current_compensation) > 5000
                THEN 'CRITICAL_VIOLATION'
            -- Major violations: Significant compensation gaps
            WHEN abs(p.promotion_previous_salary - ws.snapshot_current_compensation) > 1000
                THEN 'MAJOR_VIOLATION'
            -- Minor violations: Small discrepancies that may be acceptable
            WHEN abs(p.promotion_previous_salary - ws.snapshot_current_compensation) > 100
                THEN 'MINOR_VIOLATION'
            -- Warnings: Very small gaps that should be investigated
            WHEN abs(p.promotion_previous_salary - ws.snapshot_current_compensation) > 10
                THEN 'WARNING'
            -- Pass: Acceptable compensation continuity
            ELSE 'PASS'
        END as data_quality_status,

        -- Additional validation flags
        CASE
            WHEN ws.snapshot_current_compensation IS NULL
                THEN 'MISSING_PREVIOUS_COMPENSATION'
            WHEN p.promotion_previous_salary <= 0
                THEN 'INVALID_PROMOTION_PREVIOUS_SALARY'
            WHEN p.promotion_new_salary <= p.promotion_previous_salary
                THEN 'INVALID_PROMOTION_INCREASE'
            WHEN ((p.promotion_new_salary - p.promotion_previous_salary) /
                  NULLIF(p.promotion_previous_salary, 0) * 100) > 50
                THEN 'EXCESSIVE_PROMOTION_INCREASE'
            WHEN ((p.promotion_new_salary - p.promotion_previous_salary) /
                  NULLIF(p.promotion_previous_salary, 0) * 100) < 5
                THEN 'INSUFFICIENT_PROMOTION_INCREASE'
            ELSE 'PROMOTION_INCREASE_VALID'
        END as promotion_increase_validation,

        -- Audit trail information
        CURRENT_TIMESTAMP as validation_timestamp,
        '{{ var("simulation_year", "unknown") }}' as validation_run_year

    FROM promotion_events p
    LEFT JOIN previous_year_compensation ws
        ON p.employee_id = ws.employee_id
        AND p.simulation_year - 1 = ws.simulation_year
),

-- Merit event impact analysis - shows if merit events should have updated compensation
merit_impact_analysis AS (
    SELECT
        cv.*,

        -- Check for merit events in previous year that should have updated compensation
        me.merit_new_salary,
        me.merit_effective_date,
        me.merit_increase_amount,

        -- If merit event exists, calculate expected compensation vs actual
        CASE
            WHEN me.merit_new_salary IS NOT NULL
            THEN cv.promotion_previous_salary - me.merit_new_salary
            ELSE NULL
        END as merit_propagation_gap,

        -- Merit propagation status
        CASE
            WHEN me.merit_new_salary IS NOT NULL AND
                 abs(cv.promotion_previous_salary - me.merit_new_salary) > 100
                THEN 'MERIT_NOT_PROPAGATED'
            WHEN me.merit_new_salary IS NOT NULL AND
                 abs(cv.promotion_previous_salary - me.merit_new_salary) <= 100
                THEN 'MERIT_PROPERLY_PROPAGATED'
            ELSE 'NO_MERIT_EVENT'
        END as merit_propagation_status

    FROM compensation_validation cv
    LEFT JOIN (
        -- Get the most recent merit event for each employee in the previous year
        SELECT
            employee_id,
            simulation_year,
            effective_date as merit_effective_date,
            compensation_amount as merit_new_salary,
            compensation_amount - previous_compensation as merit_increase_amount,
            ROW_NUMBER() OVER (
                PARTITION BY employee_id, simulation_year
                ORDER BY effective_date DESC
            ) as merit_recency_rank
        FROM {{ ref('fct_yearly_events') }}
        WHERE event_type = 'raise'
    ) me ON cv.employee_id = me.employee_id
        AND cv.simulation_year - 1 = me.simulation_year
        AND me.merit_recency_rank = 1
)

SELECT
    employee_id,
    simulation_year,
    effective_date,

    -- Compensation values
    promotion_previous_salary,
    promotion_new_salary,
    snapshot_current_compensation,
    prev_year_prorated,
    prev_year_full_year,

    -- Gap analysis
    compensation_gap,
    gap_percentage,
    promotion_increase_percentage,

    -- Data quality status
    data_quality_status,
    promotion_increase_validation,

    -- Merit event analysis
    merit_new_salary,
    merit_effective_date,
    merit_increase_amount,
    merit_propagation_gap,
    merit_propagation_status,

    -- Additional context
    event_details,
    validation_timestamp,
    validation_run_year,

    -- Summary flags for dashboard
    CASE
        WHEN data_quality_status IN ('CRITICAL_VIOLATION', 'MAJOR_VIOLATION')
            THEN TRUE
        ELSE FALSE
    END as requires_immediate_attention,

    CASE
        WHEN merit_propagation_status = 'MERIT_NOT_PROPAGATED'
            THEN TRUE
        ELSE FALSE
    END as merit_propagation_issue,

    -- Financial impact estimation
    CASE
        WHEN compensation_gap > 0
            THEN compensation_gap * 1.0  -- Employee was underpaid
        ELSE 0
    END as estimated_underpayment_amount

FROM merit_impact_analysis
ORDER BY
    data_quality_status DESC,  -- Show violations first
    abs(compensation_gap) DESC,  -- Then by severity of gap
    employee_id,
    simulation_year
