# Tasks: Expand Scenario Comparison Limit

**Input**: Design documents from `/specs/019-expand-scenario-comparison/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: No automated tests requested. Manual testing per acceptance scenarios.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Frontend**: `planalign_studio/` at repository root
- Primary files: `planalign_studio/constants.ts`, `planalign_studio/components/ScenarioCostComparison.tsx`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Add shared constants and configuration used by all user stories

- [x] T001 [P] Add MAX_SCENARIO_SELECTION constant (value: 6) in planalign_studio/constants.ts
- [x] T002 [P] Extend COLORS.charts array from 5 to 6 colors (add '#E91E63') in planalign_studio/constants.ts

**Checkpoint**: Constants ready - user story implementation can now begin

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Import constant into component - required before any selection logic changes

- [x] T003 Import MAX_SCENARIO_SELECTION from constants in planalign_studio/components/ScenarioCostComparison.tsx

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Compare Six Scenarios Side-by-Side (Priority: P1) 🎯 MVP

**Goal**: Enable users to select up to 6 scenarios for comparison, with disabled checkboxes when limit is reached

**Independent Test**: Select 6 different completed scenarios and verify all 6 appear in the comparison charts and table

### Implementation for User Story 1

- [x] T004 [US1] Update toggleSelection callback to use MAX_SCENARIO_SELECTION constant instead of hardcoded 5 in planalign_studio/components/ScenarioCostComparison.tsx (line ~370)
- [x] T005 [US1] Add isAtLimit computed variable (selectedScenarioIds.length >= MAX_SCENARIO_SELECTION) in planalign_studio/components/ScenarioCostComparison.tsx
- [x] T006 [US1] Add disabled prop to scenario checkbox buttons when isAtLimit && not already selected in planalign_studio/components/ScenarioCostComparison.tsx
- [x] T007 [US1] Add title attribute with tooltip message "Maximum of 6 scenarios selected" to disabled checkboxes in planalign_studio/components/ScenarioCostComparison.tsx
- [x] T008 [US1] Add visual disabled styling (opacity-50 cursor-not-allowed) to disabled checkboxes in planalign_studio/components/ScenarioCostComparison.tsx

**Checkpoint**: User Story 1 complete - users can select 6 scenarios with proper limit enforcement

---

## Phase 4: User Story 2 - Visual Clarity with Six Scenarios (Priority: P2)

**Goal**: Ensure all 6 scenarios are visually distinguishable in charts and tables

**Independent Test**: Select 6 scenarios with varying cost values and verify chart legends, bars/lines, and table columns are all distinguishable

### Implementation for User Story 2

- [x] T009 [US2] Verify chart color assignment uses extended COLORS.charts array (idx % COLORS.charts.length pattern) in planalign_studio/components/ScenarioCostComparison.tsx

**Checkpoint**: User Story 2 complete - all 6 scenarios have distinct colors in charts

---

## Phase 5: User Story 3 - Copy Full Comparison Data (Priority: P3)

**Goal**: Ensure copy-to-clipboard includes data for all 6 scenarios

**Independent Test**: Select 6 scenarios, click copy button, paste into spreadsheet and verify all 6 scenarios' data is present

### Implementation for User Story 3

- [x] T010 [US3] Verify tableToTSV function handles all selectedScenarioIds (no hardcoded limit) in planalign_studio/components/ScenarioCostComparison.tsx

**Checkpoint**: User Story 3 complete - clipboard export works with 6 scenarios

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and cleanup

- [ ] T011 Manual test: Select 6 scenarios, verify all appear in charts and table
- [ ] T012 Manual test: With 6 selected, verify unchecked checkboxes are disabled with tooltip
- [ ] T013 Manual test: Copy data with 6 scenarios, paste to Excel, verify all 6 present
- [ ] T014 Manual test: Deselect one scenario, verify checkboxes re-enable

> **Note**: Manual tests T011-T014 require running the application and testing in browser. Run `cd planalign_studio && npm run dev` to start the dev server.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion
- **User Story 1 (Phase 3)**: Depends on Foundational
- **User Story 2 (Phase 4)**: Depends on Setup (color palette) - can run parallel with US1
- **User Story 3 (Phase 5)**: Depends on Setup - can run parallel with US1/US2
- **Polish (Phase 6)**: Depends on all user stories

### User Story Dependencies

- **User Story 1 (P1)**: Requires T001 (constant), T003 (import) - Core functionality
- **User Story 2 (P2)**: Requires T002 (colors) - Independent of US1
- **User Story 3 (P3)**: No code changes expected - verification only

### Parallel Opportunities

- T001 and T002 can run in parallel (different parts of same file, non-conflicting)
- After foundational phase, US2 and US3 verification can run parallel with US1 implementation
- All manual tests (T011-T014) must run sequentially after implementation

---

## Parallel Example: Setup Phase

```bash
# Launch all setup tasks together:
Task: "Add MAX_SCENARIO_SELECTION constant in planalign_studio/constants.ts"
Task: "Extend COLORS.charts array in planalign_studio/constants.ts"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001, T002)
2. Complete Phase 2: Foundational (T003)
3. Complete Phase 3: User Story 1 (T004-T008)
4. **STOP and VALIDATE**: Test 6-scenario selection works
5. Proceed to US2/US3 if needed

### Quick Path (All Stories)

This is a small feature - all phases can be completed sequentially:

1. Setup: Add constant and extend colors (~5 min)
2. Foundational: Add import (~2 min)
3. US1: Update selection logic and add disabled state (~15 min)
4. US2: Verify colors work (no changes expected) (~2 min)
5. US3: Verify copy works (no changes expected) (~2 min)
6. Polish: Run manual tests (~10 min)

**Total estimated time: ~35 minutes**

---

## Notes

- This is a small, focused feature with minimal code changes
- Most work is in User Story 1 (selection limit and disabled state)
- User Stories 2 and 3 are verification tasks - existing code should already support 6 scenarios
- No automated tests are set up in the frontend; manual testing is specified
- Commit after each phase for easy rollback if needed
