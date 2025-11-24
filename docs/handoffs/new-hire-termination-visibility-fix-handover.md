# New Hire Termination Visibility Fix - Handover Document

**Date**: 2025-08-02
**Status**: 🔴 CRITICAL BUG - New hire terminations not reflected in workforce snapshot
**Priority**: HIGH - Affects workforce reporting accuracy

## Problem Summary

New hire termination events are correctly generated and stored in `fct_yearly_events`, but employees who were hired and terminated in the same year are **NOT** showing up as terminated in `fct_workforce_snapshot`. Instead, they appear as active new hires, causing:

- **Inflated new hire active counts** (seeing ~1,750 instead of ~875)
- **Missing new hire termination records** (should show terminated new hires)
- **Inaccurate workforce reporting** (active workforce appears larger than it should be)

## Current Symptoms (as of 2025-08-02)

When running the multi-year simulation, we observe:
```
📋 Year-end Employment Makeup by Status:
   continuous_active        : 3,844 (62.8%)
   new_hire_active          : 1,750 (28.6%)  ← SHOULD BE ~875
   experienced_termination  :  524 ( 8.6%)
   new_hire_termination     :     0 ( 0.0%)  ← SHOULD BE ~875
   TOTAL                    : 6,118 (100.0%)

📈 Year 2025 Event Summary:
   hire           : 1,532
   termination    :  960
```

**Expected Result:**
- `new_hire_active`: ~875 (roughly half of hires)
- `new_hire_termination`: ~875 (the other half that were terminated)

## How to Find New Hire Termination Events

### 1. **Location**: Events are stored in `fct_yearly_events` table

### 2. **Identification Criteria**:
```sql
-- Query to find new hire termination events
SELECT
    employee_id,
    event_type,
    event_category,
    event_details,
    effective_date,
    simulation_year
FROM fct_yearly_events
WHERE event_type = 'termination'
  AND event_category = 'new_hire_termination'
  AND simulation_year = 2025
ORDER BY employee_id;
```

### 3. **Count Query**:
```sql
-- Count new hire termination events
SELECT COUNT(*) as new_hire_termination_count
FROM fct_yearly_events
WHERE event_type = 'termination'
  AND event_category = 'new_hire_termination'
  AND simulation_year = 2025;
```

### 4. **Cross-Reference with Hire Events**:
```sql
-- Find employees who were both hired and terminated in same year
SELECT
    h.employee_id,
    h.effective_date as hire_date,
    t.effective_date as termination_date,
    t.event_details as termination_reason
FROM fct_yearly_events h
INNER JOIN fct_yearly_events t
    ON h.employee_id = t.employee_id
    AND h.simulation_year = t.simulation_year
WHERE h.event_type = 'hire'
  AND t.event_type = 'termination'
  AND t.event_category = 'new_hire_termination'
  AND h.simulation_year = 2025
ORDER BY h.employee_id;
```

## Root Cause Analysis

### Issue Location: `fct_workforce_snapshot.sql`

The problem is in the event processing logic around **lines 164-191** in the `new_hires` CTE:

```sql
-- **CURRENT ISSUE**: This logic should apply termination status to new hires
new_hires AS (
    SELECT
        CAST(ye.employee_id AS VARCHAR) AS employee_id,
        ye.employee_ssn,
        -- ... other fields ...
        -- **CRITICAL FIX**: Apply termination status from consolidated event processing
        CASE
            WHEN ec.has_termination THEN CAST(ec.termination_date AS TIMESTAMP)
            ELSE NULL
        END AS termination_date,
        CASE
            WHEN ec.has_termination THEN 'terminated'
            ELSE 'active'
        END AS employment_status,
        ec.termination_reason
    FROM {{ ref('fct_yearly_events') }} ye
    -- **KEY FIX**: Join with consolidated events to get termination status
    LEFT JOIN employee_events_consolidated ec ON ye.employee_id = ec.employee_id
    WHERE ye.event_type = 'hire'
      AND ye.simulation_year = {{ simulation_year }}
),
```

### Potential Issues to Investigate:

1. **JOIN Issue**: The `LEFT JOIN employee_events_consolidated ec` may not be matching correctly
2. **Flag Issue**: The `ec.has_termination` flag may not be set properly for new hire terminations
3. **Union Issue**: The union logic may be overriding terminated new hires with active records
4. **Timing Issue**: Events may not be processed in the correct order

## Diagnostic Queries

### 1. **Check Employee Events Consolidated Logic**:
```sql
-- Debug the consolidated events for new hire terminations
WITH consolidated_debug AS (
    SELECT
        employee_id,
        COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN 1 END) > 0 AS has_termination,
        COUNT(CASE WHEN UPPER(event_type) = 'TERMINATION' AND event_category = 'new_hire_termination' THEN 1 END) > 0 AS is_new_hire_termination,
        COUNT(CASE WHEN event_type = 'hire' THEN 1 END) > 0 AS is_new_hire,
        MAX(CASE WHEN UPPER(event_type) = 'TERMINATION' THEN effective_date END) AS termination_date
    FROM fct_yearly_events
    WHERE simulation_year = 2025
      AND employee_id IS NOT NULL
    GROUP BY employee_id
)
SELECT
    COUNT(*) as total_employees,
    COUNT(CASE WHEN is_new_hire AND has_termination THEN 1 END) as new_hires_with_termination,
    COUNT(CASE WHEN is_new_hire AND is_new_hire_termination THEN 1 END) as new_hire_terminations
FROM consolidated_debug;
```

