# Tasks: DC Plan Comparison Charts

**Input**: Design documents from `/specs/057-dc-comparison-charts/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: No test tasks included — not requested in the feature specification. Verification is manual per quickstart.md.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Include exact file paths in descriptions

## Path Conventions

- **Frontend**: `planalign_studio/components/`, `planalign_studio/services/`
- No backend or API changes required (per research.md R1)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the new component file scaffold and prepare the parent component for integration

- [x] T001 Create `DCPlanComparisonSection.tsx` component scaffold with props interface, imports (React, Recharts LineChart/Line/BarChart/Bar/XAxis/YAxis/CartesianGrid/Tooltip/Legend/ResponsiveContainer, lucide-react Loader2/AlertCircle/DollarSign/TrendingUp/TrendingDown), and empty render function in `planalign_studio/components/DCPlanComparisonSection.tsx`
- [x] T002 Add local formatting utilities (`formatCurrency`, `formatPercent`) and type definitions (`TrendDataPoint`, `ContributionBreakdownPoint`, `SummaryMetricRow`) to the top of `planalign_studio/components/DCPlanComparisonSection.tsx` (per contracts/component-props.ts and data-model.md)
- [x] T003 Add loading, error, and empty state renders to `DCPlanComparisonSection.tsx`: loading spinner when `loading=true`, error alert when `error` is set, "No DC plan data available" message when `comparisonData` is null or has empty analytics array — follow existing patterns from `ScenarioComparison.tsx` (Loader2 spinner, AlertCircle icon) in `planalign_studio/components/DCPlanComparisonSection.tsx`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Wire up DC plan data fetching in the parent component and render the collapsible section shell

**CRITICAL**: No user story chart work can begin until this phase is complete

- [x] T004 Add DC plan state variables and imports to `ScenarioComparison.tsx`: import `compareDCPlanAnalytics` and `DCPlanComparisonResponse` from `../services/api`, import `DCPlanComparisonSection` from `./DCPlanComparisonSection`, add state variables `dcPlanData` (DCPlanComparisonResponse | null), `dcPlanLoading` (boolean), `dcPlanError` (string | null), and `expandedDCPlan` (boolean, default true) in `planalign_studio/components/ScenarioComparison.tsx`
- [x] T005 Add `useEffect` to fetch DC plan comparison data in `ScenarioComparison.tsx`: trigger when `scenariosWithResults` has 2+ entries, derive `workspaceId` from the first scenario's workspace_id property, collect scenario IDs, call `compareDCPlanAnalytics(workspaceId, scenarioIds)`, set loading/data/error states with try/catch/finally — follow the existing fetch pattern from the component's scenario loading useEffect in `planalign_studio/components/ScenarioComparison.tsx`
- [x] T006 Compute `scenarioColors` map in `ScenarioComparison.tsx`: build a `Record<string, string>` mapping each scenario name to its color from `COMPARISON_COLORS[idx % COMPARISON_COLORS.length]`, using the same index order as `scenariosWithResults` — this ensures DC plan charts use identical colors to workforce charts. Add this as a derived variable (not state) in `planalign_studio/components/ScenarioComparison.tsx`
- [x] T007 Add collapsible "DC Plan Comparison" section to the render output of `ScenarioComparison.tsx`: place below the existing chart grid and above the footer, use the same collapsible pattern as "Key Metrics Comparison" (button with DollarSign icon + ChevronUp/ChevronDown toggle, `expandedDCPlan` state), render `<DCPlanComparisonSection>` inside the collapsible body passing props: `comparisonData={dcPlanData}`, `loading={dcPlanLoading}`, `error={dcPlanError}`, `scenarioNames={scenariosWithResults.map(d => d.scenario.name)}`, `scenarioColors={scenarioColors}` in `planalign_studio/components/ScenarioComparison.tsx`

**Checkpoint**: At this point, the DC Plan Comparison section should appear as a collapsible panel showing loading/empty/error states. No charts yet.

---

## Phase 3: User Story 1 - Employer Cost Rate Trends (Priority: P1) MVP

**Goal**: Display a line chart showing employer cost as % of compensation over simulation years, one line per scenario

**Independent Test**: Open comparison page with 2+ completed scenarios → see employer cost rate line chart with correct scenario colors, year labels, and tooltip values

### Implementation for User Story 1

- [x] T008 [US1] Add `employerCostTrendData` useMemo in `DCPlanComparisonSection.tsx`: transform `comparisonData.analytics` into `TrendDataPoint[]` — collect union of all years from all scenarios' `contribution_by_year`, sort ascending, map each year to an object `{ year, [scenarioName]: yearData.employer_cost_rate }` using `comparisonData.scenario_names` for display names. Return empty array if no data in `planalign_studio/components/DCPlanComparisonSection.tsx`
- [x] T009 [US1] Render the employer cost rate trend LineChart in `DCPlanComparisonSection.tsx`: wrap in a card (`bg-white rounded-xl shadow-sm border border-gray-200 p-6`) with heading "Employer Cost Rate Trends" and subheading "Employer cost as % of total compensation". Inside a `div className="h-80"`, render `<ResponsiveContainer><LineChart data={employerCostTrendData}>` with `CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#E5E7EB"`, `XAxis dataKey="year" stroke="#9CA3AF"`, `YAxis stroke="#9CA3AF" tickFormatter={v => formatPercent(v)}`, `Tooltip` with standard contentStyle and `formatter={(value: number) => [formatPercent(value, 2), '']}`, `Legend verticalAlign="top" height={36}`, and one `<Line>` per scenario name from `scenarioNames` prop with `type="monotone" stroke={scenarioColors[name]} strokeWidth={3} dot={{ r: 4 }} activeDot={{ r: 6 }}` in `planalign_studio/components/DCPlanComparisonSection.tsx`

