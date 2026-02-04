# Tasks: Multi-Year Compensation Matrix

**Input**: Design documents from `/specs/033-compensation-matrix/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: Manual testing only (no unit test infrastructure for React components per plan.md)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

## Path Conventions

- **Frontend**: `planalign_studio/` at repository root
- Single file modification: `planalign_studio/components/ScenarioCostComparison.tsx`

---

## Phase 1: Setup (Verification)

**Purpose**: Verify existing infrastructure and data availability

- [x] T001 Verify `total_compensation` field exists in `ContributionYearSummary` interface at `planalign_studio/services/api.ts:807`
- [x] T002 Verify `useCopyToClipboard` hook is available at `planalign_studio/hooks/useCopyToClipboard.ts`
- [x] T003 Verify existing cost matrix implementation pattern at `planalign_studio/components/ScenarioCostComparison.tsx:1039-1141`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add supporting infrastructure within the component

**Note**: This feature has no blocking foundational tasks - all infrastructure already exists.

**Checkpoint**: Foundation ready - user story implementation can begin

---

## Phase 3: User Story 1 - View Annual Compensation by Scenario (Priority: P1) MVP

**Goal**: Display a "Multi-Year Compensation Matrix" table below the cost matrix showing total compensation for each scenario and simulation year

**Independent Test**: Select 2+ scenarios on the compare cost page, scroll below the cost matrix, verify compensation matrix appears with values for each year/scenario

### Implementation for User Story 1

- [x] T004 [US1] Add second `useCopyToClipboard` hook instance for compensation matrix near line 185 in `planalign_studio/components/ScenarioCostComparison.tsx`

- [x] T005 [US1] Add `compensationTableToTSV` callback function (parallel to existing `tableToTSV`) near line 607 in `planalign_studio/components/ScenarioCostComparison.tsx` that:
  - Builds header row: `['Scenario', ...years, 'Total', 'Variance']`
  - For each scenario: extracts `total_compensation` from `contribution_by_year`
  - Calculates total across years
  - Calculates variance from anchor scenario
  - Returns tab-separated string

- [x] T006 [US1] Add `handleCompensationCopy` callback (parallel to existing `handleCopy`) in `planalign_studio/components/ScenarioCostComparison.tsx`

- [x] T007 [US1] Add compensation matrix table JSX after line 1141 (after cost matrix `</div>`) in `planalign_studio/components/ScenarioCostComparison.tsx` with:
  - Container: `<div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">`
  - Header section with title "Multi-Year Compensation Matrix" and copy button
  - Table structure matching cost matrix: Scenario Name column, year columns, Total column, Variance column
  - Same styling classes as cost matrix

- [x] T008 [US1] Implement table body rows using `orderedScenarioIds.map()` in `planalign_studio/components/ScenarioCostComparison.tsx`:
  - Access `analytics.contribution_by_year.find(y => y.year === year)?.total_compensation`
  - Apply `formatCurrency()` to compensation values
  - Display dash (-) for missing year data
  - Highlight anchor row with blue background (`bg-blue-50/30`)
  - Calculate and display total as sum of year values

- [x] T009 [US1] Implement variance column logic in `planalign_studio/components/ScenarioCostComparison.tsx`:
  - For anchor row: display `--`
  - For non-anchor rows: calculate delta from anchor's total compensation
  - Apply conditional formatting: orange badge for positive, green badge for negative

**Checkpoint**: User Story 1 complete - compensation matrix displays correctly with all data

---

## Phase 4: User Story 2 - Copy Compensation Data (Priority: P2)

**Goal**: Enable copying compensation matrix data to clipboard in spreadsheet-compatible format

**Independent Test**: Click copy button on compensation matrix header, paste into spreadsheet, verify tab-separated format with correct columns

### Implementation for User Story 2

- [x] T010 [US2] Wire up copy button in compensation matrix header to `handleCompensationCopy` in `planalign_studio/components/ScenarioCostComparison.tsx`:
  - Button toggles between Copy icon and Check icon based on `copiedCompensation` state
  - Same styling as cost matrix copy button
  - Title attribute shows "Copy to clipboard" / "Copied!"

