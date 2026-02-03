# Tasks: Workspace Export and Import

**Input**: Design documents from `/specs/031-workspace-export/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/openapi.yaml

**Tests**: Tests are included based on Constitution III (Test-First Development) requirement.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `planalign_api/` (FastAPI)
- **Frontend**: `planalign_studio/` (React/Vite)
- **Tests**: `tests/api/` (pytest)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add py7zr dependency and create base export module structure

- [x] T001 Add py7zr[all] dependency to pyproject.toml
- [x] T002 [P] Create export models file at planalign_api/models/export.py with base Pydantic models (ExportManifest, ManifestContents)
- [x] T003 [P] Create export service skeleton at planalign_api/services/export_service.py with ExportService class
- [x] T004 [P] Add TypeScript types for export/import in planalign_studio/types.ts

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core export/import infrastructure that all user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 Implement manifest generation in planalign_api/services/export_service.py (create_manifest method)
- [x] T006 Implement archive creation with py7zr in planalign_api/services/export_service.py (create_archive method)
- [x] T007 Implement archive extraction with py7zr in planalign_api/services/export_service.py (extract_archive method)
- [x] T008 [P] Implement archive validation in planalign_api/services/export_service.py (validate_archive method)
- [x] T009 [P] Add helper method get_workspace_files_for_export in planalign_api/storage/workspace_storage.py
- [x] T010 Add simulation status check method in planalign_api/storage/workspace_storage.py (is_simulation_running)

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Export Single Workspace (Priority: P1) 🎯 MVP

**Goal**: Allow users to export a single workspace as a timestamped 7z archive

**Independent Test**: Export one workspace, verify downloaded archive contains all data and valid manifest

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T011 [P] [US1] Unit test for manifest generation in tests/api/test_export_service.py
- [x] T012 [P] [US1] Unit test for archive creation in tests/api/test_export_service.py
- [x] T013 [P] [US1] Integration test for export endpoint in tests/api/test_export_endpoints.py

### Implementation for User Story 1

- [x] T014 [US1] Implement export_workspace method in planalign_api/services/export_service.py
- [x] T015 [US1] Add POST /api/workspaces/{workspace_id}/export endpoint in planalign_api/routers/workspaces.py
- [x] T016 [US1] Add active simulation check to export endpoint (FR-013)
- [x] T017 [P] [US1] Add exportWorkspace API method in planalign_studio/services/api.ts
- [x] T018 [US1] Add Export button to workspace card in planalign_studio/components/WorkspaceManager.tsx
- [x] T019 [US1] Implement file download handling in WorkspaceManager (trigger browser download)

**Checkpoint**: User Story 1 complete - single workspace export is fully functional

---

## Phase 4: User Story 2 - Import Single Workspace (Priority: P1)

**Goal**: Allow users to import a workspace from a 7z archive with conflict resolution

**Independent Test**: Import a valid 7z archive, verify workspace appears in list with all data accessible

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T020 [P] [US2] Unit test for archive validation in tests/api/test_import_validation.py
- [x] T021 [P] [US2] Unit test for import with name conflict in tests/api/test_import_validation.py
- [x] T022 [P] [US2] Integration test for import endpoint in tests/api/test_export_endpoints.py

### Implementation for User Story 2

- [x] T023 [P] [US2] Add ImportValidationResponse, ImportConflict, ImportResponse models in planalign_api/models/export.py
- [x] T024 [US2] Implement validate_import method in planalign_api/services/export_service.py
- [x] T025 [US2] Implement import_workspace method in planalign_api/services/export_service.py
- [x] T026 [US2] Implement name conflict detection and suggested_name generation in export_service.py
- [x] T027 [US2] Add POST /api/workspaces/import/validate endpoint in planalign_api/routers/workspaces.py
- [x] T028 [US2] Add POST /api/workspaces/import endpoint in planalign_api/routers/workspaces.py
- [x] T029 [US2] Add file size limit check (1GB max) per FR-014 in import endpoint
- [x] T030 [P] [US2] Add validateImport and importWorkspace API methods in planalign_studio/services/api.ts
- [x] T031 [US2] Create ImportDialog component at planalign_studio/components/ImportDialog.tsx
- [x] T032 [US2] Add conflict resolution UI (rename/replace options) in ImportDialog
- [x] T033 [US2] Add Import button to WorkspaceManager header in planalign_studio/components/WorkspaceManager.tsx
- [x] T034 [US2] Integrate ImportDialog with WorkspaceManager and refresh workspace list on success

**Checkpoint**: User Stories 1 AND 2 complete - full export/import cycle is functional (MVP complete)

---

## Phase 5: User Story 3 - Bulk Export Multiple Workspaces (Priority: P2)

**Goal**: Allow users to select and export multiple workspaces with progress tracking

**Independent Test**: Select 3+ workspaces, export them, verify each generates its own timestamped archive

### Tests for User Story 3

- [x] T035 [P] [US3] Unit test for bulk export operation in tests/api/test_export_service.py
- [x] T036 [P] [US3] Integration test for bulk export endpoints in tests/api/test_export_endpoints.py

### Implementation for User Story 3

- [x] T037 [P] [US3] Add BulkExportRequest, BulkExportStatus, ExportResult models in planalign_api/models/export.py
- [x] T038 [US3] Implement bulk_export method with progress tracking in planalign_api/services/export_service.py
- [x] T039 [US3] Add in-memory operation storage for bulk export status in export_service.py
- [x] T040 [US3] Add POST /api/workspaces/bulk-export endpoint in planalign_api/routers/workspaces.py
- [x] T041 [US3] Add GET /api/workspaces/bulk-export/{operation_id} status endpoint in workspaces.py
- [x] T042 [US3] Add GET /api/workspaces/bulk-export/{operation_id}/download/{workspace_id} endpoint in workspaces.py
- [x] T043 [P] [US3] Add bulkExportWorkspaces and getBulkExportStatus API methods in planalign_studio/services/api.ts
- [ ] T044 [US3] Add checkbox selection mode to WorkspaceManager in planalign_studio/components/WorkspaceManager.tsx
- [ ] T045 [US3] Create ExportProgressDialog component at planalign_studio/components/ExportProgressDialog.tsx
- [ ] T046 [US3] Add "Export Selected" button and integrate with ExportProgressDialog
- [ ] T047 [US3] Implement sequential download triggering for completed exports

**Checkpoint**: User Story 3 complete - bulk export with progress tracking is functional

---

## Phase 6: User Story 4 - Bulk Import Multiple Workspaces (Priority: P3)

**Goal**: Allow users to import multiple archives at once with batch progress tracking

**Independent Test**: Select multiple valid 7z archives for import, verify all workspaces are restored

### Tests for User Story 4

- [x] T048 [P] [US4] Unit test for bulk import operation in tests/api/test_import_validation.py
- [x] T049 [P] [US4] Integration test for bulk import endpoint in tests/api/test_export_endpoints.py

### Implementation for User Story 4

- [x] T050 [P] [US4] Add BulkImportStatus model in planalign_api/models/export.py
- [x] T051 [US4] Implement bulk_import method with progress tracking in planalign_api/services/export_service.py
- [x] T052 [US4] Add batch conflict resolution (rename/skip) in bulk_import method
- [x] T053 [US4] Add POST /api/workspaces/bulk-import endpoint in planalign_api/routers/workspaces.py
- [x] T054 [US4] Add GET /api/workspaces/bulk-import/{operation_id} status endpoint in workspaces.py
- [x] T055 [P] [US4] Add bulkImportWorkspaces and getBulkImportStatus API methods in planalign_studio/services/api.ts
- [ ] T056 [US4] Extend ImportDialog to support multi-file selection in planalign_studio/components/ImportDialog.tsx
- [ ] T057 [US4] Add bulk import progress display in ImportDialog
- [ ] T058 [US4] Display import results summary (success/failed counts) in ImportDialog

**Checkpoint**: All user stories complete - full export/import functionality is operational

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Error handling improvements and edge case coverage

- [ ] T059 [P] Add edge case handling for export during active simulation (FR-013)
- [ ] T060 [P] Add version compatibility warning for imports from newer app versions
- [ ] T061 [P] Add disk space error handling for export failures
- [ ] T062 [P] Add user-friendly error messages for all failure scenarios (FR-009)
- [ ] T063 [P] Add logging for export/import operations for audit trail
- [ ] T064 Run quickstart.md validation to verify developer setup works

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - US1 and US2 together form the MVP
  - US3 and US4 are enhancements that can be deferred
- **Polish (Phase 7)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational - No dependencies on other stories
- **User Story 2 (P1)**: Can start after Foundational - Complements US1 but independently testable
- **User Story 3 (P2)**: Can start after Foundational - Builds on US1 export infrastructure
- **User Story 4 (P3)**: Can start after Foundational - Builds on US2 import infrastructure

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Models before services
- Services before endpoints
- Backend before frontend
- Core implementation before UI integration
- Story complete before moving to next priority

### Parallel Opportunities

- All Setup tasks marked [P] can run in parallel
- All Foundational tasks marked [P] can run in parallel (T008-T009)
- All tests for a user story marked [P] can run in parallel
- Models and API methods marked [P] can run in parallel within a story
- US1 and US2 can technically be worked in parallel by different developers
- US3 and US4 can be worked in parallel after their dependencies are met

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Unit test for manifest generation in tests/api/test_export_service.py"
Task: "Unit test for archive creation in tests/api/test_export_service.py"
Task: "Integration test for export endpoint in tests/api/test_export_endpoints.py"

# After tests written, launch backend + frontend API in parallel:
Task: "Add exportWorkspace API method in planalign_studio/services/api.ts"
# (runs in parallel with backend implementation T014-T016)
```

