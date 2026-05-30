# Tasks: Data Import with Field Mapping

**Input**: Design documents from `/specs/087-data-import/`
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/api-imports.md ✅ quickstart.md ✅

**Tests**: Included per Constitution Principle III (test-first development is mandatory for all significant features).

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to ([US1]–[US5])

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create new directories, stubs, and wire the router into the existing FastAPI app and React Studio. All setup tasks can run in parallel.

- [X] T001 [P] Create `planalign_studio/components/imports/` directory (empty, signals intent)
- [X] T002 [P] Create stub `planalign_api/routers/imports.py` — empty `APIRouter` with prefix `/api/workspaces`, tags `["imports"]`
- [X] T003 Register `imports_router` export in `planalign_api/routers/__init__.py`
- [X] T004 Mount imports router in `planalign_api/main.py` (add to existing router list)
- [X] T005 [P] Create stub `planalign_studio/services/importService.ts` — empty module with typed placeholder exports
- [X] T050 [P] Create `tests/fixtures/sample_census_import.csv` — 200-row CSV with columns: `EMP_ID` (string), `HIRE_DATE` (MM/DD/YYYY), `SALARY` (numeric), `DEPT` (string with mixed case), `ACTIVE` (boolean); include 3 rows with invalid HIRE_DATE values and 1 row with null SALARY to exercise error paths

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Pydantic v2 models and core service skeletons that every user story depends on. **No user story work begins until this phase is complete.**

⚠️ **Constitution III — write tests FIRST, confirm they FAIL, then implement**

- [X] T006 Create `planalign_api/models/imports.py` with all Pydantic v2 models: `ImportStatus` enum, `InferredType` enum, `OutputType` enum, `TransformType` enum, `DetectedColumn`, `Transformation`, `FieldMapping`, `ImportSession` (include `correlation_id: str = Field(default_factory=lambda: str(uuid4()))`), `ParquetFile`, `ParquetColumn`, `MappingTemplate` — per `data-model.md` field tables; also add `ImportErrorResponse` model with `correlation_id`, `error_code`, `message`, `resolution_hint`, `context` fields
- [X] T007 [P] Write `tests/unit/test_mapping_engine.py` — one failing test per transform type: rename, string_case (upper/lower/title), date_parse, null_replace, null_drop, calculated_field; test chaining; **security test: assert `ValueError` raised for expressions containing `__import__`, `exec`, `eval`, `open`, and `os.`** (must FAIL before T009)
- [X] T008 [P] Write `tests/unit/test_import_service.py` — failing tests for session create (assert `correlation_id` in response), status transitions (uploaded → mapping_in_progress → generating → completed/failed), session metadata read/write, parquet index append, audit log written on create/generate/delete (must FAIL before T010 and T051)
- [X] T051 Implement audit log foundation in `planalign_api/services/import_service.py` stub — add `_write_audit_log(workspace_id, action, import_id, filename, row_count, user, mapping_config)` helper that appends a JSON line to `data/imports/audit.log`; wire it into `create_session` and stub calls in `generate_parquet` and `delete_parquet_file` (depends on T006, T008; **must be in foundation before any endpoints run**)
- [X] T009 Implement `planalign_api/services/mapping_engine.py` — `MappingEngine` class with `apply(df, field_mappings) → pd.DataFrame`; dispatch dict per `TransformType`; `df.eval()` with whitelist (column refs + `+`, `-`, `*`, `/` only; reject `__`, `import`, `exec`, `eval`, `open`, `os.`); type cast with `errors='coerce'` (depends on T006, T007 passing)
- [X] T010 Implement `planalign_api/services/import_service.py` — `ImportService` class with methods: `create_session`, `get_session`, `update_status`, `save_mapping`, `get_mapping`, `generate_parquet`, `save_parquet_record`, `list_parquet_files`, `delete_parquet_file`; filesystem paths per `data-model.md` layout; wire `_write_audit_log` calls on `create_session`, `save_mapping`, generation success/failure, and `delete_parquet_file` (depends on T006, T051, T008 passing)

