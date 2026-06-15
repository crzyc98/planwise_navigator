# Tasks: DC Plan Analytics — 0% Deferral Fix and Year Filter

**Input**: Design documents from `/specs/097-dc-analytics-year/`
**Prerequisites**: plan.md ✅ spec.md ✅ research.md ✅ data-model.md ✅ contracts/ ✅ quickstart.md ✅

**Tests**: Included for the backend bug fix (US1) per spec success criteria SC-001.

**Organization**: Tasks grouped by user story. US1 (bug fix) is entirely backend. US2/US3 (year picker) are frontend, with a small shared backend model extension in Phase 2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no cross-task dependency)
- **[Story]**: User story this task belongs to

---

## Phase 1: Setup

**Purpose**: Locate or create the analytics test file so test tasks have a landing pad.

- [x] T001 Verify `tests/test_dc_plan_analytics.py` exists; if missing, create it with the standard pytest imports and a placeholder fixture connecting to an in-memory DuckDB with `fct_workforce_snapshot` seeded with at least 10 enrolled + 5 non-enrolled active employees

---

## Phase 2: Foundational (Blocking Prerequisite)

**Purpose**: Extend the `ContributionYearSummary` model with `total_eligible_count` — needed by the US1 query fix and the US2 year-filtered participation KPI. Both the Python model and TypeScript interface must be updated before US2 UI work begins.

**⚠️ CRITICAL**: US2 KPI subtext work (T010) cannot start until T002 and T003 are complete.

- [x] T002 Add `total_eligible_count: int = Field(default=0, description="Total eligible employees (enrolled + non-enrolled) for this year")` to `ContributionYearSummary` in `planalign_api/models/analytics.py`
- [x] T003 [P] Add `total_eligible_count: number;` to the `ContributionYearSummary` TypeScript interface in `planalign_studio/services/api.ts`

**Checkpoint**: Model extended — US1 service work and US2 UI work can now proceed.

---

## Phase 3: User Story 1 — Deferral Rate Distribution Includes Non-Participants (Priority: P1) 🎯 MVP

**Goal**: Fix the Deferral Rate Distribution chart so the 0% bucket shows non-enrolled active employees, making the chart represent the full eligible active workforce rather than enrolled-only.

**Independent Test**: After T004–T007, query a completed simulation; the sum of all deferral bucket counts must equal the total count of active employees in the final simulation year (enrolled + non-enrolled). The 0% bucket count must equal `total_active - total_enrolled`.

### Tests for User Story 1

> **Write FIRST, verify they FAIL before touching the service code (T004–T006)**

- [x] T004 [US1] In `tests/test_analytics_service.py`, add `test_deferral_distribution_includes_non_enrolled`: seed in-memory DB with 10 enrolled (non-zero deferral) + 5 non-enrolled active employees; call `AnalyticsService._get_deferral_distribution(conn)`; assert `bucket['0%'].count == 5` and `sum(b.count for b in result) == 15`
- [x] T005 [P] [US1] In `tests/test_analytics_service.py`, add `test_deferral_distribution_all_years_includes_non_enrolled`: same seed, call `_get_deferral_distribution_all_years(conn)`; assert year entry 0% count == 5 and total per year == 15
- [x] T006 [P] [US1] In `tests/test_analytics_service.py`, add `test_contribution_by_year_total_eligible_count`: call `_get_contribution_by_year(conn)`; assert `result[0].total_eligible_count == 17` (10 enrolled + 5 non-enrolled active + 2 terminated when active_only=False)

### Implementation for User Story 1

- [x] T007 [US1] In `planalign_api/services/analytics_service.py`, fix `_get_deferral_distribution`: in the `bucketed` CTE's WHERE clause, remove `AND is_enrolled_flag = true` (keep `AND UPPER(employment_status) = 'ACTIVE'`). Verify T004 now passes.
- [x] T008 [P] [US1] In `planalign_api/services/analytics_service.py`, fix `_get_deferral_distribution_all_years`: in the `bucketed` CTE's WHERE clause, remove `AND is_enrolled_flag = true` (keep `WHERE UPPER(employment_status) = 'ACTIVE'`). Verify T005 now passes.
- [x] T009 [P] [US1] In `planalign_api/services/analytics_service.py`, update `_get_contribution_by_year`: add `COUNT(*) as total_eligible` to the SELECT, and populate `total_eligible_count=int(row["total_eligible"])` in the `ContributionYearSummary` constructor. Verify T006 now passes.

**Checkpoint**: Run `pytest tests/test_dc_plan_analytics.py -v` — all three new tests must pass. The 0% deferral bug is fixed.

---

## Phase 4: User Story 2 — Year Picker for Single-Scenario View (Priority: P2)

**Goal**: Add a year picker dropdown to the DC Plan analytics controls. When a specific year is selected, all KPI cards and the Deferral Rate Distribution chart update to show that year's data; the Contributions by Year chart highlights the selected year while keeping other years visible.

