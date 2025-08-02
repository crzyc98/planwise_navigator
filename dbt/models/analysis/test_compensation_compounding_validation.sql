{{ config(
    materialized='view',
    tags=['analysis', 'compensation', 'validation']
) }}

-- Comprehensive validation query to verify that compensation raises are compounding correctly across simulation years
-- This model tracks individual employees across multiple years to validate compensation progression

WITH

employee_year_over_year AS (
    -- Track each employee's compensation progression year over year
    SELECT
        curr.employee_id,
        curr.simulation_year AS current_year,
        prev.simulation_year AS previous_year,
        prev.full_year_equivalent_compensation AS previous_year_ending_salary,
        curr.current_compensation AS current_year_starting_salary,
        curr.full_year_equivalent_compensation AS current_year_ending_salary,
        -- Calculate if compensation carried forward correctly
        CASE
            WHEN curr.current_compensation = prev.full_year_equivalent_compensation THEN 'CORRECT'
            WHEN curr.current_compensation = prev.current_compensation THEN 'INCORRECT_NO_COMPOUND'
            ELSE 'MISMATCH'
        END AS compounding_status,
        -- Calculate the discrepancy
        curr.current_compensation - prev.full_year_equivalent_compensation AS salary_discrepancy,
        -- Get raise information
        raises.total_raise_amount,
        raises.raise_count
    FROM {{ ref('fct_workforce_snapshot') }} curr
    INNER JOIN {{ ref('fct_workforce_snapshot') }} prev
        ON curr.employee_id = prev.employee_id
        AND curr.simulation_year = prev.simulation_year + 1
        AND prev.employment_status = 'active'
        AND curr.employment_status = 'active'
    LEFT JOIN (
        -- Aggregate raises by employee and year
        SELECT
            employee_id,
            simulation_year,
            SUM(CASE WHEN event_category = 'RAISE' THEN compensation_amount - previous_compensation ELSE 0 END) AS total_raise_amount,
            COUNT(CASE WHEN event_category = 'RAISE' THEN 1 END) AS raise_count
        FROM {{ ref('fct_yearly_events') }}
        WHERE event_category = 'RAISE'
        GROUP BY employee_id, simulation_year
    ) raises
        ON prev.employee_id = raises.employee_id
        AND prev.simulation_year = raises.simulation_year
),

compounding_summary AS (
    -- Summary statistics on compounding accuracy
    SELECT
        current_year,
        COUNT(*) AS total_employees_tracked,
        SUM(CASE WHEN compounding_status = 'CORRECT' THEN 1 ELSE 0 END) AS correct_compounding_count,
        SUM(CASE WHEN compounding_status = 'INCORRECT_NO_COMPOUND' THEN 1 ELSE 0 END) AS no_compounding_count,
        SUM(CASE WHEN compounding_status = 'MISMATCH' THEN 1 ELSE 0 END) AS mismatch_count,
        -- Calculate percentages
        ROUND(100.0 * SUM(CASE WHEN compounding_status = 'CORRECT' THEN 1 ELSE 0 END) / COUNT(*), 2) AS correct_compounding_pct,
        -- Average discrepancy for incorrect cases
        AVG(CASE WHEN compounding_status != 'CORRECT' THEN ABS(salary_discrepancy) END) AS avg_discrepancy_amount,
        -- Total lost compensation due to non-compounding
        SUM(CASE WHEN compounding_status = 'INCORRECT_NO_COMPOUND' THEN salary_discrepancy ELSE 0 END) AS total_lost_compensation
    FROM employee_year_over_year
    GROUP BY current_year
),

