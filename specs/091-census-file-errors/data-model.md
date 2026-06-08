# Data Model: Census File Error Handling

## Summary

No new persistent entities or schema changes. This feature improves error classification and early detection within existing components. The changes affect:
1. The in-process exception hierarchy (`dbt_runner.py`) — new subclass only
2. The `_validate_census()` pre-flight logic (`simulation/service.py`) — new checks, no new data stored
3. The `error_message` string stored in run metadata — content improved, structure unchanged

---

## New Exception: `DbtCensusFileError`

**Location**: `planalign_orchestrator/dbt_runner.py`

| Attribute | Value |
|-----------|-------|
| Inherits from | `DbtError` |
| Category | Census/parquet file failure |
| String representation | `"Census file corrupted or unreadable. Re-upload your census file via the Import tab to fix."` |
| Raised by | `classify_dbt_error()` when parquet/census patterns detected |
| Used in | `DbtRunner.run_command()` (subprocess-side error classification) |

---

## Extended Pre-flight Validation Logic

**Location**: `SimulationService._validate_census()` in `planalign_api/services/simulation/service.py`

### Validation sequence (ordered, fail-fast)

| Step | Check | Error type raised | Error message |
|------|-------|-------------------|---------------|
| 1 | Path configured | `ConfigurationError` (existing) | census_parquet_path is required |
| 2 | File exists on disk | `ConfigurationError` (existing) | Census file not found at path |
| 3 (NEW) | File readable (DuckDB read test, ≤4s) | `ConfigurationError` | Census file cannot be read. Re-upload... |
| 4 (NEW) | File has ≥1 row | `ConfigurationError` | Census file is empty. Re-upload... |
| 5 (NEW) | Required columns present | `ConfigurationError` | Census file is missing required columns: [list]. Re-upload... |

### Required census columns (from `stg_census_data.sql`)

| Column | Type | Reason required |
|--------|------|-----------------|
| `employee_id` | VARCHAR | Primary key for all downstream joins |
| `employee_hire_date` | DATE (or parseable) | Eligibility and tenure calculations |
| `employee_gross_compensation` | DECIMAL (or numeric) | Compensation engine input |

### ConfigurationError construction for new checks (step 3–5)

Each new `ConfigurationError` includes:
- `message`: Plain-language description + actionable suggestion (so `str(error)` is UI-ready)
- `resolution_hints`: One `ResolutionHint` with title "Re-upload census file", steps pointing to Import tab
- `context`: `ExecutionContext(scenario_id=..., metadata={"census_path": ..., "workspace_id": ...})`
- `severity`: `ErrorSeverity.ERROR`

---

## Error Message Enrichment in `_handle_simulation_failure()`

**Location**: `SimulationService._handle_simulation_failure()` in `planalign_api/services/simulation/service.py`

### Current behavior
```python
error_message=str(error)   # loses resolution_hints for NavigatorError subclasses
```

### Updated behavior
```python
error_message = _format_error_for_ui(error)
# If NavigatorError with resolution_hints: appends "Suggestion: <hint steps>"
# Otherwise: same as str(error)
```

**Helper function**: `_format_error_for_ui(error: Exception) -> str`
- If `isinstance(error, NavigatorError)` and `error.resolution_hints`: appends first hint's steps as a one-liner
- Otherwise: returns `str(error)` unchanged
- No change to callers or data model

---

## Error Flow Diagram

```
[User triggers simulation]
        │
        ▼
_validate_census()  ◄── ENHANCED: steps 3-5 added
        │ fail → ConfigurationError("Census file cannot be read. Re-upload...")
        │           └─ resolution_hints = [ResolutionHint("Re-upload census file", steps=[...])]
        │ pass ↓
subprocess: planalign simulate
        │
        ▼
DbtRunner.run_command()
        │ fail → classify_dbt_error()  ◄── ENHANCED: DbtCensusFileError branch added
        │           └─ DbtCensusFileError("Census file corrupted or unreadable. Re-upload...")
        │ pass ↓
(simulation completes)

[Exception propagates]
        │
        ▼
_handle_simulation_failure()  ◄── ENHANCED: _format_error_for_ui() extracts hints
        │
        ▼
update_run_status(error_message="Census file ... Re-upload via Import tab.\nSuggestion: ...")
        │
        ▼
SimulationRunDetails.error_message  →  UI error panel
```

---

## Unchanged Entities

- **`SimulationRunDetails`** (Pydantic model in `routers/simulations.py`): no field changes
- **`DbtError`, `DbtCompilationError`, `DbtExecutionError`, `DbtDataQualityError`**: unchanged
- **`NavigatorError`, `ConfigurationError`**: unchanged; new instances created with richer hints
- **`stg_census_data.sql`**: unchanged
- **`fct_yearly_events`, `fct_workforce_snapshot`**: unchanged
