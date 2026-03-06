# Research: Winners & Losers Comparison Tab

## R1: Cross-Scenario Data Access Pattern

**Decision**: Load employee-level data from each scenario's DuckDB database independently, join in Python.

**Rationale**: Each scenario may resolve to a different database file via `DatabasePathResolver`. DuckDB's `read_only=True` connections allow safe parallel reads. The existing `ComparisonService._load_scenario_data()` pattern already demonstrates this approach.

**Alternatives considered**:
- ATTACH both databases in a single DuckDB connection — rejected because `DatabasePathResolver` may return the same physical file for both scenarios (shared database), causing ATTACH conflicts.
- Pre-compute comparison in dbt — rejected because comparisons are ad-hoc (any two scenarios), not part of the simulation pipeline.

## R2: Winner/Loser Classification Metric

**Decision**: Use `total_employer_contributions` (= `employer_match_amount + employer_core_amount`) from `fct_workforce_snapshot` at the final simulation year.

**Rationale**: FR-013 explicitly requires "total employer contribution value (employer match + any employer core contributions)". The `fct_workforce_snapshot` already computes and exposes both columns plus `total_employer_contributions`.

**Alternatives considered**:
- Compare total compensation (salary + benefits) — rejected per spec; FR-013 is explicit about employer contributions only.
- Compare across all years — rejected; spec assumption states "comparison is done at a single point in time (the final simulation year)".

## R3: Neutral Threshold

**Decision**: Use exact zero difference (`delta == 0`) for neutral classification. No rounding threshold.

**Rationale**: Employer contributions are computed deterministically from the same compensation base. Floating-point issues are mitigated by DuckDB's DECIMAL types. The spec says "zero difference... within a reasonable rounding threshold" — since we use DECIMAL arithmetic, exact zero is the reasonable threshold.

**Alternatives considered**:
- Threshold of $1 or $0.01 — adds complexity without benefit given DECIMAL precision.

## R4: Heatmap Visualization in Recharts

**Decision**: Build a custom CSS Grid heatmap using Tailwind classes with interactive tooltips, not a Recharts chart.

**Rationale**: Recharts v3.5 has no native heatmap component. A CSS grid with colored cells provides better control over the diverging color scale (green→gray→red) and is simpler than hacking ScatterChart. The existing codebase uses Tailwind extensively.

**Alternatives considered**:
- Recharts ScatterChart with colored squares — overly complex for a grid layout, poor axis label control.
- Third-party heatmap library (nivo, visx) — adds a dependency for one component; not justified.

## R5: Band Definitions Source

**Decision**: Read band labels from the query results themselves (`age_band` and `tenure_band` columns in `fct_workforce_snapshot`), which are already assigned during simulation.

**Rationale**: Band assignment happens in `fct_workforce_snapshot` using macros (`assign_age_band`, `assign_tenure_band`). Both scenarios use the same band definitions since they share workspace config. Querying the distinct bands from results ensures consistency with what was simulated.

**Alternatives considered**:
- Read from seed CSVs via API — adds an extra API call; bands in snapshot already reflect the configured values.

## R6: Session Persistence of Selections

**Decision**: Use URL search params (`?plan_a=...&plan_b=...`) for plan selections, matching the existing `AnalyticsDashboard` pattern with `useSearchParams`.

**Rationale**: URL params enable bookmarking, sharing, and browser back/forward navigation. The existing analytics pages already use `searchParams.get('scenario')` for this purpose.

**Alternatives considered**:
- `localStorage` — works but doesn't support URL sharing or deep linking.
- React context — overkill for two string values scoped to one tab.

## R7: API Endpoint Location

**Decision**: Add `GET /api/workspaces/{workspace_id}/analytics/winners-losers?plan_a=...&plan_b=...` to the existing `analytics.py` router.

**Rationale**: The analytics router already hosts `compare_dc_plan_analytics` which follows the same pattern (workspace-scoped, multi-scenario query params). Reusing the router keeps related endpoints together.

**Alternatives considered**:
- New dedicated router — unnecessary; the analytics router is the natural home.
- Add to comparison router — that router handles full scenario comparison, not demographic breakdowns.
