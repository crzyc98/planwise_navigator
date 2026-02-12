# Research: DC Plan Metrics in Scenario Comparison

**Feature**: 048-comparison-dc-metrics
**Date**: 2026-02-12

## R1: Response Structure Pattern

**Decision**: Follow the existing per-year comparison pattern (`WorkforceComparisonYear`) rather than the user's proposed per-scenario pattern (`DCPlanScenarioMetrics`).

**Rationale**: The existing `ComparisonResponse` organizes data by year first, with scenario-keyed dictionaries for `values` and `deltas`. This pattern (`WorkforceComparisonYear`) enables year-over-year comparison views in the frontend. Using a different structure (per-scenario with nested years) would create inconsistency in the API response.

**Alternatives considered**:
- Per-scenario structure (user-proposed `DCPlanScenarioMetrics`): Rejected because it diverges from the existing API pattern and would require different frontend consumption logic.
- Flat list with scenario+year keys: Rejected because it loses the hierarchical structure that makes delta calculation intuitive.

**Implementation**: Create `DCPlanMetrics` (inner model) and `DCPlanComparisonYear` (outer model with `year`, `values: Dict[str, DCPlanMetrics]`, `deltas: Dict[str, DCPlanMetrics]`), mirroring the `WorkforceMetrics` / `WorkforceComparisonYear` pattern.

## R2: SQL Query Pattern

**Decision**: Use the proven SQL pattern from `analytics_service.py::_get_contribution_by_year()` with COALESCE for null safety.

**Rationale**: This exact query is already running in production via the analytics service. It handles NULL columns, zero denominators, and the active-only filter for participation rate.

**Alternatives considered**:
- Custom query with different aggregation: Rejected because the analytics service query is proven and tested.
- Reuse `AnalyticsService` directly: Rejected because it has different initialization requirements (workspace-scoped, not scenario-scoped) and would introduce coupling.

**Key details**:
- Participation rate denominator: ACTIVE employees only (`UPPER(employment_status) = 'ACTIVE'`)
- Contribution totals: ALL employees (active + terminated) to capture full-year contributions
- Average deferral rate: enrolled employees only (`CASE WHEN is_enrolled_flag THEN current_deferral_rate`)
- Null safety: `COALESCE()` on all SUMs, `NULLIF()` on denominators

## R3: Database Connection Reuse

**Decision**: Add DC plan query to the existing `_load_scenario_data()` method, reusing the same DuckDB connection.

**Rationale**: The comparison service already opens a read-only connection to each scenario's database in `_load_scenario_data()`. Adding a second query to the same connection avoids the overhead of opening/closing additional connections and follows the existing pattern.

**Alternatives considered**:
- Separate `_load_dc_plan_data()` method with its own connection: Rejected because it doubles connection overhead and risks database lock contention.
- Combined single mega-query: Rejected because it would make the workforce and DC plan logic harder to maintain separately.

## R4: Test Infrastructure

**Decision**: Create `tests/test_comparison_dc_plan.py` using in-memory DuckDB fixtures, following the `test_analytics_service.py` pattern.

**Rationale**: The analytics service tests demonstrate the exact pattern needed: in-memory DuckDB with seeded `fct_workforce_snapshot` data, mocked `DatabasePathResolver`, and targeted assertions on aggregation results.

**Key test cases**:
1. Happy path: 2 scenarios, multi-year, with different match formulas
2. Delta calculations: verify absolute and percentage deltas against baseline
3. Zero enrollment: all active employees, none enrolled → 0% participation
4. Zero active employees: all terminated → 0% participation, 0 deferral rate
5. NULL contribution columns: NULLs treated as 0
6. Mismatched year ranges: only overlapping years compared
7. Zero baseline values: percentage delta = 0% (no division by zero)
8. Summary deltas: final-year participation rate and employer cost in summary_deltas

**No existing comparison tests**: This is new test coverage for the comparison service. Follow `test_analytics_service.py` fixture patterns.

## R5: Summary Deltas Scope

**Decision**: Add two summary delta entries: `final_participation_rate` and `final_employer_cost`.

**Rationale**: The spec (FR-009) explicitly calls for "final-year participation rate and total employer cost" in summary_deltas. These use the existing `DeltaValue` model with baseline/scenarios/deltas/delta_pcts structure.

**Alternatives considered**:
- Include all DC plan metrics in summary: Rejected as over-engineering; the summary should highlight the two most decision-relevant metrics.
- Separate summary section: Rejected because it would break the existing `summary_deltas: Dict[str, DeltaValue]` contract.

## R6: Column Name Verification

**Decision**: Use exact column names as they exist in `fct_workforce_snapshot`.

**Verified columns** (from `dbt/models/marts/fct_workforce_snapshot.sql` and `analytics_service.py`):
- `is_enrolled_flag` (BOOLEAN)
- `current_deferral_rate` (DECIMAL)
- `employer_match_amount` (DECIMAL)
- `employer_core_amount` (DECIMAL)
- `prorated_annual_contributions` (DECIMAL)
- `prorated_annual_compensation` (DECIMAL)
- `employment_status` (VARCHAR, values: 'Active', 'Terminated')
- `simulation_year` (INTEGER)
