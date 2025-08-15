# Workforce Snapshot Incremental Model Regression

**Date**: 2025-08-14
**Severity**: HIGH
**Epic**: E039 (Employer Contribution Integration)
**Story**: S039-01 (Basic Employer Contributions)
**Status**: 🔴 BLOCKING - Epic completion delayed

## Issue Summary

During implementation of Epic E039 Story S039-01 (Basic Employer Contributions), changes to `fct_workforce_snapshot.sql` have caused a regression where the incremental model only retains data for the final year (2029) instead of maintaining historical data for all simulation years (2025-2029).

## Previous Behavior (Working)
- Navigator orchestrator produced complete multi-year data in `fct_workforce_snapshot`
- All years 2025-2029 were preserved in the incremental table
- Multi-year simulations worked correctly

## Current Behavior (Broken)
- Only 2029 data exists in `fct_workforce_snapshot` after navigator orchestrator runs
- Historical years (2025-2028) are missing/overwritten
- Simple orchestrator (`run_multi_year.py`) may still work correctly

## Root Cause Analysis

### Changes Made in S039-01
1. **Added LEFT JOINs to workforce snapshot**:
   ```sql
   -- Epic E039: Join employer match calculations
   LEFT JOIN {{ ref('int_employee_match_calculations') }} match_calc
   -- Epic E039: Join employer core contributions
   LEFT JOIN {{ ref('int_employer_core_contributions') }} core_contrib
   ```

2. **Added new columns**:
   - `employer_match_amount`
   - `employer_core_amount`
   - `total_employer_contributions`

3. **Updated orchestrators** to include new foundation models:
   - `int_employer_eligibility`
   - `int_employer_core_contributions`

### Suspected Issues
1. **Schema Change Impact**: Adding new columns to incremental model may require full refresh
2. **JOIN Dependencies**: New LEFT JOINs may affect incremental strategy
3. **Unique Key Conflicts**: Changes may interfere with `unique_key=['employee_id', 'simulation_year']`
4. **Navigator Orchestrator Logic**: Multi-year execution may be overwriting previous years

## Impact Assessment

### Business Impact
- **HIGH**: Epic E039 completion blocked on first story
- **HIGH**: Navigator orchestrator multi-year functionality broken
- **MEDIUM**: Data integrity compromised for historical workforce analysis

### Technical Impact
- Multi-year simulations produce incomplete results
- Historical workforce data lost
- Potential need to rebuild all historical data

## Immediate Actions Required

1. **Identify Root Cause** (Priority 1)
   - Determine if issue is with incremental model configuration
   - Check if navigator orchestrator execution logic changed
   - Verify if schema changes require full refresh

2. **Restore Multi-Year Data** (Priority 1)
   - Run multi-year simulation to rebuild all years 2025-2029
   - Verify complete data restoration
   - Test navigator orchestrator end-to-end

3. **Fix Implementation** (Priority 2)
   - Adjust incremental model strategy if needed
   - Update orchestrator logic if required
   - Ensure schema changes don't break incremental behavior

## Potential Solutions

### Option 1: Force Full Refresh
```bash
dbt run --select fct_workforce_snapshot --full-refresh --vars "simulation_year: 2025"
# Then run for all years 2025-2029
```

### Option 2: Fix Incremental Strategy
- Review incremental model configuration
- Consider using `delete+insert` strategy explicitly
- Add proper incremental filters for new JOINs

### Option 3: Navigator Orchestrator Fix
- Review multi-year execution logic
- Ensure proper year-by-year incremental building
- Check for any concurrency or ordering issues

## Testing Required

1. **Regression Test**: Verify original functionality restored
2. **Integration Test**: Confirm employer contributions work with multi-year data
3. **Performance Test**: Ensure incremental model still performs efficiently
4. **End-to-End Test**: Full navigator orchestrator multi-year simulation

## Timeline

- **Tonight (2025-08-14)**: Epic E039 completion was planned
- **Now**: Blocked until this regression is resolved
- **Target Fix**: Within 2 hours to minimize Epic delay
- **Validation**: Additional 1 hour for thorough testing

## Lessons Learned

1. **Schema Changes Risk**: Adding columns to incremental models requires careful testing
2. **Regression Testing**: Multi-year functionality should be tested for all model changes
3. **Incremental Strategy**: Need better understanding of DuckDB incremental behavior
4. **Change Isolation**: Large changes should be implemented incrementally

## Next Steps

1. Immediately investigate and fix the incremental model issue
2. Restore multi-year workforce snapshot data
3. Complete S039-01 testing with proper multi-year validation
4. Document proper incremental model change procedures
5. Add automated tests to prevent similar regressions

---

**Assigned**: Platform Team
**Priority**: P0 (Blocking)
**Epic**: E039
**Story**: S039-01

*This regression was introduced during employer contribution integration and must be resolved before Epic E039 can be completed.*
