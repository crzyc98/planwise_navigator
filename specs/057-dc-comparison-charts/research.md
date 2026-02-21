# Research: DC Plan Comparison Charts

**Feature Branch**: `057-dc-comparison-charts`
**Date**: 2026-02-21

## R1: Backend Data Availability

**Decision**: No backend changes needed. The existing `compareDCPlanAnalytics` endpoint already returns all required year-by-year metrics.

**Rationale**: The `DCPlanComparisonResponse` → `DCPlanAnalytics` → `ContributionYearSummary[]` chain provides every field needed:
- `participation_rate` (0-100%)
- `average_deferral_rate` (decimal)
- `employer_cost_rate` (% of compensation)
- `total_employee_contributions`, `total_employer_match`, `total_employer_core`
- `total_compensation`, `total_employer_cost`, `participant_count`

**Alternatives considered**:
- Creating a new comparison endpoint with pre-computed deltas → Rejected; delta computation is trivial on frontend and already done in `ScenarioCostComparison.tsx`
- Using the `ComparisonResponse` from `comparison_service.py` → Rejected; it includes workforce metrics but DC plan data is better accessed through the dedicated analytics endpoint

## R2: Component Integration Strategy

**Decision**: Add DC plan charts directly to `ScenarioComparison.tsx` as a new collapsible section below existing workforce charts.

**Rationale**: The spec requires charts on the scenario comparison page (not the cost comparison page). `ScenarioComparison.tsx` already fetches scenario data via URL params and has a collapsible section pattern (Key Metrics table). Adding a new section follows the established pattern.

**Alternatives considered**:
- Creating a separate `DCPlanComparisonSection.tsx` sub-component → Preferred for modularity; the main component is already 567 lines. Extract chart logic into a child component that receives processed data as props.
- Embedding into `ScenarioCostComparison.tsx` → Rejected; that component is a separate page with sidebar layout, not the comparison page referenced in the spec.

## R3: Data Fetching Approach

**Decision**: Fetch DC plan data separately from workforce data using `compareDCPlanAnalytics`, triggered after scenarios are loaded.

**Rationale**: The DC plan data requires a workspace ID and scenario IDs. `ScenarioComparison.tsx` currently loads scenarios across all workspaces, so we need the workspace context. The existing `compareDCPlanAnalytics` function groups scenarios by workspace.

**Implementation detail**: Since `ScenarioComparison.tsx` uses `useSearchParams` (not workspace context), we must derive the workspace ID from the loaded scenario data. All compared scenarios belong to the same workspace (enforced by batch comparison flow).

**Alternatives considered**:
- Piggybacking on existing `getSimulationResults` calls → Rejected; that returns workforce data, not DC plan analytics
- Fetching per-scenario via `getDCPlanAnalytics` → Rejected; the comparison endpoint is more efficient (single call)

## R4: Chart Rendering Pattern

**Decision**: Follow `ScenarioComparison.tsx` patterns (index-based coloring, `COMPARISON_COLORS`, simple tooltip formatting) rather than `ScenarioCostComparison.tsx` patterns (ID-based maps, anchor concept).

**Rationale**: Consistency within the same component. The comparison page uses scenario names as data keys and index-based coloring. Introducing a different pattern within the same page would be confusing.

**Alternatives considered**:
- Adopting `ScenarioCostComparison.tsx` patterns (ID-based, anchor) → Rejected; different page, different context. Would require significant refactoring of the host component.

## R5: Formatting Utilities

**Decision**: Define `formatCurrency` and `formatPercent` locally in the component (or sub-component), following the existing pattern.

**Rationale**: Every chart component in the codebase duplicates these functions locally. While a shared utility would be ideal, creating one is outside the scope of this feature and would touch unrelated files.

**Alternatives considered**:
- Creating a shared `utils/formatting.ts` → Desirable but out of scope; would require updating all existing components for consistency

## R6: Year Range Handling

**Decision**: Compute the union of all simulation years across scenarios and build data arrays indexed by year. Missing data for a scenario in a given year is represented as `undefined` (Recharts naturally handles gaps by not rendering the point).

**Rationale**: `ScenarioComparison.tsx` already implements this exact pattern in `buildComparisonData()` using `allYears = new Set<number>()`.

**Alternatives considered**:
- Intersection of years only → Rejected; would hide data for longer simulations
- Filling gaps with zero → Rejected; zero is a valid value, would be misleading
