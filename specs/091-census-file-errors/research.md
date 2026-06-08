# Research: Census File Error Handling — Clear Messages and Early Detection

## Decision 1: Error Classification for Census/Parquet Failures in dbt Output

**Decision**: Add a `DbtCensusFileError` subclass of `DbtError` and extend `classify_dbt_error()` in `planalign_orchestrator/dbt_runner.py` to detect parquet/census error patterns before the generic fallback.

**Rationale**: The existing `classify_dbt_error()` already pattern-matches stdout/stderr for compilation errors, database errors, and test failures. Adding a census-specific branch follows the same pattern and is the lowest-risk change. The `stg_census_data.sql` model contains `read_parquet('{{ var("census_parquet_path") }}')`, so DuckDB error output for a corrupted file will contain distinctive keywords.

**Patterns to detect** (from DuckDB 1.0.0 error messages for bad parquet files):
- `"read_parquet"` in the combined output — the model uses `read_parquet(...)` directly
- `"stg_census_data"` in the output — the model name that fails
- `"invalid parquet file"`, `"no such file"`, `"error reading"`, `"parquet"` in the error context

**Message format**: `"Census file corrupted or unreadable. Re-upload your census file via the Import tab to fix."`
The message is included directly in the exception `__str__` so it propagates through the subprocess output buffer to the API's `error_message` field without needing changes to the error serialization path.

**Alternatives considered**:
- Changing `DbtError` to inherit from `NavigatorError` (adds resolution_hints): higher blast radius; DbtError is used across the orchestrator. Rejected for this targeted fix.
- Parsing dbt JSON output: dbt can emit JSON with model-level error info. Too complex for this quick-win scope. Rejected.

---

## Decision 2: Pre-flight Census File Read Test

**Decision**: Extend `_validate_census()` in `planalign_api/services/simulation/service.py` to perform a DuckDB in-process read test (`SELECT COUNT(*) FROM read_parquet(path)`) after confirming the file exists, with a 4-second timeout using `concurrent.futures.ThreadPoolExecutor`.

**Rationale**: `_validate_census()` is called inside `_prepare_simulation()`, which runs before the subprocess is spawned. This is the earliest possible interception point. Using DuckDB in-process (not subprocess) is faster and avoids subprocess overhead. The `concurrent.futures` timeout approach is the safest way to bound the read time without introducing a new dependency.

**Three checks added**:
1. **Readability**: `SELECT COUNT(*) FROM read_parquet(path)` — if this throws, the file is corrupted
2. **Non-empty**: The count from above must be > 0 — catches empty census files
3. **Required columns**: `PRAGMA table_info(read_parquet(path))` or check columns from result — validates `employee_id`, `employee_hire_date`, `employee_gross_compensation` are present

**Required columns** (from `stg_census_data.sql` inspection):
- `employee_id` — used in all downstream joins; absent = total simulation failure
- `employee_hire_date` — required for eligibility and tenure calculations
- `employee_gross_compensation` — required for compensation engine

**Timeout**: 4 seconds. If exceeded, the exception is caught and the simulation proceeds (per FR-002 — don't block indefinitely). A warning is logged.

**Error raised on failure**: `ConfigurationError` with:
- A plain-language message that includes the actionable suggestion (so `str(error)` already contains UI-ready text)
- `resolution_hints` with a `ResolutionHint` pointing to the Import workflow
- `ExecutionContext` carrying `workspace_id`, `scenario_id`, `census_path`

**Alternatives considered**:
- Using `subprocess.run(["duckdb", path, "SELECT COUNT(*)..."])`: requires DuckDB CLI, adds subprocess overhead, harder to test. Rejected.
- Checking only file size > 0: doesn't catch corrupted or schema-mismatched files. Rejected.
- Full column-type validation: out of scope per spec Assumptions section. Deferred.

---

## Decision 3: UI Error Message Surfacing

**Decision**: Include the actionable message directly in the exception `message` field for all census file errors, so `str(error)` produces UI-ready text. Additionally, extend `_handle_simulation_failure()` to append `resolution_hints` text to `error_message` when the caught exception is a `NavigatorError` with hints.

**Rationale**: The existing path from exception → `str(error)` → `update_run_status(error_message=...)` → JSON → UI is already in place. The cheapest safe fix is to ensure the error message itself is actionable. A small enhancement to `_handle_simulation_failure()` can additionally surface resolution hints for `NavigatorError`-typed exceptions without requiring API model changes.

**Format of enhanced error_message**:
```
Census file cannot be read. Re-upload your census file via the Import tab.
Suggestion: Re-upload census file → Open Import tab → Select a valid .csv or .xlsx file → Complete mapping → Generate parquet.
```

**What NOT to change**:
- The `SimulationRunDetails` Pydantic model — `error_message: Optional[str]` is already present and surfaced to the UI
- The router logic — no changes needed to `get_run_details` or `update_run_status`

**Alternatives considered**:
- Adding a `resolution_hints: List[str]` field to `SimulationRunDetails`: cleanest long-term approach, but changes the API contract. Out of scope for Quick Wins. Deferred.
- Adding a `suggestions` field only for census errors: inconsistent UX. Rejected.

---

## Decision 4: Test Strategy

**Decision**: Two new test files under `@pytest.mark.fast`:
1. `tests/test_dbt_runner_census_error.py` — tests `classify_dbt_error()` for parquet patterns
2. `tests/test_simulation_census_validation.py` — tests `_validate_census()` for corrupted/empty/schema-mismatch cases using `tmp_path` parquet fixtures

**Pattern for parquet test fixtures**: Create test parquet files using `duckdb` in-process (as already established in `tests/test_import_dtype_bug.py`):
- Valid file: a proper parquet with all required columns and 2 rows
- Corrupted file: a file containing random bytes (not valid parquet)
- Empty file: a valid parquet schema with 0 rows
- Schema-mismatch file: a valid parquet missing required columns

**Rationale**: Matches the project's TDD pattern from E075 and 090. Uses in-memory DuckDB for speed. Constitution III requires test-first.
