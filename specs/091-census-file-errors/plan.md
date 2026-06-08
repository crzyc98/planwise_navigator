# Implementation Plan: Census File Error Handling — Clear Messages and Early Detection

**Branch**: `091-census-file-errors` | **Date**: 2026-06-05 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/091-census-file-errors/spec.md`

## Summary

Three targeted improvements to census file error handling: (1) a DuckDB-based pre-flight readability check added to `_validate_census()` that catches corrupted, empty, and schema-mismatched files before the simulation subprocess starts; (2) a `DbtCensusFileError` subclass added to `classify_dbt_error()` to pattern-match parquet/census error text in dbt output, replacing "Unknown dbt error (code 1)"; (3) UI-ready error messages by enriching the `error_message` field in `_handle_simulation_failure()` with resolution hints from structured exceptions.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: DuckDB 1.0.0 (in-process read test), FastAPI, Pydantic v2, concurrent.futures (stdlib timeout)
**Storage**: No persistent schema changes; `error_message` string content improved
**Testing**: pytest, `@pytest.mark.fast`, in-memory DuckDB parquet fixtures
**Target Platform**: macOS / Linux server (on-premises)
**Project Type**: web-service (FastAPI backend) + orchestration library
**Performance Goals**: Pre-flight check ≤4 seconds timeout; zero impact on successful simulation path
**Constraints**: Must not break existing error classification for non-census failures; no API contract changes
**Scale/Scope**: 3 files changed, 2 new test files, ~5-10 lines of production code per file

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | ✅ Pass | No event store changes |
| II. Modular Architecture | ✅ Pass | Each change is in its natural home; `_validate_census()` is already the validation function; `classify_dbt_error()` is already the classifier; `_handle_simulation_failure()` is already the error handler |
| III. Test-First Development | ✅ Pass | Two new `@pytest.mark.fast` test files written red-first |
| IV. Enterprise Transparency | ✅ Pass | Error messages become more diagnostic, not less; resolution hints improve auditability |
| V. Type-Safe Configuration | ✅ Pass | `ConfigurationError` with `resolution_hints: List[ResolutionHint]` uses the existing typed hierarchy; no untyped dicts |
| VI. Performance & Scalability | ✅ Pass | Pre-flight check is bounded by a 4s timeout; on the happy path (valid file) the overhead is ~50ms for a typical census file |

No violations. Complexity Tracking table not needed.

## Project Structure

### Documentation (this feature)

```text
specs/091-census-file-errors/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Root cause analysis and design decisions
├── data-model.md        # Exception hierarchy, validation sequence, error flow
├── quickstart.md        # Reproduction steps and verification commands
└── checklists/
    └── requirements.md  # Spec quality checklist
```

### Source Code (repository root)

```text
planalign_orchestrator/
└── dbt_runner.py              # ADD DbtCensusFileError class; EXTEND classify_dbt_error()

planalign_api/services/simulation/
└── service.py                 # EXTEND _validate_census() with 3 new checks;
                               # ADD _format_error_for_ui() helper;
                               # UPDATE _handle_simulation_failure() to use it

tests/
├── test_dbt_runner_census_error.py       # NEW: fast tests for classify_dbt_error parquet branch
└── test_simulation_census_validation.py  # NEW: fast tests for _validate_census read/empty/schema
```

**Structure Decision**: Single-project layout. All changes are in existing modules — no new packages or files in production code.

## Implementation Design

### Change 1: `DbtCensusFileError` + `classify_dbt_error()` extension

**File**: `planalign_orchestrator/dbt_runner.py`

Add after `DbtDataQualityError`:
```python
class DbtCensusFileError(DbtError):
    """Error caused by an unreadable, corrupted, or schema-mismatched census parquet file."""
```

Extend `classify_dbt_error()` — add ONE branch before the generic fallback:
```python
_CENSUS_PARQUET_PATTERNS = ("read_parquet", "stg_census_data", "invalid parquet", "parquet")

