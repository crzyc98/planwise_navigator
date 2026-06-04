# Developer Quickstart: Data Import with Field Mapping

**Feature**: 087-data-import
**Date**: 2026-05-30

---

## What This Feature Adds

A multi-step data import wizard in PlanAlign Studio that lets analysts:
1. Upload a CSV or Excel file (up to 500MB)
2. Map input columns to output fields with optional transformations
3. Generate a Parquet file stored in the workspace

---

## New Files

### Backend (Python)

| File | Purpose |
|------|---------|
| `planalign_api/routers/imports.py` | FastAPI router — 14 endpoints (upload, mapping, preview, generate, list, download, delete, templates) |
| `planalign_api/services/import_service.py` | Orchestrates upload → parse → store → generate lifecycle |
| `planalign_api/services/mapping_engine.py` | Applies field transformations (rename, type cast, case, date parse, null handling, calculated fields) |
| `planalign_api/models/imports.py` | Pydantic v2 models: `ImportSession`, `FieldMapping`, `Transformation`, `ParquetFile`, `MappingTemplate` |
| `tests/unit/test_mapping_engine.py` | Unit tests for all transformation types (written first, TDD) |
| `tests/unit/test_import_service.py` | Unit tests for session lifecycle and parquet generation |
| `tests/integration/test_data_import.py` | End-to-end: upload CSV → map → generate → verify parquet |

### Frontend (TypeScript/React)

| File | Purpose |
|------|---------|
| `planalign_studio/components/DataImportWizard.tsx` | Root wizard component with step state machine |
| `planalign_studio/components/imports/FileUploadStep.tsx` | Drag-and-drop file upload, sheet selector for XLSX |
| `planalign_studio/components/imports/FieldMappingStep.tsx` | Column mapping table with type selector and transformation builder |
| `planalign_studio/components/imports/PreviewStep.tsx` | Mapped data preview with transformation warnings |
| `planalign_studio/components/imports/ImportedFilesList.tsx` | Workspace parquet files list with metadata and download |
| `planalign_studio/services/importService.ts` | API client functions for all import endpoints |

### Modified Files

| File | Change |
|------|--------|
| `planalign_api/routers/__init__.py` | Register `imports_router` |
| `planalign_api/main.py` | Mount imports router at `/api/workspaces` |
| `planalign_studio/App.tsx` | Add "Import Data" navigation entry |

---

## Running the Feature Locally

```bash
# 1. Start the API and Studio
planalign studio

# 2. Open browser to http://localhost:5173

# 3. Create or open a workspace

# 4. Click "Import Data" in the sidebar

# 5. Upload a test CSV (sample at tests/fixtures/sample_census_import.csv)

# 6. Map fields and click "Generate Parquet"

# 7. Verify file appears in workspace data files list
```

---

## Running Tests

```bash
# Unit tests (fast, TDD red-green-refactor)
pytest tests/unit/test_mapping_engine.py -v -m fast

# Import service unit tests
pytest tests/unit/test_import_service.py -v -m fast

# Integration test (requires no active DB lock)
pytest tests/integration/test_data_import.py -v -m integration
```

---

## Key Patterns

### Parquet Generation (DuckDB)

```python
import duckdb
import pandas as pd

# Load transformed DataFrame into DuckDB in-memory
conn = duckdb.connect(":memory:")
conn.register("transformed", mapped_df)

# Write parquet
output_path = workspace_dir / "data" / "imports" / filename
conn.execute(f"COPY transformed TO '{output_path}' (FORMAT PARQUET)")
conn.close()
```

### Streaming Upload (FastAPI)

```python
# Reuse the 1MB chunk pattern from files.py
chunks = []
total_size = 0
while chunk := await file.read(1024 * 1024):
    total_size += len(chunk)
    if total_size > MAX_IMPORT_SIZE:
        raise HTTPException(413, "File exceeds 500MB limit")
    chunks.append(chunk)
content = b"".join(chunks)
```

### Transformation Application (MappingEngine)

```python
from planalign_api.services.mapping_engine import MappingEngine

engine = MappingEngine()
mapped_df = engine.apply(df, field_mappings)
# Returns transformed DataFrame with output_column names and output_types applied
```

### Session Storage Path

```python
from pathlib import Path

def import_session_path(workspaces_root: Path, workspace_id: str, import_id: str) -> Path:
    return workspaces_root / workspace_id / "imports" / import_id

def output_parquet_path(workspaces_root: Path, workspace_id: str, filename: str) -> Path:
    return workspaces_root / workspace_id / "data" / "imports" / filename
```

---

## Constitution Compliance Checklist

| Principle | How This Feature Complies |
|-----------|--------------------------|
| I. Event Sourcing | Import audit log written to `imports/index.json` — append-only, immutable after creation |
| II. Modular Architecture | `import_service.py` + `mapping_engine.py` are separate responsibilities; neither exceeds 600 lines |
| III. Test-First | `test_mapping_engine.py` and `test_import_service.py` written in Phase 2 before any service code |
| IV. Enterprise Transparency | FR-014: all imports logged with filename, rows, mapping config, user, timestamp |
| V. Type-Safe Configuration | All models use Pydantic v2 with explicit field constraints |
| VI. Performance | 500MB file, 500K-row target; chunked upload prevents memory spikes; DuckDB COPY is streaming |

---

## Workspace Directory After Import

```
workspaces/{workspace_id}/
├── imports/
│   └── {import_id}/
│       ├── source.parquet      ← uploaded file normalized on arrival
│       ├── mapping.json        ← FieldMapping[] saved by analyst
│       └── metadata.json       ← ImportSession state
└── data/
    └── imports/
        ├── index.json                          ← ParquetFile[] registry
        └── 20260530_141023_census_2025.parquet ← final output
```

---

## Adding a New Transformation Type

1. Add a new value to `TransformType` enum in `planalign_api/models/imports.py`
2. Write unit tests in `test_mapping_engine.py` for the new transform
3. Implement the transform handler in `mapping_engine.py` (add one method, register in dispatch dict)
4. Add the transform UI in `FieldMappingStep.tsx` transformation builder
5. Update `contracts/api-imports.md` `params` table
