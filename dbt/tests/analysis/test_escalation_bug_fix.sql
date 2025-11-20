-- Converted from validation model to test
-- Added simulation_year filter for performance

/*
Validation Test for Auto-Escalation Bug Fix

This test validates that the escalation bug has been fixed.

Bug Description:
- Employees with census deferral rates >= maximum_rate were incorrectly being enrolled in escalation
- Their rates were being reduced (e.g., 15% → 6%)

Fix:
- Use int_deferral_rate_state_accumulator_v2 for current deferral rates instead of calculating demographic baseline
- Enhanced eligibility check: (w.current_deferral_rate > 0 AND w.current_deferral_rate < maximum_rate)

Expected Results After Fix:
- 0 rows returned means no employees with census rate > max being escalated
- All employees at/above max are properly excluded from escalation
*/

WITH escalation_config AS (
    SELECT 0.10 as maximum_rate  -- From deferral_auto_escalation.maximum_rate
),

baseline_census_rates AS (
    SELECT
        employee_id,
        employee_deferral_rate as census_rate
    FROM {{ ref('int_baseline_workforce') }}
    WHERE simulation_year = {{ var('simulation_year') }}
        AND employee_deferral_rate IS NOT NULL
),

-- Test 1: Find employees with census rate > maximum_rate being escalated (should be 0)
census_rate_above_max_escalated AS (
    SELECT
        e.employee_id,
        b.census_rate,
        e.previous_deferral_rate as calculated_rate,
        e.new_deferral_rate,
        c.maximum_rate,
        'BUG: Census rate above max but being escalated' as issue_description
    FROM {{ ref('int_deferral_rate_escalation_events') }} e
    JOIN baseline_census_rates b ON e.employee_id = b.employee_id
    CROSS JOIN escalation_config c
    WHERE b.census_rate > c.maximum_rate
      AND e.simulation_year = {{ var('simulation_year') }}
),

-- Test 2: Find employees at/above max being escalated (should be 0)
employees_at_max_escalating AS (
    SELECT
        e.employee_id,
        e.previous_deferral_rate as current_rate_before_escalation,
        e.new_deferral_rate,
        c.maximum_rate,
        'BUG: Employee at/above max is escalating' as issue_description
    FROM {{ ref('int_deferral_rate_escalation_events') }} e
    CROSS JOIN escalation_config c
    WHERE e.previous_deferral_rate >= c.maximum_rate
      AND e.simulation_year = {{ var('simulation_year') }}
),

-- Test 3: Find employees escalating too soon after enrollment (should be 0)
enrollment_dates AS (
    SELECT
        employee_id,
        MIN(effective_date) as first_enrollment_date
    FROM (
        SELECT employee_id, effective_date
        FROM {{ ref('int_enrollment_events') }}
        WHERE LOWER(event_type) = 'enrollment'
          AND simulation_year = {{ var('simulation_year') }}
        UNION ALL
        SELECT employee_id, effective_date
        FROM {{ ref('int_synthetic_baseline_enrollment_events') }}
        WHERE simulation_year = {{ var('simulation_year') }}
    )
    GROUP BY employee_id
),

escalation_delay_violations AS (
    SELECT
        e.employee_id,
        ed.first_enrollment_date,
        e.effective_date as escalation_date,
        EXTRACT('year' FROM e.effective_date) - EXTRACT('year' FROM ed.first_enrollment_date) as years_delay,
        'BUG: Escalating too soon after enrollment (delay < 1 year)' as issue_description
    FROM {{ ref('int_deferral_rate_escalation_events') }} e
    JOIN enrollment_dates ed ON e.employee_id = ed.employee_id
    WHERE e.simulation_year = {{ var('simulation_year') }}
      AND EXTRACT('year' FROM e.effective_date) - EXTRACT('year' FROM ed.first_enrollment_date) < 1
)

-- Return only failing records (0 rows = all tests pass)
SELECT
    employee_id,
    census_rate as rate_value,
    issue_description,
    {{ var('simulation_year') }} as simulation_year,
    CURRENT_TIMESTAMP as validation_timestamp
FROM census_rate_above_max_escalated

UNION ALL

SELECT
    employee_id,
    current_rate_before_escalation as rate_value,
    issue_description,
    {{ var('simulation_year') }},
    CURRENT_TIMESTAMP
FROM employees_at_max_escalating

UNION ALL

SELECT
    employee_id,
    CAST(years_delay AS DECIMAL) as rate_value,
    issue_description,
    {{ var('simulation_year') }},
    CURRENT_TIMESTAMP
FROM escalation_delay_violations

ORDER BY employee_id
