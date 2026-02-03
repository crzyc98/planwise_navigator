# Tasks: Vesting Hours Requirement Toggle

**Input**: Design documents from `/specs/030-vesting-hours-toggle/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: Manual browser testing only (per plan.md - no automated tests requested)

**Organization**: Tasks grouped by user story. All tasks modify single file: `planalign_studio/components/VestingAnalysis.tsx`

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different sections of the file)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- All tasks target: `planalign_studio/components/VestingAnalysis.tsx`

## Path Conventions

- **Project type**: Web application (frontend modification only)
- **Primary file**: `planalign_studio/components/VestingAnalysis.tsx`
- **Types file**: `planalign_studio/services/api.ts` (NO CHANGES - types already exist)

---

## Phase 1: Setup

**Purpose**: Verify development environment and understand existing code

- [x] T001 Start development server with `cd planalign_studio && npm run dev`
- [x] T002 Navigate to Vesting Analysis page and verify current functionality works
- [x] T003 Review existing `handleScheduleChange` function at line ~233 in `planalign_studio/components/VestingAnalysis.tsx`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add event handlers that all user stories depend on

**⚠️ CRITICAL**: US1-US4 implementation depends on these handlers being in place

- [x] T004 Add `handleHoursToggle` function to handle checkbox toggle in `planalign_studio/components/VestingAnalysis.tsx`
- [x] T005 Add `handleHoursThresholdChange` function to handle threshold input in `planalign_studio/components/VestingAnalysis.tsx`
- [x] T006 Update `handleScheduleChange` function to preserve hours settings when switching schedule types (FR-008) in `planalign_studio/components/VestingAnalysis.tsx`

**Checkpoint**: Event handlers ready - UI implementation can begin ✓

---

## Phase 3: User Story 1 - Configure Hours Requirement (Priority: P1) 🎯 MVP

**Goal**: Add toggle checkbox and threshold input below each schedule selector

**Independent Test**: Open Vesting Analysis page, verify toggle appears below each schedule selector, toggle on shows input with default 1000, toggle off hides input

**Requirements**: FR-001, FR-002, FR-003, FR-004

### Implementation for User Story 1

- [x] T007 [US1] Add hours requirement toggle checkbox below Current Schedule selector in `planalign_studio/components/VestingAnalysis.tsx`
- [x] T008 [US1] Add conditional threshold number input (0-2080) when toggle is enabled for Current Schedule in `planalign_studio/components/VestingAnalysis.tsx`
- [x] T009 [P] [US1] Add hours requirement toggle checkbox below Proposed Schedule selector in `planalign_studio/components/VestingAnalysis.tsx`
- [x] T010 [P] [US1] Add conditional threshold number input (0-2080) when toggle is enabled for Proposed Schedule in `planalign_studio/components/VestingAnalysis.tsx`
- [ ] T011 [US1] Verify toggle checkbox shows/hides threshold input correctly for both schedules

**Checkpoint**: User can toggle hours requirement on/off and adjust threshold for both schedules ✓

---

## Phase 4: User Story 2 - Analyze with Hours Requirement (Priority: P1)

**Goal**: Ensure API request includes hours requirement fields

**Independent Test**: Enable hours requirement, click Analyze, verify browser DevTools Network tab shows `require_hours_credit` and `hours_threshold` in request payload

**Requirements**: FR-005

### Implementation for User Story 2

- [x] T012 [US2] Verify `handleAnalyze` function builds request with full `VestingScheduleConfig` including hours fields in `planalign_studio/components/VestingAnalysis.tsx`
- [ ] T013 [US2] Test API request payload with hours enabled (DevTools Network inspection)
- [ ] T014 [US2] Test API request payload with hours disabled (verify `require_hours_credit: false`)
- [ ] T015 [US2] Test API request with custom threshold (e.g., 750 hours)

**Checkpoint**: API requests correctly include hours requirement configuration

---

## Phase 5: User Story 3 - View Hours in Results (Priority: P2)

**Goal**: Display hours requirement settings in analysis results summary

**Independent Test**: Run analysis with hours enabled, verify results banner shows hours configuration

**Requirements**: FR-006

### Implementation for User Story 3

- [x] T016 [US3] Update Scenario Info Banner to conditionally display hours requirement section in `planalign_studio/components/VestingAnalysis.tsx`
- [x] T017 [US3] Show Current Schedule hours threshold when `require_hours_credit` is true
- [x] T018 [US3] Show Proposed Schedule hours threshold when `require_hours_credit` is true
- [ ] T019 [US3] Verify banner hides hours section when neither schedule has hours requirement

**Checkpoint**: Analysis results clearly show which hours settings were applied ✓

---

## Phase 6: User Story 4 - Explanatory Text (Priority: P3)

**Goal**: Add help text explaining the hours requirement impact

**Independent Test**: View toggle area, verify explanatory text is visible and explains vesting credit impact

**Requirements**: FR-007

### Implementation for User Story 4

- [x] T020 [P] [US4] Add explanatory text below Current Schedule toggle in `planalign_studio/components/VestingAnalysis.tsx`
- [x] T021 [P] [US4] Add explanatory text below Proposed Schedule toggle in `planalign_studio/components/VestingAnalysis.tsx`
- [ ] T022 [US4] Verify text reads: "Employees below threshold lose 1 year vesting credit"

**Checkpoint**: Users understand the impact of enabling hours requirement ✓

---

## Phase 7: Polish & Validation

**Purpose**: Edge case handling and final verification

- [ ] T023 Test edge case: Set threshold to 0 (should be accepted)
- [ ] T024 Test edge case: Set threshold above 2080 (should clamp to 2080)
- [ ] T025 Test edge case: Toggle on/off multiple times before analyzing
- [ ] T026 Test edge case: Change schedule type with hours enabled (should preserve hours settings per FR-008)
- [ ] T027 Run full acceptance criteria verification per quickstart.md
- [ ] T028 Visual review: Ensure styling matches existing component patterns

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - verify environment works ✓
- **Foundational (Phase 2)**: Depends on Setup - adds required event handlers ✓
- **User Story 1 (Phase 3)**: Depends on Foundational - adds UI controls ✓
- **User Story 2 (Phase 4)**: Depends on US1 - verifies API integration (code complete, manual testing pending)
- **User Story 3 (Phase 5)**: Depends on US2 - displays results ✓
- **User Story 4 (Phase 6)**: Can run parallel to US2/US3 (independent UI text) ✓
- **Polish (Phase 7)**: Depends on all user stories complete (pending manual testing)

### User Story Dependencies

- **User Story 1 (P1)**: Core MVP - UI controls for toggle/input ✓
- **User Story 2 (P1)**: Depends on US1 UI being functional to test API (code complete)
- **User Story 3 (P2)**: Depends on US2 API working to show results ✓
- **User Story 4 (P3)**: Independent of US2/US3 - can be added anytime after US1 ✓

### Parallel Opportunities

Tasks T007/T008 (Current Schedule) and T009/T010 (Proposed Schedule) modify different JSX sections and can be developed in parallel.

Tasks T020/T021 (explanatory text) can run in parallel with US2/US3 implementation.

---

## Parallel Example: User Story 1

```bash
# These tasks modify different JSX sections and can run in parallel:
Task: "T007 [US1] Add hours toggle for Current Schedule"
Task: "T009 [US1] Add hours toggle for Proposed Schedule"

