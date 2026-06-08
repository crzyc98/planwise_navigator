# Quickstart: Census File Error Handling

## What this adds

Three improvements to make census file problems self-diagnosable:

1. **Pre-flight check** — `_validate_census()` now also tries to read the file before spawning the simulation subprocess. Catches corrupted, empty, and schema-mismatched files in ≤5 seconds.

2. **Better dbt error classification** — `classify_dbt_error()` now recognises parquet/census failure patterns in dbt output and returns "Census file corrupted or unreadable. Re-upload..." instead of "Unknown dbt error (code 1)".

3. **UI-ready messages** — `_handle_simulation_failure()` enriches the stored `error_message` with resolution hints from structured `ConfigurationError` exceptions, so the UI shows actionable guidance.

## Files changed

| File | Change |
|------|--------|
| `planalign_orchestrator/dbt_runner.py` | Add `DbtCensusFileError`; extend `classify_dbt_error()` |
| `planalign_api/services/simulation/service.py` | Extend `_validate_census()` with read test, empty check, column check; add `_format_error_for_ui()` helper; use it in `_handle_simulation_failure()` |
| `tests/test_dbt_runner_census_error.py` | New fast unit tests for `classify_dbt_error()` parquet patterns |
| `tests/test_simulation_census_validation.py` | New fast unit tests for `_validate_census()` with parquet fixtures |

## How to reproduce each failure before the fix

```python
# 1. Corrupted parquet
import pathlib
bad = pathlib.Path("/tmp/bad.parquet")
bad.write_bytes(b"this is not a parquet file")
# Configure a scenario to use bad.parquet → trigger simulation → expect HTTP 422 with cryptic message

# 2. Empty parquet
import duckdb, io
conn = duckdb.connect(":memory:")
conn.execute("CREATE TABLE t (employee_id VARCHAR, employee_hire_date DATE, employee_gross_compensation DECIMAL(12,2))")
conn.execute("COPY t TO '/tmp/empty.parquet' (FORMAT PARQUET)")
conn.close()
# Configure scenario → trigger simulation → no meaningful error

# 3. Missing required column
conn = duckdb.connect(":memory:")
conn.execute("CREATE TABLE t (name VARCHAR)")  # missing employee_id etc.
conn.execute("INSERT INTO t VALUES ('Alice')")
conn.execute("COPY t TO '/tmp/bad_schema.parquet' (FORMAT PARQUET)")
conn.close()
# Configure scenario → trigger simulation → generic dbt compilation error
```

## How to verify the fix

```bash
# Run the new fast regression tests
uv run pytest tests/test_dbt_runner_census_error.py tests/test_simulation_census_validation.py -v -m fast

# Run full fast suite to confirm no regressions
uv run pytest -m fast -q
```

## Manual end-to-end check

1. `planalign studio`
2. Create a workspace and scenario
3. Upload a corrupted file (create a text file renamed to `.csv` with `.parquet` extension)
4. Map and generate parquet from that file
5. Trigger simulation
6. Confirm the error panel shows: "Census file cannot be read. Re-upload your census file via the Import tab."
