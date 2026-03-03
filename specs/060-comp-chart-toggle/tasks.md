# Tasks: Compensation Chart Toggle (Average/Total) with CAGR

**Input**: Design documents from `/specs/060-comp-chart-toggle/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/ui-contract.md

**Tests**: No automated tests — manual verification only (no frontend test framework in planalign_studio).

**Organization**: Tasks are grouped by user story. Both stories are P1 but naturally sequential since they modify the same chart card in the same file.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Data Transform Extension)

**Purpose**: Extend the existing data transformation to include total compensation so both user stories can consume it.

- [x] T001 Add `compMetric` state variable (`'average' | 'total'`, default `'average'`) near existing state declarations in `planalign_studio/components/AnalyticsDashboard.tsx` (around line 104)
- [x] T002 Extend `workforceChartData` transform to include `totalCompensation` field derived from `row.total_compensation / 1_000_000` (in $M) in `planalign_studio/components/AnalyticsDashboard.tsx` (line 223-227)

**Checkpoint**: Data transform now produces both `avgCompensation` (in $K) and `totalCompensation` (in $M) for each year. Existing chart behavior unchanged.

---

## Phase 2: User Story 1 - Toggle Between Average and Total Compensation (Priority: P1) — MVP

**Goal**: Add a segmented toggle to the compensation chart card that switches between average and total views, updating the chart data, Y-axis, tooltips, and legend dynamically.

**Independent Test**: Load Analytics Dashboard with a completed simulation. Click the toggle between "Average" and "Total" — chart data, Y-axis labels, tooltips, and legend should update. Default should be "Average" on page load.

### Implementation for User Story 1

- [x] T003 [US1] Add segmented toggle button (Average / Total) to the compensation chart card header, right-aligned next to the title, styled with Tailwind CSS (fidelity-green active state, gray inactive) in `planalign_studio/components/AnalyticsDashboard.tsx` (lines 504-506)
- [x] T004 [US1] Make chart `dataKey` dynamic: use `avgCompensation` when `compMetric === 'average'` and `totalCompensation` when `compMetric === 'total'` in `planalign_studio/components/AnalyticsDashboard.tsx` (line 519)
- [x] T005 [US1] Make Y-axis `tickFormatter` dynamic: use `$XXK` format for average, auto-detect `$XXK` or `$X.XM` for total based on max value in `planalign_studio/components/AnalyticsDashboard.tsx` (line 513)
- [x] T006 [US1] Make tooltip `formatter` dynamic: match Y-axis formatting for the selected metric, update label to "Avg Compensation" or "Total Compensation" in `planalign_studio/components/AnalyticsDashboard.tsx` (line 516)
- [x] T007 [US1] Update chart title text to be dynamic: "Average Compensation - All Employees ($K)" or "Total Compensation - All Employees ($M)" based on toggle state in `planalign_studio/components/AnalyticsDashboard.tsx` (line 506)
- [x] T008 [US1] Update `Line` component `name` prop to dynamic legend label: "Avg Compensation" or "Total Compensation" based on toggle state in `planalign_studio/components/AnalyticsDashboard.tsx` (line 519)

**Checkpoint**: Toggle switches chart between average ($K) and total ($M) views. Y-axis, tooltips, legend, and title all reflect the selected metric. Defaults to "Average" on page load.

---

## Phase 3: User Story 2 - Display CAGR in Chart Title (Priority: P1)

**Goal**: Append the CAGR percentage to the chart title, sourced from the pre-computed `cagr_metrics` in the API response, updating dynamically when the toggle changes.

**Independent Test**: Load Analytics Dashboard with a multi-year simulation. Verify CAGR appears in chart title (e.g., "— CAGR: 3.2%"). Switch toggle — CAGR value should change. Load a single-year simulation — CAGR should not appear.

### Implementation for User Story 2

- [x] T009 [US2] Add CAGR lookup helper that finds the matching metric from `results.cagr_metrics` based on `compMetric` state (`"Average Compensation"` or `"Total Compensation"`) in `planalign_studio/components/AnalyticsDashboard.tsx` (near the chart data transform section)
- [x] T010 [US2] Append CAGR to chart title in format " — CAGR: X.XX%" when `cagr_metrics` entry exists and `years > 0`; omit CAGR suffix when data has fewer than 2 years or metric is not found in `planalign_studio/components/AnalyticsDashboard.tsx` (line 506, updating T007's dynamic title)
- [x] T011 [US2] Handle edge case: when starting compensation is $0, display CAGR as "N/A" instead of a calculated value in `planalign_studio/components/AnalyticsDashboard.tsx`

**Checkpoint**: Chart title shows CAGR that updates with toggle. Single-year simulations show no CAGR. Zero-start-value shows "N/A".

---

## Phase 4: Polish & Verification

**Purpose**: Final verification of all acceptance scenarios and edge cases.

- [ ] T012 Manually verify all US1 acceptance scenarios: default state, toggle to Total, toggle back to Average, Y-axis/tooltip formatting
- [ ] T013 Manually verify all US2 acceptance scenarios: CAGR in title for multi-year, CAGR updates on toggle, no CAGR for single-year
- [ ] T014 Verify edge cases: very large total compensation values format correctly ($M), page refresh resets toggle to default

> **Note**: T012-T014 require running the frontend and interacting with the UI. Code implementation is complete (T001-T011). Zero TypeScript diagnostics confirmed.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **User Story 1 (Phase 2)**: Depends on Phase 1 (needs `compMetric` state and `totalCompensation` data field)
- **User Story 2 (Phase 3)**: Depends on Phase 2 (builds on dynamic title from T007)
- **Polish (Phase 4)**: Depends on Phases 2 and 3

### Within Each Phase

- **Phase 1**: T001 and T002 are independent (different code sections) but T002 is trivial after T001
- **Phase 2**: T003 must come first (toggle UI). T004-T008 depend on T003 but can be done in a single pass since they all modify the same chart card JSX block
- **Phase 3**: T009 (helper) before T010 (title integration). T011 (edge case) after T010

### Parallel Opportunities

Limited parallelism since all tasks modify the same file and largely the same JSX block. Best executed sequentially in a single focused pass through the component.

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T002)
2. Complete Phase 2: User Story 1 (T003-T008)
3. **STOP and VALIDATE**: Toggle works, chart switches correctly
4. Commit working MVP

### Full Feature

1. Complete Phase 1 + Phase 2 → Toggle works (MVP)
2. Complete Phase 3 → CAGR in title
3. Complete Phase 4 → All edge cases verified
4. Commit complete feature

### Practical Note

Given the small scope (~50 lines of changes in a single file), the most efficient approach is to implement all tasks in a single focused editing session rather than committing after each task.

---

## Notes

- All changes are in `planalign_studio/components/AnalyticsDashboard.tsx`
- No backend changes required — `total_compensation` and `cagr_metrics` already in API response
- No new dependencies — uses existing React state, Recharts, and Tailwind CSS
- Total estimated scope: ~50 lines of modifications
