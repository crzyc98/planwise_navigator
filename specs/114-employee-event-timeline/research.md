# Research: Employee Event Timeline (Storyline) View

**Feature**: 114-employee-event-timeline | **Date**: 2026-07-15

All findings below were verified directly against the codebase and a built scenario database (not assumed). No NEEDS CLARIFICATION items remained after the spec's clarification sessions; this document records the technical decisions and their evidence.

## R1. Data sources and event inventory

**Decision**: Timeline reads three existing marts: `fct_yearly_events` (primary history), `fct_employer_match_events` (merged in), `fct_workforce_snapshot` (state strip + filters + autocomplete population).

**Evidence** (queried `dbt/simulation.duckdb` read-only):
- `fct_yearly_events.event_type` distinct values: `hire`, `termination`, `promotion`, `raise`, `enrollment`, `enrollment_change`, `eligibility`, `deferral_escalation`, `deferral_match_response`. No HCE or contribution events — confirming the spec's Clarifications.
- `fct_yearly_events` columns cover every payload field FR-004 needs: `compensation_amount`, `previous_compensation`, `employee_deferral_rate`, `prev_employee_deferral_rate`, `level_id`, `event_details`, `effective_date`, `simulation_year`, plus **`event_sequence`** (see R2).
- `fct_employer_match_events` has the same event-shaped columns (`event_id`, `event_type`, `effective_date`, `simulation_year`, `amount`, `employee_deferral_rate`, `event_payload` JSON) — merge is a UNION-shaped read, not a join.
- `fct_workforce_snapshot` carries all state-strip fields: `employment_status`, `detailed_status_code`, `current_compensation`, `prorated_annual_compensation`, `is_enrolled_flag`, `current_deferral_rate`, `participation_status`, `total_deferral_escalations`, `ytd_contributions`, `pre_tax_contributions`, `roth_contributions`, `employer_match_amount`, `employer_core_amount`, `total_employer_contributions`, `irs_limit_reached`, plus identity fields (`employee_ssn` — masked upstream, `employee_birth_date`) which per Clarification Q1 are displayed as-is.

**Alternatives considered**: Reading `int_*` models — rejected: some are orphaned/not built by the pipeline (CLAUDE.md §8), and marts are the sanctioned API read surface used by every existing service.

## R2. Deterministic ordering (FR-005)

**Decision**: Order by `simulation_year, effective_date, event_sequence, event_id`. `event_sequence` already encodes the lifecycle's natural order for same-day events; `event_id` (UUID) is the final total-order tiebreaker. Match events (no `event_sequence`) sort after primary events on the same date via `COALESCE(event_sequence, 999)`.

**Rationale**: Zero new logic — the event store already solves same-day ordering; we just have to use it.

**Alternatives considered**: Hard-coded event-type priority map in Python — rejected: duplicates what `event_sequence` encodes and drifts when event types are added.

## R3. Backend architecture

**Decision**: New `planalign_api/routers/timeline.py` + `planalign_api/services/timeline_service.py` + `planalign_api/models/timeline.py`, registered in `main.py` under the existing `/api/workspaces` prefix. Service takes `WorkspaceStorage`, resolves the scenario DB via `create_api_database_path_resolver(storage)`, and opens `duckdb.connect(path, read_only=True)` per request.

**Rationale**: This is a verbatim copy of the established pattern — `analytics.py` router → `WinnersLosersService`/`AnalyticsService` → `DatabasePathResolver`. It inherits for free: path-traversal validation on workspace/scenario IDs, multi-tenant isolation policy (`PLANALIGN_API_ALLOW_PROJECT_DB_FALLBACK`), the shared-token auth applied to all API routes, and 404/400 scenario validation helpers (`_require_completed_scenario` precedent in `comparison.py`).

**Alternatives considered**: Extending `analytics.py` — rejected: unrelated responsibility, and the router is already large. A standalone `/api/scenarios/...` path (as the issue sketched) — rejected: every scenario-scoped endpoint in this codebase is workspace-scoped (`/{workspace_id}/scenarios/{scenario_id}/...`); FR-010 was deliberately written interface-agnostic to allow this.

## R4. API surface: two endpoints, comparison composed client-side