-- MERIT EVENTS COMPOUNDING FIX: Add specific merit event validation
merit_event_validation AS (
    -- Verify merit events are using correct previous year compensation as baseline
    SELECT
        me.employee_id,
        me.simulation_year,
        me.previous_compensation AS merit_baseline_used,
        me.compensation_amount AS merit_new_salary,
        awfe.employee_gross_compensation AS expected_baseline,
        ws_prev.full_year_equivalent_compensation AS actual_prev_year_final,
        -- Check if merit used correct baseline
        CASE
            WHEN ABS(me.previous_compensation - awfe.employee_gross_compensation) < 0.01 THEN 'CORRECT_BASELINE'
            WHEN ABS(me.previous_compensation - ws_prev.current_compensation) < 0.01 THEN 'USING_STARTING_COMPENSATION'
            ELSE 'UNKNOWN_BASELINE'
        END AS baseline_status,
        -- Calculate merit percentage applied
        ROUND((me.compensation_amount / me.previous_compensation - 1) * 100, 2) AS merit_percentage_applied,
        -- Validate the merit calculation chain
        me.previous_compensation - expected_baseline AS baseline_discrepancy
    FROM {{ ref('fct_yearly_events') }} me
    INNER JOIN {{ ref('int_workforce_active_for_events') }} awfe
        ON me.employee_id = awfe.employee_id
        AND me.simulation_year = awfe.simulation_year
    LEFT JOIN {{ ref('fct_workforce_snapshot') }} ws_prev
        ON me.employee_id = ws_prev.employee_id
        AND ws_prev.simulation_year = me.simulation_year - 1
        AND ws_prev.employment_status = 'active'
    WHERE me.event_category = 'RAISE'
        AND me.simulation_year > 2025  -- Only check subsequent years
),

merit_event_summary AS (
    -- Summary of merit event baseline usage
    SELECT
        simulation_year,
        COUNT(*) AS total_merit_events,
        SUM(CASE WHEN baseline_status = 'CORRECT_BASELINE' THEN 1 ELSE 0 END) AS correct_baseline_count,
        SUM(CASE WHEN baseline_status = 'USING_STARTING_COMPENSATION' THEN 1 ELSE 0 END) AS wrong_baseline_count,
        SUM(CASE WHEN baseline_status = 'UNKNOWN_BASELINE' THEN 1 ELSE 0 END) AS unknown_baseline_count,
        ROUND(100.0 * SUM(CASE WHEN baseline_status = 'CORRECT_BASELINE' THEN 1 ELSE 0 END) / COUNT(*), 2) AS correct_baseline_pct,
        AVG(ABS(baseline_discrepancy)) AS avg_baseline_discrepancy,
        -- Check if merit counts vary appropriately between years (compounding should cause variation)
        COUNT(*) - LAG(COUNT(*)) OVER (ORDER BY simulation_year) AS merit_count_change_from_prev_year
    FROM merit_event_validation
    GROUP BY simulation_year
),

specific_examples AS (
    -- Track specific employee examples for validation
    SELECT
        employee_id,
        current_year,
        previous_year,
        previous_year_ending_salary,
        current_year_starting_salary,
        current_year_ending_salary,
        compounding_status,
        salary_discrepancy,
        total_raise_amount,
        -- Calculate expected vs actual progression
        previous_year_ending_salary * 1.043 AS expected_with_4_3_pct_raise,
        current_year_ending_salary - (previous_year_ending_salary * 1.043) AS deviation_from_expected
    FROM employee_year_over_year
    WHERE
        -- Focus on employees with known raise patterns or issues
        (ABS(salary_discrepancy) > 100 OR compounding_status != 'CORRECT')
        -- Include specific test case mentioned in the plan
        OR (previous_year_ending_salary BETWEEN 175000 AND 177000)
    ORDER BY ABS(salary_discrepancy) DESC
    LIMIT 20
),