### 2. **Check Workforce Snapshot Status**:
```sql
-- Check what's actually in the workforce snapshot
SELECT
    detailed_status_code,
    employment_status,
    COUNT(*) as count
FROM fct_workforce_snapshot
WHERE simulation_year = 2025
  AND EXTRACT(YEAR FROM employee_hire_date) = 2025  -- Hired this year
GROUP BY detailed_status_code, employment_status
ORDER BY count DESC;
```

### 3. **Find Missing Employees**:
```sql
-- Find employees who should be terminated but show as active
WITH should_be_terminated AS (
    SELECT DISTINCT t.employee_id
    FROM fct_yearly_events h
    INNER JOIN fct_yearly_events t
        ON h.employee_id = t.employee_id
        AND h.simulation_year = t.simulation_year
    WHERE h.event_type = 'hire'
      AND t.event_type = 'termination'
      AND t.event_category = 'new_hire_termination'
      AND h.simulation_year = 2025
),
actually_in_snapshot AS (
    SELECT
        employee_id,
        employment_status,
        detailed_status_code
    FROM fct_workforce_snapshot
    WHERE simulation_year = 2025
)
SELECT
    sbt.employee_id,
    ais.employment_status,
    ais.detailed_status_code,
    CASE
        WHEN ais.employment_status = 'terminated' THEN 'CORRECT'
        WHEN ais.employment_status = 'active' THEN 'BUG - SHOULD BE TERMINATED'
        WHEN ais.employee_id IS NULL THEN 'MISSING FROM SNAPSHOT'
        ELSE 'OTHER'
    END as issue_type
FROM should_be_terminated sbt
LEFT JOIN actually_in_snapshot ais ON sbt.employee_id = ais.employee_id
ORDER BY issue_type, sbt.employee_id;
```

## Attempted Fixes (What We've Tried)

### 1. **Unified Event Processing** ✅ Implemented
- Created `employee_events_consolidated` CTE to process all events in single pass
- Added `is_new_hire_termination` flag to identify new hire terminations
- **Status**: Implemented but not working

### 2. **Database Clearing** ✅ Implemented
- Added `clear_simulation_database()` function to `run_multi_year.py`
- Clears stale data before running simulation
- **Status**: Working correctly

### 3. **Enhanced dbt Tests** ✅ Implemented
- Added comprehensive tests in `schema.yml` for new hire termination validation
- Created data quality audit models
- **Status**: Tests will catch the issue but don't fix it

## Next Steps for Fix

### Immediate Actions:
1. **Run Diagnostic Queries** above to identify exactly where the logic breaks
2. **Debug the JOIN** between `new_hires` CTE and `employee_events_consolidated`
3. **Check Union Logic** in `unioned_workforce_raw` for conflicts
4. **Verify Event Generation** - ensure new hire termination events are being created correctly

### Likely Solutions:
1. **Fix JOIN Logic**: The `LEFT JOIN employee_events_consolidated ec ON ye.employee_id = ec.employee_id` may need additional conditions
2. **Fix Union Priority**: The deduplication logic may be prioritizing wrong records
3. **Add Explicit Check**: Add a direct check for `event_category = 'new_hire_termination'` in the termination status logic

### Test Validation:
After any fix, run this validation:
```sql
-- This should return ZERO rows if fix works
SELECT COUNT(*) as incorrect_records
FROM fct_workforce_snapshot ws
WHERE simulation_year = 2025
  AND EXTRACT(YEAR FROM employee_hire_date) = 2025
  AND employment_status = 'active'
  AND EXISTS (
      SELECT 1 FROM fct_yearly_events ye
      WHERE ye.employee_id = ws.employee_id
        AND ye.event_type = 'termination'
        AND ye.event_category = 'new_hire_termination'
        AND ye.simulation_year = 2025
  );
```

## Files Involved

- **Primary**: `/dbt/models/marts/fct_workforce_snapshot.sql` (lines 164-191, 554-563)
- **Events Source**: `/dbt/models/marts/fct_yearly_events.sql`
- **Event Generation**: `/dbt/models/intermediate/events/int_new_hire_termination_events.sql`
- **Validation**: `/dbt/models/analysis/data_quality_new_hire_termination_audit.sql`
- **Tests**: `/dbt/models/marts/schema.yml`

## Expected Behavior After Fix

When running `python run_multi_year.py`, should see:
```
📋 Year-end Employment Makeup by Status:
   continuous_active        : 3,844 (XX.X%)
   new_hire_active          :   875 (XX.X%)  ← Fixed count
   experienced_termination  :   524 (XX.X%)
   new_hire_termination     :   875 (XX.X%)  ← Now visible!
   TOTAL                    : 6,118 (100.0%)
```

## Contact & Handoff Notes

- **Database Path**: `/Users/nicholasamaral/planalign_engine/dbt/simulation.duckdb`
- **Run Command**: `python run_multi_year.py` (includes database clearing)
- **Key CTE**: `employee_events_consolidated` and `new_hires` in `fct_workforce_snapshot.sql`

The core issue is that we have the events correctly generated, but the workforce snapshot logic is not properly applying the termination status to new hires. The consolidated event processing approach is sound, but there's a bug in the implementation that needs to be identified through the diagnostic queries above.

---
**Priority**: 🔴 HIGH - This affects the accuracy of all workforce reporting and needs immediate resolution.
