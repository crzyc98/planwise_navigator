# Multi-Year Simulation Fix - 2025-01-24

## Problem Summary
Multi-year simulations were failing with the error: "No workforce snapshot found for year 2026" despite reporting successful completion of year 2026. This caused cascading failures in subsequent years (2027+).

## Root Cause Analysis
The issue was in `/orchestrator_mvp/core/workforce_snapshot.py` at lines 186-211. The code had a **model validation mismatch**:

1. **✅ Correct Model Built**: Line 175 built `int_active_employees_prev_year_snapshot` successfully
2. **❌ Wrong Model Validated**: Lines 191-211 attempted to validate `int_workforce_previous_year_v2` (different model!)
3. **🚫 Premature Exit**: When validation of the wrong model failed, the function returned `{"success": False}` before `fct_workforce_snapshot` could run

### Error Flow
```
Year 2026 Simulation:
1. Build int_active_employees_prev_year_snapshot ✅ (4,510 records)
2. Try to validate int_workforce_previous_year_v2 ❌ (wrong model)
3. Return {"success": False} and exit ❌
4. fct_workforce_snapshot never runs ❌
5. No 2026 workforce snapshot created ❌
6. Year 2027 fails: "No workforce snapshot found for year 2026" ❌
```

## Investigation Process

### 1. Initial Debugging
- Confirmed `int_active_employees_prev_year_snapshot` was building correctly (4,510 records)
- Confirmed events were being generated (5,685 events)
- Found database showed no `fct_workforce_snapshot` data for 2026

### 2. Model Configuration Fixes (Red Herrings)
- Fixed `fct_yearly_events` materialization from `table` to `incremental`
- Fixed column reference issues in helper models
- Fixed orchestration to pass `simulation_year` variables

### 3. Core Issue Discovery
Used Gemini to analyze the orchestration code and discovered the validation mismatch in `workforce_snapshot.py`.

## Solution Implemented

### Files Changed
1. **`/orchestrator_mvp/core/workforce_snapshot.py`**
   - **Removed lines 186-211**: Incorrect validation block for `int_workforce_previous_year_v2`
   - **Kept existing validation**: Lines 233-239 for `int_active_employees_prev_year_snapshot`

### Code Diff
```python
# REMOVED (lines 186-211):
# Verify that int_workforce_previous_year_v2 was created correctly
try:
    conn = get_connection()
    # ... validation logic for wrong model ...
    if not verify_previous_result or verify_previous_result[0] == 0:
        return {
            "success": False,
            "error": f"int_workforce_previous_year_v2 produced no data..."
        }
except Exception as e:
    return {
        "success": False,
        "error": f"Could not verify int_workforce_previous_year_v2: {str(e)}"
    }

# KEPT: Correct validation later in the function (lines 233-239)
helper_verify_query = "SELECT COUNT(*) FROM int_active_employees_prev_year_snapshot WHERE simulation_year = ?"
```

## Verification
- Multi-year simulation now proceeds correctly from 2025 → 2026 → 2027
- `fct_workforce_snapshot` is now properly invoked for each year
- Temporal dependencies work as expected

## Key Learnings

### Model Naming Consistency
- The codebase uses both `int_workforce_previous_year_v2` and `int_active_employees_prev_year_snapshot`
- **Actual Model Used**: `fct_workforce_snapshot.sql` references `int_active_employees_prev_year_snapshot`
- **Incorrect Validation**: Code was validating `int_workforce_previous_year_v2`

### Validation Strategy
- Validation should match the actual models being used
- Failed validation should not prevent downstream processes unless truly blocking
- Consider using `LEFT JOIN` validation patterns instead of hard failures

### Multi-Year Dependencies
- Year N depends on completed `fct_workforce_snapshot` from Year N-1
- Helper models (`int_active_employees_prev_year_snapshot`) use dynamic references to break circular dependencies
- Event accumulation requires incremental materialization

## Future Improvements
1. **Model Naming**: Consolidate to single naming pattern for workforce year-over-year models
2. **Validation Strategy**: Make validations more resilient with warnings vs. hard failures
3. **Integration Tests**: Add end-to-end multi-year simulation tests
4. **Documentation**: Update architectural docs to reflect actual model dependencies

## Files Modified
- `orchestrator_mvp/core/workforce_snapshot.py` - Removed incorrect validation block
- `dbt/models/marts/fct_yearly_events.sql` - Changed to incremental materialization (cleanup)
- `dbt/models/intermediate/int_active_employees_prev_year_snapshot.sql` - Fixed column reference (cleanup)

## Commit Reference
This fix resolves the multi-year simulation blocking issue and enables proper sequential year processing.
