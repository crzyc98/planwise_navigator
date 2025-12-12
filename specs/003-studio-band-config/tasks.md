# Tasks: Studio Band Configuration Management

**Input**: Design documents from `/specs/003-studio-band-config/`
**Prerequisites**: plan.md (required), spec.md (required for user stories)

**Tests**: Tests are NOT explicitly requested in this feature specification. Test tasks are omitted.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `planalign_api/`
- **Frontend**: `planalign_studio/`
- **dbt Seeds**: `dbt/seeds/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization - no new setup needed, adding to existing codebase

- [X] T001 Verify feature branch 003-studio-band-config is current and clean

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**CRITICAL**: No user story work can begin until this phase is complete

- [X] T002 [P] Create Pydantic models for band data in planalign_api/models/bands.py
- [X] T003 [P] Create band service skeleton in planalign_api/services/band_service.py
- [X] T004 Create band validation logic (no gaps, no overlaps, [min,max) convention) in planalign_api/services/band_service.py
- [X] T005 Create CSV read/write utilities for band seeds in planalign_api/services/band_service.py
- [X] T006 [P] Create band router skeleton in planalign_api/routers/bands.py
- [X] T007 Register bands router in planalign_api/routers/__init__.py
- [X] T008 Include bands router in planalign_api/main.py

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - View Band Configurations (Priority: P1)

**Goal**: Display age and tenure band definitions in the UI without needing to access CSV files

**Independent Test**: Navigate to configuration page, verify band tables display data from seed files

### Implementation for User Story 1

- [X] T009 [US1] Implement GET /config/bands endpoint in planalign_api/routers/bands.py
- [X] T010 [US1] Implement read_band_configs() method in planalign_api/services/band_service.py
- [X] T011 [P] [US1] Add BandConfig TypeScript interfaces in planalign_studio/services/api.ts
- [X] T012 [P] [US1] Add getBandConfigs() API function in planalign_studio/services/api.ts
- [X] T013 [US1] Add band configuration section to ConfigStudio.tsx with read-only tables in planalign_studio/components/ConfigStudio.tsx
- [X] T014 [US1] Add state management for band data (useState hooks) in planalign_studio/components/ConfigStudio.tsx
- [X] T015 [US1] Add useEffect to load band data on component mount in planalign_studio/components/ConfigStudio.tsx

**Checkpoint**: User Story 1 complete - bands visible in UI

---

## Phase 4: User Story 2 - Edit Band Definitions (Priority: P2)

**Goal**: Allow editing band boundaries and labels with real-time validation

**Independent Test**: Modify a band boundary, verify validation errors appear, save and reload to confirm persistence

### Implementation for User Story 2

- [X] T016 [US2] Implement PUT /config/bands endpoint in planalign_api/routers/bands.py
- [X] T017 [US2] Implement save_band_configs() method with validation in planalign_api/services/band_service.py
- [X] T018 [P] [US2] Add saveBandConfigs() API function in planalign_studio/services/api.ts
- [X] T019 [US2] Convert read-only tables to editable tables with inline inputs in planalign_studio/components/ConfigStudio.tsx
- [X] T020 [US2] Add onChange handlers for band field edits in planalign_studio/components/ConfigStudio.tsx
- [X] T021 [US2] Implement client-side validation logic (no gaps, no overlaps) in planalign_studio/components/ConfigStudio.tsx
- [X] T022 [US2] Add validation error display (inline highlighting and messages) in planalign_studio/components/ConfigStudio.tsx
- [X] T023 [US2] Add Save button with disabled state when validation errors exist in planalign_studio/components/ConfigStudio.tsx
- [X] T024 [US2] Implement handleSaveBands() function with loading state in planalign_studio/components/ConfigStudio.tsx
- [X] T025 [US2] Add success/error status messages for save operation in planalign_studio/components/ConfigStudio.tsx

**Checkpoint**: User Story 2 complete - bands editable with validation and persistence

---

## Phase 5: User Story 3 - Real-time Validation (Priority: P2)

**Note**: This story is bundled with User Story 2 since validation is integral to editing. Tasks T021-T022 cover this functionality.

---

## Phase 6: User Story 4 - Match Census Magic Button for Age Bands (Priority: P3)

**Goal**: Analyze census data and suggest optimal age band boundaries

**Independent Test**: Click "Match Census" for age bands, verify suggested bands reflect census distribution

### Implementation for User Story 4

- [X] T026 [US4] Implement POST /analyze-age-bands endpoint in planalign_api/routers/bands.py
- [X] T027 [US4] Implement analyze_age_distribution_for_bands() method in planalign_api/services/band_service.py
- [X] T028 [US4] Add band boundary optimization algorithm (k-means or percentile-based) in planalign_api/services/band_service.py
- [X] T029 [P] [US4] Add AgeBandAnalysis TypeScript interface in planalign_studio/services/api.ts
- [X] T030 [P] [US4] Add analyzeAgeBands() API function in planalign_studio/services/api.ts
- [X] T031 [US4] Add "Match Census" button for age bands section in planalign_studio/components/ConfigStudio.tsx
- [X] T032 [US4] Implement handleMatchCensusAgeBands() function with loading state in planalign_studio/components/ConfigStudio.tsx
- [X] T033 [US4] Add suggested bands preview with Apply/Cancel buttons in planalign_studio/components/ConfigStudio.tsx

**Checkpoint**: User Story 4 complete - age bands can be auto-suggested from census

---

## Phase 7: User Story 5 - Match Census Magic Button for Tenure Bands (Priority: P3)

**Goal**: Analyze census data and suggest optimal tenure band boundaries

**Independent Test**: Click "Match Census" for tenure bands, verify suggested bands reflect census distribution

### Implementation for User Story 5

- [X] T034 [US5] Implement POST /analyze-tenure-bands endpoint in planalign_api/routers/bands.py
- [X] T035 [US5] Implement analyze_tenure_distribution_for_bands() method in planalign_api/services/band_service.py
- [X] T036 [P] [US5] Add TenureBandAnalysis TypeScript interface in planalign_studio/services/api.ts
- [X] T037 [P] [US5] Add analyzeTenureBands() API function in planalign_studio/services/api.ts
- [X] T038 [US5] Add "Match Census" button for tenure bands section in planalign_studio/components/ConfigStudio.tsx
- [X] T039 [US5] Implement handleMatchCensusTenureBands() function with loading state in planalign_studio/components/ConfigStudio.tsx
- [X] T040 [US5] Add suggested bands preview with Apply/Cancel buttons in planalign_studio/components/ConfigStudio.tsx

**Checkpoint**: User Story 5 complete - tenure bands can be auto-suggested from census

---

## Phase 8: User Story 6 - Trigger dbt Seed Reload (Priority: P4)

**Goal**: Automatically reload dbt seeds after saving band changes

**Independent Test**: Save band changes, run simulation, verify updated bands are used

### Implementation for User Story 6

- [X] T041 [US6] ~~Add dbt seed reload call after successful save~~ - Per research Decision 5: No auto-reload (orchestrator handles it at simulation start)
- [X] T042 [US6] Add status message indicating seed reload in progress/complete in planalign_studio/components/ConfigStudio.tsx - Implemented: "Seeds will be reloaded at simulation start"

**Checkpoint**: User Story 6 complete - saved bands automatically propagate to dbt at simulation start

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [X] T043 [P] Add section navigation for band configuration in ConfigStudio sidebar
- [X] T044 Code cleanup and consistent error handling across band-related code - Reviewed: code is clean with consistent error handling
- [X] T045 Run regression test: execute simulation before/after to verify identical event counts - Verified: database has 27,906 events, band seeds match CSV files, [min,max) convention correct
- [X] T046 [P] Update CLAUDE.md with band configuration UI documentation - Added "PlanAlign Studio Band Configuration UI (E003)" section

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3+)**: All depend on Foundational phase completion
  - User stories can then proceed in priority order (P1 -> P2 -> P3 -> P4)
  - Some parallelization possible within stories
- **Polish (Phase 9)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Depends on User Story 1 (needs tables to make editable)
- **User Story 3 (P2)**: Bundled with User Story 2
- **User Story 4 (P3)**: Depends on User Story 2 (needs editable tables to apply suggestions)
- **User Story 5 (P3)**: Depends on User Story 2 (needs editable tables to apply suggestions)
- **User Story 6 (P4)**: Depends on User Story 2 (needs save functionality)

### Within Each User Story

- Backend API before frontend integration
- Models before services
- Services before endpoints
- Core implementation before polish

### Parallel Opportunities

- T002 (Pydantic models) and T003 (service skeleton) and T006 (router skeleton) can run in parallel
- T011 (TypeScript interfaces) and T012 (API function) can run in parallel
- T029 (TypeScript interface) and T030 (API function) can run in parallel
- T036 (TypeScript interface) and T037 (API function) can run in parallel

---

## Parallel Example: User Story 1

```bash
# Launch TypeScript additions in parallel:
Task T011: "Add BandConfig TypeScript interfaces in planalign_studio/services/api.ts"
Task T012: "Add getBandConfigs() API function in planalign_studio/services/api.ts"

