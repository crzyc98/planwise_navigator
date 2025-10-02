/*
Validation Queries for Auto-Escalation Bug Fix

This file contains queries to validate that the escalation bug has been fixed.

Bug Description:
- Employees with census deferral rates >= maximum_rate were incorrectly being enrolled in escalation
- Their rates were being reduced (e.g., 15% → 6%)

Fix:
- Use int_deferral_rate_state_accumulator_v2 for current deferral rates instead of calculating demographic baseline
- Enhanced eligibility check: (w.current_deferral_rate > 0 AND w.current_deferral_rate < maximum_rate)

Expected Results After Fix:
- Query 1 should return 0 rows (no employees with census rate > max being escalated)
- Query 2 should return 0 rows (no employees at/above max in escalation events)
- Query 3 should show proper distribution respecting census rates
*/

-- Query 1: Pre-fix validation (confirm bug existed)
-- Find employees with census rate > maximum_rate being escalated
-- EXPECTED AFTER FIX: 0 rows
WITH escalation_config AS (
    SELECT 0.10 as maximum_rate  -- From deferral_auto_escalation.maximum_rate
),
baseline_census_rates AS (
    SELECT
        employee_id,
        employee_deferral_rate as census_rate
    FROM {{ ref('int_baseline_workforce') }}
    WHERE simulation_year = {{ var('simulation_year', 2025) }}
        AND employee_deferral_rate IS NOT NULL
)
SELECT
    e.employee_id,
    b.census_rate,
    e.previous_deferral_rate as calculated_rate,
    e.new_deferral_rate,
    'BUG: Census rate above max but being escalated' as issue
FROM {{ ref('int_deferral_rate_escalation_events') }} e
JOIN baseline_census_rates b ON e.employee_id = b.employee_id
CROSS JOIN escalation_config c
WHERE b.census_rate > c.maximum_rate
  AND e.simulation_year = {{ var('simulation_year', 2025) }}
ORDER BY b.census_rate DESC;


-- Query 2: Post-fix validation (confirm fix works)
-- Should return 0 rows after fix - no employees at/above max should be escalating
-- EXPECTED AFTER FIX: 0 rows
WITH escalation_config AS (
    SELECT 0.10 as maximum_rate
)
SELECT
    e.employee_id,
    e.previous_deferral_rate as current_rate_before_escalation,
    e.new_deferral_rate,
    'BUG: Employee at/above max is escalating' as issue
FROM {{ ref('int_deferral_rate_escalation_events') }} e
CROSS JOIN escalation_config c
WHERE e.previous_deferral_rate >= c.maximum_rate
  AND e.simulation_year = {{ var('simulation_year', 2025) }};


-- Query 3: Escalation rate distribution analysis
-- Verify that escalations are happening for the right employees
-- EXPECTED: All current_deferral_rate < maximum_rate, proper progression
SELECT
    ROUND(current_deferral_rate * 100, 1) as current_rate_pct,
    ROUND(new_deferral_rate * 100, 1) as new_rate_pct,
    COUNT(*) as employee_count,
    MIN(current_deferral_rate) as min_current_rate,
    MAX(current_deferral_rate) as max_current_rate
FROM {{ ref('int_deferral_rate_escalation_events') }}
WHERE simulation_year = {{ var('simulation_year', 2025) }}
GROUP BY current_rate_pct, new_rate_pct
ORDER BY current_rate_pct;


-- Query 4: First escalation delay validation
-- Verify escalations respect the configured delay (default 1 year)
WITH enrollment_dates AS (
    SELECT
        employee_id,
        MIN(effective_date) as first_enrollment_date
    FROM (
        SELECT employee_id, effective_date
        FROM {{ ref('int_enrollment_events') }}
        WHERE LOWER(event_type) = 'enrollment'
        UNION ALL
        SELECT employee_id, effective_date
        FROM {{ ref('int_synthetic_baseline_enrollment_events') }}
    )
    GROUP BY employee_id
)
SELECT
    e.employee_id,
    ed.first_enrollment_date,
    e.effective_date as escalation_date,
    EXTRACT(YEAR FROM e.effective_date) - EXTRACT(YEAR FROM ed.first_enrollment_date) as years_delay,
    CASE
        WHEN EXTRACT(YEAR FROM e.effective_date) - EXTRACT(YEAR FROM ed.first_enrollment_date) < 1
        THEN 'BUG: Escalating too soon after enrollment'
        ELSE 'OK'
    END as validation_status
FROM {{ ref('int_deferral_rate_escalation_events') }} e
JOIN enrollment_dates ed ON e.employee_id = ed.employee_id
WHERE e.simulation_year = {{ var('simulation_year', 2025) }}
ORDER BY years_delay;
