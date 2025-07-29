-- Validation test: Promotion Compensation State Management Fix
-- Ensures promotion events use full_year_equivalent_compensation from previous year
-- instead of stale current_compensation, maintaining workforce state continuity

{{ config(
    tags=['data_quality', 'promotion_fix', 'validation']
) }}

WITH promotion_compensation_validation AS (
    -- Get promotion events and their previous compensation
    SELECT
        p.employee_id,
        p.simulation_year,
        p.effective_date,
        p.previous_compensation AS promotion_previous_salary,
        p.compensation_amount AS promotion_new_salary,

        -- Get the previous year's workforce snapshot data
        ws.current_compensation AS snapshot_start_compensation,
        ws.full_year_equivalent_compensation AS snapshot_end_compensation,

        -- Calculate compensation gaps
        p.previous_compensation - ws.full_year_equivalent_compensation AS expected_gap,
        p.previous_compensation - ws.current_compensation AS baseline_gap,

        -- Validation logic
        CASE
            WHEN ABS(p.previous_compensation - ws.full_year_equivalent_compensation) < 0.01
                THEN 'CORRECT_USES_FULL_YEAR_EQUIVALENT'
            WHEN ABS(p.previous_compensation - ws.current_compensation) < 0.01
                THEN 'INCORRECT_USES_START_OF_YEAR'
            ELSE 'UNKNOWN_COMPENSATION_SOURCE'
        END AS compensation_source_validation,

        -- Financial impact assessment
        CASE
            WHEN ABS(p.previous_compensation - ws.full_year_equivalent_compensation) > 1000
                THEN 'SIGNIFICANT_IMPACT'
            WHEN ABS(p.previous_compensation - ws.full_year_equivalent_compensation) > 100
                THEN 'MODERATE_IMPACT'
            WHEN ABS(p.previous_compensation - ws.full_year_equivalent_compensation) > 10
                THEN 'MINOR_IMPACT'
            ELSE 'NO_IMPACT'
        END AS financial_impact_level

    FROM {{ ref('fct_yearly_events') }} p
    LEFT JOIN {{ ref('fct_workforce_snapshot') }} ws
        ON p.employee_id = ws.employee_id
        AND p.simulation_year - 1 = ws.simulation_year
        AND ws.employment_status = 'active'
    WHERE p.event_type = 'promotion'
        AND p.simulation_year > 2025  -- Skip baseline year
)

-- Return test failures (any promotion using incorrect compensation source)
SELECT
    employee_id,
    simulation_year,
    promotion_previous_salary,
    snapshot_start_compensation,
    snapshot_end_compensation,
    expected_gap,
    baseline_gap,
    compensation_source_validation,
    financial_impact_level,
    'Promotion event uses stale compensation instead of full_year_equivalent' AS failure_reason
FROM promotion_compensation_validation
WHERE compensation_source_validation = 'INCORRECT_USES_START_OF_YEAR'
   OR financial_impact_level IN ('SIGNIFICANT_IMPACT', 'MODERATE_IMPACT')
