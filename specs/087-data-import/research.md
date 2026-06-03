# Research: Data Import with Field Mapping

**Feature**: 087-data-import
**Date**: 2026-05-30
**Status**: Complete — all unknowns resolved

---

## Decision 1: CSV/Excel Parsing Library

**Decision**: Use `pandas` (already in `pyproject.toml`) for both CSV and Excel parsing.

**Rationale**:
- `pandas` is already a declared dependency (`pandas>=2.0.0`) — no new package needed.
- `openpyxl` is also already present (`openpyxl>=3.1.0`), which pandas uses automatically for `.xlsx` files.
- `pandas.read_csv()` handles encoding detection, delimiter sniffing, and header inference.
- `pandas.read_excel()` handles multi-sheet workbooks with the `sheet_name` parameter.
- `pandas.DataFrame.dtypes` provides column type inference for the mapping UI.

**Alternatives considered**:
- `polars`: Faster but was removed in E024 (full project commitment to SQL-only mode); reintroducing it contradicts the codebase direction.
- `openpyxl` direct: More control but much more verbose; pandas wraps it cleanly.
- DuckDB `read_csv_auto()`: DuckDB can parse CSV natively but offers no Excel support; mixing DuckDB CSV + pandas Excel would be inconsistent.

---

## Decision 2: Parquet Generation

**Decision**: Use DuckDB 1.0.0's native `COPY ... TO ... (FORMAT PARQUET)` to write parquet from a DuckDB in-memory relation.

**Rationale**:
- DuckDB 1.0.0 is already a core dependency; it writes Parquet natively without `pyarrow`.
- Pattern: load pandas DataFrame into DuckDB in-memory → apply transformation SQL → `COPY` to parquet file.
- This integrates naturally with the existing DuckDB-centric architecture and avoids adding `pyarrow` as a new dependency.
- DuckDB's parquet writer produces files compatible with all major analytics tools (Pandas, Spark, DuckDB query, Tableau, etc.).

**Alternatives considered**:
- `pandas.DataFrame.to_parquet()`: Requires `pyarrow` or `fastparquet` as an optional backend, neither of which is in `pyproject.toml`.
- `pyarrow` directly: Adds a ~30MB binary dependency for a single use case DuckDB already handles.

---

## Decision 3: Transformation Engine Design

**Decision**: Implement a `MappingEngine` class that applies transformations via in-memory pandas operations before parquet generation.

**Supported transformations** (per FR-012):
| Transform Type | Implementation |
|----------------|----------------|
| Column rename | `df.rename(columns={...})` |
| Type conversion | `df[col].astype(target_type)` with error coercion |
| String case | `.str.upper()`, `.str.lower()`, `.str.title()` |
| Date format parsing | `pd.to_datetime(df[col], format=fmt, errors='coerce')` |
| Null handling | Replace with default value or drop row |
| Calculated fields | `df.eval()` or `df.assign()` with safe expression evaluation |

**Rationale**: Pandas transformations are well-understood, already available, and handle the column-level operations the spec requires. Calculated fields use `df.eval()` with a restricted expression set (no Python `exec`/`eval`) to prevent injection.

**Alternatives considered**:
- SQL-only transformations via DuckDB: Would require converting the DataFrame to a DuckDB table first, running SQL, then writing parquet. Adds complexity for the same result.
- dbt models: Not appropriate — dbt is for simulation pipeline models, not ad-hoc user data imports.

---

## Decision 4: Import Session State

**Decision**: Store import session state as a JSON file on disk in the workspace directory (`workspaces/{id}/imports/{import_id}/`).

**Storage layout**:
```
workspaces/{workspace_id}/
└── imports/
    └── {import_id}/
        ├── source.parquet        # Uploaded file, converted to parquet immediately
        ├── mapping.json          # Field mapping configuration
        └── metadata.json         # Import session metadata (status, timestamps, row count)
```

**Why convert source to parquet on upload**: Normalizes CSV and XLSX into a single in-memory-queryable format immediately. Simplifies preview generation (just query the stored parquet) and avoids re-parsing the original file on every preview request.

**Output parquet files** go to:
```
workspaces/{workspace_id}/
└── data/
    └── imports/
        └── {timestamp}_{original_name}.parquet
```
This separates the import working directory from the final analyst-accessible output, matching how census files are stored in `data/`.

**Rationale**: Consistent with existing workspace storage pattern (JSON files alongside scenario data). No new database tables needed — the workspace filesystem IS the state store.

**Alternatives considered**:
- In-memory session cache: Lost on server restart; unacceptable for long-running mapping sessions.
- SQLite sidecar database: Overkill for a simple key-value state; JSON file is sufficient.

---

## Decision 5: File Upload Streaming

**Decision**: Reuse the existing chunked upload pattern from `planalign_api/routers/files.py` (1MB chunks, 500MB hard limit enforced server-side).

**Rationale**: The existing pattern is already correct and battle-tested. The new router will follow identical streaming logic but raise the limit from 50MB (census files) to 500MB (general imports).

**Alternatives considered**:
- Presigned URL / S3-style upload: Not applicable — this is an on-premises deployment with filesystem storage.
- Multipart HTTP upload with resumability: Significantly higher complexity; not required given 500MB limit and fast LAN uploads.

---

## Decision 6: Mapping Template Persistence

**Decision**: Store mapping templates as JSON files in a workspace-level `templates/imports/` directory.

```
workspaces/{workspace_id}/
└── templates/
    └── imports/
        └── {template_id}.json   # Template definition + field mappings
```

**Rationale**: Consistent with the existing template storage pattern used by `template_service.py`. Templates are workspace-scoped (shared within a workspace, not globally).

---

## Decision 7: Access Control

**Decision**: Workspace members (anyone with workspace access) can view and download parquet files. Deletion is restricted to workspace managers (checked via the workspace `role` field on the requesting user).

**Rationale**: Matches the confirmed requirement (Q1: Option A). The existing workspace model includes a `created_by` field that can serve as a proxy for "manager" (the workspace creator). No new RBAC system needed.

---

## Resolved Unknowns Summary

| Unknown | Resolution |
|---------|-----------|
| Parquet writer without pyarrow | DuckDB 1.0.0 native COPY TO PARQUET |
| Excel multi-sheet handling | Sheet selector — pandas sheet_name param |
| 500MB upload streaming | Reuse existing 1MB chunk pattern from files.py |
| Calculated field safety | pandas df.eval() with expression whitelist |
| Import state persistence | JSON files in workspace imports/ directory |
| Access control model | Creator = manager; others = view/download only |
