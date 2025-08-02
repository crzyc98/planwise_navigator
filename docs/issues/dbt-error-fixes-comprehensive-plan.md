# dbt Error Fixes - Comprehensive Implementation Plan

**Status**: In Progress
**Created**: 2025-08-02
**Priority**: High

## Overview

During a full `dbt run`, 10 models failed with various errors. This document tracks the systematic fix implementation for all errors.

## Error Categories and Fixes

### ✅ Phase 1: Configuration & Contract Errors (COMPLETED)

#### 1. Missing Variable References
- **Files**: `int_active_employees_by_year.sql`, `int_workforce_snapshot_optimized.sql`
- **Issue**: Models used `var('start_year')` but config has `simulation_start_year`
- **Fix**: Changed `var('start_year')` → `var('simulation_start_year')`
- **Status**: ✅ FIXED

#### 2. Missing Schema Contracts
- **File**: `int_workforce_snapshot_optimized.sql`
- **Issue**: Contract enforced but no column specifications in schema.yml
- **Fix**: Added complete column specifications with data types in `intermediate/schema.yml`
- **Status**: ✅ FIXED

### ✅ Phase 2: SQL Syntax Errors (PARTIALLY COMPLETED)

#### 3. CREATE TABLE Statements
- **File**: `mon_scd_performance.sql`
- **Issue**: Contains `CREATE TABLE` statements (not allowed in dbt models)
- **Fix**: Replaced with SELECT-based metadata model
- **Status**: ✅ FIXED

#### 4. Missing Comma in CTE
- **File**: `fct_compensation_growth.sql`
- **Issue**: Missing comma after `target_assessment` CTE before `compounding_validation`
- **Fix**: Added comma after `target_assessment CTE`
- **Status**: ✅ FIXED but model still has parsing issues - needs further investigation

#### 5. ORDER BY with UNION Issue
- **File**: `debug_enrollment_eligibility.sql`
- **Issue**: ORDER BY applied directly to UNION ALL (not allowed)
- **Fix**: Wrapped UNION ALL in subquery, moved ORDER BY to outer query
- **Status**: ✅ FIXED

#### 6. Syntax Error Near SELECT
- **File**: `int_workforce_changes.sql`
- **Issue**: "syntax error at or near SELECT" but file appears correct
- **Status**: ❌ PENDING - May be dependency issue

### ⏳ Phase 3: Column Reference Errors (IN PROGRESS)

#### 7. Missing payload_json Column
- **File**: `fct_participant_balance_snapshots.sql`
- **Issue**: References `payload_json` column that doesn't exist in `fct_yearly_events`
- **Root Cause**: Model designed for JSON event schema, but actual schema uses normalized columns
- **Fix Required**: Comprehensive rewrite to use discrete columns
- **Status**: ⏳ IN PROGRESS

#### 8. Column Name Mismatch
- **File**: `test_compensation_compounding_validation.sql`
- **Issue**: Uses `previous_salary` but actual column is `previous_compensation`
- **Fix Required**: Replace all instances of `previous_salary` with `previous_compensation`
- **Status**: ❌ PENDING

#### 9. Missing Table Reference
- **File**: `int_workforce_previous_year_v2.sql`
- **Issue**: Direct table reference `fct_workforce_snapshot` instead of dbt ref
- **Fix Required**: Change to `{{ ref('fct_workforce_snapshot') }}`
- **Status**: ❌ PENDING

## Progress Summary

| Phase | Status | Completed | Total | Success Rate |
|-------|--------|-----------|--------|--------------|
| Phase 1: Config/Contract | ✅ Complete | 2/2 | 2 | 100% |
| Phase 2: SQL Syntax | ⏳ Partial | 3/4 | 4 | 75% |
| Phase 3: Column References | ⏳ In Progress | 0/3 | 3 | 0% |
| **Overall** | ⏳ **In Progress** | **5/9** | **9** | **56%** |

## Successful Fixes Validated

✅ **Working Models** (tested successfully):
- `mon_scd_performance.sql` - CREATE TABLE statements removed
- `debug_enrollment_eligibility.sql` - UNION/ORDER BY fixed
- `int_active_employees_by_year.sql` - Variable reference fixed
- `int_workforce_snapshot_optimized.sql` - Schema contract added

## Remaining Work

### High Priority
1. **`fct_compensation_growth.sql`** - Still has parsing issues despite comma fix
2. **`int_workforce_changes.sql`** - Investigate dependency or hidden syntax issue

### Medium Priority
3. **`fct_participant_balance_snapshots.sql`** - Complete rewrite needed for column schema
4. **`test_compensation_compounding_validation.sql`** - Simple column name replacement
5. **`int_workforce_previous_year_v2.sql`** - Add dbt ref() macro

## Implementation Notes

- **Configuration errors** (Phase 1) were highest priority as they block compilation
- **Syntax errors** (Phase 2) prevent model execution
- **Column reference errors** (Phase 3) are runtime issues but easier to fix
- Two models (`fct_compensation_growth`, `int_workforce_changes`) need deeper investigation
- `fct_participant_balance_snapshots` requires most extensive rework

## Context

These fixes are independent of the **workforce needs architecture** implementation which is working perfectly. The failing models are pre-existing issues in other parts of the codebase.

## Next Steps

1. Continue with column reference fixes
2. Investigate remaining syntax issues in `fct_compensation_growth` and `int_workforce_changes`
3. Run comprehensive validation after all fixes
4. Document any models that may need to be disabled if unfixable

---

**Updated**: 2025-08-02 15:18 EST
**Next Review**: After Phase 3 completion
