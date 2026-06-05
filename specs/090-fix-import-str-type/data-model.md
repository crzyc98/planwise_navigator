# Data Model: Fix Import File 422 — Data Type "str" Not Recognized

## Summary

No new entities or schema changes. This bug fix touches the internal data-type handling of the `ImportService` class — specifically how it normalizes pandas DataFrame column types before passing them to DuckDB. The public data model (API request/response shapes, Pydantic models, Parquet file schema) is unchanged.

---

## Affected Internal State Flow

```
Upload (CSV/XLSX)
  └─ pd.read_csv(dtype=object)           → dtype('O')  columns   [OK for DuckDB]
       └─ COPY _src TO source.parquet    → Parquet file on disk

Generate Parquet
  └─ read_parquet(source.parquet).df()   → StringDtype columns    [FAILS DuckDB register]
       └─ _normalize_dtypes(df)          → dtype('O')  columns    [FIX — normalizes here]
            └─ MappingEngine.apply()     → dtype('O')  columns    [safe to transform]
                 └─ conn.register(transformed)                     [OK after fix]
                      └─ COPY TO output.parquet                    [OK]
```

---

## Changed Component: ImportService._normalize_dtypes_for_duckdb

**Location**: `planalign_api/services/import_service.py`

| Attribute | Description |
|-----------|-------------|
| **Input** | `pd.DataFrame` — may contain `StringDtype(storage='python')` columns returned by DuckDB's `read_parquet().df()` |
| **Output** | `pd.DataFrame` — identical values, but all `StringDtype` columns cast to `object` dtype |
| **Side effects** | None — returns a new DataFrame, does not mutate in place |
| **Null handling** | `NaN` in `StringDtype` columns remains `float('nan')` in `object` columns — consistent with how `pd.read_csv(dtype=object)` stores nulls |

---

## Column dtype Lifecycle (string columns)

| Stage | dtype | DuckDB compatible? |
|-------|-------|--------------------|
| `pd.read_csv(..., dtype=object)` | `object` | Yes |
| `COPY _src TO source.parquet` | Parquet `UTF8` | — |
| `read_parquet(...).df()` | `StringDtype(storage='python')` | **No — causes 422** |
| After `_normalize_dtypes_for_duckdb()` | `object` | Yes |
| After MappingEngine transforms | `object` (string cols) | Yes |
| `COPY _transformed TO output.parquet` | Parquet `UTF8` | — |

---

## Entities (unchanged)

- **ImportSession**: No change.
- **FieldMapping**: No change. `OutputType` literal (`"string"`, `"decimal"`, `"date"`, etc.) is correct and not the source of the error.
- **ParquetFile**: No change. The output schema reported by `_infer_output_type` continues to return `"string"` for `object` dtype columns.
- **DetectedColumn**: No change.