**Checkpoint**: Run `pytest tests/unit/ -v` — all unit tests should now pass, audit log helper is exercised

---

## Phase 3: User Story 1 — Upload and Map CSV/Excel Data (Priority: P1) 🎯 MVP

**Goal**: Analyst uploads CSV or XLSX, sees column preview, configures field mappings, and saves them.

**Independent Test**: Upload `tests/fixtures/sample_census_import.csv`, configure 3 field mappings (rename + type cast + date_parse), save mapping — verify `mapping.json` written and `GET .../preview` returns 100 rows.

- [X] T011 [P] [US1] Write integration test block "upload and map" in `tests/integration/test_data_import.py`: POST upload CSV → assert 201 + detected_columns; PATCH sheet (XLSX variant); PUT mapping → assert 200 + no validation_errors (must FAIL before T012–T014)
- [X] T012 [P] [US1] Implement `POST /{workspace_id}/imports/upload` in `planalign_api/routers/imports.py`: 1 MB chunked read (500 MB limit), pandas parse CSV/XLSX, write `source.parquet` via DuckDB, write `metadata.json`, return `ImportSession` response (depends on T010)
- [X] T013 [US1] Implement `PATCH /{workspace_id}/imports/{import_id}/sheet` in `planalign_api/routers/imports.py`: re-parse XLSX with selected sheet_name, refresh detected_columns + preview_rows in `metadata.json` (depends on T012)
- [X] T014 [US1] Implement `PUT /{workspace_id}/imports/{import_id}/mapping` in `planalign_api/routers/imports.py`: validate uniqueness and column existence, write `mapping.json`, return validation_errors list (depends on T010)
- [X] T015 [P] [US1] Implement `planalign_studio/components/imports/FileUploadStep.tsx`: drag-and-drop file zone (CSV/XLSX), POST upload call, loading state, sheet selector dropdown when `available_sheets.length > 1`, display detected_columns table with inferred types and sample values
- [X] T016 [US1] Implement `planalign_studio/components/imports/FieldMappingStep.tsx`: table with one row per detected column; editable output_column name, output_type selector, is_excluded toggle; transformation builder (add/remove/reorder transforms per column, transform_type selector + params inputs); validation error inline display (depends on T015 for shared type definitions)
- [X] T017 [US1] Wire upload + mapping calls in `planalign_studio/services/importService.ts`: `uploadFile`, `selectSheet`, `saveMapping` functions with TypeScript types matching `planalign_api/models/imports.py`
- [X] T018 [US1] Implement `planalign_studio/components/DataImportWizard.tsx` for steps 1–2 (Upload → Mapping): step state machine, back/next navigation, pass `importId` between steps, call `importService.saveMapping` on "Next" from mapping step (depends on T015, T016, T017)
- [X] T055 [US1] Implement encoding detection in `planalign_api/services/import_service.py` upload path: attempt UTF-8 decode; on `UnicodeDecodeError`, retry with `latin-1`; surface encoding warnings in `ImportSession.encoding_warnings: List[str]` (e.g., "File decoded as latin-1; 12 characters may render incorrectly"); add `encoding_used` field to `ImportSession`
- [X] T056 [US1] Implement duplicate column-name deduplication in `planalign_api/services/import_service.py` upload path: after pandas parse, scan for duplicate header names and rename second+ occurrences to `{name}_1`, `{name}_2`, etc.; add `column_renames: List[dict]` field to upload response so analyst sees what was renamed (follows existing pattern in `files.py`)

**Checkpoint**: Launch `planalign studio`, upload a CSV, configure 3 mappings → "Next" saves mapping — verify no console errors and `mapping.json` exists on disk

---

## Phase 4: User Story 2 — Generate Parquet Output (Priority: P1)

**Goal**: From saved mappings, analyst generates a Parquet file. Progress is visible for large files. Errors name the problematic row and column.