**Independent Test**: Load a completed multi-year scenario; select a year that is not the final year; verify all four KPI cards show different values than the "All Years" view; verify the deferral distribution changes; verify the selected year's bar appears at full opacity while others appear at 30–40% opacity.

### Implementation for User Story 2

- [x] T010 [US2] In `planalign_studio/components/DCPlanAnalytics.tsx`, add `selectedYear` state (`useState<number | null>(null)`) and three `useMemo` hooks:
  - `availableYears`: derives sorted year list from `analytics.contribution_by_year` (or empty array when no data)
  - `activeYearData`: finds the `ContributionYearSummary` matching `selectedYear` (null when "All Years")
  - `activeDeferralDistribution`: returns `deferral_distribution_by_year[selectedYear].distribution` when a year is selected, else `deferral_rate_distribution` (final-year aggregate)

- [x] T011 [US2] In `planalign_studio/components/DCPlanAnalytics.tsx`, add the year picker `<select>` to the controls row (between scenario selector and comparison toggle). Only render it when `(analytics || comparisonData) && availableYears.length > 1`. Options: `<option value="">All Years</option>` plus one per year in `availableYears`. On change: `setSelectedYear(value ? Number(value) : null)`.

- [x] T012 [US2] In `planalign_studio/components/DCPlanAnalytics.tsx`, update the four KPI `<KPICard>` values to use `activeYearData` when non-null:
  - Employee Deferrals: `activeYearData?.total_employee_contributions ?? analytics.total_employee_contributions`
  - Employer Match: `activeYearData?.total_employer_match ?? analytics.total_employer_match`
  - Employer Core: `activeYearData?.total_employer_core ?? analytics.total_employer_core`
  - Participation Rate: value = `activeYearData?.participation_rate ?? analytics.participation_rate`; subtext = `activeYearData ? \`${activeYearData.participant_count.toLocaleString()} of ${activeYearData.total_eligible_count.toLocaleString()} eligible\` : \`${analytics.total_enrolled.toLocaleString()} of ${analytics.total_eligible.toLocaleString()} ${activeOnly ? 'active eligible' : 'eligible'}\``

- [x] T013 [US2] In `planalign_studio/components/DCPlanAnalytics.tsx`, update the deferral distribution chart data source: replace the `deferralDistributionData` computation to use `activeDeferralDistribution` (already derived in T010) instead of `analytics.deferral_rate_distribution`.

- [x] T014 [US2] In `planalign_studio/components/DCPlanAnalytics.tsx`, update the Contributions by Year stacked bar chart to use `<Cell>` per bar for year highlighting. For each of the three `<Bar>` elements (Employee, Match, Core), add a `<Cell>` child per data point with `opacity={selectedYear === null || entry.year === selectedYear ? 1 : 0.35}`. Import `Cell` from `recharts` if not already imported.

- [x] T015 [US2] In `planalign_studio/components/DCPlanAnalytics.tsx`, add `setSelectedYear(null)` to the `useEffect` that fires when `activeWorkspace?.id` changes (alongside the existing `setAnalytics(null)` resets). This ensures the year picker resets to "All Years" when switching workspaces or scenarios.

**Checkpoint**: Single-scenario year picker works end-to-end. Verify by loading a 2+ year scenario and selecting each year — KPIs and distribution chart must update independently.

---

## Phase 5: User Story 3 — Year Picker Applied to Comparison View (Priority: P3)