**Checkpoint**: Employer cost rate line chart renders with one colored line per scenario. Tooltips show exact percentage on hover. This is the MVP — validates the entire data pipeline from API to chart.

---

## Phase 4: User Story 2 - Participation & Deferral Rate Trends (Priority: P2)

**Goal**: Display two additional line charts: participation rate trends and average deferral rate trends

**Independent Test**: Open comparison page → see participation rate and deferral rate line charts below the employer cost chart, each with scenario-colored lines and accurate percentage values

### Implementation for User Story 2

- [x] T010 [P] [US2] Add `participationTrendData` useMemo in `DCPlanComparisonSection.tsx`: same transformation pattern as `employerCostTrendData` (T008) but keyed on `participation_rate` field from `contribution_by_year`. Values are already 0-100 percentages, no multiplication needed in `planalign_studio/components/DCPlanComparisonSection.tsx`
- [x] T011 [P] [US2] Add `deferralTrendData` useMemo in `DCPlanComparisonSection.tsx`: same transformation pattern as `employerCostTrendData` (T008) but keyed on `average_deferral_rate` field from `contribution_by_year`. IMPORTANT: multiply values by 100 for display (API returns decimal 0.06, display as 6.0%) per research.md R5 and data-model.md validation rules in `planalign_studio/components/DCPlanComparisonSection.tsx`
- [x] T012 [US2] Render participation rate trend LineChart in `DCPlanComparisonSection.tsx`: same card + chart structure as employer cost chart (T009) but with heading "Participation Rate Trends", subheading "Percentage of eligible employees enrolled", data from `participationTrendData`, YAxis domain `[0, 100]`, tooltip formatter using `formatPercent(value, 1)`. Place below the employer cost chart in a 2-column grid layout (`grid grid-cols-1 lg:grid-cols-2 gap-6`) in `planalign_studio/components/DCPlanComparisonSection.tsx`
- [x] T013 [US2] Render deferral rate trend LineChart in `DCPlanComparisonSection.tsx`: same card + chart structure as participation rate chart (T012) but with heading "Average Deferral Rate Trends", subheading "Average employee deferral rate", data from `deferralTrendData`, tooltip formatter using `formatPercent(value, 2)`. Place as the second column in the same grid row as the participation chart in `planalign_studio/components/DCPlanComparisonSection.tsx`

**Checkpoint**: Three line charts now visible — employer cost (full width), participation + deferral (side by side). All use consistent scenario colors.

---

## Phase 5: User Story 3 - Contribution Breakdown (Priority: P3)

**Goal**: Display a grouped bar chart comparing employee contributions, employer match, and employer core across scenarios using the final simulation year

**Independent Test**: Open comparison page → see grouped bar chart with 3 bars per scenario (employee blue, match green, core amber) showing correct dollar values in tooltips

### Implementation for User Story 3

