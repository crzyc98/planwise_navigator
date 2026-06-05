# Implementation Plan: Fix Import File 422 — Data Type "str" Not Recognized

**Branch**: `090-fix-import-str-type` | **Date**: 2026-06-05 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/090-fix-import-str-type/spec.md`

## Summary

When a user completes the import workflow (upload CSV → map columns → generate parquet), the generate step fails with HTTP 422 `"Not implemented Error: Data type 'str' not recognized"`. Root cause: DuckDB 1.0.0's `read_parquet().df()` returns `pandas.StringDtype` extension columns; DuckDB then refuses to re-register those columns when writing the output parquet. The fix is a 3-line helper that normalizes `StringDtype` → `object` dtype before DuckDB registration.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: FastAPI, pandas ≥2.0, DuckDB 1.0.0, Pydantic v2
**Storage**: Filesystem (Parquet files per import session, no DuckDB state changes)
**Testing**: pytest, `@pytest.mark.fast` (in-memory DuckDB, no dbt)
**Target Platform**: macOS / Linux server (on-premises)
**Project Type**: web-service (FastAPI backend)
**Performance Goals**: No change — parquet generation time unaffected
**Constraints**: DuckDB must stay at 1.0.0 (version-pinned project)
**Scale/Scope**: Single-file import sessions; fix applies to all file types (CSV, XLSX)

## Constitution Check

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | ✅ Pass | No event store changes; parquet output is append-only |
| II. Modular Architecture | ✅ Pass | Helper function added to `import_service.py`; stays under 600-line module limit |
| III. Test-First Development | ✅ Pass | New `tests/test_import_dtype_bug.py` written red-first before fix |
| IV. Enterprise Transparency | ✅ Pass | No change to audit log or error context; error message improves (user sees success, not 422) |
| V. Type-Safe Configuration | ✅ Pass | No Pydantic model changes; dtype normalization is internal to service layer |
| VI. Performance & Scalability | ✅ Pass | `astype({col: object})` is O(n) one-pass; no memory overhead for typical census files |

No violations. Complexity Tracking table not needed.

## Project Structure

### Documentation (this feature)

```text
specs/090-fix-import-str-type/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Root cause analysis and fix rationale
├── data-model.md        # Column dtype lifecycle diagram
├── quickstart.md        # Reproduction steps and verification
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (from /speckit.tasks)
```

### Source Code (repository root)

```text
planalign_api/
├── services/
│   └── import_service.py     # ADD _normalize_dtypes_for_duckdb(); CALL in generate_parquet()
└── routers/
    └── imports.py             # No change (422 handler stays; bug fix prevents it being reached)

tests/
└── test_import_dtype_bug.py   # NEW: fast unit test for StringDtype → object normalization
```

**Structure Decision**: Single-project layout. The fix is entirely within `planalign_api/services/import_service.py` — one helper function and two call sites. No new files in production code.

## Implementation Design

### Helper Function

Add to `import_service.py` as a module-level private function (near `_infer_output_type`):

```python
def _normalize_dtypes_for_duckdb(df: pd.DataFrame) -> pd.DataFrame:
    str_cols = [c for c in df.columns if isinstance(df[c].dtype, pd.StringDtype)]
    return df.astype({c: object for c in str_cols}) if str_cols else df
```

**Why**: DuckDB 1.0.0 raises `NotImplementedException` when registering DataFrames with `pandas.StringDtype` columns. The root cause is that `duckdb.DuckDBPyRelation.df()` (called by `conn.execute(...).df()`) returns `StringDtype` for VARCHAR/TEXT Parquet columns, whereas the original upload DataFrame uses `dtype=object`. Casting back to `object` restores the type DuckDB can handle.

### Call Sites in `generate_parquet()`

**Call site 1** — after reading source parquet (line ~251), before MappingEngine transforms:
```python
df = conn.execute(f"SELECT * FROM read_parquet('{source_path}')").df()
conn.close()
df = _normalize_dtypes_for_duckdb(df)   # ADD THIS LINE
```

**Call site 2** — defensive guard before registering with DuckDB (line ~278):
```python
transformed = _normalize_dtypes_for_duckdb(transformed)   # ADD THIS LINE
conn = duckdb.connect(":memory:")
conn.register("_transformed", transformed)
```

Both call sites serve different purposes:
- Call site 1 prevents `StringDtype` from propagating through the MappingEngine (some `.str.*` transforms on `StringDtype` return `str` series dtype, which also fails DuckDB).
- Call site 2 is a belt-and-suspenders guard for any future DataFrame path that might introduce `StringDtype` (e.g., a calculated_field that returns a string series).

### Test Structure

New file `tests/test_import_dtype_bug.py`:

```python
"""Regression test: DuckDB 1.0.0 StringDtype normalization in generate_parquet."""
import io, os, tempfile
import pandas as pd
import duckdb
import pytest