**Independent Test**: With a valid mapping saved (from US1), POST `/generate` → verify `data/imports/` contains a valid Parquet file, row count matches source, and the file is readable by DuckDB `SELECT COUNT(*) FROM read_parquet(...)`.

- [X] T019 [P] [US2] Add "generate parquet" test block to `tests/integration/test_data_import.py`: POST generate → assert 201 (or poll for `completed`); open generated parquet with DuckDB and assert row count = source row count; add failure case: upload CSV with type mismatch → assert `failed` status + error_rows populated (must FAIL before T020–T021)
- [X] T020 [US2] Implement `POST /{workspace_id}/imports/{import_id}/generate` in `planalign_api/routers/imports.py`: validate mapping saved, set status `generating`, call `import_service.generate_parquet`, return 201 with ParquetFile on success or 422 with error details on failure (depends on T021)
- [X] T021 [US2] Add `generate_parquet(import_id, workspace_id) → ParquetFile` to `planalign_api/services/import_service.py`: load source.parquet via pandas, call `MappingEngine.apply()`, write output via `duckdb.connect(':memory:')` + `COPY transformed TO path (FORMAT PARQUET)`, append ParquetFile to `data/imports/index.json`, update `metadata.json` status (depends on T009, T010)
- [X] T022 [P] [US2] Implement `planalign_studio/components/imports/PreviewStep.tsx`: tabular display of mapped preview rows (from `GET .../mapped-preview` call), transformation_warnings list, "Generate Parquet" button, progress indicator during generation polling, success state with filename + row count
- [X] T023 [US2] Extend `planalign_studio/components/DataImportWizard.tsx` to step 3 (Preview → Generate): call `importService.getMappedPreview` on entering preview step, call `importService.generateParquet` on button click, poll `importService.getImportStatus` every 2s until `completed` or `failed`, show error details on failure (depends on T018, T022)
- [X] T024 [US2] Add generate + status + mapped-preview calls to `planalign_studio/services/importService.ts`: `generateParquet`, `getImportStatus`, `getMappedPreview` functions (depends on T017)

**Checkpoint**: Full wizard end-to-end — upload CSV → map → preview → generate → verify parquet file appears

---

## Phase 5: User Story 3 — Store and Manage Imported Data (Priority: P2)

**Goal**: Generated parquet files appear in a workspace list with metadata. Members can download; only the workspace creator can delete.

**Independent Test**: After generating a parquet file (US2), navigate to "Imported Files" in the workspace → verify file appears with correct row count, file size, and created_at; download it and open in DuckDB; attempt delete as non-creator → verify 403.

- [X] T052 [P] [US3] Write failing integration tests for file management in `tests/integration/test_data_import.py`: assert generated parquet appears in `GET /parquet-files`; assert two imports from same source produce distinct filenames (collision avoidance); assert `GET .../download` returns binary with correct `Content-Disposition`; assert `DELETE` by non-creator returns 403; assert `DELETE` by creator returns 204 and file is gone (must FAIL before T025–T027)
- [X] T025 [P] [US3] Implement `GET /{workspace_id}/parquet-files` in `planalign_api/routers/imports.py`: read `data/imports/index.json`, return sorted list (newest first) with full ParquetFile metadata (depends on T010)
- [X] T026 [P] [US3] Implement `GET /{workspace_id}/parquet-files/{file_id}/download` in `planalign_api/routers/imports.py`: resolve storage_path from index, return `FileResponse` with `Content-Disposition: attachment` (depends on T010)
- [X] T027 [US3] Implement `DELETE /{workspace_id}/parquet-files/{file_id}` in `planalign_api/routers/imports.py`: compare `created_by` of workspace (from `WorkspaceStorage.get_workspace`) against request identity — return 403 if not creator; remove file from filesystem and from index.json (depends on T010)
- [X] T028 [P] [US3] Implement `planalign_studio/components/imports/ImportedFilesList.tsx`: table of parquet files (filename, original_filename, row_count, file_size_bytes formatted, created_at, created_by); "Download" button per row; "Delete" button visible only for workspace creator (check `workspace.created_by`); confirmation dialog before delete
- [X] T029 [US3] Add file list + download + delete calls to `planalign_studio/services/importService.ts`: `listParquetFiles`, `downloadParquetFile`, `deleteParquetFile` functions (depends on T017)
- [X] T030 [US3] Add "Imported Files" tab or section to `planalign_studio/components/WorkspaceManager.tsx`: render `ImportedFilesList` component, wire to workspace context (depends on T028, T029)

