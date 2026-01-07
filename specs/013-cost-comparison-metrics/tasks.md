# Tasks: Employer Cost Ratio Metrics

**Input**: Design documents from `/specs/013-cost-comparison-metrics/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Not explicitly requested in spec. Backend tests included per constitution (Test-First Development principle).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Backend**: `planalign_api/` (Python 3.11, FastAPI, Pydantic v2)
- **Frontend**: `planalign_studio/` (TypeScript 5.x, React 18)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No new project setup required - extending existing infrastructure

- [X] T001 Read existing ContributionYearSummary and DCPlanAnalytics models in planalign_api/models/analytics.py
- [X] T002 Read existing _get_contribution_by_year() query in planalign_api/services/analytics_service.py
- [X] T003 [P] Read existing TypeScript interfaces in planalign_studio/services/api.ts
- [X] T004 [P] Read existing ScenarioCostComparison component in planalign_studio/components/ScenarioCostComparison.tsx

**Checkpoint**: Existing code understood - implementation can begin

---

## Phase 2: Foundational (Backend API Extension)

**Purpose**: Extend backend API to return compensation and cost rate data - MUST complete before frontend changes

**⚠️ CRITICAL**: Frontend user stories depend on backend API returning new fields

- [X] T005 [P] Add total_compensation field (float, default 0.0) to ContributionYearSummary in planalign_api/models/analytics.py
- [X] T006 [P] Add employer_cost_rate field (float, default 0.0) to ContributionYearSummary in planalign_api/models/analytics.py
- [X] T007 [P] Add total_compensation field (float, default 0.0) to DCPlanAnalytics in planalign_api/models/analytics.py
- [X] T008 [P] Add employer_cost_rate field (float, default 0.0) to DCPlanAnalytics in planalign_api/models/analytics.py
- [X] T009 Extend _get_contribution_by_year() SQL query to include SUM(prorated_annual_compensation) in planalign_api/services/analytics_service.py
- [X] T010 Add employer_cost_rate calculation logic in _get_contribution_by_year() with zero-division handling in planalign_api/services/analytics_service.py
- [X] T011 Update get_dc_plan_analytics() to calculate aggregate total_compensation and employer_cost_rate in planalign_api/services/analytics_service.py
- [X] T012 [P] Add total_compensation and employer_cost_rate fields to ContributionYearSummary interface in planalign_studio/services/api.ts
- [X] T013 [P] Add total_compensation and employer_cost_rate fields to DCPlanAnalytics interface in planalign_studio/services/api.ts

**Checkpoint**: API returns new fields - frontend implementation can begin

---

## Phase 3: User Story 1 - View Average Employer Contribution Rate Per Employee (Priority: P1) 🎯 MVP

**Goal**: Display employer cost rate in summary MetricCard with variance calculation

**Independent Test**: Select two scenarios, verify "Employer Cost Rate" card appears with percentage values and variance indicator

### Implementation for User Story 1

- [X] T014 [US1] Add "Employer Cost Rate" MetricCard to the summary grid (after existing Total Employer Cost card) in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T015 [US1] Configure MetricCard with isCost=true for correct variance coloring (positive = red) in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T016 [US1] Use formatPercent utility for displaying employer_cost_rate values in planalign_studio/components/ScenarioCostComparison.tsx

**Checkpoint**: Summary MetricCard displays employer cost rate with variance - User Story 1 complete

---

## Phase 4: User Story 2 - View Total Employer Cost as Percentage of Total Payroll (Priority: P1)

**Goal**: Display aggregate employer cost rate in Grand Totals Summary section

**Independent Test**: View Grand Totals section, verify fourth card shows "Employer Cost Rate" with aggregate percentage

### Implementation for User Story 2

- [X] T017 [US2] Add fourth card to Grand Totals Summary grid showing employer cost rate percentage in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T018 [US2] Display comparison scenario rate prominently with baseline rate for comparison in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T019 [US2] Apply consistent styling (bg-white/10 rounded-lg p-4) matching existing cards in planalign_studio/components/ScenarioCostComparison.tsx

**Checkpoint**: Grand Totals shows aggregate cost rate - User Story 2 complete

---

## Phase 5: User Story 3 - Compare Employer Cost Metrics Across Individual Years (Priority: P2)

**Goal**: Display employer cost rate in year-by-year breakdown table

**Independent Test**: View year-by-year table, verify "Employer Cost Rate" row appears for each year with variance

### Implementation for User Story 3

- [X] T020 [US3] Extend yearByYearData memo to extract employerCostRate from each ContributionYearSummary in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T021 [US3] Add employerCostRate to metrics object in yearByYearData transformation in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T022 [US3] Add "Employer Cost Rate" row to metrics array in table rendering (after Total Employer Cost) in planalign_studio/components/ScenarioCostComparison.tsx
- [X] T023 [US3] Configure row with isCost=true and formatPercent formatter in planalign_studio/components/ScenarioCostComparison.tsx

**Checkpoint**: Year-by-year table shows cost rate - User Story 3 complete

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Validation and documentation

- [X] T024 Manual test: Run two scenarios with different match formulas, verify all three views display correct employer cost rates
- [X] T025 Manual test: Verify variance indicators show red for higher cost scenario, green for lower
- [X] T026 Manual test: Verify edge case handling (zero compensation displays 0.00%, no errors)
- [X] T027 Update spec.md status from Draft to Implemented in /workspace/specs/013-cost-comparison-metrics/spec.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - read-only code review
- **Foundational (Phase 2)**: Depends on Setup - BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Foundational (Phase 2) completion
  - US1 and US2 are both P1 and can run in parallel
  - US3 is P2 and can run in parallel with US1/US2
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2 - Adds MetricCard
- **User Story 2 (P1)**: Can start after Phase 2 - Adds Grand Totals card (different UI section than US1)
- **User Story 3 (P2)**: Can start after Phase 2 - Adds table row (different UI section than US1/US2)

### Within Each User Story

- All US1 tasks are sequential (same file section)
- All US2 tasks are sequential (same file section)
- All US3 tasks are sequential (same file section)

### Parallel Opportunities

- Setup tasks T003 and T004 can run in parallel (different files)
- Foundational model tasks T005-T008 can run in parallel (same file but different classes)
- Foundational TypeScript tasks T012-T013 can run in parallel (same file but different interfaces)
- User Stories 1, 2, and 3 can run in parallel (different UI sections in same file)

---

## Parallel Example: Foundational Backend Models

```bash
# Launch all backend model updates together:
Task: "Add total_compensation field to ContributionYearSummary in planalign_api/models/analytics.py"
Task: "Add employer_cost_rate field to ContributionYearSummary in planalign_api/models/analytics.py"
Task: "Add total_compensation field to DCPlanAnalytics in planalign_api/models/analytics.py"
Task: "Add employer_cost_rate field to DCPlanAnalytics in planalign_api/models/analytics.py"
```

## Parallel Example: All User Stories After Phase 2

```bash
# After Phase 2 completes, launch all user story starts:
Task: "[US1] Add Employer Cost Rate MetricCard to summary grid"
Task: "[US2] Add fourth card to Grand Totals Summary"
Task: "[US3] Extend yearByYearData memo to extract employerCostRate"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (read existing code)
2. Complete Phase 2: Foundational (backend API + TypeScript interfaces)
3. Complete Phase 3: User Story 1 (MetricCard)
4. **STOP and VALIDATE**: Test MetricCard displays correctly
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → API ready
2. Add User Story 1 → MetricCard visible → Deploy/Demo (MVP!)
3. Add User Story 2 → Grand Totals updated → Deploy/Demo
4. Add User Story 3 → Year-by-year table updated → Deploy/Demo
5. Each story adds value without breaking previous stories

### Single Developer Strategy (Recommended)

1. Complete Setup (read code)
2. Complete Foundational (backend first, then TypeScript)
3. Complete US1 → US2 → US3 sequentially
4. Each story testable after completion

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- All three user stories modify the same React component but different sections
- Backend changes (Phase 2) must complete before any frontend work
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