@pytest.mark.fast
def test_normalize_dtypes_removes_string_dtype():
    """_normalize_dtypes_for_duckdb converts StringDtype → object dtype."""
    from planalign_api.services.import_service import _normalize_dtypes_for_duckdb
    df = pd.DataFrame({"name": pd.array(["Alice", None, "Bob"], dtype="string")})
    result = _normalize_dtypes_for_duckdb(df)
    assert result["name"].dtype == object

@pytest.mark.fast
def test_normalize_dtypes_noop_for_object_dtype():
    """_normalize_dtypes_for_duckdb returns DataFrame unchanged if no StringDtype."""
    from planalign_api.services.import_service import _normalize_dtypes_for_duckdb
    df = pd.DataFrame({"name": ["Alice", None, "Bob"]})  # object dtype
    result = _normalize_dtypes_for_duckdb(df)
    assert result["name"].dtype == object
    assert result is df  # same object returned — no copy when no-op

@pytest.mark.fast
def test_duckdb_register_after_read_parquet(tmp_path):
    """Full reproduction: upload → read_parquet → normalize → register → copy to parquet."""
    csv_data = "employee_id,name,salary\nEMP001,Alice,75000\nEMP002,,85000\n"
    df = pd.read_csv(io.StringIO(csv_data), dtype=object)

    src = tmp_path / "source.parquet"
    conn = duckdb.connect(":memory:")
    conn.register("_src", df)
    conn.execute(f"COPY _src TO '{src}' (FORMAT PARQUET)")
    conn.close()

    conn = duckdb.connect(":memory:")
    df2 = conn.execute(f"SELECT * FROM read_parquet('{src}')").df()
    conn.close()
    # Before fix, df2 has StringDtype columns → DuckDB register fails
    # After fix, normalization converts to object → succeeds
    from planalign_api.services.import_service import _normalize_dtypes_for_duckdb
    df2 = _normalize_dtypes_for_duckdb(df2)

    out = tmp_path / "output.parquet"
    conn = duckdb.connect(":memory:")
    conn.register("_transformed", df2)
    conn.execute(f"COPY _transformed TO '{out}' (FORMAT PARQUET)")  # Must not raise
    conn.close()
    assert out.exists()
    assert out.stat().st_size > 0
```

## Phases

### Phase 1: Red Test (TDD — test before fix)

Write `tests/test_import_dtype_bug.py` with the three tests above. Run — all three should fail (the import of `_normalize_dtypes_for_duckdb` fails because it doesn't exist yet).

```bash
pytest tests/test_import_dtype_bug.py -v -m fast
# Expected: 3 errors (ImportError)
```

### Phase 2: Green Fix

1. Open `planalign_api/services/import_service.py`
2. Add `_normalize_dtypes_for_duckdb()` helper near `_infer_output_type` (line ~476)
3. Add call site 1 in `generate_parquet()` after line ~251
4. Add call site 2 in `generate_parquet()` before line ~277

```bash
pytest tests/test_import_dtype_bug.py -v -m fast
# Expected: 3 passed
```

### Phase 3: Regression Check

```bash
# Full fast suite — must stay under 10 seconds, no regressions
pytest -m fast -v

# Import-specific tests
pytest tests/ -k "import" -v

# Manual end-to-end (optional but recommended)
planalign studio
# Upload a CSV → map → generate → confirm parquet appears
```