- [x] T014 [US3] Add `contributionBreakdownData` useMemo in `DCPlanComparisonSection.tsx`: for each scenario in `comparisonData.analytics`, find the last entry in `contribution_by_year` (final simulation year), extract `total_employee_contributions`, `total_employer_match`, `total_employer_core`, map to `ContributionBreakdownPoint` array `{ name: scenarioName, employee, match, core }`. Return empty array if no data in `planalign_studio/components/DCPlanComparisonSection.tsx`
- [x] T015 [US3] Render contribution breakdown grouped BarChart in `DCPlanComparisonSection.tsx`: wrap in a card with heading "Contribution Breakdown" and subheading showing the final year (e.g., "Final year (2027) — Employee, Employer Match, and Employer Core"). Inside a `div className="h-80"`, render `<ResponsiveContainer><BarChart data={contributionBreakdownData}>` with `XAxis dataKey="name"`, `YAxis tickFormatter={v => formatCurrency(v)}`, `Tooltip formatter={(value: number) => [formatCurrency(value), '']}`, three `<Bar>` elements: `dataKey="employee" name="Employee Contributions" fill="#0088FE" radius={[4,4,0,0]}`, `dataKey="match" name="Employer Match" fill="#00C49F" radius={[4,4,0,0]}`, `dataKey="core" name="Employer Core" fill="#FFBB28" radius={[4,4,0,0]}`. Adjust `barSize` based on scenario count in `planalign_studio/components/DCPlanComparisonSection.tsx`

**Checkpoint**: Grouped bar chart renders with 3 colored bars per scenario. Currency tooltips show exact dollar amounts.

---

## Phase 6: User Story 4 - Summary Comparison Table (Priority: P4)

**Goal**: Display a summary table with 4 metric rows, scenario columns, color-coded deltas relative to baseline

**Independent Test**: Open comparison page with baseline + alternative scenario → see table with correct metric values, computed deltas, green for favorable, red for unfavorable

### Implementation for User Story 4

- [x] T016 [US4] Add `summaryRows` useMemo in `DCPlanComparisonSection.tsx`: compute 4 `SummaryMetricRow` objects using overall (not year-by-year) analytics data from each scenario. Rows: (1) "Participation Rate" using `analytics.participation_rate`, unit="percent", favorable="higher"; (2) "Avg Deferral Rate" using `analytics.average_deferral_rate * 100`, unit="percent", favorable="higher"; (3) "Employer Cost Rate" using `analytics.employer_cost_rate`, unit="percent", favorable="lower"; (4) "Total Contributions" using `analytics.total_all_contributions`, unit="currency", favorable="lower". For each row, compute `deltas` and `deltaPcts` relative to the first scenario (baseline). Use `scenarioNames[0]` as baseline in `planalign_studio/components/DCPlanComparisonSection.tsx`
- [x] T017 [US4] Render summary comparison table in `DCPlanComparisonSection.tsx`: wrap in a card with heading "DC Plan Summary Comparison". Render an HTML `<table>` with Tailwind classes (`w-full text-sm`). Header row: "Metric" column + one column per scenario name (baseline labeled with "(Baseline)" suffix). Body: one row per `summaryRows` entry — metric name in first cell, then for each scenario: display the formatted value (percent or currency). For non-baseline scenarios, add a delta badge below the value: green background + text (`bg-green-50 text-green-700`) when delta direction is favorable, red (`bg-red-50 text-red-700`) when unfavorable. Show delta as "+X.X%" or "-X.X%" for percent metrics, "+$XK" / "-$XK" for currency. When only one scenario, show values without any deltas in `planalign_studio/components/DCPlanComparisonSection.tsx`

**Checkpoint**: Summary table renders with all 4 metrics, scenario columns, and color-coded deltas. Single-scenario case shows values only.

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Edge case handling, layout refinements, and final validation

