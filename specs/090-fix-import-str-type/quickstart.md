# Quickstart: Fix Import File 422 — Data Type "str" Not Recognized

## What this fixes

Uploading a CSV/XLSX file and then generating parquet output fails with HTTP 422 `"Not implemented Error: Data type 'str' not recognized"`. The error occurs because DuckDB 1.0.0's `read_parquet().df()` returns pandas `StringDtype` columns, and DuckDB cannot re-register a DataFrame containing those columns.

## Files changed

| File | Change |
|------|--------|
| `planalign_api/services/import_service.py` | Add `_normalize_dtypes_for_duckdb()` helper; call it in `generate_parquet()` before `conn.register()` |
| `tests/test_import_dtype_bug.py` | New fast unit test reproducing and verifying the fix |

## How to reproduce the bug (before fix)

```bash
source .venv/bin/activate
python -c "
import pandas as pd, duckdb, io, tempfile, os

csv_data = 'employee_id,name\nEMP001,Alice\n'
df = pd.read_csv(io.StringIO(csv_data), dtype=object)

src = '/tmp/test_src.parquet'
conn = duckdb.connect(':memory:')
conn.register('_src', df)
conn.execute(f\"COPY _src TO '{src}' (FORMAT PARQUET)\")
conn.close()

conn = duckdb.connect(':memory:')
df2 = conn.execute(f\"SELECT * FROM read_parquet('{src}')\").df()
conn.close()

out = '/tmp/test_out.parquet'
conn = duckdb.connect(':memory:')
conn.register('_transformed', df2)     # FAILS HERE
conn.execute(f\"COPY _transformed TO '{out}' (FORMAT PARQUET)\")
conn.close()
"
# Expected: NotImplementedException: Not implemented Error: Data type 'str' not recognized
```

## How to verify the fix

```bash
# Run the fast unit test (< 10 seconds)
pytest tests/test_import_dtype_bug.py -v -m fast

# Run the full import service tests
pytest tests/ -k "import" -v
```

## Manual end-to-end test

1. `planalign studio` to start the API + frontend
2. Open a workspace → Import Data
3. Upload any CSV file with text columns
4. Complete field mapping
5. Click "Generate" — should succeed and list a parquet file
