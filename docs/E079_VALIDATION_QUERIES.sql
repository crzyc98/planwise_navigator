-- E079 Phase 2B & 2C Validation Queries
-- Purpose: Validate circular dependency fix and enrollment simplification
-- Date: 2025-11-03

-- ============================================================================
-- PHASE 2B: CIRCULAR DEPENDENCY FIX VALIDATION
-- ============================================================================

-- Query 1: Verify int_new_hire_termination_events has data
SELECT
  simulation_year,
  COUNT(*) as total_new_hire_terminations,
  COUNT(DISTINCT employee_id) as unique_employees,
  ROUND(AVG(termination_rate), 4) as avg_termination_rate
FROM int_new_hire_termination_events
GROUP BY simulation_year
ORDER BY simulation_year;

-- Expected: Non-zero counts for each simulation year
-- Expected: Termination rate between 0.05 and 0.15 (5-15%)


-- Query 2: Verify new hire terminations are included in fct_yearly_events
SELECT
  simulation_year,
  event_type,
  COUNT(*) as event_count,
  COUNT(DISTINCT employee_id) as unique_employees
FROM fct_yearly_events
WHERE event_type = 'termination'
  AND employee_id LIKE 'NH_%'  -- New hire pattern
GROUP BY simulation_year, event_type
ORDER BY simulation_year;

-- Expected: Should match counts from Query 1


-- Query 3: Verify no orphaned new hire terminations
SELECT
  nt.simulation_year,
  COUNT(DISTINCT nt.employee_id) as terminations_without_hires
FROM int_new_hire_termination_events nt
LEFT JOIN int_hiring_events h
  ON nt.employee_id = h.employee_id
  AND nt.simulation_year = h.simulation_year
WHERE h.employee_id IS NULL
GROUP BY nt.simulation_year;

-- Expected: 0 rows (all terminated new hires should have hire events)


-- Query 4: Verify termination dates are valid (after hire date, within year)
SELECT
  nt.simulation_year,
  COUNT(*) as total_terminations,
  COUNT(CASE WHEN nt.effective_date > h.effective_date THEN 1 END) as valid_termination_dates,
  COUNT(CASE WHEN nt.effective_date <= h.effective_date THEN 1 END) as invalid_before_hire,
  COUNT(CASE WHEN nt.effective_date > CAST(nt.simulation_year || '-12-31' AS DATE) THEN 1 END) as invalid_after_year_end
FROM int_new_hire_termination_events nt
JOIN int_hiring_events h
  ON nt.employee_id = h.employee_id
  AND nt.simulation_year = h.simulation_year
GROUP BY nt.simulation_year
ORDER BY nt.simulation_year;

-- Expected: All terminations have valid_termination_dates = total_terminations
-- Expected: invalid_before_hire = 0, invalid_after_year_end = 0


-- ============================================================================
-- PHASE 2C: ENROLLMENT SIMPLIFICATION VALIDATION
-- ============================================================================

-- Query 5: Compare enrollment counts (original vs v2)
-- NOTE: Run this query twice - once with int_enrollment_events, once with int_enrollment_events_v2
-- to compare results

WITH enrollment_summary AS (
  SELECT
    simulation_year,
    event_type,
    event_category,
    COUNT(*) as event_count,
    COUNT(DISTINCT employee_id) as unique_employees,
    ROUND(AVG(employee_deferral_rate), 4) as avg_deferral_rate,
    ROUND(MIN(employee_deferral_rate), 4) as min_deferral_rate,
    ROUND(MAX(employee_deferral_rate), 4) as max_deferral_rate
  FROM int_enrollment_events  -- Change to int_enrollment_events_v2 for v2 comparison
  WHERE simulation_year IN (2025, 2026, 2027)
  GROUP BY simulation_year, event_type, event_category
)
SELECT * FROM enrollment_summary
ORDER BY simulation_year, event_type, event_category;

-- Expected: Similar counts between original and v2 (within 5% tolerance)
-- Expected: avg_deferral_rate should be consistent


-- Query 6: Check for duplicate enrollments (multi-year)
SELECT
  employee_id,
  COUNT(*) as total_enrollment_events,
  STRING_AGG(CAST(simulation_year AS VARCHAR), ', ' ORDER BY simulation_year) as enrollment_years,
  STRING_AGG(event_category, ', ' ORDER BY simulation_year) as enrollment_categories
FROM int_enrollment_events_v2
WHERE event_type = 'enrollment'
GROUP BY employee_id
HAVING COUNT(*) > 1
ORDER BY COUNT(*) DESC
LIMIT 50;

-- Expected: 0 rows (no duplicate enrollments)
-- If rows exist, investigate why employees are enrolling multiple times