- [x] T018 Handle single-scenario edge case in `DCPlanComparisonSection.tsx`: when `scenarioNames.length === 1`, all line charts render with a single line, bar chart shows one group of 3 bars, summary table shows values without delta columns. Ensure no division-by-zero in delta calculations in `planalign_studio/components/DCPlanComparisonSection.tsx`
- [x] T019 Handle zero-participant and missing data edge cases in `DCPlanComparisonSection.tsx`: when a scenario has `contribution_by_year` as empty array, exclude it from trend data (don't add `undefined` entries that could break charts). When all contribution values are 0, charts render with flat zero lines and empty bars — no console errors in `planalign_studio/components/DCPlanComparisonSection.tsx`
- [x] T020 Refine chart layout for responsive behavior in `DCPlanComparisonSection.tsx`: employer cost chart at full width, participation + deferral in `grid grid-cols-1 lg:grid-cols-2 gap-6`, contribution breakdown at full width, summary table at full width with `overflow-x-auto` wrapper for horizontal scroll on narrow screens. Verify no element overlap at 768px width in `planalign_studio/components/DCPlanComparisonSection.tsx`
- [x] T021 Verify tooltip accuracy and chart correctness: manually compare displayed chart values against raw API response data (use browser DevTools Network tab to inspect `compareDCPlanAnalytics` response). Confirm `average_deferral_rate` is correctly multiplied by 100, `participation_rate` shows as-is (0-100), `employer_cost_rate` shows as-is. Fix any discrepancies found

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 completion (T001-T003) — BLOCKS all user stories
- **User Stories (Phases 3-6)**: All depend on Phase 2 completion (T004-T007)
  - US1 (Phase 3) can proceed first as MVP
  - US2, US3, US4 can proceed in parallel after US1 or concurrently
- **Polish (Phase 7)**: Depends on all user story phases being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2 — No dependencies on other stories. This is the MVP.
- **User Story 2 (P2)**: Can start after Phase 2 — Independent of US1 (uses same data transformation pattern)
- **User Story 3 (P3)**: Can start after Phase 2 — Independent of US1/US2 (different chart type, different data shape)
- **User Story 4 (P4)**: Can start after Phase 2 — Independent of US1/US2/US3 (uses overall analytics, not year-by-year)

### Within Each User Story

- Data transformation (useMemo) MUST be implemented before chart rendering
- Chart rendering depends on the useMemo providing data

### Parallel Opportunities

- T001, T002, T003 are sequential (same file, building on each other)
- T004, T005, T006 are sequential (same file, state → effect → derived)
- T007 depends on T004-T006
- T010 and T011 can run in parallel [P] (independent useMemo hooks, no render dependency)
- T014 and T016 can run in parallel [P] (independent data transformations)
- Once Phase 2 is complete, US1-US4 implementations could theoretically proceed in parallel across different sections of the same file

---

## Parallel Example: User Story 2

```bash
# These two useMemo hooks can be written in parallel (different data, no dependency):
Task: T010 "Add participationTrendData useMemo in DCPlanComparisonSection.tsx"
Task: T011 "Add deferralTrendData useMemo in DCPlanComparisonSection.tsx"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (T001-T003) — Component scaffold
2. Complete Phase 2: Foundational (T004-T007) — Data fetch + collapsible section
3. Complete Phase 3: User Story 1 (T008-T009) — Employer cost chart
4. **STOP and VALIDATE**: Verify employer cost line chart renders correctly with 2+ scenarios
5. This MVP validates the entire pipeline: API fetch → data transform → chart render

### Incremental Delivery

1. Setup + Foundational → Section shell visible with loading state
2. Add US1 (employer cost chart) → **Deploy/Demo** — answers the key "what does it cost?" question
3. Add US2 (participation + deferral charts) → **Deploy/Demo** — explains cost drivers
4. Add US3 (contribution breakdown bar chart) → **Deploy/Demo** — shows cost components
5. Add US4 (summary table with deltas) → **Deploy/Demo** — complete comparison view
6. Polish (edge cases + responsive) → Final validation

### Single Developer Strategy

Work sequentially in priority order. Each phase builds on the previous but adds independent value:

1. Phases 1-2: Foundation (~30 min)
2. Phase 3: US1 MVP (~30 min)
3. Phase 4: US2 (~30 min)
4. Phase 5: US3 (~20 min)
5. Phase 6: US4 (~30 min)
6. Phase 7: Polish (~20 min)

**Total estimated effort**: ~2.5-3 hours

---

## Notes

- All work is in 2 files: `ScenarioComparison.tsx` (modify) and `DCPlanComparisonSection.tsx` (create)
- No backend changes, no new dependencies, no API type changes needed
- `average_deferral_rate` × 100 is the most critical data transformation to get right (research.md R5)
- Consistent use of `COMPARISON_COLORS` and `scenarioColors` prop ensures visual continuity with workforce charts
- The `compareDCPlanAnalytics` endpoint requires a `workspaceId` — derived from the first loaded scenario's data