**Checkpoint**: Open workspace in Studio → "Imported Files" shows correct list; download works; delete restricted to creator

---

## Phase 6: User Story 4 — Preview Mapped Data Before Generation (Priority: P2)

**Goal**: Analyst sees first 100 rows with mappings applied before committing to parquet generation. Transformation warnings are shown inline.

**Independent Test**: After saving mapping with a date_parse transform, click "Preview" → verify output columns match configured names/types, date values are reformatted, transformation_warnings appear for any failed parses.

- [X] T053 [P] [US4] Write failing integration tests for preview endpoints in `tests/integration/test_data_import.py`: assert `GET .../preview` returns 100 raw rows with original column names; assert `GET .../mapped-preview` returns output_column names (not input names) with correct types; assert `transformation_warnings` lists date-parse failures when 3 rows have invalid dates; assert `GET .../mapped-preview` returns 409 when no mapping saved (must FAIL before T031–T033)
- [X] T031 [P] [US4] Implement `GET /{workspace_id}/imports/{import_id}/preview` in `planalign_api/routers/imports.py`: load source.parquet, return first 100 rows as list of dicts with original column names (raw, no mapping applied) (depends on T010)
- [X] T032 [P] [US4] Implement `GET /{workspace_id}/imports/{import_id}/mapped-preview` in `planalign_api/routers/imports.py`: load source.parquet, load mapping.json, call `MappingEngine.apply_preview(df.head(100), mappings)` returning transformed rows + transformation_warnings; return 409 if no mapping saved yet (depends on T009, T010)
- [X] T033 [US4] Add `apply_preview(df, field_mappings) → (pd.DataFrame, List[TransformationWarning])` to `planalign_api/services/mapping_engine.py`: same as `apply()` but collects per-column warnings (null-coerced count, parse failures) without raising; returns warnings alongside transformed data (depends on T009)
- [X] T034 [US4] Update `planalign_studio/components/imports/PreviewStep.tsx` to call `getMappedPreview` and display transformation_warnings above the preview table (each warning shows column name + rows_affected + message) (depends on T022, T024)
- [X] T035 [US4] Add `getRawPreview` call to `planalign_studio/services/importService.ts` (depends on T017)
- [X] T036 [US4] Ensure `DataImportWizard.tsx` calls `getMappedPreview` when analyst navigates to preview step and refreshes when mapping changes (depends on T023, T034)

**Checkpoint**: In wizard, after configuring a date_parse transform with 3 invalid values → preview shows correct reformatted dates + warning "3 values could not be parsed..."

---

## Phase 7: User Story 5 — Save and Reuse Mapping Templates (Priority: P3)

**Goal**: Analysts save a configured mapping as a named template, then apply it to future uploads with one click.

**Independent Test**: Save mapping as "Standard HR Export", upload a second CSV with same column headers, select template → verify mappings auto-populated with all transformations intact.

