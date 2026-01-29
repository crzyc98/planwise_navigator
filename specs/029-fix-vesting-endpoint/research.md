# Research: Fix Vesting Analytics Endpoint

**Branch**: `029-fix-vesting-endpoint` | **Date**: 2026-01-28

## Summary

This is a straightforward bug fix with no unknowns requiring research. The root cause is clearly identified from the error traceback.

## Findings

### 1. Root Cause Verification

**Decision**: The bug is a type mismatch - treating a Pydantic model as a dictionary.

**Evidence**:
- Error traceback shows `AttributeError: 'Scenario' object has no attribute 'get'`
- `planalign_api/models/scenario.py` defines `Scenario` as a Pydantic `BaseModel` with a `name: str` attribute
- `workspace_storage.get_scenario()` returns a `Scenario` model instance
- Line 70 incorrectly uses `scenario.get("name", scenario_id)` instead of attribute access

**Rationale**: Pydantic models don't inherit from dict; attributes must be accessed via dot notation.

### 2. Similar Patterns in Codebase

**Decision**: No other endpoints have this bug.

**Evidence**:
- Searched for `.get("name"` in `planalign_api/` directory
- Found 2 other occurrences in `workspace_storage.py` (lines 742, 762)
- Both are operating on `salvaged` dictionary (raw JSON data), not Pydantic models
- Pattern is correct for dictionary access in recovery code

**Alternatives Considered**: N/A - isolated bug

### 3. Fix Approach

**Decision**: Change `scenario.get("name", scenario_id)` to `scenario.name or scenario_id`

**Rationale**:
- Maintains same fallback behavior (use `scenario_id` if name is None/empty)
- Uses proper Pydantic attribute access
- Minimal change, no side effects
- Consistent with how other Pydantic models are accessed in the codebase

**Alternatives Considered**:
- `getattr(scenario, "name", scenario_id)`: Works but unnecessarily complex for a model with guaranteed `name` attribute
- `scenario.name if scenario.name else scenario_id`: More verbose, equivalent to `or` for strings

## Conclusion

No additional research needed. The fix is well-defined and isolated.
