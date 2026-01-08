# Tasks: Compare Variance Alignment & Copy Button

**Input**: Design documents from `/specs/015-compare-variance-copy/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md

**Tests**: No automated tests requested. Manual visual testing and browser testing only.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Frontend**: `planalign_studio/components/`, `planalign_studio/hooks/`
- Main file: `planalign_studio/components/ScenarioCostComparison.tsx`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create reusable hook and utility functions needed by multiple user stories

- [x] T001 Create hooks directory if not exists at planalign_studio/hooks/
- [x] T002 Create useCopyToClipboard hook in planalign_studio/hooks/useCopyToClipboard.ts
- [x] T003 Create tableToTSV utility function in planalign_studio/components/ScenarioCostComparison.tsx
- [x] T004 Import Copy and Check icons from lucide-react in planalign_studio/components/ScenarioCostComparison.tsx

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: No foundational blocking tasks - all setup tasks in Phase 1 are sufficient

**Checkpoint**: Setup complete - user story implementation can begin

---

## Phase 3: User Story 1 - Copy Table Data to Excel (Priority: P1) 🎯 MVP

**Goal**: Enable users to copy individual metric tables to clipboard in TSV format for Excel

**Independent Test**: Click copy button on any metric table → paste into Excel → data appears correctly formatted with headers and all rows

### Implementation for User Story 1

- [x] T005 [US1] Add copy button state (copied, error) to MetricTable component in planalign_studio/components/ScenarioCostComparison.tsx
- [x] T006 [US1] Add copy button (lucide Copy icon) to MetricTable header next to title in planalign_studio/components/ScenarioCostComparison.tsx
- [x] T007 [US1] Implement copy click handler using useCopyToClipboard hook and tableToTSV in planalign_studio/components/ScenarioCostComparison.tsx
- [x] T008 [US1] Add visual feedback: icon changes to Check (green) for 2 seconds after successful copy in planalign_studio/components/ScenarioCostComparison.tsx
- [x] T009 [US1] Add disabled state for copy button when years.length === 0 in planalign_studio/components/ScenarioCostComparison.tsx
- [x] T010 [US1] Add error handling: display error message if clipboard access fails in planalign_studio/components/ScenarioCostComparison.tsx

**Checkpoint**: Users can copy any single metric table and paste into Excel with correct formatting

---

## Phase 4: User Story 2 - Variance Row Alignment Fix (Priority: P1)

**Goal**: Fix the misaligned variance row so values align with year columns

**Independent Test**: View any metric table → variance row values should be vertically aligned with Baseline and Comparison values for each year

### Implementation for User Story 2

- [x] T011 [US2] Modify VarianceDisplay component: add justify-end to flex container class in planalign_studio/components/ScenarioCostComparison.tsx (line ~121)
- [x] T012 [US2] Verify variance row td cells maintain text-right alignment in planalign_studio/components/ScenarioCostComparison.tsx

**Checkpoint**: Variance row values align vertically with other rows' year columns

---

## Phase 5: User Story 3 - Copy All Tables at Once (Priority: P3)

**Goal**: Enable users to copy all 6 metric tables at once with section headers

**Independent Test**: Click "Copy All Tables" button → paste into Excel → all 6 tables appear with metric titles as section headers

### Implementation for User Story 3

- [x] T013 [US3] Create allTablesToTSV utility function in planalign_studio/components/ScenarioCostComparison.tsx
- [x] T014 [US3] Add "Copy All Tables" button to Year-by-Year Breakdown section header in planalign_studio/components/ScenarioCostComparison.tsx
- [x] T015 [US3] Implement copy all click handler using useCopyToClipboard hook and allTablesToTSV in planalign_studio/components/ScenarioCostComparison.tsx
- [x] T016 [US3] Add visual feedback for Copy All button (icon change to Check for 2 seconds) in planalign_studio/components/ScenarioCostComparison.tsx

**Checkpoint**: Users can copy all 6 metric tables in one action with clear section separators

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final cleanup and validation

- [x] T017 Run TypeScript build to verify no type errors: npm run build in planalign_studio/
- [x] T018 Run linter to verify code style: npm run lint in planalign_studio/ (N/A - no lint script configured)
- [ ] T019 Manual browser testing: verify copy works in Chrome, Firefox, Safari, Edge
- [ ] T020 Manual visual testing: verify variance alignment across all 6 metric tables

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **User Story 1 (Phase 3)**: Depends on Setup (T001-T004)
- **User Story 2 (Phase 4)**: No dependencies on other stories - can run in parallel with US1
- **User Story 3 (Phase 5)**: Depends on US1 completion (reuses tableToTSV and hook)
- **Polish (Phase 6)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Depends only on Setup phase
- **User Story 2 (P1)**: Independent - can start after Setup, no dependencies on US1
- **User Story 3 (P3)**: Depends on US1 (reuses copy infrastructure)

### Within Each User Story

- All tasks within a story must be completed sequentially (they modify the same file)
- No parallel opportunities within stories (all tasks touch ScenarioCostComparison.tsx)

### Parallel Opportunities

- **US1 and US2 can run in parallel** after Setup - they modify different sections of the component
- Setup tasks T002, T003, T004 can technically run in parallel (different concerns) but touch the same file, so sequential is safer

---

## Parallel Example: User Stories 1 & 2

```bash
# After Setup complete, these can run in parallel:

# Developer A: User Story 1 (Copy functionality)
Task: "T005-T010 Copy button implementation"

# Developer B: User Story 2 (Alignment fix)
Task: "T011-T012 Variance alignment fix"
```

---

## Implementation Strategy

### MVP First (User Stories 1 & 2)

1. Complete Phase 1: Setup (T001-T004)
2. Complete Phase 3: User Story 1 - Copy Table (T005-T010)
3. Complete Phase 4: User Story 2 - Variance Alignment (T011-T012)
4. **STOP and VALIDATE**: Test both stories independently
5. Deploy/demo if ready - core user needs are met

### Incremental Delivery

1. Complete Setup → Foundation ready
2. Add User Story 1 (Copy) → Test independently → Core functionality available
3. Add User Story 2 (Alignment) → Test independently → Visual fix deployed
4. Add User Story 3 (Copy All) → Test independently → Enhanced export available
5. Each story adds value without breaking previous stories

### Single Developer Strategy

Recommended order for a single developer:

1. T001-T004: Setup (create hook, utilities, imports)
2. T011-T012: User Story 2 (alignment fix - quick win, 2 tasks)
3. T005-T010: User Story 1 (copy button - 6 tasks)
4. T013-T016: User Story 3 (copy all - 4 tasks, if time permits)
5. T017-T020: Polish (validation)

---

## Notes

- All implementation tasks modify the same file (ScenarioCostComparison.tsx)
- The hook (useCopyToClipboard.ts) is the only separate file
- US2 (alignment) is a 2-line CSS change - consider doing first for quick win
- US3 (copy all) is optional/enhancement - can be deferred if needed
- Verify tests fail before implementing (visual check that variance is misaligned)
- Commit after each user story completion
