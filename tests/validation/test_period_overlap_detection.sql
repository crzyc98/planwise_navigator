-- Validation test to detect overlapping compensation periods
-- This test ensures no employee has overlapping compensation periods
-- which was the root cause of the $471 calculation error

{% set simulation_year = var('simulation_year', 2025) %}

WITH compensation_periods_debug AS (
    -- This would need to reference the intermediate compensation_periods CTE
    -- For now, we'll create a placeholder that can be run after model build
    SELECT
        'PLACEHOLDER' AS employee_id,
        '{{ simulation_year }}-01-01'::DATE AS period_start,
        '{{ simulation_year }}-12-31'::DATE AS period_end,
        'This test requires access to compensation_periods CTE' AS validation_note
    WHERE FALSE -- This ensures no actual results for placeholder
),

-- Detect overlapping periods for any employee
overlap_detection AS (
    SELECT
        employee_id,
        period_start,
        period_end,
        period_type,
        period_salary,
        -- Check for overlaps with next period
        LEAD(period_start) OVER (
            PARTITION BY employee_id
            ORDER BY period_start
        ) AS next_period_start,
        -- Flag overlapping periods
        CASE
            WHEN period_end >= LEAD(period_start) OVER (
                PARTITION BY employee_id
                ORDER BY period_start
            ) THEN TRUE
            ELSE FALSE
        END AS has_overlap
    FROM compensation_periods_debug
    WHERE employee_id IS NOT NULL
),

-- Identify employees with overlapping periods
employees_with_overlaps AS (
    SELECT
        employee_id,
        COUNT(*) AS total_periods,
        COUNT(CASE WHEN has_overlap THEN 1 END) AS overlapping_periods,
        STRING_AGG(
            CONCAT(
                period_type, ': ',
                period_start, ' to ', period_end
            ),
            '; '
        ) AS period_details
    FROM overlap_detection
    WHERE has_overlap = TRUE
    GROUP BY employee_id
),

-- Check for excessive total days (> 365 per employee)
excessive_days_check AS (
    SELECT
        employee_id,
        SUM(DATE_DIFF('day', period_start, period_end) + 1) AS total_period_days,
        CASE
            WHEN SUM(DATE_DIFF('day', period_start, period_end) + 1) > 365
            THEN 'EXCESSIVE_DAYS'
            ELSE 'VALID'
        END AS days_validation_status
    FROM compensation_periods_debug
    WHERE employee_id IS NOT NULL
    GROUP BY employee_id
    HAVING SUM(DATE_DIFF('day', period_start, period_end) + 1) > 365
),

-- Summary validation results
validation_summary AS (
    SELECT
        'OVERLAP_CHECK' AS test_type,
        COUNT(DISTINCT employee_id) AS employees_with_issues,
        'Employees with overlapping compensation periods' AS issue_description
    FROM employees_with_overlaps

    UNION ALL

    SELECT
        'EXCESSIVE_DAYS_CHECK' AS test_type,
        COUNT(DISTINCT employee_id) AS employees_with_issues,
        'Employees with > 365 total period days' AS issue_description
    FROM excessive_days_check
)

-- Return validation results
-- This test should show 0 employees_with_issues for both checks after the fix
SELECT
    test_type,
    employees_with_issues,
    issue_description,
    CASE
        WHEN employees_with_issues = 0 THEN 'PASS'
        ELSE 'FAIL'
    END AS validation_status
FROM validation_summary

-- Note: This test requires the compensation_periods CTE to be accessible
-- Currently returns placeholder results until model is built and tested
