# Implementation Plan: Workspace Export and Import

**Branch**: `031-workspace-export` | **Date**: 2026-01-30 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/031-workspace-export/spec.md`

## Summary

Add workspace export and import functionality to the Manage Workspaces page, allowing users to back up workspaces as timestamped 7z archives and restore them from previously exported files. The implementation uses py7zr for pure Python 7z support, integrates with the existing WorkspaceStorage infrastructure, and provides both single and bulk operations with progress tracking.

## Technical Context

**Language/Version**: Python 3.11 (backend), TypeScript 5.x (frontend)
**Primary Dependencies**: FastAPI (backend), React 18 + Vite (frontend), py7zr (7z compression), Pydantic v2 (validation)
**Storage**: Filesystem (workspace directories at `~/.planalign/workspaces/`), 7z archives for export/import
**Testing**: pytest (backend), existing test infrastructure from E075
**Target Platform**: macOS, Windows, Linux (cross-platform via py7zr pure Python)
**Project Type**: Web application (frontend + backend)
**Performance Goals**: Export <30s for 100MB workspace, Import <60s for typical workspace
**Constraints**: Max import size 1GB, sequential downloads for bulk export, no active simulation during export
**Scale/Scope**: Typical workspace <500MB compressed, bulk operations up to 50 workspaces

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | N/A | Feature does not modify event store; exports include DuckDB databases |
| II. Modular Architecture | ✅ Pass | New ExportService as single-responsibility module |
| III. Test-First Development | ✅ Pass | Tests defined in quickstart.md, using existing fixture library |
| IV. Enterprise Transparency | ✅ Pass | Manifest includes version info, checksums for audit trail |
| V. Type-Safe Configuration | ✅ Pass | Pydantic v2 models for all API contracts |
| VI. Performance & Scalability | ✅ Pass | Targets align with SC-001/SC-002/SC-005 |

**Gate Status**: PASSED

## Project Structure

### Documentation (this feature)

```text
specs/031-workspace-export/
├── plan.md              # This file
├── spec.md              # Feature specification
├── research.md          # Phase 0 research findings
├── data-model.md        # Entity and API models
├── quickstart.md        # Developer setup guide
├── contracts/
│   └── openapi.yaml     # OpenAPI specification
├── checklists/
│   └── requirements.md  # Specification quality checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
planalign_api/
├── models/
│   └── export.py              # NEW: Export/import Pydantic models
├── services/
│   └── export_service.py      # NEW: Archive creation and extraction
├── routers/
│   └── workspaces.py          # MODIFY: Add export/import endpoints
└── storage/
    └── workspace_storage.py   # MODIFY: Add export helper methods

planalign_studio/
├── components/
│   ├── WorkspaceManager.tsx   # MODIFY: Add export/import UI
│   ├── ExportProgressDialog.tsx  # NEW: Progress tracking dialog
│   └── ImportDialog.tsx       # NEW: Import with conflict resolution
├── services/
│   └── api.ts                 # MODIFY: Add export/import API methods
└── types.ts                   # MODIFY: Add TypeScript types

tests/
├── api/
│   ├── test_export_service.py    # NEW: Unit tests
│   ├── test_import_validation.py # NEW: Validation tests
│   └── test_export_endpoints.py  # NEW: API endpoint tests
└── fixtures/
    └── workspace_archives/       # NEW: Test archive fixtures
```

**Structure Decision**: Web application pattern matching existing codebase. Backend in `planalign_api/`, frontend in `planalign_studio/`. New service module `export_service.py` follows single-responsibility principle from Constitution II.

## Complexity Tracking

> No violations - all design decisions align with Constitution principles.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| None | N/A | N/A |

## Design Artifacts

- **[research.md](./research.md)**: Technology decisions (py7zr), export/import strategies, API design rationale
- **[data-model.md](./data-model.md)**: ExportManifest, validation/response models, state transitions
- **[contracts/openapi.yaml](./contracts/openapi.yaml)**: REST API specification for 8 new endpoints
- **[quickstart.md](./quickstart.md)**: Developer setup, testing commands, troubleshooting guide

## Implementation Phases

### Phase 1: Core Export (P1)
- Backend: ExportService.export_workspace(), manifest generation
- Backend: POST /api/workspaces/{id}/export endpoint
- Frontend: Export button on workspace cards
- Tests: Unit tests for archive creation

### Phase 2: Core Import (P1)
- Backend: ExportService.validate_import(), import_workspace()
- Backend: POST /api/workspaces/import/validate, POST /api/workspaces/import
- Frontend: ImportDialog component with conflict resolution
- Tests: Validation and import tests

### Phase 3: Bulk Export (P2)
- Backend: Bulk export operation with progress tracking
- Frontend: Checkbox selection, ExportProgressDialog
- Tests: Bulk operation tests

### Phase 4: Bulk Import (P3)
- Backend: Bulk import with batch conflict resolution
- Frontend: Multi-file selection in ImportDialog
- Tests: Bulk import tests

## Next Steps

Run `/speckit.tasks` to generate detailed task breakdown for implementation.