multi_year_progression AS (
    -- Track employees across multiple years to verify compounding
    SELECT
        ws2025.employee_id,
        ws2025.current_compensation AS salary_2025_start,
        ws2025.full_year_equivalent_compensation AS salary_2025_end,
        ws2026.current_compensation AS salary_2026_start,
        ws2026.full_year_equivalent_compensation AS salary_2026_end,
        ws2027.current_compensation AS salary_2027_start,
        ws2027.full_year_equivalent_compensation AS salary_2027_end,
        ws2028.current_compensation AS salary_2028_start,
        ws2028.full_year_equivalent_compensation AS salary_2028_end,
        -- Verify compounding at each transition
        CASE WHEN ws2026.current_compensation = ws2025.full_year_equivalent_compensation THEN 'YES' ELSE 'NO' END AS compound_2025_to_2026,
        CASE WHEN ws2027.current_compensation = ws2026.full_year_equivalent_compensation THEN 'YES' ELSE 'NO' END AS compound_2026_to_2027,
        CASE WHEN ws2028.current_compensation = ws2027.full_year_equivalent_compensation THEN 'YES' ELSE 'NO' END AS compound_2027_to_2028,
        -- Calculate cumulative growth
        (ws2028.full_year_equivalent_compensation / ws2025.current_compensation - 1) * 100 AS total_growth_pct,
        -- Expected growth with 4.3% annual raises compounded
        (POWER(1.043, 3) - 1) * 100 AS expected_growth_pct
    FROM {{ ref('fct_workforce_snapshot') }} ws2025
    LEFT JOIN {{ ref('fct_workforce_snapshot') }} ws2026
        ON ws2025.employee_id = ws2026.employee_id AND ws2026.simulation_year = 2026
    LEFT JOIN {{ ref('fct_workforce_snapshot') }} ws2027
        ON ws2025.employee_id = ws2027.employee_id AND ws2027.simulation_year = 2027
    LEFT JOIN {{ ref('fct_workforce_snapshot') }} ws2028
        ON ws2025.employee_id = ws2028.employee_id AND ws2028.simulation_year = 2028
    WHERE ws2025.simulation_year = 2025
        AND ws2025.employment_status = 'active'
        -- Focus on employees who remain active through all years
        AND ws2026.employment_status = 'active'
        AND ws2027.employment_status = 'active'
        AND ws2028.employment_status = 'active'
    LIMIT 10
)

-- Final output combining all validation results
SELECT
    'SUMMARY' AS validation_type,
    s.current_year,
    s.total_employees_tracked,
    s.correct_compounding_count,
    s.correct_compounding_pct,
    s.no_compounding_count,
    s.mismatch_count,
    s.avg_discrepancy_amount,
    s.total_lost_compensation,
    NULL AS employee_id,
    NULL AS previous_year_ending_salary,
    NULL AS current_year_starting_salary,
    NULL AS compounding_status,
    NULL AS salary_discrepancy
FROM compounding_summary s

UNION ALL

SELECT
    'EXAMPLE' AS validation_type,
    e.current_year,
    NULL AS total_employees_tracked,
    NULL AS correct_compounding_count,
    NULL AS correct_compounding_pct,
    NULL AS no_compounding_count,
    NULL AS mismatch_count,
    NULL AS avg_discrepancy_amount,
    NULL AS total_lost_compensation,
    e.employee_id,
    e.previous_year_ending_salary,
    e.current_year_starting_salary,
    e.compounding_status,
    e.salary_discrepancy
FROM specific_examples e

UNION ALL

-- MERIT EVENTS COMPOUNDING FIX: Add merit event validation results to output
SELECT
    'MERIT_EVENTS' AS validation_type,
    mes.simulation_year AS current_year,
    mes.total_merit_events AS total_employees_tracked,
    mes.correct_baseline_count AS correct_compounding_count,
    mes.correct_baseline_pct AS correct_compounding_pct,
    mes.wrong_baseline_count AS no_compounding_count,
    mes.unknown_baseline_count AS mismatch_count,
    mes.avg_baseline_discrepancy AS avg_discrepancy_amount,
    NULL AS total_lost_compensation,
    NULL AS employee_id,
    NULL AS previous_year_ending_salary,
    NULL AS current_year_starting_salary,
    CAST(mes.merit_count_change_from_prev_year AS TEXT) AS compounding_status,
    NULL AS salary_discrepancy
FROM merit_event_summary mes

ORDER BY validation_type, current_year
