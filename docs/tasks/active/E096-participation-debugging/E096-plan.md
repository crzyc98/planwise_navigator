# E096: Participation Debugging Dashboard & Critical Bug Fix

**Branch:** `feature/E096-participation-debugging-dashboard`
**Created:** 2025-12-09
**Status:** In Progress

## Problem Statement
**No one is participating in any scenarios** - both census employees who were already participating AND new hires who should be auto-enrolled at 2% are showing 0% participation.

## Root Cause Analysis

### BUG #1: Event Type Mismatch (CRITICAL)
**Location:** `dbt/models/intermediate/int_deferral_rate_state_accumulator_v2.sql` (lines 39-63, 115-142)

The v2 accumulator looks for:
```sql
WHERE LOWER(event_type) = 'benefit_enrollment'
```

BUT `int_enrollment_events.sql` generates events with:
```sql
'enrollment' as event_type  -- Line 254
```

**Result:** Zero enrollment events are matched, so no one gets a deferral rate in the accumulator.

### BUG #2: Census Participation Carryover
**Location:** `dbt/models/staging/stg_census_data.sql` (lines 108-112)

If census file has `employee_deferral_rate = NULL` or `= 0` for everyone, then:
- `employee_enrollment_date` = NULL for all
- `is_enrolled_flag` = false for all
- No census participation carries forward

## Fix Implementation

### Fix 1: Event Type Mismatch
**File:** `dbt/models/intermediate/int_deferral_rate_state_accumulator_v2.sql`

Change:
```sql
-- FROM:
WHERE LOWER(event_type) = 'benefit_enrollment'
-- TO:
WHERE LOWER(event_type) IN ('enrollment', 'benefit_enrollment')
```

### Fix 2: Create Participation Debug Dashboard
**File:** `dbt/models/analysis/debug_participation_pipeline.sql`

Traces participation through entire pipeline to identify where participants are being filtered out.

## Expected Outcome
- Census employees with existing deferral rates -> participating
- New hires -> auto-enrolled at 2% default rate -> participating
- All scenarios should show expected participation rates
