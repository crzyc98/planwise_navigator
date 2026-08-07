# Phase 0 Research: New-Hire Cohort Isolation for Cost Comparison

## R1: Where to resolve and cross-check the "first simulation year"

**Decision**: Resolve `first_simulation_year = MIN(simulation_year) FROM fct_workforce_snapshot` once per open DuckDB connection inside `AnalyticsService.get_dc_plan_analytics`, immediately after `conn = duckdb.connect(...)`. Cross-check it against the most recent row's `start_year` in the `run_metadata` table (`planalign_orchestrator.run_metadata.RUN_METADATA_TABLE = "run_metadata"`, Feature 109, `planalign_orchestrator/run_metadata.py:45-51`) if that table exists in the scenario database; log a warning (not an error) on mismatch or on a missing table (older databases predate Feature 109).

**Rationale**: The issue explicitly cites "Feature 109" for the cross-check, which is the DuckDB `run_metadata` table (`start_year INTEGER NOT NULL`), not the JSON-file-based `run_metadata.json` surfaced separately by `planalign_api/services/current_result.py` and already exposed as `ResolvedDatabasePath.start_year` on the resolver result. The two are different mechanisms with the same name: the JSON pointer is written by the orchestrator's run-execution service for API polling/history, while the DuckDB table is the config-drift-detection ledger written by `check_and_record_run` at the start of every simulation run against that exact database. The DuckDB table is the one actually inside the connection AnalyticsService already opens, so cross-checking it costs one extra query on an already-open connection — no new dependency. `ResolvedDatabasePath.start_year` is a convenient secondary signal but is sourced from files the analytics service doesn't currently read; it is not required for this feature and pulling it in would mean plumbing a second value through `DatabasePathResolver.resolve()` for no correctness gain over the `MIN(simulation_year)` query, which is what actually determines cohort membership.

**Resolution logic**:
```sql
SELECT start_year FROM run_metadata ORDER BY run_timestamp DESC LIMIT 1
```
compared to
```sql
SELECT MIN(simulation_year) FROM fct_workforce_snapshot
```
If the `run_metadata` table doesn't exist (`duckdb.CatalogException` / equivalent), skip the cross-check silently (this is the pre-Feature-109 case, not an anomaly). If it exists and the two values differ, `logger.warning(...)` with both values and the scenario/workspace ids, then proceed using `MIN(simulation_year)` from `fct_workforce_snapshot` as the classification source of truth — it's the value that actually determines which employees fall in which cohort, so the classification must be self-consistent with the data being classified, not with a possibly-stale recorded intent.

