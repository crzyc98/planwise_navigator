# Phase 0 Research: Census Path Validation

**Date**: 2026-03-18
**Feature**: Enforce Census Path Validation on Simulation Start
**Branch**: `080-census-path-validation`

## Executive Summary

Current implementation in `planalign_api/services/simulation/service.py:_validate_census()` logs a warning and continues when `census_parquet_path` is missing—silent fallback to an undocumented default path causes simulations to run against the wrong census data without visible errors.

**Decision**: Replace the silent fallback with hard-fail validation using existing `ConfigurationError` infrastructure. Validation occurs in `_validate_census()` before simulation subprocess launch.

---

## Research Findings

### R1. Current Census Path Validation Implementation

**Location**: `planalign_api/services/simulation/service.py:404-412`

**Current Code**:
```python
@staticmethod
def _validate_census(config: Dict[str, Any]) -> None:
    census_path = config.get("setup", {}).get("census_parquet_path")
    if census_path:
        if not Path(census_path).exists():
            raise ValueError(f"Census file not found: {census_path}")
        logger.info(f"Using census file: {census_path}")
    else:
        logger.warning("No census_parquet_path in config - using default")
```

**Issues**:
1. **Silent fallback** when `census_parquet_path` is missing (line 412)
2. **Generic error** uses `ValueError` instead of `ConfigurationError` (line 409)
3. **No error context** — error lacks scenario_id, timestamp, or resolution guidance
4. **Logs only** — warning is buried in log output, not surfaced to UI
5. **No audit trail** — no record of which simulations used fallback paths

**Decision**: Replace with ConfigurationError that includes execution context and actionable error messages.

---

### R2. ConfigurationError Infrastructure

**Location**: `planalign_orchestrator/exceptions.py:248-251`

**Base Classes**:
```python
class ConfigurationError(NavigatorError):
    """Configuration-related errors"""
    def __init__(self, message: str, **kwargs):
        super().__init__(message, category=ErrorCategory.CONFIGURATION, **kwargs)
```

**NavigatorError** (parent class) provides:
- `message`: User-facing error description
- `context`: ExecutionContext with correlation_id, scenario_id, timestamp, etc.
- `category`: ErrorCategory.CONFIGURATION
- `severity`: ErrorSeverity.ERROR (configurable)
- `resolution_hints`: List[ResolutionHint] for actionable guidance

**Decision**: Extend ConfigurationError with resolution hints for census-specific errors.

---

### R3. Error Catalog System

**Location**: `planalign_orchestrator/error_catalog.py`

**Structure**:
- `ErrorPattern`: Regex pattern + category + resolution hints
- `ErrorCatalog`: Registry of known error patterns
- Usage: `catalog.find_resolution_hints(error_message)` returns resolution steps

**Current Catalog**: 20+ patterns for database locks, data quality, resource constraints

**Status**: No census-related patterns exist yet.

**Decision**: Add two error patterns to catalog:
1. **Missing census_parquet_path**: "census_parquet_path is required but was not found"
2. **Missing file on disk**: "Census file not found at" + path

---

### R4. Error Handling in SimulationService

**Location**: `planalign_api/services/simulation/service.py:70-123`

**Flow**:
1. `execute_simulation()` calls `_prepare_simulation()` (line 103)
2. `_prepare_simulation()` calls `_validate_census()` (line 147)
3. On exception, `_handle_simulation_failure()` catches and logs (line 120-123)
4. Exception string is set as `error_message` in status update (line 299)

**UI Integration**: `_handle_simulation_failure()` calls `update_run_status()` which is passed to Studio for display.

**Current behavior**: ValueError message would be displayed to user, but message lacks guidance.

**Decision**: ConfigurationError will be caught by existing error handler and message will be displayed in UI through `error_message` field.

---

### R5. Studio API Integration

**Location**: `planalign_api/services/simulation/service.py:70-96`

**Error Propagation**:
- `execute_simulation()` (async) is called by API endpoint
- On exception (lines 119-123), error is logged and status is updated
- Exception message is converted to string and stored in `error_message` field
- Frontend receives error via `update_run_status` callback

**Current Issues**:
- Exception type not preserved (only message string)
- No way to distinguish validation errors from runtime errors
- UI displays generic error format without context

**UI Assumption**: Frontend expects `error_message` field in run status. No additional infrastructure needed for display.

**Decision**: Validation errors will be caught and displayed via existing error_message field. No changes to Studio API contract needed.

---

### R6. Config Structure and Merging

**Location**: `planalign_api/services/simulation/service.py:135-149`

**Config Access**:
```python
sim_config = config.get("simulation", {})
census_path = config.get("setup", {}).get("census_parquet_path")
```

**Merge Point**: Config is passed as parameter to `execute_simulation()` from API handler (caller is responsible for merging).

**Assumption**: Per spec, Studio constructs merged config before calling orchestrator. No null config scenarios should occur.

**Access Pattern**: Uses `dict.get()` with defaults — all config access is safe (no KeyError).

**Decision**: Keep existing `dict.get()` access pattern. Validation occurs after merge, so config is guaranteed complete.

---

### R7. Testing Infrastructure

**Location**: `tests/fixtures/`

**Available Fixtures**:
- `populated_db`: Pre-populated DuckDB with sample data
- `minimal_config`: Minimal SimulationConfig for testing
- `sample_employees`: Sample workforce data
- Fixture library in `tests/fixtures/` (database.py, config.py, workforce_data.py)

