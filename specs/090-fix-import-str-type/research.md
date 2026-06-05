# Research: Fix Import File 422 — Data Type "str" Not Recognized

## Decision 1: Root Cause

**Decision**: The bug is a DuckDB 1.0.0 / pandas `StringDtype` incompatibility in the generate-parquet code path.

**Rationale**: Confirmed by reproduction:
1. `pd.read_csv(..., dtype=object)` produces `dtype('O')` (classic object dtype) — DuckDB can register these fine.
2. When DuckDB reads a Parquet file back into pandas via `conn.execute("SELECT * FROM read_parquet(...)").df()`, it returns columns with `pandas.StringDtype(storage='python')` — a newer pandas extension type.
3. DuckDB 1.0.0 cannot re-register a DataFrame that contains `StringDtype` columns. It raises `NotImplementedException: Not implemented Error: Data type 'str' not recognized`.

**Affected line**: `import_service.py:251` — `df = conn.execute("SELECT * FROM read_parquet(...)").df()` — this is where `StringDtype` enters the pipeline. The failure surfaces at line 278: `conn.register("_transformed", transformed)`.

**Alternatives considered**:
- Upgrade DuckDB: DuckDB 1.1.x handles `StringDtype` natively, but this is a version constraint project; not a valid fix path.
- Use `conn.read_parquet()` instead of `SELECT * FROM read_parquet()`: Same result — `.df()` always uses the same pandas conversion path.

---

## Decision 2: Fix Location

**Decision**: Normalize `StringDtype` → `object` dtype immediately before `conn.register("_transformed", transformed)` in `generate_parquet()`.

**Rationale**:
- This is the single point of failure confirmed by the reproduction test.
- Normalizing at the source (`read_parquet` call) would also work but would change behavior for `get_raw_preview` / `get_mapped_preview`, which currently return `StringDtype` DataFrames that are serialized to JSON without DuckDB re-registration (so they don't fail).
- Fixing at the registration point is narrowest, safest, and does not affect the preview paths.

**Alternatives considered**:
- Normalize at the `read_parquet` call site in `generate_parquet()`: Also valid and slightly more explicit — converts before the MappingEngine sees `StringDtype` columns, which might also avoid edge cases in string transforms (e.g., `.str.upper()` on `StringDtype` returns `str` series dtype, which also fails DuckDB registration). This is actually preferred.
- Convert using Arrow: `pa.Table.from_pandas(df)` then `conn.register("_t", arrow_table)` — valid but adds a PyArrow dependency and is more complex than needed.

**Final decision**: Normalize immediately after `read_parquet` in `generate_parquet()` (before the MappingEngine transforms), so that `StringDtype` never enters the transformation pipeline. Additionally, add a defensive normalization just before `conn.register` as a belt-and-suspenders guard.

---

## Decision 3: Normalization Strategy

**Decision**: Cast `StringDtype` columns to `object` dtype using `df.astype({col: object for col in str_cols})`.

**Rationale**:
- `object` dtype is what `pd.read_csv(..., dtype=object)` naturally produces.
- DuckDB 1.0.0 handles `object` dtype with mixed `str`/`NaN` values correctly (confirmed by test).
- The cast preserves all values including NaN (NaN stays as `float('nan')` in object columns — same as the original upload input).

**Alternatives considered**:
- `df[col].astype(str)`: Converts `NaN` to the string `"nan"` — loses null information. Rejected.
- `df[col].astype("object")`: Same as `object` — equivalent.
- `df[col].where(pd.notna(df[col]), other=None)`: Converts NaN to Python `None` — changes null representation unnecessarily. Rejected.

---

## Decision 4: Helper Function vs. Inline Fix

**Decision**: Extract a private helper `_normalize_dtypes_for_duckdb(df)` in `import_service.py`.

**Rationale**: The normalization may be needed in multiple places (before read-back and before register). A named helper is self-documenting and avoids duplication. Under 5 lines — does not introduce complexity.

---

## Decision 5: Test Strategy

**Decision**: Add a unit test in `tests/test_import_service.py` (or a new `tests/test_import_dtype_bug.py`) that:
1. Creates a CSV with string/null columns, uploads it (saves to source parquet).
2. Reads source parquet back via DuckDB (which now returns `StringDtype`).
3. Saves a mapping and calls `generate_parquet`.
4. Asserts no exception is raised and the output parquet file exists.

Mark with `@pytest.mark.fast` — no dbt or external dependencies needed (in-memory DuckDB only).

**Rationale**: Constitution III requires test-first. This test can be written before the fix and should fail red, then pass green after the one-line change.
