# Implementation Plan: Data Import with Field Mapping

**Branch**: `087-data-import` | **Date**: 2026-05-30 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/087-data-import/spec.md`

## Summary

Analysts need a general-purpose CSV/Excel import wizard in PlanAlign Studio that allows flexible field mapping and outputs a Parquet file stored in the workspace. The implementation adds a new `imports` router and `MappingEngine` service to the FastAPI backend, and a multi-step `DataImportWizard` to the React frontend. File parsing uses pandas (already a dependency); Parquet generation uses DuckDB 1.0.0's native `COPY TO PARQUET` capability to avoid adding pyarrow. Import sessions are tracked as JSON files in the workspace filesystem, consistent with the existing storage pattern.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript/React 18 (frontend)
**Primary Dependencies**: FastAPI + Pydantic v2 (backend); React 18 + Tailwind CSS v4 (frontend); pandas ≥2.0, openpyxl ≥3.1, DuckDB 1.0.0 (data processing — all already in `pyproject.toml`)
**Storage**: Filesystem JSON (session state + metadata) + Parquet files in `workspaces/{id}/` directories
**Testing**: pytest (backend unit + integration); React Testing Library (frontend)
**Target Platform**: On-premises macOS/Linux (same as rest of project)
**Project Type**: Web service (FastAPI + React) — new feature within existing Studio
**Performance Goals**: Full import workflow (upload → map → generate) in < 5 min for 100K-row files (SC-001); upload-to-preview sub-goal: < 5s for 100K rows (internal target, not in spec)
**Constraints**: Max 500MB upload; no new pip dependencies for parquet writing; no circular dependencies with existing routers
**Scale/Scope**: Single-workspace single-user sessions; up to 100 concurrent import operations

## Constitution Check

*GATE: All principles pass — no violations.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | ✅ Pass | Import audit records in `data/imports/index.json` are append-only and immutable after creation. Not workforce simulation events — administrative metadata only. |
| II. Modular Architecture | ✅ Pass | `import_service.py` (session lifecycle) and `mapping_engine.py` (transformations) are separate responsibilities. Neither will exceed 600 lines. |
| III. Test-First Development | ✅ Pass | `test_mapping_engine.py` and `test_import_service.py` written before service implementation (Red-Green-Refactor). |
| IV. Enterprise Transparency | ✅ Pass | FR-014 requires full audit log (filename, rows, mapping config, user, timestamp). Satisfied by `index.json` append. |
| V. Type-Safe Configuration | ✅ Pass | All models use Pydantic v2 with explicit field constraints and `Literal` types for enums. |
| VI. Performance & Scalability | ✅ Pass | Chunked upload (1MB), DuckDB COPY streaming, in-memory pandas within session scope. |

## Project Structure

### Documentation (this feature)

```text
specs/087-data-import/
├── plan.md              ← This file
├── research.md          ← Phase 0: library decisions and resolved unknowns
├── data-model.md        ← Phase 1: entity model and filesystem layout
├── quickstart.md        ← Phase 1: developer guide
├── contracts/
│   └── api-imports.md  ← Phase 1: all 14 endpoint contracts
└── tasks.md             ← Phase 2 output (/speckit.tasks)
```

### Source Code

```text
planalign_api/
├── models/
│   └── imports.py          ← NEW: ImportSession, FieldMapping, Transformation,
│                                   ParquetFile, MappingTemplate Pydantic v2 models
├── services/
│   ├── import_service.py   ← NEW: Session lifecycle (upload, store, status, delete)
│   └── mapping_engine.py   ← NEW: Transformation engine (rename, cast, case, date,
│                                   null handling, calculated fields)
└── routers/
    ├── imports.py           ← NEW: 14 FastAPI endpoints
    └── __init__.py          ← MODIFIED: register imports_router

planalign_studio/
├── components/
│   ├── DataImportWizard.tsx          ← NEW: Root multi-step wizard
│   └── imports/
│       ├── FileUploadStep.tsx        ← NEW: Drag-drop + sheet selector
│       ├── FieldMappingStep.tsx      ← NEW: Column mapping table + transform builder
│       ├── PreviewStep.tsx           ← NEW: Mapped data preview table
│       └── ImportedFilesList.tsx     ← NEW: Workspace parquet files list
└── services/
    └── importService.ts              ← NEW: API client for all import endpoints

tests/
├── unit/
│   ├── test_mapping_engine.py        ← NEW: All transformation types (written first)
│   └── test_import_service.py        ← NEW: Session lifecycle
└── integration/
    └── test_data_import.py           ← NEW: Upload → map → generate → verify
```

**Structure Decision**: Web application pattern. Backend extends the existing `planalign_api` package with three new files (`routers/imports.py`, `services/import_service.py`, `services/mapping_engine.py`) and one new model file. Frontend extends `planalign_studio` with a new `imports/` component directory under `components/`. No new top-level packages; consistent with all prior feature additions.

## Complexity Tracking

> No constitution violations. Table not required.