def classify_dbt_error(stdout: str, stderr: str, return_code: int) -> DbtError:
    s_err = (stderr or "").lower()
    s_out = (stdout or "").lower()
    combined = s_err + s_out

    if "compilation error" in s_err:
        return DbtCompilationError("Model compilation failed")
    if "database error" in s_err or "operationalerror" in s_err:
        return DbtExecutionError("Database execution failed")
    if "test failed" in s_out or "failing tests" in s_out:
        return DbtDataQualityError("Data quality tests failed")
    if any(p in combined for p in _CENSUS_PARQUET_PATTERNS):
        return DbtCensusFileError(
            "Census file corrupted or unreadable. "
            "Re-upload your census file via the Import tab to fix."
        )
    tail = (stdout or "").strip()
    tail = tail[-400:] if len(tail) > 400 else tail
    return DbtError(f"Unknown dbt error (code {return_code}). Tail: {tail}")
```

**Why the ordering matters**: The census pattern check runs AFTER the other pattern checks so it does not accidentally capture genuine compilation or database errors that might happen to mention "parquet" in their output for unrelated reasons.

---

### Change 2: `_validate_census()` extension

**File**: `planalign_api/services/simulation/service.py`

Add a `_check_census_readable()` static helper (to keep `_validate_census()` under 40 lines):

```python
_CENSUS_REQUIRED_COLUMNS = {"employee_id", "employee_hire_date", "employee_gross_compensation"}
_CENSUS_READ_TIMEOUT_S = 4.0

@staticmethod
def _check_census_readable(
    census_path: str,
    scenario_id: str,
    workspace_id: str,
) -> None:
    """Try to read the census parquet file; raise ConfigurationError on any failure."""
    import concurrent.futures
    import duckdb
    from planalign_orchestrator.exceptions import (
        ConfigurationError, ErrorSeverity, ExecutionContext, ResolutionHint
    )

    def _do_read():
        conn = duckdb.connect(":memory:")
        try:
            rel = conn.execute(f"SELECT * FROM read_parquet('{census_path}') LIMIT 1")
            cols = {c[0].lower() for c in rel.description}
            count = conn.execute(f"SELECT COUNT(*) FROM read_parquet('{census_path}')").fetchone()[0]
            return cols, count
        finally:
            conn.close()

    _hint = ResolutionHint(
        title="Re-upload census file",
        description="The census parquet file cannot be used as-is.",
        steps=[
            "Open the Import tab in PlanAlign Studio",
            "Upload a valid CSV or Excel census file",
            "Complete field mapping and generate a new parquet file",
            "Retry the simulation",
        ],
    )
    ctx = ExecutionContext(
        scenario_id=scenario_id,
        metadata={"census_path": census_path, "workspace_id": workspace_id},
    )

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(_do_read)
            cols, count = future.result(timeout=_CENSUS_READ_TIMEOUT_S)
    except concurrent.futures.TimeoutError:
        logger.warning("Census file read check timed out; proceeding with simulation.")
        return
    except Exception as exc:
        raise ConfigurationError(
            f"Census file cannot be read: {exc}. "
            "Re-upload your census file via the Import tab.",
            context=ctx,
            resolution_hints=[_hint],
            severity=ErrorSeverity.ERROR,
        ) from exc

    if count == 0:
        raise ConfigurationError(
            "Census file is empty (0 rows). "
            "Re-upload a census file with at least one employee record.",
            context=ctx,
            resolution_hints=[_hint],
            severity=ErrorSeverity.ERROR,
        )

    missing = _CENSUS_REQUIRED_COLUMNS - cols
    if missing:
        raise ConfigurationError(
            f"Census file is missing required columns: {sorted(missing)}. "
            "Re-upload a census file that includes all required workforce fields.",
            context=ctx,
            resolution_hints=[_hint],
            severity=ErrorSeverity.ERROR,
        )
