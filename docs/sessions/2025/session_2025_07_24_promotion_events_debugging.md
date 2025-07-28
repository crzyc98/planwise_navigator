# Session 2025-07-24: Promotion Events Debugging Session

## Session Summary
**Date**: July 24, 2025
**Duration**: ~3 hours
**Focus**: Debugging persistent promotion events issue where employees get promoted but workforce snapshots don't reflect the promotion until years later

## Problem Statement
- Employee EMP_000011 gets promoted from Level 1→2 in 2025 (shows correctly in `fct_yearly_events`)
- Workforce snapshots show `level_id=1` for years 2025-2028
- Employee suddenly shows `level_id=2` in 2029
- This suggests promotion events are generated but not applied to workforce snapshots

## Attempted Fixes That Failed

### 1. Initial Promotion Logic Fixes
- **Fixed `int_promotion_events.sql`**: Switched from `int_workforce_active_for_events` to `int_employee_compensation_by_year` for current employee state
- **Fixed `fct_yearly_events.sql`**: Changed from `from_level AS level_id` to `to_level AS level_id`
- **Fixed `fct_workforce_snapshot.sql`**: Updated to use `level_id` directly instead of parsing event details
- **Result**: Still not working

### 2. Level Correction Logic Fix
- **Issue**: `workforce_with_corrected_levels` CTE was overriding promotion events with compensation-based level calculation
- **Fix**: Changed logic to preserve `level_id` from promotion events, only use compensation as fallback
- **Result**: Still not working

### 3. Anti-Duplication Logic Cleanup
- **Removed**: Anti-join logic in `int_promotion_events.sql`
- **Removed**: DISTINCT clauses that were masking real issues
- **Created**: `test_deterministic_promotion_events.sql` to verify deterministic behavior
- **Result**: Cleaner code but still not working

### 4. Circular Dependency Fix
- **Issue**: `int_employee_compensation_by_year` was using complex helper model with `adapter.get_relation()`
- **Fix**: Replaced with direct SQL query to previous year's workforce snapshot
- **Result**: Still not working

### 5. Data Type Mismatch Fix (Gemini's Analysis)
- **Theory**: `employee_id` data type mismatch causing silent JOIN failures
- **Fix**: Added `CAST(employee_id AS VARCHAR)` to all JOIN conditions in `fct_workforce_snapshot.sql`
- **Reasoning**: New hires use `NH_2025_12345678_000001` format vs existing `EMP_000011`
- **Result**: User confirmed still not working

### 6. Case Sensitivity Fix (Gemini's Second Analysis)
- **Theory**: Inconsistent case handling between event types
- **Issue**: Terminations use `UPPER(event_type) = 'TERMINATION'` but promotions use `event_type = 'promotion'`
- **Status**: Identified but not implemented due to user skepticism

## Key Insights from Analysis

### Root Cause Theories
1. **Silent JOIN Failure**: Most likely explanation - promotion events exist but aren't being applied due to JOIN issues
2. **Data Type Mismatch**: Different employee_id formats between existing and new hire employees
3. **Case Sensitivity**: Inconsistent event_type filtering across different event types
4. **Timing Issues**: Circular dependency or sequencing problems in multi-year simulations

### Why Level 2 Appears in 2029
- The `COALESCE` logic in `workforce_with_corrected_levels` has compensation-based fallback
- By 2029, employee's compensation grew enough to qualify for Level 2 based on salary ranges
- This explains the sudden appearance without a successful promotion JOIN

## Current Status
- **Problem**: Still unresolved after multiple attempted fixes
- **Next Steps**: Need systematic data debugging instead of theoretical fixes
- **User Feedback**: Frustrated with theoretical approaches, wants actual investigation

## Approved Debugging Plan
Created systematic plan to trace actual data through pipeline:

1. **Query `int_promotion_events`** for EMP_000011 in 2025 - verify promotion exists
2. **Query `fct_yearly_events`** for EMP_000011 promotion in 2025 - verify event structure
3. **Check `base_workforce` CTE** - verify baseline level_id=1
4. **Check `current_year_events` CTE** - verify promotion event is included
5. **Check `workforce_after_promotions` CTE** - CRITICAL STEP - verify promotion is applied
6. **Check `workforce_with_corrected_levels` CTE** - verify level isn't overridden
7. **Identify exact failure point** - pinpoint where level_id is lost

## Files Modified During Session
- `dbt/models/intermediate/events/int_promotion_events.sql`
- `dbt/models/marts/fct_yearly_events.sql`
- `dbt/models/marts/fct_workforce_snapshot.sql`
- `dbt/models/intermediate/int_employee_compensation_by_year.sql`
- `tests/validation/test_promotion_events_duplicate_prevention.sql` (new)
- `tests/validation/test_promotion_events_level_progression.sql` (new)
- `tests/validation/test_deterministic_promotion_events.sql` (new)
- `docs/implementation/promotion_events_data_propagation_fix.md` (new)
- `docs/implementation/anti_duplication_logic_cleanup.md` (new)

## Lessons Learned
- **Stop Guessing**: Theoretical fixes without understanding the real data flow are ineffective
- **Need Data Investigation**: Must trace actual data through each step to find the real issue
- **Complex Systems**: Multiple interconnected models make root cause analysis challenging
- **Test Fixes**: Always validate that changes actually solve the problem before moving on

## Action Items for Next Session
1. Execute the systematic debugging plan
2. Query each step of the pipeline for EMP_000011 data
3. Identify the exact CTE where level_id is lost
4. Fix the specific root cause instead of making more theoretical changes
5. Validate the fix actually works before declaring success

## User Sentiment
- Frustrated with repeated failed attempts
- Wants concrete debugging over theoretical fixes
- Emphasized need to actually test solutions
- Requested systematic data investigation approach