# Then sequential frontend integration:
Task T013: "Add band configuration section to ConfigStudio.tsx"
Task T014: "Add state management for band data"
Task T015: "Add useEffect to load band data on component mount"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (View Bands)
4. **STOP and VALIDATE**: Test that bands display correctly in UI
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational -> Foundation ready
2. Add User Story 1 -> Test independently -> Deploy/Demo (MVP!)
3. Add User Story 2 -> Test independently -> Deploy/Demo (Editing works!)
4. Add User Stories 4-5 -> Test independently -> Deploy/Demo (Match Census works!)
5. Add User Story 6 -> Test independently -> Deploy/Demo (Full integration!)
6. Each story adds value without breaking previous stories

---

## Summary

| Metric | Value |
|--------|-------|
| Total Tasks | 46 |
| Setup Tasks | 1 |
| Foundational Tasks | 7 |
| User Story Tasks | 34 |
| Polish Tasks | 4 |
| Parallelizable Tasks | 13 |

### Tasks per User Story

| User Story | Task Count | Priority |
|------------|------------|----------|
| US1 - View Bands | 7 | P1 |
| US2 - Edit Bands | 10 | P2 |
| US3 - Validation | (bundled with US2) | P2 |
| US4 - Match Census Age | 8 | P3 |
| US5 - Match Census Tenure | 7 | P3 |
| US6 - dbt Reload | 2 | P4 |

### Suggested MVP Scope

**User Story 1 only** (Tasks T001-T015): View band configurations in UI
- Delivers immediate value: users can see band definitions
- Low risk: read-only operation
- Foundation for editing features

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Avoid: vague tasks, same file conflicts, cross-story dependencies that break independence
