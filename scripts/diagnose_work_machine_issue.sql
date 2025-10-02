-- Run these queries on your work machine to diagnose the issue
-- Database location: dbt/simulation.duckdb

-- 1. Check if Year 1 hire events are leaking into Year 2
SELECT
    simulation_year,
    event_type,
    COUNT(*) as event_count,
    COUNT(DISTINCT employee_id) as unique_employees
FROM fct_yearly_events
WHERE event_type = 'hire'
GROUP BY simulation_year, event_type
ORDER BY simulation_year;

-- 2. Check year-over-year employee transitions
SELECT
    'Year 1 Active' as category,
    COUNT(*) as count
FROM fct_workforce_snapshot
WHERE simulation_year = 2025 AND employment_status = 'active'
UNION ALL
SELECT
    'Year 2 Base (from prev year)' as category,
    COUNT(*) as count
FROM int_active_employees_prev_year_snapshot
WHERE simulation_year = 2026
UNION ALL
SELECT
    'Year 2 Active' as category,
    COUNT(*) as count
FROM fct_workforce_snapshot
WHERE simulation_year = 2026 AND employment_status = 'active';

-- 3. Check if Year 1 new hires are being reclassified correctly in Year 2
WITH year1_new_hires AS (
    SELECT employee_id, employee_hire_date
    FROM fct_workforce_snapshot
    WHERE simulation_year = 2025
      AND detailed_status_code = 'new_hire_active'
)
SELECT
    y2.detailed_status_code,
    COUNT(*) as count
FROM year1_new_hires y1
LEFT JOIN fct_workforce_snapshot y2
    ON y1.employee_id = y2.employee_id
    AND y2.simulation_year = 2026
GROUP BY y2.detailed_status_code
ORDER BY count DESC;

-- 4. Check for duplicate events
SELECT
    employee_id,
    simulation_year,
    event_type,
    COUNT(*) as event_count
FROM fct_yearly_events
WHERE event_type = 'hire'
GROUP BY employee_id, simulation_year, event_type
HAVING COUNT(*) > 1
LIMIT 20;

-- 5. Check int_active_employees_prev_year_snapshot existence and row count
SELECT
    simulation_year,
    COUNT(*) as count
FROM int_active_employees_prev_year_snapshot
GROUP BY simulation_year
ORDER BY simulation_year;
