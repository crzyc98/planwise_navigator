# Research: Fix Yearly Participation Rate Consistency

**Feature**: 041-fix-yearly-participation-rate
**Date**: 2026-02-10

## R1: Current Participation Rate Calculation Inconsistency

**Decision**: The per-year participation rate in `_get_contribution_by_year()` must be changed to filter to active employees only, matching `_get_participation_summary()`.

**Rationale**: The two methods use different population scopes:
- `_get_participation_summary()` (line 134): Filters `UPPER(employment_status) = 'ACTIVE'` — only counts active employees
- `_get_contribution_by_year()` (line 185): Uses `COUNT(*)` as denominator — includes all employees (active + terminated)

This means the per-year rate includes terminated employees in the denominator, producing artificially lower participation rates compared to the top-level summary. For a simulation with 10% termination, this could produce a ~10 percentage point discrepancy.

**Alternatives considered**:
- **Change top-level to match per-year (include all)**: Rejected — active-only is the standard definition of participation rate in retirement plan reporting.
- **Add a separate field for active-only rate**: Rejected — the `participation_rate` field already exists on `ContributionYearSummary` and semantically should mean the same thing as the top-level rate. Adding a second field creates confusion.

## R2: Contribution Totals Should Remain Inclusive

**Decision**: Keep contribution totals (employee, match, core) inclusive of all employees, including those who terminated during the year.

**Rationale**: Terminated employees may have made contributions before leaving. Excluding them from contribution totals would undercount actual plan costs. This is consistent with standard 401(k) reporting where plan costs reflect all contributions made during the period regardless of employment status at year-end.

**Alternatives considered**:
- **Filter contributions to active only**: Rejected — would lose partial-year contributions from terminated employees, understating true plan costs.

## R3: No Existing Tests for AnalyticsService

**Decision**: Create new unit tests for `AnalyticsService` with in-memory DuckDB databases.

**Rationale**: Searched `tests/` directory — no test files exist for `AnalyticsService` or its methods. Tests must be created to validate the fix and prevent regression.

**Test approach**: Use in-memory DuckDB with a `fct_workforce_snapshot` table seeded with controlled data including both active and terminated employees. Verify:
1. Per-year participation rate matches active-only calculation
2. Final-year per-year rate matches top-level rate
3. Contribution totals still include all employees
4. Edge cases (zero active, all enrolled, single year)

## R4: Frontend Impact Assessment

**Decision**: No frontend changes needed.

**Rationale**: The frontend TypeScript interface `ContributionYearSummary` (api.ts line 815) already has a `participation_rate: number` field. The fix changes only the server-side calculation that populates this field. The top-level `DCPlanAnalytics.participation_rate` (api.ts line 850) is unchanged. All frontend components that display participation rate use the top-level field or the per-year field without transformation.

**Components verified**:
- `DCPlanAnalytics.tsx:476` — Uses top-level `analytics.participation_rate` (unchanged)
- `DCPlanAnalytics.tsx:373` — Uses top-level comparison `a.participation_rate` (unchanged)
- `ScenarioComparison.tsx:357,499` — Uses `results.participation_rate` (different model, unchanged)
- `AnalyticsDashboard.tsx:366` — Uses `results.participation_rate` (different model, unchanged)

## R5: SQL Fix Design

**Decision**: Modify the participation rate subexpression in the `_get_contribution_by_year()` SQL query to scope both numerator and denominator to active employees.

**Current SQL** (line 185):
```sql
COUNT(CASE WHEN is_enrolled_flag THEN 1 END) * 100.0 / NULLIF(COUNT(*), 0) as participation_rate
```

**Fixed SQL**:
```sql
COUNT(CASE WHEN UPPER(employment_status) = 'ACTIVE' AND is_enrolled_flag THEN 1 END) * 100.0
  / NULLIF(COUNT(CASE WHEN UPPER(employment_status) = 'ACTIVE' THEN 1 END), 0) as participation_rate
```

**Rationale**: This scopes the participation rate to active employees while leaving all other aggregations (SUM of contributions, AVG deferral rate, participant_count) unchanged. The `NULLIF` prevents division by zero when a year has no active employees.
