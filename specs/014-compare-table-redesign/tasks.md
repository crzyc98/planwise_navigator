# Tasks: Compare Page Table Redesign

**Input**: Design documents from `/specs/014-compare-table-redesign/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, quickstart.md

**Tests**: No automated tests requested. Manual visual testing as per constitution (no existing React test suite).

**Organization**: Tasks are grouped to enable incremental implementation. All user stories (US1-US4) are tightly coupled since they all modify the same table structure - implemented as one cohesive unit.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Frontend**: `planalign_studio/components/`
- Single file modification: `ScenarioCostComparison.tsx`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Read and understand existing code structure

- [X] T001 Read existing ScenarioCostComparison.tsx to understand current table structure in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T002 [P] Identify existing utility functions (formatCurrency, formatPercent, calculateVariance, VarianceDisplay) in planalign_studio/components/ScenarioCostComparison.tsx

**Checkpoint**: Existing code understood - implementation can begin

---

## Phase 2: Foundational (Core Component Creation)

**Purpose**: Create the reusable MetricTable component that all user stories depend on

**⚠️ CRITICAL**: This component is the foundation for the new table design

- [X] T003 Define MetricTableProps interface with title, years, baselineData, comparisonData, formatValue, isCost, comparisonLabel, rawMultiplier in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T004 Create MetricTable component skeleton with props destructuring in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T005 Define METRICS constant array with all 6 metrics (participationRate, avgDeferralRate, employerMatch, employerCore, totalEmployerCost, employerCostRate) in planalign_studio/components/ScenarioCostComparison.tsx

**Checkpoint**: MetricTable component ready - table rendering can begin

---

## Phase 3: Core Implementation - Table Structure (US1+US2+US3) 🎯 MVP

**Goal**: Implement the complete new table layout with years as columns and Baseline/Comparison/Variance as rows

**Independent Test**: Load compare page with two scenarios, verify 6 separate tables appear with correct row/column structure

### Implementation

- [X] T006 [US1] Implement MetricTable header row with year columns (sorted chronologically) in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T007 [US2] Implement MetricTable Baseline row (row 1) with values per year in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T008 [US2] Implement MetricTable Comparison row (row 2) with scenario name label and values per year in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T009 [US2] Implement MetricTable Variance row (row 3) with calculated differences per year in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T010 [US3] Add table header displaying metric title prominently in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T011 [US1] Apply Tailwind styling for table container (bg-white, rounded-xl, shadow-sm, border) in planalign_studio/components/ScenarioCostComparison.tsx

**Checkpoint**: MetricTable component complete with full row/column structure

---

## Phase 4: Integration - Replace Existing Table (US1)

**Goal**: Replace the old year-by-year table with the new metric tables layout

**Independent Test**: Verify old table is removed and 6 new metric tables appear stacked vertically

### Implementation

- [X] T012 [US1] Create data transformation to build metric-specific Maps (year -> value) from yearByYearData in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T013 [US1] Extract sorted years array from yearByYearData in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T014 [US1] Remove old year-by-year table JSX (lines ~588-714) in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T015 [US1] Add new Year-by-Year Breakdown section with header in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T016 [US1] Render 6 MetricTable components using METRICS.map() in correct order in planalign_studio/components/ScenarioCostComparison.tsx

**Checkpoint**: New table structure integrated - old table replaced

---

## Phase 5: Visual Polish - Variance Styling (US4)

**Goal**: Add color-coded variance indicators with correct logic for cost vs rate metrics

**Independent Test**: Compare scenarios with known differences, verify red for cost increases, green for decreases

### Implementation

- [X] T017 [US4] Integrate existing VarianceDisplay component in variance row cells in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T018 [US4] Apply isCost logic: red for positive cost variance, green for negative in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T019 [US4] Apply rate logic: green for positive participation/deferral variance, red for negative in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T020 [US4] Handle zero variance with neutral gray styling in planalign_studio/components/ScenarioCostComparison.tsx

**Checkpoint**: Visual variance indicators complete

---

## Phase 6: Edge Cases & Polish

**Purpose**: Handle edge cases and ensure robustness

- [X] T021 Handle missing data by displaying "-" when year value is undefined in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T022 Handle single-year simulation (single column display) in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T023 Handle loading state in new MetricTable components in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T024 Manual test: Run quickstart.md testing checklist

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion
- **Core Implementation (Phase 3)**: Depends on Foundational (MetricTable component)
- **Integration (Phase 4)**: Depends on Core Implementation (MetricTable complete)
- **Visual Polish (Phase 5)**: Depends on Integration (tables rendering)
- **Edge Cases (Phase 6)**: Depends on Visual Polish

### User Story Notes

All user stories (US1-US4) are implemented together because they define a single cohesive table structure:
- US1: Separate tables per metric + vertical stacking
- US2: Baseline/Comparison/Variance rows
- US3: Years as columns
- US4: Variance color coding

These cannot be implemented independently - they form one MVP unit.

### Parallel Opportunities

- T001 and T002 can run in parallel (both are read-only)
- T006-T011 could theoretically run in parallel but they're in the same component section
- T017-T020 could run in parallel (different row styling concerns)

---

## Parallel Example: Setup Phase

```bash
# Launch both setup tasks together:
Task: "Read existing ScenarioCostComparison.tsx structure"
Task: "Identify existing utility functions (formatCurrency, formatPercent, etc.)"
```

---

## Implementation Strategy

### MVP Delivery (All-in-One)

This feature is small enough to implement as a single unit:

1. Complete Phase 1-2: Setup + Foundational
2. Complete Phase 3: Core table structure
3. Complete Phase 4: Integration (replace old table)
4. Complete Phase 5: Visual polish
5. Complete Phase 6: Edge cases
6. **VALIDATE**: Run quickstart.md testing checklist

### Estimated Effort

- **Total Tasks**: 24
- **Single File**: planalign_studio/components/ScenarioCostComparison.tsx
- **Lines Changed**: ~200 (remove old table ~130 lines, add new structure ~200 lines)
- **Estimated Time**: 1-2 hours

---

## Notes

- All changes are in a single file: ScenarioCostComparison.tsx
- No API changes required - reuses existing data structures
- Reuses existing utility functions (formatCurrency, formatPercent, VarianceDisplay)
- Manual visual testing per constitution (no React test suite)
- Commit after each phase checkpoint for easy rollback