**Testing Strategy** (per Constitution III: Test-First Development):
- Unit tests: Mock SimulationService, call `_validate_census()` with various config states
- Integration tests: Full simulation run with valid/invalid census paths
- Fast tests (<10s): Unit tests only
- Coverage: 90%+ for validation module

**Decision**: Use existing fixture library. Write tests before implementation (TDD workflow).

---

## Design Decisions

### D1. Validation Location

**Options Evaluated**:
- **Option A**: In `_validate_census()` [SELECTED]
  - Pros: Single responsibility, centralized validation
  - Cons: Late validation (after other config is written)
- **Option B**: In API router/endpoint
  - Pros: Earlier validation, avoids subprocess spawn
  - Cons: Duplicates validation logic, harder to maintain

**Selected**: Option A — keep validation in `_validate_census()` to maintain single responsibility and reuse existing error handling.

---

### D2. Error Type

**Options Evaluated**:
- **Option A**: ConfigurationError with ExecutionContext [SELECTED]
  - Pros: Consistent with codebase, includes scenario context, audit trail
  - Cons: Slightly more verbose
- **Option B**: Minimal ValueError
  - Pros: Simple, backward compatible
  - Cons: No context, no resolution guidance, inconsistent with codebase

**Selected**: Option A — ConfigurationError with ExecutionContext for audit compliance and debugging efficiency.

---

### D3. Error Messages

**Messages**:

**Missing path**:
```
census_parquet_path is required but was not found in the scenario config.
Ensure a census file has been uploaded to the scenario folder before running.
```

**Missing file on disk**:
```
Census file not found at '/path/to/census.parquet'.
Upload a valid census parquet file to the scenario folder and retry.
```

**Rationale**: Per FR-002 and FR-004 in spec. Messages are user-friendly, actionable, and include the file path for debugging.

---

### D4. Severity Level

**Severity**: `ErrorSeverity.ERROR` (from Constitution IV: Enterprise Transparency)

**Rationale**:
- Silent data corruption risk (CRITICAL data integrity issue)
- User must take action to resolve (upload census file)
- Not transient/recoverable without user intervention
- Warrants immediate UI error display, not just log warning

---

### D5. Execution Context

**Context Fields to Populate**:
- `scenario_id`: From method parameter (passed through from API)
- `timestamp`: Auto-generated by ExecutionContext
- `correlation_id`: Auto-generated by ExecutionContext (8-char UUID)
- `metadata`: Additional context (e.g., expected path)

**Rationale**: Per Constitution IV, error messages must include correlation IDs and execution context for audit reconstruction.

---

## Implementation Roadmap

### Phase 1: Validation Logic (4 hours)

1. **Update `_validate_census()` method**:
   - Check if `census_parquet_path` key exists and is non-empty
   - Raise ConfigurationError if missing (with scenario_id context)
   - Validate file exists at resolved path
   - Raise ConfigurationError if file missing (with path in message)

2. **Create ExecutionContext**:
   - Extract scenario_id from call stack or method parameter
   - Generate auto-populated fields (timestamp, correlation_id)
   - Store in error context

3. **Add Resolution Hints**:
   - Create ResolutionHint objects with steps to upload census
   - Include documentation link

### Phase 2: Error Catalog (2 hours)

1. **Add two ErrorPatterns** to error_catalog.py:
   - Pattern 1: "census_parquet_path is required"
   - Pattern 2: "Census file not found at"

2. **Create ResolutionHint** for each pattern:
   - Title: "Upload Census File"
   - Steps: Check file exists, upload via Studio, retry

### Phase 3: Testing (6 hours)

1. **Unit Tests** (<10s fast suite):
   - Test: missing census_parquet_path → ConfigurationError
   - Test: missing file on disk → ConfigurationError
   - Test: valid path → no error
   - Test: empty string path → ConfigurationError
   - Test: error message format and context

2. **Integration Tests**:
   - Test: full simulation run with invalid path → UI error display
   - Test: error recovery workflow (upload file, retry)

3. **Coverage**: Aim for 90%+ of validation module

---

## Unknowns Resolved

✅ **How is config merged from Studio?** — Caller responsibility; merged config passed as parameter.

✅ **What happens when census_parquet_path is missing?** — Currently just logs warning; will be changed to hard-fail.

✅ **How are configuration errors handled in existing codebase?** — Via ConfigurationError exception class with context.

✅ **Can validation errors be displayed in Studio UI?** — Yes, via existing `error_message` field in run status.

✅ **Do we need to change Studio API contract?** — No, existing error_message field is sufficient.

✅ **What test infrastructure is available?** — Complete fixture library in tests/fixtures/ with 256 existing tests.

---

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|-----------|
| Breaking change for existing workflows | Low | High | Check release notes; no automated migration needed (users must upload census anyway) |
| Validation overhead | Low | Low | Filesystem stat is O(1); <1ms impact |
| Error message clarity | Low | Medium | User testing in design phase; keep messages simple and actionable |
| Audit trail completeness | Low | Medium | Log context with correlation_id; integrate with existing error catalog |

---

## Next Steps

1. **Design Phase**: Create data-model.md defining ValidationContext and error contracts
2. **Implementation**: Implement validation with tests (Red-Green-Refactor)
3. **Integration**: Add error catalog entries and test UI error display
4. **Deployment**: Release with clear migration guidance in release notes