- [X] T054 [P] [US5] Write failing integration tests for mapping templates in `tests/integration/test_data_import.py`: assert saved template appears in `GET /mapping-templates`; assert `POST /apply-template` on a new import with same headers populates all mappings; assert `POST /apply-template` silently skips template fields whose `input_column` is absent in the new session (must FAIL before T037–T039)
- [X] T037 [P] [US5] Implement `GET /{workspace_id}/mapping-templates` in `planalign_api/routers/imports.py`: list JSON files in `templates/imports/`, return summary (template_id, name, description, field_count, created_at) (depends on T010)
- [X] T038 [P] [US5] Implement `POST /{workspace_id}/mapping-templates` in `planalign_api/routers/imports.py`: load mapping from `imports/{import_id}/mapping.json`, write to `templates/imports/{template_id}.json`, return MappingTemplate response (depends on T010)
- [X] T039 [US5] Implement `POST /{workspace_id}/imports/{import_id}/apply-template` in `planalign_api/routers/imports.py`: load template's field_mappings, filter to only input_columns present in session's detected_columns (silent skip mismatches), write to `mapping.json`, return updated mapping validation response (depends on T014, T038)
- [X] T040 [US5] Add `save_template`, `list_templates`, `apply_template` methods to `planalign_api/services/import_service.py` (depends on T010)
- [X] T041 [P] [US5] Add "Load Template" dropdown to `planalign_studio/components/imports/FieldMappingStep.tsx`: appears above mapping table; selecting a template calls `applyTemplate` and refreshes the mapping table (depends on T016)
- [X] T042 [US5] Add "Save as Template" button to `planalign_studio/components/imports/FieldMappingStep.tsx`: opens name+description modal, calls `saveTemplate` on confirm (depends on T016, T041)
- [X] T043 [US5] Add `listTemplates`, `saveTemplate`, `applyTemplate` calls to `planalign_studio/services/importService.ts` (depends on T017)

**Checkpoint**: Save mapping as template → upload new file with same headers → load template → verify all mappings populate; unmatched columns are unmapped, not errored

---

## Phase 8: Polish & Cross-Cutting Concerns

**Purpose**: Navigation wiring, audit logging (FR-014), session cleanup, and end-to-end validation.

- [X] T044 [P] Add "Import Data" navigation entry to `planalign_studio/App.tsx` (sidebar link that renders `DataImportWizard`)
- [X] T045 [P] Verify and complete audit log coverage in `planalign_api/services/import_service.py` (FR-014): confirm all 5 auditable events write to `data/imports/audit.log` — (1) session create, (2) mapping save, (3) generation success, (4) generation failure (include `error_message` in log entry), (5) file delete; add any missing calls that T051/T010 did not cover
- [X] T046 Add unsaved-mapping confirmation dialog to `planalign_studio/components/DataImportWizard.tsx` — prompt before navigating away when mapping is dirty (edge case from spec)
- [X] T047 [P] Add session temp file cleanup to `planalign_api/services/import_service.py`: after status reaches `completed` or `cancelled`, delete `imports/{import_id}/source.parquet` to reclaim disk space (retain `mapping.json` and `metadata.json` for audit)
- [X] T048 [P] Add error boundary component wrapping `DataImportWizard.tsx` to surface backend errors as user-friendly messages rather than blank screens
- [X] T049 Run full integration test suite and validate end-to-end wizard manually: `pytest tests/integration/test_data_import.py -v` then `planalign studio` → complete one full import flow
- [X] T057 [P] Performance benchmark (SC-001): time the full upload → map → generate cycle against `tests/fixtures/sample_census_import.csv` (200 rows) and a generated 100K-row CSV; assert total elapsed < 5 minutes for 100K rows; document actual elapsed time in a comment in `tests/integration/test_data_import.py`

---

## Dependencies & Execution Order

### Phase Dependencies

```
Phase 1 (Setup)      → no deps, start immediately
Phase 2 (Foundation) → depends on Phase 1 complete; BLOCKS all user stories
Phase 3 (US1, P1)   → depends on Phase 2; blocks nothing (US2 can run in parallel)
Phase 4 (US2, P1)   → depends on Phase 2; can parallel with US1 (different files)
Phase 5 (US3, P2)   → depends on Phase 2 + US2 (needs ParquetFile entity working)
Phase 6 (US4, P2)   → depends on Phase 2 + US1 (needs mapping saved) + US2 (PreviewStep)
Phase 7 (US5, P3)   → depends on Phase 2 + US1 (needs mapping workflow)
Phase 8 (Polish)     → depends on all user stories desired for current scope
```

