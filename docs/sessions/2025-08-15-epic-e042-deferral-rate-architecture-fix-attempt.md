# Epic E042: Deferral Rate Architecture Fix Session - 2025-08-15

## Session Overview
**Date**: 2025-08-15
**Duration**: Extended session
**Objective**: Fix $0 contributions issue in workforce simulation
**Status**: ❌ INCOMPLETE - 2025 contributions still showing $0 after all fixes

## Problem Statement

After running a complete multi-year simulation (2025-2029), employee 401(k) contributions show as $0 for year 2025, despite:
- V2 deferral rate accumulator working correctly (875 employees at 6% deferral rate)
- Test employee NH_2025_000007 showing proper enrollment and deferral rates
- fct_workforce_snapshot having 5,243 employees with compensation data

## Root Cause Analysis

### Initial Hypothesis (WRONG)
Initially suspected foundation models (`int_baseline_workforce`, `int_employee_compensation_by_year`) were missing data for 2025.

### Agent Investigation Results
Used general-purpose agent to trace the contribution calculation pipeline:

**Key Finding**: `int_employee_contributions` uses `materialized='table'` which overwrites all data each simulation year. After a 2025-2029 run, only 2029 data remains, but `fct_workforce_snapshot` (incremental) tries to JOIN with missing historical contribution data.

### Data State After Full Simulation
```
int_baseline_workforce: Only 2026 data (4,368 rows)
int_employee_compensation_by_year: Only 2026 data (4,501 rows)
int_workforce_snapshot_optimized: Only 2026 data (4,501 rows)
int_employee_contributions: Only 2026 data (4,501 rows)
fct_workforce_snapshot: ALL years 2025-2029 (5,243-5,910 rows per year)
```

## Solution Implemented

### Fix Applied
Converted `int_employee_contributions` from table to incremental materialization:

**File**: `/dbt/models/intermediate/events/int_employee_contributions.sql`

**Changes Made**:
1. Configuration update:
```sql
{{ config(
    materialized='incremental',
    unique_key=['employee_id', 'simulation_year'],
    incremental_strategy='delete+insert',
    on_schema_change='sync_all_columns'
) }}
```

2. Added incremental filter:
```sql
{% if is_incremental() %}
    -- Incremental processing - only include current simulation year
    WHERE simulation_year = {{ simulation_year }}
{% endif %}
```

### Testing Results
- ✅ Model builds successfully with new configuration
- ✅ dbt recognizes it as incremental model
- ❌ Still no contribution data generated (empty table)
- ❌ 2025 contributions still show $0 in fct_workforce_snapshot

## Current Status

### What's Working
- V2 deferral rate accumulator: 875 employees with 6% deferral in 2025
- NH_2025_000007 shows 9% in 2026 (escalation working but rate is wrong - should be 7%)
- fct_workforce_snapshot has complete multi-year data
- Incremental model conversion successful

### What's Still Broken
- `int_employee_contributions` has 0 rows for 2025
- Dependencies like `int_workforce_snapshot_optimized` missing 2025 data
- Pipeline dependency chain broken for historical years

## Outstanding Issues

### Issue 1: Dependency Chain Problems
`int_employee_contributions` depends on `int_workforce_snapshot_optimized` which only has 2026+ data, not 2025.

### Issue 2: Foundation Model Overwriting
`int_baseline_workforce` and related models get overwritten each year instead of preserving historical data.

### Issue 3: Pipeline Execution Order
Models may be building in wrong sequence or with incomplete dependencies for year 2025.

## Next Steps Required

### Immediate Actions
1. **Fix Foundation Models**: Ensure `int_baseline_workforce` and `int_employee_compensation_by_year` preserve 2025 data
2. **Rebuild Complete Pipeline**: Run full 2025 simulation with proper dependency chain
3. **Test Incremental Fix**: Verify `int_employee_contributions` now preserves historical data across years

### Alternative Approaches
1. **Fallback Strategy**: Modify `int_employee_contributions` to use `fct_workforce_snapshot` as data source when dependencies missing
2. **Pipeline Restructure**: Ensure foundation models are incremental or don't get rebuilt in subsequent years
3. **Dependency Analysis**: Full audit of which models should preserve historical data vs. single-year data

## Technical Debt Created
- Model materialization strategy needs comprehensive review
- Pipeline dependency management requires systematic fix
- Multi-year simulation architecture has fundamental design issues

## Handover Information
- Test employee: NH_2025_000007 (hired 2025-01-08, should have 6% → 7% → 8% deferral progression)
- Database: dbt/simulation.duckdb
- Key models modified: `int_employee_contributions.sql`
- Expected 2025 contribution amount: ~$14,676 for test employee (6% of $244,602 prorated compensation)

## Context Window Status
🔴 **HITTING CONTEXT LIMIT** - Session requires fresh context for continuation.