# After toggle tasks complete, input tasks can run in parallel:
Task: "T008 [US1] Add threshold input for Current Schedule"
Task: "T010 [US1] Add threshold input for Proposed Schedule"
```

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Complete Phase 1: Setup (T001-T003) ✓
2. Complete Phase 2: Foundational (T004-T006) ✓
3. Complete Phase 3: User Story 1 (T007-T011) ✓
4. Complete Phase 4: User Story 2 (T012-T015) - code complete, manual testing pending
5. **STOP and VALIDATE**: Toggle works, API receives hours fields
6. Can deploy MVP at this point

### Incremental Delivery

1. Setup + Foundational → Handlers ready ✓
2. Add User Story 1 → Users can configure hours (MVP foundation) ✓
3. Add User Story 2 → API receives configuration (MVP complete) - code complete
4. Add User Story 3 → Results show configuration (transparency) ✓
5. Add User Story 4 → Help text improves usability (polish) ✓
6. Polish phase → Edge cases validated (pending manual testing)

---

## Notes

- All tasks modify single file: `planalign_studio/components/VestingAnalysis.tsx`
- No new files created
- No backend changes required (API already supports hours fields)
- TypeScript types already exist in `api.ts`
- Manual testing via browser DevTools for API verification
- Each user story builds on previous but can be tested independently