```

Call it at the end of `_validate_census()` after the file-exists check:
```python
SimulationService._check_census_readable(str(census_path), scenario_id, workspace_id)
```

---

### Change 3: `_format_error_for_ui()` + `_handle_simulation_failure()` update

**File**: `planalign_api/services/simulation/service.py`

Add module-level helper (near imports, under `_get_memory_mb()`):
```python
def _format_error_for_ui(error: Exception) -> str:
    """Return str(error) enriched with resolution hint steps for NavigatorError subclasses."""
    from planalign_orchestrator.exceptions import NavigatorError
    if isinstance(error, NavigatorError) and error.resolution_hints:
        hint = error.resolution_hints[0]
        steps = " → ".join(hint.steps)
        return f"{error.message}\nSuggestion: {hint.title} → {steps}"
    return str(error)
```

Update `_handle_simulation_failure()`:
```python
# Change:
error_message=str(error),
# To:
error_message=_format_error_for_ui(error),
```

---

### Test Design

**`tests/test_dbt_runner_census_error.py`** (3 fast tests):
```python
@pytest.mark.fast
def test_classify_returns_census_error_for_read_parquet_in_stderr():
    err = classify_dbt_error("", "Error: read_parquet failed", 1)
    assert isinstance(err, DbtCensusFileError)
    assert "Re-upload" in str(err)

@pytest.mark.fast
def test_classify_returns_census_error_for_stg_census_data_in_stdout():
    err = classify_dbt_error("stg_census_data: FAIL", "", 1)
    assert isinstance(err, DbtCensusFileError)

@pytest.mark.fast
def test_classify_does_not_return_census_error_for_unrelated_output():
    err = classify_dbt_error("compilation error: bad model", "", 1)
    assert not isinstance(err, DbtCensusFileError)
```

**`tests/test_simulation_census_validation.py`** (4 fast tests using `tmp_path`):
```python
@pytest.mark.fast
def test_corrupted_parquet_raises_configuration_error(tmp_path):
    bad = tmp_path / "bad.parquet"
    bad.write_bytes(b"not a parquet file")
    with pytest.raises(ConfigurationError, match="cannot be read"):
        SimulationService._check_census_readable(str(bad), "s1", "w1")

@pytest.mark.fast
def test_empty_parquet_raises_configuration_error(tmp_path):
    # Create valid parquet with 0 rows
    ...
    with pytest.raises(ConfigurationError, match="empty"):
        ...

@pytest.mark.fast
def test_missing_required_columns_raises_configuration_error(tmp_path):
    # Create valid parquet missing employee_id
    ...
    with pytest.raises(ConfigurationError, match="missing required columns"):
        ...

@pytest.mark.fast
def test_valid_parquet_passes_silently(tmp_path):
    # Create valid parquet with all required columns and 2 rows
    ...
    SimulationService._check_census_readable(str(valid), "s1", "w1")  # no exception
```

## Phases

### Phase 1: Red Tests (TDD — write before fix)

Write both test files, confirm they fail (ImportError for `DbtCensusFileError`, AttributeError for `_check_census_readable`).

### Phase 2: Change 1 — dbt_runner.py

Add `DbtCensusFileError` and extend `classify_dbt_error()`. Run `test_dbt_runner_census_error.py` → all green.

### Phase 3: Change 2 — \_validate\_census() / \_check\_census\_readable()

Add `_CENSUS_REQUIRED_COLUMNS`, `_CENSUS_READ_TIMEOUT_S`, and `_check_census_readable()` to service.py. Add call in `_validate_census()`. Run `test_simulation_census_validation.py` → all green.

### Phase 4: Change 3 — \_format\_error\_for\_ui()

Add helper and update `_handle_simulation_failure()`. No new tests needed (behavior verified by integration with Change 2 fixtures).

### Phase 5: Regression

```bash
uv run pytest -m fast -q   # must match baseline (no new failures)
uv run pytest tests/ -k "simulation" -v   # import-related tests
```
