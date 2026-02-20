# Tasks: Census Field Validation Warnings

**Input**: Design documents from `/specs/055-census-field-warnings/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-contracts.md

**Tests**: Included per Constitution Principle III (Test-First Development). Tests are written before implementation within each user story phase.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Foundational (Blocking Prerequisites)

**Purpose**: Shared models and types that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T001 Add `StructuredWarning` Pydantic model with fields (`field_name`, `severity`, `warning_type`, `impact_description`, `detected_alias`, `suggested_action`) and add `structured_warnings: List[StructuredWarning]` field to `FileUploadResponse`, add `validation_warnings: List[str]` and `structured_warnings: List[StructuredWarning]` fields to `FileValidationResponse` in `planalign_api/models/files.py`
- [x] T002 [P] Add `StructuredWarning` TypeScript interface and add `structured_warnings: StructuredWarning[]` to `FileUploadResponse`, add `validation_warnings: string[]` and `structured_warnings: StructuredWarning[]` to `FileValidationResponse` in `planalign_studio/services/api.ts`

**Checkpoint**: Models and types ready — user story implementation can now begin

---

## Phase 2: User Story 1 — Critical Field Missing Warning (Priority: P1) — MVP

**Goal**: When an analyst uploads a census file missing critical fields (hire date, compensation, birth date), a prominent amber warning panel appears listing each missing field with a human-readable explanation of what simulation features are affected.

**Independent Test**: Upload a CSV with only `employee_id` → verify amber warning panel lists `employee_hire_date`, `employee_gross_compensation`, `employee_birth_date` as missing, each with impact descriptions. Upload a CSV with all fields → verify no warnings appear.

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation (T004)**

- [x] T003 [US1] Create test file and write tests for critical field structured warning generation: test missing single critical field returns structured warning with `severity="critical"` and correct `impact_description`; test missing multiple critical fields returns one warning per field; test all critical fields present returns no critical warnings; test `validation_warnings` flat strings are still populated for backward compatibility. Create `tests/api/test_file_validation.py`

### Implementation for User Story 1

- [x] T004 [US1] Add `CRITICAL_COLUMNS` list (`employee_hire_date`, `employee_gross_compensation`, `employee_birth_date`) and `FIELD_IMPACT_DESCRIPTIONS` dict mapping each critical column to its severity tier and impact text. Enhance `_parse_and_validate_file()` to build `structured_warnings` list alongside existing flat `validation_warnings` strings. Return `structured_warnings` in the metadata dict in `planalign_api/services/file_service.py`
- [x] T005 [US1] Update `upload_census_file()` handler to read `structured_warnings` from service metadata and include in `FileUploadResponse` in `planalign_api/routers/files.py`
- [x] T006 [US1] Remove the static "Required Census Columns" info box (the `bg-blue-50` div with hardcoded column list). Add a warning results section below the upload area that renders critical warnings as an amber/orange panel (`bg-amber-50 border-amber-200`) listing each missing field name and its `impact_description`. Preserve upload success info (row count, column count) above warnings. Clear warnings state on new upload in `planalign_studio/components/config/DataSourcesSection.tsx`

**Checkpoint**: User Story 1 fully functional — critical field warnings display after upload with impact descriptions

---

## Phase 3: User Story 2 — Optional Field Missing Info (Priority: P2)

**Goal**: When an analyst uploads a census file with all critical fields but missing optional fields (`employee_termination_date`, `active`), a blue informational notice appears explaining what defaults the simulation will use.

**Independent Test**: Upload a CSV with all critical fields but missing `employee_termination_date` and `active` → verify blue notice appears listing optional fields with default behavior descriptions. Upload with all fields → verify no notices.

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation (T008)**

- [x] T007 [US2] Add tests for optional field warning generation: test missing optional field returns structured warning with `severity="optional"` and correct impact/default text; test all optional fields present returns no optional warnings; test mixed (critical + optional missing) returns both tiers correctly. Append to `tests/api/test_file_validation.py`

### Implementation for User Story 2

- [x] T008 [US2] Add optional field entries (`employee_termination_date`, `active`) to `FIELD_IMPACT_DESCRIPTIONS` with severity `"optional"`, impact descriptions, and default behavior text. Update `_parse_and_validate_file()` to generate optional-tier structured warnings in `planalign_api/services/file_service.py`
- [x] T009 [US2] Add informational notice panel (blue background `bg-blue-50 border-blue-200`, visually distinct from amber critical panel) for optional field warnings. Display below critical warnings if both tiers present. Show default behavior text for each optional field in `planalign_studio/components/config/DataSourcesSection.tsx`

**Checkpoint**: User Stories 1 AND 2 both work — critical (amber) and optional (blue) warnings display correctly

---

## Phase 4: User Story 3 — Column Alias Detection (Priority: P3)

**Goal**: When an analyst uploads a census file with non-standard column names (e.g., `hire_date` instead of `employee_hire_date`), a notice appears suggesting the correct column name for compatibility.

**Independent Test**: Upload a CSV with `hire_date` column but no `employee_hire_date` → verify notice suggests renaming. Upload with `annual_salary` → verify suggestion to rename to `employee_gross_compensation`.

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation (T011)**

- [x] T010 [US3] Add tests for alias detection: test alias found generates structured warning with `warning_type="alias_found"` and `detected_alias` populated; test alias found AND target column also missing uses alias warning (not generic missing); test alias found when target column already present generates no warning. Append to `tests/api/test_file_validation.py`

### Implementation for User Story 3

- [x] T011 [US3] Enhance structured warning generation in `_parse_and_validate_file()` to produce `warning_type="alias_found"` warnings when a known alias from `COLUMN_ALIASES` is detected. Set `detected_alias` to the found alias name and `suggested_action` to rename instruction. Alias warnings should replace generic missing warnings for the same field in `planalign_api/services/file_service.py`
- [x] T012 [US3] Render alias suggestion notices in warning panel showing the detected alias name, the expected column name, and a rename recommendation. Use a distinct visual style (e.g., info icon with rename suggestion text) within the appropriate tier panel in `planalign_studio/components/config/DataSourcesSection.tsx`

**Checkpoint**: All three user stories work independently — critical warnings, optional notices, and alias suggestions

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Fix validate-path gap, edge cases, and final verification

- [x] T013 Update `validate_path()` method to include `validation_warnings` and `structured_warnings` from `_parse_and_validate_file()` metadata in its return dict, and update the `validate_file_path()` handler to pass both fields through to `FileValidationResponse` in `planalign_api/services/file_service.py` and `planalign_api/routers/files.py`
- [x] T014 [P] Update manual path validation flow in `DataSourcesSection.tsx` to read `structured_warnings` from validate-path response and display the same tiered warning panel as the upload flow in `planalign_studio/components/config/DataSourcesSection.tsx`
- [x] T015 [P] Add edge case tests: file with only `employee_id` shows all critical fields missing; `validation_warnings` flat strings remain populated when `structured_warnings` present; re-upload clears previous warnings; verify backward compat of `validation_warnings: List[str]` in `tests/api/test_file_validation.py`
- [x] T016 Run full test suite (`pytest tests/api/test_file_validation.py -v`) and verify all tests pass. Verify `validation_warnings` backward compatibility by checking flat string format unchanged

---

## Dependencies & Execution Order

### Phase Dependencies

- **Foundational (Phase 1)**: No dependencies — start immediately
- **User Story 1 (Phase 2)**: Depends on Phase 1 completion — BLOCKS frontend display
- **User Story 2 (Phase 3)**: Depends on Phase 2 (extends `FIELD_IMPACT_DESCRIPTIONS` and warning panel)
- **User Story 3 (Phase 4)**: Depends on Phase 2 (extends warning generation and panel rendering)
- **Polish (Phase 5)**: Depends on Phase 4 completion (all tiers implemented)

### User Story Dependencies

- **US1 (P1)**: Depends on Foundational only — delivers MVP
- **US2 (P2)**: Depends on US1 (extends the `FIELD_IMPACT_DESCRIPTIONS` dict and adds blue panel to the same component)
- **US3 (P3)**: Depends on US1 (extends `_parse_and_validate_file()` and renders in the same panel). Can run in parallel with US2 if modifying different sections.

### Within Each User Story

- Tests MUST be written and FAIL before implementation (Constitution Principle III)
- Backend service before backend router (router depends on service returning structured warnings)
- Backend complete before frontend (frontend needs API to return data)

### Parallel Opportunities

- T001 and T002 can run in parallel (different files: Python models vs TypeScript types)
- T013 and T014 and T015 can run in parallel (different files: backend, frontend, tests)
- Within each story: test writing can start immediately after Foundational phase

---

## Parallel Example: Phase 1 (Foundational)

```
# These two tasks touch different files and can run simultaneously:
Task T001: "Add StructuredWarning model in planalign_api/models/files.py"
Task T002: "Add StructuredWarning interface in planalign_studio/services/api.ts"
```

## Parallel Example: Phase 5 (Polish)

```
# These three tasks touch different files:
Task T013: "Fix validate-path in file_service.py + files.py router"
Task T014: "Update validate-path UI in DataSourcesSection.tsx"
Task T015: "Add edge case tests in test_file_validation.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Foundational (T001-T002)
2. Complete Phase 2: User Story 1 (T003-T006)
3. **STOP and VALIDATE**: Upload a CSV missing critical fields → verify amber warnings appear
4. Deploy/demo if ready — users get immediate value from critical field warnings

### Incremental Delivery

1. Phase 1 → Foundational models ready
2. Phase 2 (US1) → Critical warnings live → **MVP deployed**
3. Phase 3 (US2) → Optional notices added → Deploy
4. Phase 4 (US3) → Alias detection added → Deploy
5. Phase 5 → Validate-path fixed, edge cases covered → Feature complete

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps each task to a specific user story for traceability
- Constitution Principle III requires test-first: write tests, verify they fail, then implement
- Backward compatibility: `validation_warnings: List[str]` must remain populated with flat strings
- The static "Required Census Columns" info box is removed in T006, not moved — the dynamic warnings replace it entirely
- `FileValidationResponse` currently lacks `validation_warnings` — T001 adds it, T013 wires it through