-- Query 7: Validate demographic segmentation consistency
SELECT
  age_band,
  tenure_band,
  event_category,
  COUNT(*) as event_count,
  COUNT(DISTINCT employee_id) as unique_employees,
  ROUND(AVG(employee_deferral_rate), 4) as avg_deferral_rate,
  ROUND(AVG(event_probability), 4) as avg_probability
FROM int_enrollment_events_v2
WHERE event_type = 'enrollment'
  AND simulation_year = 2025
GROUP BY age_band, tenure_band, event_category
ORDER BY age_band, tenure_band, event_category;

-- Expected: Deferral rates should increase with age
-- Expected: Event probabilities should increase with age


-- Query 8: Verify opt-out events are only for enrolled employees
SELECT
  oo.simulation_year,
  COUNT(*) as total_opt_outs,
  COUNT(DISTINCT oo.employee_id) as unique_opt_outs,
  COUNT(CASE WHEN ee.employee_id IS NOT NULL THEN 1 END) as opt_outs_with_enrollment
FROM int_enrollment_events_v2 oo
LEFT JOIN (
  SELECT DISTINCT employee_id, simulation_year
  FROM int_enrollment_events_v2
  WHERE event_type = 'enrollment'
) ee ON oo.employee_id = ee.employee_id AND oo.simulation_year = ee.simulation_year
WHERE oo.event_type = 'enrollment_change'
GROUP BY oo.simulation_year
ORDER BY oo.simulation_year;

-- Expected: opt_outs_with_enrollment = total_opt_outs (100% match)
-- Expected: Opt-outs should only occur for employees who enrolled


-- Query 9: Multi-year enrollment continuity check
SELECT
  simulation_year,
  COUNT(DISTINCT employee_id) as total_active_employees,
  COUNT(DISTINCT CASE WHEN event_type = 'enrollment' THEN employee_id END) as new_enrollments,
  COUNT(DISTINCT CASE WHEN event_type = 'enrollment_change' THEN employee_id END) as opt_outs,
  ROUND(
    COUNT(DISTINCT CASE WHEN event_type = 'enrollment' THEN employee_id END) * 100.0 /
    NULLIF(COUNT(DISTINCT employee_id), 0),
    2
  ) as enrollment_rate
FROM int_enrollment_events_v2
GROUP BY simulation_year
ORDER BY simulation_year;

-- Expected: Enrollment rate should be relatively stable across years (e.g., 30-50%)
-- Expected: New enrollments should decline over time (as more employees are already enrolled)


-- Query 10: Validate enrollment state accumulator consistency
-- This checks if the enrollment state accumulator matches the enrollment events
WITH enrollment_events_aggregated AS (
  SELECT
    employee_id,
    simulation_year,
    MAX(CASE WHEN event_type = 'enrollment' THEN 1 ELSE 0 END) as had_enrollment_event,
    MAX(CASE WHEN event_type = 'enrollment_change' AND LOWER(event_details) LIKE '%opt-out%' THEN 1 ELSE 0 END) as had_opt_out_event
  FROM int_enrollment_events_v2
  GROUP BY employee_id, simulation_year
)
SELECT
  ea.simulation_year,
  COUNT(*) as total_employees_with_events,
  COUNT(CASE WHEN ea.had_enrollment_event = 1 AND sa.enrollment_status = true THEN 1 END) as matching_enrollments,
  COUNT(CASE WHEN ea.had_opt_out_event = 1 AND sa.enrollment_status = false THEN 1 END) as matching_opt_outs,
  COUNT(CASE WHEN ea.had_enrollment_event = 1 AND sa.enrollment_status != true THEN 1 END) as mismatched_enrollments,
  COUNT(CASE WHEN ea.had_opt_out_event = 1 AND sa.enrollment_status != false THEN 1 END) as mismatched_opt_outs
FROM enrollment_events_aggregated ea
LEFT JOIN int_enrollment_state_accumulator sa
  ON ea.employee_id = sa.employee_id
  AND ea.simulation_year = sa.simulation_year
GROUP BY ea.simulation_year
ORDER BY ea.simulation_year;

-- Expected: mismatched_enrollments = 0, mismatched_opt_outs = 0
-- Expected: State accumulator should reflect all enrollment events


-- Query 11: Performance comparison (run with EXPLAIN ANALYZE)
EXPLAIN ANALYZE
SELECT
  event_type,
  event_category,
  COUNT(*) as event_count
FROM int_enrollment_events_v2
WHERE simulation_year = 2025
GROUP BY event_type, event_category;

-- Expected: Query should complete in < 1 second
-- Compare execution time with original int_enrollment_events model


-- Query 12: Data quality validation
SELECT
  simulation_year,
  data_quality_flag,
  COUNT(*) as event_count,
  COUNT(DISTINCT employee_id) as unique_employees
FROM int_enrollment_events_v2
GROUP BY simulation_year, data_quality_flag
ORDER BY simulation_year, data_quality_flag;

