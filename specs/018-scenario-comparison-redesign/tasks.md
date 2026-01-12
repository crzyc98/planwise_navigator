# Tasks: Scenario Cost Comparison Redesign

**Input**: Design documents from `/specs/018-scenario-comparison-redesign/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: Manual UI testing per constitution waiver (Test-First Development waived for frontend UI components)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Frontend component**: `planalign_studio/components/ScenarioCostComparison.tsx`
- **Reference component**: `planalign_studio/components/CostComparison.tsx`
- **API client**: `planalign_studio/services/api.ts`
- **Hooks**: `planalign_studio/hooks/`
- **Constants**: `planalign_studio/constants.ts`

---

## Phase 1: Setup

**Purpose**: Prepare the component file and understand existing patterns

- [x] T001 Backup existing component by copying `planalign_studio/components/ScenarioCostComparison.tsx` to `planalign_studio/components/ScenarioCostComparison.old.tsx`
- [x] T002 Create new empty `planalign_studio/components/ScenarioCostComparison.tsx` with basic React component scaffold and TypeScript types

---

## Phase 2: Foundational (Core Layout & State)

**Purpose**: Establish the sidebar + main content layout and core state management that ALL user stories depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T003 Implement flexbox layout (sidebar `w-80` + main content `flex-1`) in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T004 Add core state: `selectedWorkspaceId`, `selectedScenarioIds[]`, `anchorScenarioId`, `viewMode`, `searchQuery`, `loading`, `error` in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T005 Implement workspace selector dropdown (reuse pattern from existing component) in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T006 Implement `fetchWorkspaces()`, `fetchScenarios()`, `fetchComparison()` API functions (copy from existing component) in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T007 Add `useEffect` hooks for initial data loading and scenario changes in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T008 Implement smart auto-selection logic: find "baseline" scenario as anchor + first other scenario per FR-001a in `planalign_studio/components/ScenarioCostComparison.tsx`

**Checkpoint**: Foundation ready - sidebar layout visible, workspace selector works, API data loads

---

## Phase 3: User Story 1 - Compare Multiple Scenarios Side-by-Side (Priority: P1) 🎯 MVP

**Goal**: Enable multi-scenario selection in sidebar with color-coded cost trend chart

**Independent Test**: Select 3+ scenarios, view chart, verify distinct colors and legend

### Implementation for User Story 1

- [x] T009 [US1] Implement sidebar scenario list with checkboxes (map completed scenarios) in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T010 [US1] Implement `toggleSelection()` function with min/max constraints (1-5 scenarios) in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T011 [US1] Add anchor icon button per scenario in sidebar (set anchor on click) in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T012 [US1] Style anchor scenario distinctly (blue highlight, anchor icon, "Baseline Anchor" label) in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T013 [US1] Implement `processedData` useMemo for chart data transformation in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T014 [US1] Implement Employer Cost Trends BarChart using recharts (annual view default) in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T015 [US1] Apply color palette: anchor as `#1e293b`, others from `COLORS.charts` in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T016 [US1] Add chart Legend component with scenario names in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T017 [US1] Handle edge case: anchor deselected → auto-assign to first remaining selected in `planalign_studio/components/ScenarioCostComparison.tsx`

**Checkpoint**: Sidebar shows scenarios, multi-select works, chart displays with distinct colors

---

## Phase 4: User Story 2 - Switch Between Annual and Cumulative Views (Priority: P1)

**Goal**: Toggle between BarChart (annual) and AreaChart (cumulative) views

**Independent Test**: Toggle views, verify chart type changes and data recalculates

### Implementation for User Story 2

- [x] T018 [US2] Add Annual/Cumulative toggle buttons with active state styling in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T019 [US2] Extend `processedData` useMemo to compute cumulative totals when `viewMode === 'cumulative'` in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T020 [US2] Implement conditional chart rendering: BarChart for annual, AreaChart for cumulative in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T021 [US2] Configure AreaChart with fill opacity and stroke styling per scenario in `planalign_studio/components/ScenarioCostComparison.tsx`

**Checkpoint**: Toggle switches chart type instantly, cumulative totals display correctly

---

## Phase 5: User Story 3 - Set Anchor Baseline for Variance (Priority: P2)

**Goal**: Change anchor scenario and see variance calculations update

**Independent Test**: Change anchor, verify Incremental Costs chart updates with new deltas

### Implementation for User Story 3

- [x] T022 [US3] Extend `processedData` to compute `${id}_delta` for each non-anchor scenario in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T023 [US3] Implement Incremental Costs ComposedChart with Line components for deltas in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T024 [US3] Add dashed zero baseline line to Incremental Costs chart in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T025 [US3] Add header panel showing anchor summary (name, duration, total costs) in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T026 [US3] Add Core Design and Match Design info pills in header (from anchor config) in `planalign_studio/components/ScenarioCostComparison.tsx`

**Checkpoint**: Anchor change updates both main chart styling and variance chart

---

## Phase 6: User Story 4 - View Cost Breakdown in Data Table (Priority: P2)

**Goal**: Display Multi-Year Cost Matrix table with variance column

