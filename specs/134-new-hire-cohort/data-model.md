# Phase 1 Data Model: New-Hire Cohort Isolation for Cost Comparison

No new persisted tables or dbt models. This feature only changes read-path SQL predicates in `AnalyticsService` and the shape of two existing Pydantic response models. All entities below are request/response-time constructs.

## Cohort (request-scoped value, not persisted)

| Field | Type | Values | Notes |
|---|---|---|---|
| `cohort` | `Literal["all", "new_hires", "baseline"]` | `all` (default) | Query parameter on both DC Plan analytics endpoints. Validated by FastAPI/Pydantic before reaching the service layer — invalid values never reach `AnalyticsService`. |

**Classification rule** (evaluated per employee row in `fct_workforce_snapshot`):
- `new_hires`: `employee_hire_date >= DATE '{first_simulation_year}-01-01'`
- `baseline`: `employee_hire_date < DATE '{first_simulation_year}-01-01'`
- `all`: no predicate (existing behavior, unchanged)

Where `first_simulation_year` is resolved once per request (see below) and is constant across every row/year in a single response — it is a property of the scenario's run, not of the row being classified.

## Resolved First Simulation Year (computed, per scenario, per request)

| Field | Source | Notes |
|---|---|---|
| `first_simulation_year` | `SELECT MIN(simulation_year) FROM fct_workforce_snapshot` on the scenario's own DuckDB connection | Source of truth for cohort classification (R1 in research.md). |
| cross-check value | `SELECT start_year FROM run_metadata ORDER BY run_timestamp DESC LIMIT 1` (if `run_metadata` table exists) | Logged-warning-only; never overrides the classification value. |

Exposed to callers as a new field on `DCPlanAnalytics`:

```python
resolved_first_simulation_year: int
```

Populated on every response regardless of the requested `cohort`, so the frontend has a stable value to build the "Hired during the simulation ({year}+)" label without a second round trip.

## Modified: `AnalyticsService.get_dc_plan_analytics` (service method, not a data entity)

New parameter: `cohort: Literal["all", "new_hires", "baseline"] = "all"`. Threaded into:
- `_get_participation_summary(conn, active_only, cohort, first_simulation_year)`
- `_get_contribution_by_year(conn, active_only, cohort, first_simulation_year)`

Both compose the cohort predicate with the existing `active_only` predicate via a shared `_combine_where(*fragments)` helper (replaces the current inline `AND`/`WHERE` string handling). `_get_deferral_distribution`, `_get_deferral_distribution_all_years`, `_get_escalation_metrics`, and `_get_irs_limit_metrics` are unchanged (out of scope — see research.md R3).

## Modified Pydantic models (`planalign_api/models/analytics.py`)

### `DCPlanAnalytics`
- **New field**: `resolved_first_simulation_year: int` — the year used to classify `new_hires` vs `baseline` for this scenario.
- All existing fields (`participation_rate`, `total_eligible`, `total_enrolled`, `contribution_by_year[*].{participant_count, total_eligible_count, average_deferral_rate, participation_rate, total_employer_cost, total_compensation, employer_cost_rate, employee_contribution_rate, match_contribution_rate, core_contribution_rate, total_contribution_rate}`, aggregate totals) are unchanged in *shape*; their *values* now reflect the requested cohort.

### `DCPlanComparisonResponse`
- No field changes — `analytics: List[DCPlanAnalytics]` already carries the new field per-scenario since each element is a `DCPlanAnalytics`.

## Frontend types (`planalign_studio/services/api.ts`)

- `DCPlanAnalytics` TS interface gains `resolved_first_simulation_year: number` (mirrors the Pydantic model — TS interfaces in this file are hand-kept in sync with the Python models, no codegen).
- `getDCPlanAnalytics(workspaceId, scenarioId, activeOnly, effectiveRate, cohort?)` and `compareDCPlanAnalytics(workspaceId, scenarioIds, activeOnly, effectiveRate, cohort?)` gain a `cohort: 'all' | 'new_hires' | 'baseline' = 'all'` parameter, appended to the query string only when not `'all'` (mirrors the existing `if (activeOnly) params.set(...)` omit-when-default pattern, per FR-007 / issue requirement that `all` URLs stay unchanged).

## Persisted preferences (`localStorage`, `ScenarioCostComparison.tsx`)

Existing key `planalign_comparison_{workspaceId}` JSON shape:
```ts
{ selectedIds: string[]; anchorId: string }
```
New shape (additive, backward compatible — `cohort` absent on old stored values is treated as `undefined` and defaults to `'all'`):
```ts
{ selectedIds: string[]; anchorId: string; cohort?: 'all' | 'new_hires' | 'baseline' }
```
Load-time validation: if `cohort` is present but not one of the three recognized strings, treat as absent (fall back to `'all'`) — satisfies FR-008.
