/*
  Test query to verify enrollment event logic for NH_2026_000787
  This employee should get exactly ONE enrollment event across multi-year simulation
*/

-- Test 1: Check if NH_2026_000787 exists in workforce snapshots
SELECT 'Workforce snapshots for NH_2026_000787' as test_description,
       simulation_year,
       employee_id,
       employment_status,
       employee_enrollment_date,
       detailed_status_code
FROM fct_workforce_snapshot
WHERE employee_id = 'NH_2026_000787'
ORDER BY simulation_year;

-- Test 2: Check enrollment events for NH_2026_000787
SELECT 'Enrollment events for NH_2026_000787' as test_description,
       simulation_year,
       employee_id,
       event_type,
       effective_date,
       event_details
FROM fct_yearly_events
WHERE employee_id = 'NH_2026_000787'
  AND event_type IN ('enrollment', 'enrollment_change')
ORDER BY simulation_year, effective_date;

-- Test 3: Check enrollment state accumulator for NH_2026_000787
SELECT 'Enrollment state accumulator for NH_2026_000787' as test_description,
       simulation_year,
       employee_id,
       enrollment_date,
       enrollment_status,
       enrollment_source,
       enrollment_events_this_year
FROM int_enrollment_state_accumulator
WHERE employee_id = 'NH_2026_000787'
ORDER BY simulation_year;

-- Test 4: Count total enrollment events per year to detect duplicates
SELECT 'Total enrollment events per year' as test_description,
       simulation_year,
       COUNT(*) as total_enrollment_events,
       COUNT(DISTINCT employee_id) as unique_employees_enrolled
FROM fct_yearly_events
WHERE event_type = 'enrollment'
GROUP BY simulation_year
ORDER BY simulation_year;

-- Test 5: Check for employees with multiple enrollment events (should be zero)
SELECT 'Employees with multiple enrollment events (should be empty)' as test_description,
       employee_id,
       COUNT(*) as enrollment_event_count,
       GROUP_CONCAT(DISTINCT simulation_year ORDER BY simulation_year) as years_with_enrollments
FROM fct_yearly_events
WHERE event_type = 'enrollment'
GROUP BY employee_id
HAVING COUNT(*) > 1
ORDER BY enrollment_event_count DESC;