**Goal**: When comparison mode is active and a specific year is selected, the comparison table and bar chart show per-year metrics for each scenario (sourced from each scenario's `contribution_by_year`) instead of cumulative totals.

**Independent Test**: Enter comparison mode with two 3-year scenarios. Select Year 2. Verify the comparison table shows Year 2 contribution values (not sums) for each scenario. Switch back to "All Years" — cumulative totals must be restored.

### Implementation for User Story 3

- [x] T016 [US3] In `planalign_studio/components/DCPlanAnalytics.tsx`, update the `availableYears` useMemo (from T010) to also handle comparison mode: when `comparisonData` is set, compute the **intersection** of years across all `comparisonData.analytics[*].contribution_by_year` arrays. Only years present in every scenario appear in the picker.

- [x] T017 [US3] In `planalign_studio/components/DCPlanAnalytics.tsx`, add a helper (inline or as a const above the JSX) `getComparisonYearData(a: DCPlanAnalytics): ContributionYearSummary | null` that returns `a.contribution_by_year.find(y => y.year === selectedYear) ?? null` when `selectedYear !== null`, else null.

- [x] T018 [US3] In `planalign_studio/components/DCPlanAnalytics.tsx`, update the comparison table body rows to use `getComparisonYearData(a)` when `selectedYear !== null`:
  - Participation Rate row: `yearData ? yearData.participation_rate.toFixed(1) + '%' : a.participation_rate.toFixed(1) + '%'`
  - Total Employee Contributions: `yearData ? formatCurrency(yearData.total_employee_contributions) : formatCurrency(a.total_employee_contributions)`
  - Total Employer Match: same pattern with `total_employer_match`
  - Total Employer Core: same pattern with `total_employer_core`
  - Total All Contributions: same pattern with `total_all_contributions`
  - Employees at IRS Limit row: show `—` (dash) when `selectedYear !== null` (IRS metrics are final-year only; add a tooltip or footnote "IRS metrics shown for final year only")

- [x] T019 [US3] In `planalign_studio/components/DCPlanAnalytics.tsx`, update the `comparisonContributionData` array (used by the Contribution Totals by Scenario bar chart) to use year-filtered data when `selectedYear !== null`:
  ```typescript
  const comparisonContributionData = comparisonData?.analytics.map(a => {
    const yearData = selectedYear !== null
      ? a.contribution_by_year.find(y => y.year === selectedYear)
      : null;
    return {
      scenario: a.scenario_name,
      Employee: yearData?.total_employee_contributions ?? a.total_employee_contributions,
      Match: yearData?.total_employer_match ?? a.total_employer_match,
      Core: yearData?.total_employer_core ?? a.total_employer_core,
    };
  }) || [];
  ```

**Checkpoint**: All three user stories are independently functional. Comparison mode year filtering works without requiring additional API calls.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [x] T020 [P] Run `pytest tests/test_analytics_service.py -v` — 49/49 pass including 5 new feature-097 tests
- [x] T021 [P] Run `cd planalign_studio && npx tsc --noEmit` — zero TypeScript errors
- [x] T022 Update `DeferralRateBucket.percentage` field description in `planalign_api/models/analytics.py` from "Percentage of enrolled employees" → "Percentage of eligible active employees" (align description with post-fix semantics)
- [ ] T023 Manually verify in the running Studio UI: load a completed simulation, confirm the 0% bucket count equals (total active employees − enrolled employees), and confirm the year picker renders and updates all charts correctly

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 — **blocks T012 (KPI subtext with total_eligible_count)**
- **US1 (Phase 3)**: Depends on Phase 2 (T002 must exist before T009 can populate the field)
  - Tests (T004–T006) can be written before Phase 2 is fully merged
  - Implementation (T007–T009) requires T002 to exist
- **US2 (Phase 4)**: Depends on Phase 2 (T002 + T003) and Phase 3 (T009 must be deployed for `total_eligible_count` to arrive in API response)
- **US3 (Phase 5)**: Depends on Phase 4 (T010 — `availableYears` useMemo must exist)
- **Polish (Phase 6)**: Depends on all prior phases

### User Story Dependencies

- **US1 (P1)**: Depends on Foundational (T002) — no other user story dependencies
- **US2 (P2)**: Depends on US1 (needs `total_eligible_count` in API response); T010–T015 can be written speculatively before US1 ships
- **US3 (P3)**: Depends on US2 (T010 `availableYears` useMemo must exist before T016 extends it)

### Within Each User Story

- Tests (T004–T006) written and failing **before** implementation (T007–T009)
- T010 (state + derived data) before T011 (picker UI) and T012–T014 (consuming derived data)
- T016 (extends availableYears) before T017–T019 (consume year-filtered data)

### Parallel Opportunities

- T003 (TS interface) can run in parallel with T002 (Python model)
- T005 and T006 (test tasks) can run in parallel with T004
- T007, T008, T009 (service fixes) can run in parallel after tests are written
- T011–T015 (picker UI tasks) can mostly run in parallel once T010 provides the shared state

---

## Parallel Example: User Story 1 (Bug Fix)

```bash
# Step 1: Write all three tests simultaneously (all different test functions)
Task T004: test_deferral_distribution_includes_non_enrolled
Task T005: test_deferral_distribution_all_years_includes_non_enrolled
Task T006: test_contribution_by_year_total_eligible_count

# Step 2: Run tests — all three should FAIL

# Step 3: Apply all three service fixes simultaneously (all different methods)
Task T007: fix _get_deferral_distribution (remove is_enrolled_flag filter)
Task T008: fix _get_deferral_distribution_all_years (remove is_enrolled_flag filter)
Task T009: add total_eligible to _get_contribution_by_year

# Step 4: Run tests — all three should PASS
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Phase 1: Create/verify test file
2. Phase 2: Add `total_eligible_count` model field
3. Phase 3: Write tests → verify fail → fix queries → verify pass
4. **STOP and VALIDATE**: The 0% deferral bug is fixed; chart now shows non-enrolled employees
5. Ship this independently — it has no UI changes

### Incremental Delivery

1. Setup + Foundational → model extension ready
2. US1 (backend fix) → verified with tests → deploy/merge (MVP)
3. US2 (year picker, single scenario) → verified in browser → deploy/merge
4. US3 (year picker, comparison) → verified in browser → deploy/merge
5. Polish → final validation

---

## Notes

- [P] tasks = different methods/files, no blocking dependencies on in-flight tasks
- [Story] label maps each task to its user story for traceability
- US1 is pure backend — no frontend changes needed; can be merged independently
- US3 requires zero additional API calls — year-filtered comparison uses `contribution_by_year` already in the comparison response
- IRS metrics in comparison mode show "—" when a year is selected (IRS data is final-year only in the current data model; this is documented in the contract)