**Decision**:
1. `GET /api/workspaces/{workspace_id}/scenarios/{scenario_id}/employees` — one endpoint serving both discovery paths: `q=` prefix param → ID autocomplete (US1); attribute params (`status`, `level`, `year`, `enrolled`, `has_escalations`, `page`, `page_size`) → filter list (US4).
2. `GET /api/workspaces/{workspace_id}/scenarios/{scenario_id}/employees/{employee_id}/timeline` — merged events + per-year state, paginated by year (`start_year`, `years` params), oldest-first.

Cross-scenario comparison (US5) needs **no third endpoint**: the frontend calls the timeline endpoint once per scenario and renders two columns. Employee-absent-in-scenario-B is just the endpoint's existing "no records" response rendered in one column.

**Rationale**: Smallest API surface that satisfies every FR (aligns with the user's "small, clear, unsurprising API" preference). Both scenarios live in different DuckDB files, so a server-side comparison endpoint would just do two independent reads anyway — no join, no server value-add. Year alignment and only-in-one-scenario marking are presentation concerns.

**Alternatives considered**: Dedicated `/comparison/timeline` endpoint (precedent: `comparison.py`) — rejected: existing comparison endpoints compute cross-scenario aggregates/diffs; this feature explicitly does visual juxtaposition only (spec Assumptions), so the server has nothing to compute. Separate `/employees/autocomplete` and `/employees/filter` endpoints — rejected: same underlying snapshot query with different WHERE clauses.

## R5. Frontend routing and deep links

**Decision**: New routes in `App.tsx` under the existing `Layout`:
- `timeline` — landing (scenario picker + search)
- `timeline/:workspaceId/:scenarioId/:employeeId` — single timeline (US3 deep link)
- Compare state via query param: `?compare=<scenarioId2>` (US5 deep link, FR-017)

**Rationale**: Studio uses `HashRouter`, so these are naturally shareable URLs (`.../#/timeline/ws1/scnA/EMP_001?compare=scnB`) with zero server routing work. Params-in-path for the canonical view + query param for the optional overlay mirrors `simulate/:scenarioId/runs/:runId/provenance` precedent.

**Alternatives considered**: Modal/panel on the Scenarios page — rejected: FR-011/FR-017 require stable shareable addresses, which forces a routed page.

## R6. Autocomplete & filter query strategy

**Decision**: Both discovery paths query `fct_workforce_snapshot` (not the event table): `SELECT DISTINCT employee_id ... WHERE upper(employee_id) LIKE upper(?) || '%' LIMIT 20` for autocomplete; attribute filters compose bound WHERE clauses over `employment_status`, `level_id`, `simulation_year`, `is_enrolled_flag`, `has_deferral_escalations` with `LIMIT/OFFSET` pagination. Input normalization (trim + case-insensitive, FR-001) happens in the service.

**Rationale**: The snapshot contains every employee that can render a timeline — including snapshot-only employees with zero events (FR-008), which an events-table search would miss. Filters evaluate snapshot state per the spec's Assumptions. DuckDB columnar scans of a 100K-row-per-year table with these predicates are well under the 2s constitution bound.

**Alternatives considered**: Searching `fct_yearly_events` — rejected: misses snapshot-only employees (violates FR-008's discovery path).

## R7. Testing strategy

**Decision**:
- **Fast unit tests** (`pytest -m fast`): `timeline_service` against small fixture DuckDB files built in-test (pattern: `tests/fixtures/database.py`), covering merge ordering, year pagination, empty/absent employees, filter composition, input normalization.
- **Integration test**: seed a tiny scenario DB with a known multi-year employee history (hire → enrollment → escalation → raise → termination + match events), hit both endpoints through the FastAPI test client, assert exact payloads (SC-002's "exact, not sampled" bar).
- **Isolated DB rule**: all test DBs under `tmp_path`; never `dbt/simulation.duckdb` (memory: validate-in-isolated-db).
- **Frontend**: verified against the running Studio app with the seeded DB (US-by-US acceptance walk, including seeded event-vs-state inconsistency for SC-003 and seeded scenario divergence for SC-007).

## R8. Performance posture

**Decision**: No caching, no precomputation. Per-request read-only connections; every query filters on `employee_id` and/or `simulation_year` with bound parameters; page size defaults (1 year per timeline page initially loaded, then prefetch remaining years; filter list 50/page) keep payloads small.

**Rationale**: Single-employee point lookups in DuckDB are milliseconds even at 100K employees × 10 years; SC-004's 3s budget is dominated by frontend render, not query time. Caching would add invalidation complexity against re-runnable scenario DBs for no measured need.
