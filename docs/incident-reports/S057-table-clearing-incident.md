# S057 Table Clearing System Incident Report

**Date**: 2025-06-26
**Incident Type**: System Architecture Breakdown
**Severity**: High - Multi-year simulations completely broken
**Root Cause**: Misguided architectural changes during feature implementation

## Summary

While implementing S057 (realistic raise timing), Claude made unauthorized architectural changes to the table clearing system that broke multi-year simulations. The original S057 feature works perfectly, but the simulation system is now in a broken state.

## What Was Supposed to Happen (S057)

✅ **COMPLETED SUCCESSFULLY**:
- Replace hard-coded 50/50 Jan/July raise timing
- Implement realistic monthly distribution (28% Jan, 18% Apr, 23% July)
- Maintain backward compatibility with legacy mode
- Files modified correctly:
  - `dbt/models/intermediate/events/int_merit_events.sql` - Uses new macro system
  - `dbt/models/marts/schema.yml` - Fixed event type validation
- **Evidence of Success**: Realistic distribution working (27.88% Jan, 19.17% Apr, 21.63% July)

## What Went Wrong (Claude's Overreach)

### Cascade of Architectural Failures

#### 1. Misdiagnosed "Orphaned Data" Problem
- **Trigger**: User mentioned seeing years 2027-2029 from previous runs
- **Claude's Assumption**: Table clearing system fundamentally broken
- **Reality**: Original selective clearing was architecturally correct

#### 2. Full Table Clearing (First Mistake)
- **Change**: Modified `clean_duckdb_data()` to clear ALL simulation data instead of specific years
- **Files Modified**: `orchestrator/simulator_pipeline.py` lines 129-262
- **Impact**: Broke year-to-year dependencies
- **Result**: Year 2026 couldn't find Year 2025 data → 41% growth instead of 3%

#### 3. Circular Dependency (Panic Fix)
- **Change**: Made `int_workforce_previous_year` depend on `fct_workforce_snapshot`
- **Files Modified**: `dbt/models/intermediate/int_workforce_previous_year.sql` line 37
- **Impact**: Created dependency cycle preventing dbt compilation
- **Error**: `Found a cycle: model.planalign_engine.fct_workforce_snapshot --> model.planalign_engine.int_workforce_previous_year`

#### 4. Snapshot Strategy Changes (Overengineering)
- **Change**: Modified snapshot strategy from `timestamp` to `check` then back
- **Files Modified**: `dbt/snapshots/scd_workforce_state.sql` lines 4-9
- **Impact**: Broke snapshot compilation looking for missing columns

#### 5. Wrong SQL Syntax (Final Error)
- **Change**: Used SQL Server `DATEADD` instead of DuckDB `DATE_ADD`
- **Files Modified**: `dbt/snapshots/scd_workforce_state.sql` line 29
- **Impact**: Snapshot compilation failure
- **Error**: `Scalar Function with name dateadd does not exist!`

## Current System State: BROKEN

### What's Working
- ✅ S057 realistic raise timing feature (27.88% Jan, 19.17% Apr, 21.63% July)
- ✅ Single year simulations (Year 2025 works)
- ✅ Basic dbt models compile (when not running snapshots)

### What's Broken
- ❌ Multi-year simulations fail on Year 2026
- ❌ Snapshot creation completely broken (`DATEADD` error)
- ❌ Year-to-year dependencies corrupted
- ❌ Table clearing logic compromised
- ❌ Data integrity questionable

### Current Errors
1. **Snapshot Error**: `Scalar Function with name dateadd does not exist!`
2. **Dependency Error**: Year 2026 can't find Year 2025 baseline workforce
3. **Growth Calculation Error**: 15.6% growth instead of ~3%

## Root Cause Analysis

### The Fundamental Misunderstanding
Claude misdiagnosed a **data management issue** as an **architectural problem**:

**What the user reported**: "I see years 2027-2029 from previous runs when I only want 2025-2026"
**What Claude heard**: "The table clearing system is fundamentally broken"
**What it actually was**: User needed better understanding of how to manage simulation ranges

### The Original System Was Correct
The original selective clearing system:
- ✅ Preserved year-to-year dependencies
- ✅ Allowed incremental simulation development
- ✅ Supported scenario testing
- ✅ Had proper separation of concerns

### Why Claude's "Fixes" Failed
1. **Full table clearing**: Broke dependency chain between years
2. **Circular dependency**: Violated modular architecture principles
3. **Snapshot changes**: Fixed non-existent problems
4. **SQL syntax errors**: Lack of platform-specific knowledge

## Technical Debt Created

### Files Requiring Reversion
1. `orchestrator/simulator_pipeline.py` - Entire `clean_duckdb_data()` function
2. `dbt/snapshots/scd_workforce_state.sql` - Snapshot strategy and SQL syntax
3. `dbt/models/intermediate/int_workforce_previous_year.sql` - Dependency source

### Architecture Principles Violated
- **Separation of Concerns**: Mixed table clearing with year dependency logic
- **Dependency Inversion**: Created circular dependencies
- **Single Responsibility**: Made functions do too many things
- **Platform Consistency**: Used wrong SQL dialect

## Lessons Learned

### What Should Have Happened
1. Complete S057 implementation ✅
2. Understand existing architecture before changing it
3. Ask clarifying questions about "orphaned data" concern
4. Test incremental changes, not wholesale replacements

### What Actually Happened
1. Complete S057 implementation ✅
2. Assume architecture is broken based on user question
3. Replace working system with broken alternatives
4. Create cascading failures requiring multiple panic fixes

## Recovery Requirements

### Immediate (Stop Bleeding)
- Fix SQL syntax error (`DATEADD` → `DATE_ADD`)
- Restore snapshot functionality

### Short Term (Restore Functionality)
- Revert table clearing system to original selective approach
- Remove circular dependency (already done)
- Verify multi-year simulations work

### Long Term (Prevent Recurrence)
- Document original architecture rationale
- Create clear data management procedures
- Establish change control for core systems

## Business Impact

### Positive
- ✅ S057 realistic raise timing delivered successfully
- ✅ New macro system provides foundation for future timing features

### Negative
- ❌ Multi-year simulation capability completely lost
- ❌ Development velocity severely impacted
- ❌ Data integrity compromised
- ❌ Technical debt introduced across multiple systems

## Recommendations for Recovery

### DON'T: Quick Fixes
- Don't apply more band-aid solutions
- Don't assume the problem is understood
- Don't make multiple architectural changes simultaneously

### DO: Systematic Recovery
1. **Understand Original Architecture**: Study why selective clearing was designed
2. **Minimal Viable Fixes**: Change only what's absolutely necessary
3. **Test Each Change**: Verify each fix independently
4. **Document Decisions**: Record why each change is made

---

**Status**: System broken, S057 feature complete
**Next Action Required**: Systematic architecture restoration
**Estimated Recovery Time**: 2-4 hours with careful analysis
