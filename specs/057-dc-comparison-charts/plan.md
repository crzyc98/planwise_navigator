# Implementation Plan: DC Plan Comparison Charts

**Branch**: `057-dc-comparison-charts` | **Date**: 2026-02-21 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/057-dc-comparison-charts/spec.md`

## Summary

Add five DC plan comparison visualizations (3 trend line charts, 1 grouped bar chart, 1 summary table with delta coloring) to the `ScenarioComparison.tsx` page. The backend already provides all required data via the `compareDCPlanAnalytics` endpoint. This is a frontend-only change: fetch DC plan comparison data alongside existing workforce data, transform it into Recharts-compatible shapes, and render in a new collapsible section below the existing workforce charts.

## Technical Context

**Language/Version**: TypeScript 5.x (React 18 frontend)
**Primary Dependencies**: React 18, Recharts 3.5.0, Lucide-react (icons), Tailwind CSS
**Storage**: N/A (frontend reads from existing API; no database changes)
**Testing**: Manual verification with completed simulation scenarios
**Target Platform**: Modern browsers (Chrome, Firefox, Safari, Edge)
**Project Type**: Web application (frontend-only change)
**Performance Goals**: All charts render within 3 seconds for 2-6 scenarios over 3-5 year ranges
**Constraints**: Must work on screen widths 768px-1920px; must not break existing workforce comparison
**Scale/Scope**: 2 files modified, 1 file created; ~400-500 lines of new code

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | N/A | Frontend-only; no event store changes |
| II. Modular Architecture | PASS | New charts extracted to dedicated `DCPlanComparisonSection.tsx` component (~300 lines, well under 600 limit) |
| III. Test-First Development | PASS | Frontend component; verified via manual testing with completed scenarios |
| IV. Enterprise Transparency | N/A | No simulation decisions or audit trails affected |
| V. Type-Safe Configuration | PASS | All data flows through existing TypeScript interfaces (`DCPlanComparisonResponse`, `ContributionYearSummary`) |
| VI. Performance & Scalability | PASS | Dashboard queries already under 2s; no new API calls beyond existing `compareDCPlanAnalytics` |

**Gate result**: PASS — No violations. All applicable principles satisfied.

**Post-design re-check**: PASS — Design adds one new component file with typed props, uses existing API types, follows established chart patterns.

## Project Structure

### Documentation (this feature)

```text
specs/057-dc-comparison-charts/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Phase 0: Research findings
├── data-model.md        # Phase 1: Data model documentation
├── quickstart.md        # Phase 1: Developer quickstart
├── contracts/           # Phase 1: Component prop contracts
│   └── component-props.ts
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # Phase 2 output (created by /speckit.tasks)
```

### Source Code (repository root)

```text
planalign_studio/
├── components/
│   ├── ScenarioComparison.tsx          # MODIFY: Add DC plan data fetch + render section
│   └── DCPlanComparisonSection.tsx     # CREATE: Extracted chart component
└── services/
    └── api.ts                          # NO CHANGES: Types already defined
