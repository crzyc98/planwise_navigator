# Research: Deferral Rate Distribution Comparison

**Branch**: `059-deferral-dist-comparison` | **Date**: 2026-02-21

## Key Finding: Existing Data Already Available

The `DCPlanComparisonResponse` (returned by `GET /api/workspaces/{workspace_id}/analytics/dc-plan/compare`) already includes `deferral_rate_distribution: List[DeferralRateBucket]` per scenario as part of `DCPlanAnalytics`. This means **P1 (grouped bar chart) requires zero backend changes** — the data is already in the response but not rendered.

**However**, the existing distribution is final-year-only (hardcoded `MAX(simulation_year)` in `_get_deferral_distribution`). **P2 (year selector) requires backend changes** to return distributions for all simulation years.

## Decision Log

### D1: Backend Approach for Multi-Year Distributions

- **Decision**: Add a new field `deferral_distribution_by_year` to `DCPlanAnalytics` that returns distributions for all simulation years, keeping the existing `deferral_rate_distribution` (final year) unchanged for backward compatibility.
- **Rationale**: The payload is tiny (11 buckets × ~3 years × 6 scenarios ≈ 10KB) and avoids requiring a separate API call on each year change, which would be poor UX.
- **Alternatives considered**:
  - New endpoint for year-specific queries: Rejected — adds latency for year switching and more API surface area.
  - Modify existing `_get_deferral_distribution` to accept year param: Rejected — breaks backward compatibility and changes the semantics of the existing field.

### D2: Frontend Chart Placement

- **Decision**: Add the grouped bar chart inside `DCPlanComparisonSection.tsx`, following the existing pattern of Recharts-based visualizations within that component.
- **Rationale**: Consistent with E057 architecture. The component already receives `comparisonData` with per-scenario analytics and handles scenario color mapping.
- **Alternatives considered**:
  - New standalone component: Rejected — would duplicate data loading, color mapping, and section integration logic.

### D3: Year Selector Pattern

- **Decision**: Use a `<select>` dropdown above the chart, populated from years common to all scenarios, defaulting to the final year.
- **Rationale**: Lightweight, consistent with standard form patterns in the application, and sufficient for 1-10 year ranges.
- **Alternatives considered**:
  - Slider: Rejected — overkill for small year ranges, adds dependency complexity.
  - Tabs: Rejected — doesn't scale well beyond 5 years.

### D4: Data Shape for Per-Year Distribution

- **Decision**: Use a flat list with year as a discriminator: `List[DeferralDistributionYear]` where each entry contains `year: int` and `distribution: List[DeferralRateBucket]`.
- **Rationale**: Follows the existing `contribution_by_year: List[ContributionYearSummary]` pattern in `DCPlanAnalytics`.
- **Alternatives considered**:
  - Dict keyed by year: Rejected — JSON dicts with integer keys are awkward; lists are more idiomatic for ordered temporal data.

## Existing Patterns to Reuse

| Pattern | Source | Reuse In |
|---------|--------|----------|
| Deferral bucketing SQL | `analytics_service.py:259-318` | Modified to parameterize year |
| `DeferralRateBucket` model | `analytics.py` | Unchanged |
| `buildTrendData()` helper | `DCPlanComparisonSection.tsx:88-151` | Adapted for distribution data |
| Scenario color mapping | `ScenarioComparison.tsx:169-173` | Already passed as prop |
| Recharts `BarChart` | `DCPlanComparisonSection.tsx:407-446` | Pattern for grouped bar |
| Tooltip styling | `DCPlanComparisonSection.tsx:67-75` | Reused directly |