## Parallel Example: User Story 2

```bash
# Launch all tests for User Story 2 together:
Task: "Unit test for archive validation in tests/api/test_import_validation.py"
Task: "Unit test for import with name conflict in tests/api/test_import_validation.py"
Task: "Integration test for import endpoint in tests/api/test_export_endpoints.py"

# Launch models + API methods in parallel:
Task: "Add ImportValidationResponse, ImportConflict, ImportResponse models"
Task: "Add validateImport and importWorkspace API methods in api.ts"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Export)
4. Complete Phase 4: User Story 2 (Import)
5. **STOP and VALIDATE**: Test full export/import cycle independently
6. Deploy/demo if ready - users can back up and restore workspaces

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test export independently → Demo capability
3. Add User Story 2 → Test import independently → Deploy MVP!
4. Add User Story 3 → Test bulk export → Enhanced productivity
5. Add User Story 4 → Test bulk import → Full feature complete
6. Each story adds value without breaking previous stories

### Parallel Team Strategy

With multiple developers:

1. Team completes Setup + Foundational together
2. Once Foundational is done:
   - Developer A: User Story 1 (Export)
   - Developer B: User Story 2 (Import)
3. After MVP:
   - Developer A: User Story 3 (Bulk Export)
   - Developer B: User Story 4 (Bulk Import)
4. Stories complete and integrate independently

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- py7zr requires Python 3.10+ (project uses 3.11 ✓)