- [x] T011 [US2] Verify TSV format output from `compensationTableToTSV` includes proper formatting in `planalign_studio/components/ScenarioCostComparison.tsx`:
  - Currency values formatted with `formatCurrency()`
  - Variance prefixed with + or - sign
  - Tab separators between columns
  - Newline separators between rows

**Checkpoint**: User Story 2 complete - copy functionality works independently

---

## Phase 5: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and cleanup

- [x] T012 Run TypeScript compilation check: `cd planalign_studio && npx tsc --noEmit`
- [ ] T013 Manual testing following `specs/033-compensation-matrix/quickstart.md` validation checklist:
  - [ ] Compensation matrix appears below cost matrix
  - [ ] Same visual styling as cost matrix
  - [ ] Anchor scenario highlighted in blue
  - [ ] Variance shows orange (positive) or green (negative) badges
  - [ ] Copy button works independently from cost matrix
  - [x] No TypeScript compilation errors
  - [ ] No console errors in browser
- [ ] T014 Test edge cases per `specs/033-compensation-matrix/spec.md`:
  - [ ] 2 scenarios selected: both appear
  - [ ] 6 scenarios selected: all appear with horizontal scroll
  - [ ] 1 scenario selected: variance shows "--"
  - [ ] Missing year data: cell displays "-"

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - verification only
- **Foundational (Phase 2)**: N/A - no foundational tasks needed
- **User Story 1 (Phase 3)**: Can start immediately after verification
- **User Story 2 (Phase 4)**: Depends on T004-T006 from User Story 1 (copy infrastructure)
- **Polish (Phase 5)**: Depends on User Stories 1 and 2 completion

### User Story Dependencies

- **User Story 1 (P1)**: Independent - no dependencies on other stories
- **User Story 2 (P2)**: Depends on US1's T004 (hook), T005 (TSV function), T006 (handler)

### Within User Story 1

- T004 (hook) must complete before T006 (handler)
- T005 (TSV function) must complete before T006 (handler)
- T007 (table structure) must complete before T008 (body rows) and T009 (variance)
- T008 and T009 can run in parallel after T007

### Parallel Opportunities

```text
Phase 1 (Setup): T001, T002, T003 can run in parallel

Phase 3 (US1):
  - T004 and T005 can run in parallel (different logical sections)
  - T008 and T009 can run in parallel (different table parts)

Phase 4 (US2):
  - T010 and T011 are sequential (T010 first)
```

---

## Parallel Example: User Story 1

```bash
# First batch - foundation:
Task: "Add useCopyToClipboard hook instance at line 185"
Task: "Add compensationTableToTSV callback near line 607"

# Second batch - after T004/T005:
Task: "Add handleCompensationCopy callback"

# Third batch - after T006:
Task: "Add compensation matrix table JSX after line 1141"

# Fourth batch - can run in parallel:
Task: "Implement table body rows with orderedScenarioIds.map()"
Task: "Implement variance column logic"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup verification (T001-T003)
2. Complete Phase 3: User Story 1 (T004-T009)
3. **STOP and VALIDATE**: Test compensation matrix displays correctly
4. Compensation data visible to users - core value delivered

### Incremental Delivery

1. Complete US1 → Compensation matrix visible (MVP!)
2. Complete US2 → Copy functionality added
3. Complete Polish → Full validation complete

### Single Developer Strategy

Recommended execution order:
1. T001 → T002 → T003 (verify infrastructure)
2. T004, T005 (parallel - different sections)
3. T006 (depends on T004, T005)
4. T007 (table structure)
5. T008, T009 (parallel - different parts of table)
6. T010 → T011 (copy functionality)
7. T012 → T013 → T014 (validation)

---

## Notes

- Single file modification: `planalign_studio/components/ScenarioCostComparison.tsx`
- ~100-150 lines of new code total
- No backend changes required
- Data already available in API response (`total_compensation` field)
- Visual design must exactly match existing cost matrix
- Commit after each task or logical group