### Critical Path (MVP — US1 + US2 only)

```
T001–T005, T050 (parallel) → T006 → T007+T008 (parallel) → T051 → T009+T010 (parallel)
→ T011+T012+T015 (parallel) → T013, T014, T016, T055, T056 → T017 → T018
→ T019+T022 (parallel) → T020+T021 → T023 → T024
→ T044, T045, T049
```

### User Story Dependencies

| Story | Depends On | Can Parallel With |
|-------|-----------|------------------|
| US1 (P1) | Phase 2 | US2 |
| US2 (P1) | Phase 2 | US1 |
| US3 (P2) | Phase 2 + US2 (ParquetFile storage) | US4, US5 |
| US4 (P2) | Phase 2 + US1 (mapping) + US2 (PreviewStep) | US3, US5 |
| US5 (P3) | Phase 2 + US1 (mapping workflow) | US3, US4 |

### Within Each Story

1. Write tests first (marked — must FAIL before implementation)
2. Backend models → services → endpoints
3. Frontend service client → components → wizard wiring
4. Integration before polish

---

## Parallel Execution Examples

### Phase 2 Parallel Launch

```
Parallel: T007 (test_mapping_engine.py) + T008 (test_import_service.py)
Then sequential: T009 (mapping_engine.py) + T010 (import_service.py) can parallel
```

### US1 + US2 Parallel (Two developers)

```
Dev A: T011 → T012 → T013 → T014 → T017 → T018   (backend upload+mapping + wizard)
Dev B: T015 → T016                                  (frontend components)
After US1 backend complete:
Dev A: T019 → T020 → T021                          (generate endpoint)
Dev B: T022 → T023 → T024                          (generate UI)
```

### Phase 8 Parallel

```
Parallel: T044 (nav wiring) + T045 (audit logging) + T047 (cleanup) + T048 (error boundary)
Then: T046 (dirty-state guard) → T049 (full validation)
```

---

## Implementation Strategy

### MVP Scope (US1 + US2 — deliver end-to-end value)

1. Phase 1: Setup (30 min)
2. Phase 2: Foundation — models + tests + services (2–3 hrs)
3. Phase 3: US1 — upload + mapping (3–4 hrs)
4. Phase 4: US2 — parquet generation (2–3 hrs)
5. **STOP and validate**: Run `pytest tests/integration/test_data_import.py` + manual wizard walkthrough
6. Demo: analyst can upload CSV → map → generate → see parquet file

### Incremental Delivery

| Increment | Adds | Value Delivered |
|-----------|------|----------------|
| MVP (US1+US2) | Upload, map, generate | Analysts can convert any CSV/XLSX to Parquet |
| +US3 | File list, download, delete | Workspace data library browsable |
| +US4 | Preview before generate | Reduces failed generation attempts |
| +US5 | Reusable templates | Speeds up repeat imports |

---

## Notes

- `[P]` = safe to run in parallel (different files, no shared write targets)
- Constitution III: tests T007, T008, T011, T019, T052, T053, T054 MUST FAIL before implementing their respective services/endpoints
- Constitution IV: audit log (T051) is in Phase 2 — MVP cannot ship without it
- Constitution IV: all error responses include `correlation_id` — enforced in `ImportErrorResponse` model (T006)
- DuckDB connection for parquet write: always `duckdb.connect(':memory:')` — never reuse the simulation DB
- MappingEngine must never use Python `eval()`/`exec()` — only `pd.DataFrame.eval()` with expression whitelist rejecting `__`, `import`, `exec`, `eval`, `open`, `os.`
- Total tasks: **57** (T001–T057, with T051–T057 added post-analysis)
- Total per story: Setup 6 (incl. T050) · Foundation 6 (incl. T051) · US1 10 (incl. T055–T056) · US2 6 · US3 7 (incl. T052) · US4 7 (incl. T053) · US5 8 (incl. T054) · Polish 7 (incl. T057)
