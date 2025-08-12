-- Enrollment Participation Rate Fix Validation Test
-- Run this after implementing fixes to validate restoration of ~76% participation rates

-- Test 1: Check workforce snapshot includes ALL accumulator employees
SELECT
    'Workforce Coverage Test' AS test_name,
    COUNT(DISTINCT acc.employee_id) AS accumulator_employees,
    COUNT(DISTINCT ws.employee_id) AS workforce_snapshot_employees,
    ROUND(
        COUNT(DISTINCT ws.employee_id) * 100.0 /
        NULLIF(COUNT(DISTINCT acc.employee_id), 0), 1
    ) AS coverage_percentage,
    CASE
        WHEN COUNT(DISTINCT ws.employee_id) = COUNT(DISTINCT acc.employee_id) THEN 'PASS'
        ELSE 'FAIL - Missing ' || (COUNT(DISTINCT acc.employee_id) - COUNT(DISTINCT ws.employee_id)) || ' employees'
    END AS test_result
FROM int_enrollment_state_accumulator acc
LEFT JOIN fct_workforce_snapshot ws
    ON acc.employee_id = ws.employee_id
    AND acc.simulation_year = ws.simulation_year
WHERE acc.simulation_year = 2026  -- Test with year 2026
    AND acc.enrollment_status = true;

-- Test 2: Participation rate consistency across years
SELECT
    'Participation Rate Consistency' AS test_name,
    simulation_year,
    COUNT(*) AS total_active_employees,
    COUNT(CASE WHEN employee_enrollment_date IS NOT NULL THEN 1 END) AS enrolled_employees,
    ROUND(
        COUNT(CASE WHEN employee_enrollment_date IS NOT NULL THEN 1 END) * 100.0 /
        NULLIF(COUNT(*), 0), 1
    ) AS participation_rate,
    CASE
        WHEN ROUND(
            COUNT(CASE WHEN employee_enrollment_date IS NOT NULL THEN 1 END) * 100.0 /
            NULLIF(COUNT(*), 0), 1
        ) BETWEEN 74.0 AND 78.0 THEN 'PASS'
        ELSE 'FAIL'
    END AS test_result
FROM fct_workforce_snapshot
WHERE employment_status = 'active'
    AND simulation_year IN (2025, 2026, 2027)
GROUP BY simulation_year
ORDER BY simulation_year;

-- Test 3: Check for duplicate enrollments (should be zero)
SELECT
    'Duplicate Enrollment Test' AS test_name,
    COUNT(*) AS duplicate_enrollments,
    CASE
        WHEN COUNT(*) = 0 THEN 'PASS'
        ELSE 'FAIL - ' || COUNT(*) || ' duplicate enrollments found'
    END AS test_result
FROM (
    SELECT employee_id, COUNT(*) as enrollment_count
    FROM fct_yearly_events
    WHERE event_type = 'enrollment'
        AND simulation_year IN (2025, 2026, 2027)
    GROUP BY employee_id
    HAVING COUNT(*) > 1
) duplicates;

-- Test 4: Validate enrollment state accumulator continuity
SELECT
    'Accumulator Continuity Test' AS test_name,
    simulation_year,
    COUNT(*) AS total_records,
    COUNT(CASE WHEN enrollment_status = true THEN 1 END) AS enrolled_records,
    COUNT(CASE WHEN enrollment_date IS NOT NULL THEN 1 END) AS records_with_dates,
    CASE
        WHEN COUNT(CASE WHEN enrollment_status = true AND enrollment_date IS NULL THEN 1 END) = 0 THEN 'PASS'
        ELSE 'FAIL - ' || COUNT(CASE WHEN enrollment_status = true AND enrollment_date IS NULL THEN 1 END) || ' enrolled records missing dates'
    END AS test_result
FROM int_enrollment_state_accumulator
WHERE simulation_year IN (2025, 2026, 2027)
GROUP BY simulation_year
ORDER BY simulation_year;

-- Test 5: Employee contribution calculations alignment
SELECT
    'Contribution Calculation Test' AS test_name,
    COUNT(DISTINCT ws.employee_id) AS workforce_enrolled,
    COUNT(DISTINCT ec.employee_id) AS contribution_calculated,
    CASE
        WHEN COUNT(DISTINCT ws.employee_id) = COUNT(DISTINCT ec.employee_id) THEN 'PASS'
        ELSE 'FAIL - Mismatch: ' || ABS(COUNT(DISTINCT ws.employee_id) - COUNT(DISTINCT ec.employee_id)) || ' employees'
    END AS test_result
FROM fct_workforce_snapshot ws
LEFT JOIN int_employee_contributions ec
    ON ws.employee_id = ec.employee_id
    AND ws.simulation_year = ec.simulation_year
WHERE ws.employment_status = 'active'
    AND ws.employee_enrollment_date IS NOT NULL
    AND ws.simulation_year = 2026;