**Alternatives considered**:
- *Always use `run_metadata.start_year` for classification*: rejected — if a database was re-run over a shifted year range without a fresh `run_metadata` row (or the row is stale), this would reclassify part of the census based on a wrong cutoff even though `fct_workforce_snapshot` itself is internally consistent. The snapshot's own `MIN(simulation_year)` is definitionally never wrong about what's in the snapshot.
- *Resolve per-query (inside each SQL string)*: rejected per the issue ("resolve once per scenario connection, not per query") — wasteful and risks the two queries racing against different data if anything mutates between them (won't happen for a `read_only=True` connection, but resolving once keeps the code and the invariant obviously true rather than incidentally true).

## R2: How to compose the cohort predicate with the existing `active_only` filter

**Decision**: Build a small predicate-fragment helper on `AnalyticsService` — `_cohort_predicate(cohort: str, first_year: int) -> str` — returning `""`, `"employee_hire_date >= DATE '{first_year}-01-01'"`, or `"employee_hire_date < DATE '{first_year}-01-01'"` for `all`/`new_hires`/`baseline` respectively (using a Python-interpolated integer, not a user-controlled string — `cohort` itself is validated to a `Literal` by FastAPI before it reaches the service, and `first_year` is an `int` from `MIN(simulation_year)`, so there is no injection surface). Combine fragments with existing `status_filter` fragments using a small `_combine_where(*fragments)` helper that joins non-empty fragments with `AND` and prefixes `WHERE`/`AND` correctly, replacing the current ad hoc `WHERE ...` / `AND ...` string juggling in `_get_participation_summary` and `_get_contribution_by_year`.

**Rationale**: `_get_participation_summary` currently prefixes its fragment with `AND` (assumes a `WHERE simulation_year = final_year.max_year` already present), while `_get_contribution_by_year` prefixes with `WHERE` (no other filter present) or leaves it empty. A single combinator removes the duplicated "is this the first condition or not" logic and is the shape the issue asks for ("Compose it with the existing `active_only` status filter rather than string-concatenating a second `WHERE`").

**Alternatives considered**:
- *Pass `cohort` straight into an f-string per call site*: rejected — duplicates the date-boundary logic in two places and makes the `all`/`new_hires`/`baseline` semantics implicit at each call site instead of centralized.
- *Use a DuckDB `EXTRACT(YEAR FROM employee_hire_date) >= {first_year}` predicate (as literally written in the issue's SQL sketch)*: functionally equivalent to a date-boundary comparison but `employee_hire_date >= DATE 'first_year-01-01'` is sargable and consistent with how the rest of the codebase compares dates; kept `EXTRACT(YEAR ...)` out of the generated SQL to avoid a per-row function call across the whole table when a direct range comparison does the same job.

## R3: Functions in scope for cohort filtering

**Decision**: Cohort filtering applies to exactly `_get_participation_summary` and `_get_contribution_by_year` (and, transitively, `_compute_grand_totals`, which only consumes `_get_contribution_by_year`'s output) — matching the issue's explicit "Where it plugs in" list. `_get_deferral_distribution`, `_get_deferral_distribution_all_years`, `_get_escalation_metrics`, and `_get_irs_limit_metrics` are NOT cohort-filtered in this pass.

**Rationale**: The issue's denominator checklist ("participation_rate, participant_count, total_eligible_count, total_compensation → employer_cost_rate, employee/match/core/total_contribution_rate, average_deferral_rate") maps exactly to fields produced by those two functions. The issue's acceptance criteria don't require the deferral-distribution buckets, escalation metrics, or IRS-limit metrics to move with the cohort, and cohorting them isn't necessary to satisfy "new_hires + baseline sums to all" for cost (SC-002) or to unblock the Cost Comparison view, which doesn't render those fields. Expanding scope to all four risks under-delivering the two acceptance-critical functions correctly in favor of breadth.

**Alternatives considered**: Cohort-filtering everything for uniformity — rejected as scope creep beyond the issue and this spec's acceptance criteria; the predicate helper (R2) is written so a follow-up can thread `cohort` into those functions later with the same helper, satisfying the issue's "written so those can adopt it later" intent without doing the work now.

## R4: API surface

**Decision**: Add `cohort: Literal["all", "new_hires", "baseline"] = Query("all")` to both `GET /{workspace_id}/scenarios/{scenario_id}/analytics/dc-plan` and `GET /{workspace_id}/analytics/dc-plan/compare` in `planalign_api/routers/analytics.py`, passed straight through to `AnalyticsService.get_dc_plan_analytics(..., cohort=cohort)`. FastAPI's `Literal` query-param validation already returns 422 for out-of-enum values with zero extra code — this is the same mechanism Pydantic uses elsewhere in the codebase and satisfies FR-013 for free.

**Rationale**: Matches the existing `active_only`/`effective_rate` pattern exactly; no new dependency, no new response model needed (the existing `DCPlanAnalytics`/`DCPlanComparisonResponse` shapes are unchanged — only the values inside them shift when `cohort` is non-default).

**Alternatives considered**: A separate `/compare/cohort` endpoint — rejected, unnecessary duplication when a query parameter with a 3-value enum is sufficient and keeps one response contract.

## R5: Frontend wiring

**Decision**: Add `cohort: 'all' | 'new_hires' | 'baseline'` state to `ScenarioCostComparison.tsx`, default `'all'`. Thread it into `compareDCPlanAnalytics(workspaceId, scenarioIds, cohort)` (new positional or options param in `api.ts`) and add it to the `fetchComparison` `useCallback` dependency array so a cohort change re-fetches. Persist it in the same `saveComparisonPrefs`/`loadComparisonPrefs` JSON blob (`{ selectedIds, anchorId, cohort }`), validating on load that the stored value is one of the three recognized strings before applying it (falls back to `'all'` otherwise — satisfies FR-008 and the edge case for a corrupted/future-version stored value). Render a segmented control next to the existing Annual/Cumulative toggle (same Tailwind classes, `planalign_studio/components/ScenarioCostComparison.tsx:927-941` is the pattern to copy). Add a small badge component shown next to the "Employer Cost Trends" and "Incremental Costs" chart titles and the "Multi-Year Cost Matrix" table header whenever `cohort !== 'all'`, reusing the resolved first-simulation-year (surfaced from the API response — see Data Model) for the label text "Hired during the simulation ({year}+)" / "Starting census". Update `tableToTSV` to prepend a cohort-label comment line when `cohort !== 'all'`.

**Rationale**: Reuses every existing mechanism (prefs blob, toggle styling, TSV builder) rather than introducing new state-management or persistence primitives, matching the codebase's existing patterns per CLAUDE.md guidance to match existing conventions before introducing new abstractions.

**Alternatives considered**: A separate localStorage key for cohort — rejected, fragments prefs across two keys for no benefit and risks the two getting out of sync on reset/import flows that already exist for the current single-key blob.

## R6: Surfacing "resolved first simulation year" to the frontend

**Decision**: Add `resolved_first_simulation_year: int` to `DCPlanAnalytics` (populated for every response, even under `cohort=all`, so the frontend always has it without a second cohort-specific field or endpoint).

**Rationale**: The UI must render "Hired during the simulation (2025+)" with a real, per-scenario year (FR-009), and the value is already computed once per request as part of R1 — exposing it costs one new response field, no extra query.

**Alternatives considered**: Recompute the cutoff year in the frontend from `contribution_by_year[0].year` — rejected: that's the first *simulated* year in the response, which is correct only by coincidence (it happens to equal `MIN(simulation_year)` today), and silently diverges if that assumption ever breaks (e.g. a future feature that returns a partial year range). Sourcing it from the same backend computation that defines cohort membership keeps the label and the classification provably consistent.