**Independent Test**: Verify table shows correct values, variance colors, and "--" for anchor

### Implementation for User Story 4

- [x] T027 [US4] Implement Multi-Year Cost Matrix table structure (scenario rows, year columns) in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T028 [US4] Add Total column (sum of all years) to table in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T029 [US4] Add Incremental Variance column with delta calculation in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T030 [US4] Apply color coding to variance: green for savings, orange/red for cost increase in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T031 [US4] Display "--" for anchor row variance column in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T032 [US4] Integrate `useCopyToClipboard` hook for table copy functionality in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T033 [US4] Add Copy button with visual feedback (copied state) in `planalign_studio/components/ScenarioCostComparison.tsx`

**Checkpoint**: Table displays all data, copy-to-clipboard works

---

## Phase 7: User Story 5 - Search and Filter Scenarios (Priority: P3)

**Goal**: Filter scenario list in sidebar by name

**Independent Test**: Type search term, verify list filters case-insensitively

### Implementation for User Story 5

- [x] T034 [US5] Add search input with Search icon in sidebar header in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T035 [US5] Implement `filteredScenarios` computed from `searchQuery` (case-insensitive) in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T036 [US5] Update scenario list to render `filteredScenarios` instead of full list in `planalign_studio/components/ScenarioCostComparison.tsx`

**Checkpoint**: Search filters scenarios instantly

---

## Phase 8: User Story 6 - Understand Cost Drivers and Methodology (Priority: P3)

**Goal**: Display methodology panels at page bottom

**Independent Test**: Scroll to bottom, verify Cost Sensitivity Drivers and Modeling Assumptions panels visible

### Implementation for User Story 6

- [x] T037 [US6] Add two-column grid layout for methodology footer in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T038 [US6] Implement "Cost Sensitivity Drivers" panel (dark theme) with explanatory content in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T039 [US6] Implement "Modeling Assumptions" panel (light blue theme) with bullet points in `planalign_studio/components/ScenarioCostComparison.tsx`

**Checkpoint**: Methodology panels display at bottom of page

---

## Phase 9: Polish & Edge Cases

**Purpose**: Handle edge cases, loading/error states, and cleanup

- [x] T040 Implement loading state with spinner during API calls in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T041 Implement error state with retry button on API failure in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T042 Implement empty state when only 1 scenario exists (guide to run more simulations) in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T043 Handle scenarios with different year ranges (show "-" for missing years) in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T044 Add "Download Report" button in sidebar footer in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T045 Add selected count badge in sidebar header (e.g., "3 SELECTED") in `planalign_studio/components/ScenarioCostComparison.tsx`
- [x] T046 Delete backup file `planalign_studio/components/ScenarioCostComparison.old.tsx` after validation
- [x] T047 Run quickstart.md validation checklist

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-8)**: All depend on Foundational phase completion
  - US1 and US2 are both P1 priority - complete both before P2 stories
  - Stories can proceed sequentially in priority order
- **Polish (Phase 9)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational - Core sidebar and chart
- **User Story 2 (P1)**: Can start after US1 - Extends chart with view toggle
- **User Story 3 (P2)**: Depends on US1 anchor implementation - Adds variance chart
- **User Story 4 (P2)**: Can start after US1 - Adds data table
- **User Story 5 (P3)**: Can start after US1 sidebar - Adds search
- **User Story 6 (P3)**: No dependencies on other stories - Adds footer panels

### Within Each User Story

- Tasks within a story must be completed sequentially (single file)
- No [P] markers since all tasks modify the same component file

### Parallel Opportunities

- No parallel opportunities within this feature (single component file)
- However, US4-US6 could theoretically be implemented in parallel by different developers if component is refactored into sub-components

---

## Parallel Example: Not Applicable

All tasks modify the same file (`ScenarioCostComparison.tsx`), so parallel execution is not possible for this feature.

---

## Implementation Strategy

### MVP First (User Stories 1 + 2)

1. Complete Phase 1: Setup (backup existing)
2. Complete Phase 2: Foundational (layout, state, API)
3. Complete Phase 3: User Story 1 (multi-select, chart)
4. Complete Phase 4: User Story 2 (view toggle)
5. **STOP and VALIDATE**: Test scenario selection, chart display, view toggle
6. Deploy/demo if ready

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add User Story 1 + 2 → Test → Deploy/Demo (MVP!)
3. Add User Story 3 → Test → Deploy/Demo (variance calculations)
4. Add User Story 4 → Test → Deploy/Demo (data table)
5. Add User Story 5 + 6 → Test → Deploy/Demo (search, methodology)
6. Complete Polish phase → Final release

---

## Notes

- All tasks modify `planalign_studio/components/ScenarioCostComparison.tsx`
- Reference `planalign_studio/components/CostComparison.tsx` for design patterns
- Reuse existing hooks: `useCopyToClipboard`
- Reuse existing API: `listWorkspaces`, `listScenarios`, `compareDCPlanAnalytics`
- Reuse existing constants: `COLORS.charts` for color palette
- Commit after each completed task or logical group
- Validate at checkpoints before proceeding