```

**Structure Decision**: Frontend-only change within the existing `planalign_studio/` directory. One new component file created to keep `ScenarioComparison.tsx` under the 600-line modular architecture limit. No backend, API, or service changes.

## Design Decisions

### D1: Component Extraction

Extract all DC plan chart logic into `DCPlanComparisonSection.tsx` rather than inlining in `ScenarioComparison.tsx`.

**Why**: `ScenarioComparison.tsx` is already 567 lines. Adding ~300 lines of chart logic would exceed the 600-line module limit (Constitution Principle II). The extracted component receives processed data as props, keeping the parent component focused on data orchestration.

### D2: Data Transformation Location

Transform `DCPlanComparisonResponse` into Recharts-compatible data shapes inside the child component using `useMemo`.

**Why**: Keeps the parent component simple (fetch + pass data). The child component owns its rendering concerns. `useMemo` prevents re-computation on every render.

### D3: Consistent Coloring via Props

Pass `scenarioNames` and `scenarioColors` as props from the parent, derived from the same `COMPARISON_COLORS` array and index assignments used for workforce charts.

**Why**: Ensures a scenario has the same color across workforce charts and DC plan charts. The parent already computes these for existing charts.

### D4: Baseline for Delta Calculations

Use the first scenario in the array as the baseline (index 0), consistent with the existing workforce comparison pattern.

**Why**: `ScenarioComparison.tsx` already treats the first scenario as the reference point in its Key Metrics table. Maintaining consistency avoids user confusion.

### D5: Collapsible Section Pattern

Use the same `useState` + button + `ChevronUp/ChevronDown` pattern already used for the "Key Metrics Comparison" section.

**Why**: Visual consistency within the same page. Users already understand this interaction pattern.

### D6: Deferral Rate Display

Multiply `average_deferral_rate` by 100 for display (the API returns it as a decimal like 0.06, not a percentage like 6.0).

**Why**: The `participation_rate` and `employer_cost_rate` fields are already percentages, but `average_deferral_rate` is a decimal. Must normalize for consistent y-axis display across all three trend charts.

## Implementation Phases

### Phase 1: Parent Component Integration (~30 min)

**File**: `planalign_studio/components/ScenarioComparison.tsx`

1. Add imports: `compareDCPlanAnalytics`, `DCPlanComparisonResponse`, `DCPlanComparisonSection`
2. Add state: `dcPlanData`, `dcPlanLoading`, `dcPlanError`
3. Add `useEffect` to fetch DC plan data when `scenariosWithResults` changes:
   - Derive `workspaceId` from the first scenario's data
   - Call `compareDCPlanAnalytics(workspaceId, scenarioIds)`
4. Compute `scenarioColors` map from `COMPARISON_COLORS` (shared with existing charts)
5. Add collapsible section below existing charts with `DCPlanComparisonSection` component
6. Pass props: `comparisonData`, `loading`, `error`, `scenarioNames`, `scenarioColors`

### Phase 2: Chart Component (~1-2 hours)

**File**: `planalign_studio/components/DCPlanComparisonSection.tsx` (NEW)

1. **Data transformation** (3 `useMemo` hooks):
   - `employerCostTrendData`: Transform `contribution_by_year` → `TrendDataPoint[]` keyed by `employer_cost_rate`
   - `participationTrendData`: Same pattern keyed by `participation_rate`
   - `deferralTrendData`: Same pattern keyed by `average_deferral_rate` (×100)
   - `contributionBreakdownData`: Extract final year → `ContributionBreakdownPoint[]`
   - `summaryRows`: Compute metric rows with deltas from baseline

2. **Loading/Error/Empty states**:
   - Loading: Spinner with "Loading DC plan data..."
   - Error: Alert with error message
   - Empty: "No DC plan data available" message

3. **Employer Cost Rate Trend** (LineChart):
   - X: year, Y: employer cost rate (%)
   - One `<Line>` per scenario with `COMPARISON_COLORS`
   - Tooltip: `${value.toFixed(2)}%`

4. **Participation Rate Trend** (LineChart):
   - X: year, Y: participation rate (%)
   - Same pattern as employer cost chart
   - Tooltip: `${value.toFixed(1)}%`

5. **Average Deferral Rate Trend** (LineChart):
   - X: year, Y: deferral rate (%)
   - Note: multiply raw value by 100
   - Tooltip: `${value.toFixed(2)}%`

6. **Contribution Breakdown** (BarChart, grouped):
   - X: scenario name, Y: dollar amount
   - Three bars per scenario: employee (blue), match (green), core (amber)
   - Tooltip: formatted currency

7. **Summary Comparison Table**:
   - 4 rows: Participation Rate, Avg Deferral Rate, Employer Cost Rate, Total Contributions
   - Columns: Metric name + one column per scenario
   - Non-baseline columns show delta with color: green (favorable) / red (unfavorable)
   - Favorable direction: higher participation = green, lower cost = green

### Phase 3: Polish & Edge Cases (~30 min)

1. Handle single-scenario case (no deltas in table, charts still render)
2. Handle different year ranges (union of years, gaps handled by Recharts)
3. Handle zero-participant scenarios (0% rates, $0 contributions)
4. Verify responsive behavior at 768px and 1920px widths
5. Verify tooltip accuracy against raw API data

## Risk Assessment

| Risk | Impact | Mitigation |
|------|--------|------------|
| `average_deferral_rate` format inconsistency | Low | Verified in research: API returns decimal, multiply by 100 for display |
| `ScenarioComparison.tsx` doesn't have workspace_id | Low | Derive from first scenario's loaded data; all compared scenarios share workspace |
| Large number of scenarios (6+) crowds charts | Low | `barSize` scales with count (pattern from `ScenarioCostComparison.tsx`); line charts handle up to 6 colors |
| API endpoint not available (dependency #147) | Medium | Show graceful empty state; DC plan section is independent of workforce charts |

## Complexity Tracking

> No violations to justify — all constitution principles pass.