-- Expected: All events should have data_quality_flag = 'VALID'
-- Expected: No INVALID flags


-- ============================================================================
-- INTEGRATION VALIDATION
-- ============================================================================

-- Query 13: Verify fct_yearly_events includes all enrollment events from v2
SELECT
  fy.simulation_year,
  fy.event_type,
  COUNT(DISTINCT fy.employee_id) as fct_unique_employees,
  COUNT(DISTINCT ee.employee_id) as enrollment_unique_employees,
  COUNT(DISTINCT fy.employee_id) - COUNT(DISTINCT ee.employee_id) as difference
FROM fct_yearly_events fy
FULL OUTER JOIN int_enrollment_events_v2 ee
  ON fy.employee_id = ee.employee_id
  AND fy.simulation_year = ee.simulation_year
  AND fy.event_type = ee.event_type
WHERE fy.event_type IN ('enrollment', 'enrollment_change')
  OR ee.event_type IN ('enrollment', 'enrollment_change')
GROUP BY fy.simulation_year, fy.event_type
ORDER BY fy.simulation_year, fy.event_type;

-- Expected: difference = 0 (all enrollment events from v2 are in fct_yearly_events)


-- Query 14: Verify event sequencing is correct
SELECT
  simulation_year,
  employee_id,
  event_type,
  effective_date,
  event_sequence,
  LAG(event_type) OVER (PARTITION BY employee_id, simulation_year ORDER BY event_sequence) as prev_event_type
FROM int_enrollment_events_v2
WHERE simulation_year = 2025
  AND employee_id IN (
    SELECT employee_id
    FROM int_enrollment_events_v2
    WHERE simulation_year = 2025
    GROUP BY employee_id
    HAVING COUNT(*) > 1
  )
ORDER BY employee_id, event_sequence
LIMIT 100;

-- Expected: enrollment events should come before enrollment_change events
-- Expected: event_sequence should be sequential (no gaps)


-- Query 15: Final summary comparison (original vs v2)
WITH original_summary AS (
  SELECT
    'original' as model_version,
    simulation_year,
    COUNT(*) as total_events,
    COUNT(DISTINCT employee_id) as unique_employees,
    COUNT(CASE WHEN event_type = 'enrollment' THEN 1 END) as enrollments,
    COUNT(CASE WHEN event_type = 'enrollment_change' THEN 1 END) as opt_outs
  FROM int_enrollment_events
  WHERE simulation_year IN (2025, 2026, 2027)
  GROUP BY simulation_year
),
v2_summary AS (
  SELECT
    'v2' as model_version,
    simulation_year,
    COUNT(*) as total_events,
    COUNT(DISTINCT employee_id) as unique_employees,
    COUNT(CASE WHEN event_type = 'enrollment' THEN 1 END) as enrollments,
    COUNT(CASE WHEN event_type = 'enrollment_change' THEN 1 END) as opt_outs
  FROM int_enrollment_events_v2
  WHERE simulation_year IN (2025, 2026, 2027)
  GROUP BY simulation_year
)
SELECT * FROM original_summary
UNION ALL
SELECT * FROM v2_summary
ORDER BY simulation_year, model_version;

-- Expected: Similar counts between original and v2 (within 5% tolerance)
-- Expected: If counts differ significantly, investigate root cause


-- ============================================================================
-- NOTES FOR VALIDATION
-- ============================================================================

/*
VALIDATION CHECKLIST:

Phase 2B (Circular Dependency Fix):
✓ Query 1: Verify new hire terminations exist
✓ Query 2: Verify integration with fct_yearly_events
✓ Query 3: Verify no orphaned terminations
✓ Query 4: Verify termination dates are valid

Phase 2C (Enrollment Simplification):
✓ Query 5: Compare enrollment counts (original vs v2)
✓ Query 6: Check for duplicate enrollments
✓ Query 7: Validate demographic segmentation
✓ Query 8: Verify opt-out logic
✓ Query 9: Multi-year continuity
✓ Query 10: State accumulator consistency
✓ Query 11: Performance comparison
✓ Query 12: Data quality validation

Integration:
✓ Query 13: Verify fct_yearly_events integration
✓ Query 14: Verify event sequencing
✓ Query 15: Final summary comparison

ACCEPTANCE CRITERIA:
- All queries should return expected results as documented
- Phase 2B: No circular dependencies, valid termination logic
- Phase 2C: Enrollment counts match within 5%, no duplicates, good performance
- Integration: All events flow correctly to fct_yearly_events

ROLLBACK PLAN:
If validation fails:
1. Restore original int_enrollment_events.sql from backup
2. Revert int_new_hire_termination_events.sql to use adapter.get_relation()
3. Investigate root cause before re-attempting
4. Document lessons learned
*/
