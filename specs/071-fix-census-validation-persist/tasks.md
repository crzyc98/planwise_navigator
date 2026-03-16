# Tasks: Fix Census Validation Warning Persistence on Re-Upload

**Input**: Design documents from `/specs/071-fix-census-validation-persist/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, quickstart.md

**Tests**: No test tasks included — no frontend test framework is configured. Manual testing per quickstart.md.

**Organization**: Tasks are grouped by user story. This is a small bug fix (1 file, ~4 lines), so phases are lightweight.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup

**Purpose**: No setup needed — this is a single-file fix in an existing component.

*No tasks in this phase.*

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: No foundational work needed — the component and all infrastructure already exist.

*No tasks in this phase.*

---

## Phase 3: User Story 1 & 2 — Reset File Input on Upload Complete (Priority: P1) :dart: MVP

**Goal**: After each census file upload (success or failure), reset the file input element's value so that re-selecting the same filename triggers the `onChange` event and runs fresh validation.

**Independent Test**: Upload a census CSV with a warning, fix the CSV, re-upload the same filename. Warnings must refresh to reflect the corrected file.

### Implementation

- [x] T001 [US1] Add file input value reset after successful upload in `planalign_studio/components/config/DataSourcesSection.tsx` — insert `if (fileInputRef.current) fileInputRef.current.value = '';` after line 121 (inside the `try` block, after `setUploadMessage(...)`)
- [x] T002 [US1] Add file input value reset after failed upload in `planalign_studio/components/config/DataSourcesSection.tsx` — insert `if (fileInputRef.current) fileInputRef.current.value = '';` after line 126 (inside the `catch` block, after `setDataQualityWarnings([])`)

**Checkpoint**: Re-selecting the same filename now triggers `onChange`. Warnings from the first upload are replaced by warnings from the second upload (or cleared if the corrected file has no issues).

---

## Phase 4: User Story 3 — Warnings Clear Immediately on Upload Start (Priority: P2)

**Goal**: Ensure previous warnings disappear as soon as the user initiates a new upload, before the response arrives.

**Independent Test**: Upload a file with warnings, then start uploading a second file. During upload (before response), the warning area should be empty.

### Implementation

*No additional code changes needed.* Lines 77-79 of `DataSourcesSection.tsx` already clear `structuredWarnings`, `dataQualityWarnings`, and `expandedFields` at the start of the `onChange` handler. With T001/T002 ensuring `onChange` fires on re-selection, this behavior is now reachable for same-filename re-uploads.

**Checkpoint**: Warnings visually clear as soon as a new file is selected, before the upload response arrives.

---

## Phase 5: Polish & Cross-Cutting Concerns

- [x] T003 Manual verification using quickstart.md test scenarios in `specs/071-fix-census-validation-persist/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 3 (US1/US2)**: No dependencies — can start immediately
- **Phase 4 (US3)**: Automatically satisfied by Phase 3 (no additional code)
- **Phase 5 (Polish)**: Depends on Phase 3 completion

### User Story Dependencies

- **US1 (P1) & US2 (P1)**: Independent — both fixed by the same file input reset
- **US3 (P2)**: No additional code — existing clear-on-start logic becomes reachable after US1/US2 fix

### Within Phase 3

- T001 and T002 modify the same file but different code sections (try vs. catch block). They can be applied sequentially in a single edit.

---

## Parallel Example: Phase 3

```text
# T001 and T002 are in the same file — apply sequentially in one edit:
Task T001: Reset fileInputRef after success path (line ~121)
Task T002: Reset fileInputRef after error path (line ~126)
```

---

## Implementation Strategy

### MVP (All User Stories in One Edit)

1. Apply T001 + T002 in a single edit to `DataSourcesSection.tsx`
2. Run manual verification (T003) per quickstart.md
3. Commit and create PR

This is a minimal bug fix — all three user stories are resolved by adding 2 lines of code in 1 file. No incremental delivery needed; the fix is atomic.

---

## Notes

- Total tasks: 3 (2 implementation + 1 verification)
- All 3 user stories resolved by the same 2-line fix
- No backend changes required
- No new files created
- No test framework tasks (manual testing only)
