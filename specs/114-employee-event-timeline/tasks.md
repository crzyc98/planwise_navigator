# Tasks: Employee Event Timeline (Storyline) View

**Input**: Design documents from `/specs/114-employee-event-timeline/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/timeline-api.md, quickstart.md

**Tests**: Included — the project constitution (Principle III) mandates test-first development. Each story's test tasks precede its implementation tasks.

**Organization**: Tasks are grouped by user story so each story is an independently implementable, testable increment. US1 alone is a viable MVP.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story the task belongs to (US1–US5)

## Path Conventions

Existing web-app layout: backend in `planalign_api/`, frontend in `planalign_studio/`, tests in `tests/` (per plan.md Project Structure).

---

## Phase 1: Setup

**Purpose**: Test scaffolding shared by every story — a tiny, deterministic timeline fixture database.

- [X] T001 Add a `timeline_db` fixture builder to `tests/fixtures/database.py`: creates a `tmp_path` DuckDB with minimal `fct_yearly_events`, `fct_employer_match_events`, and `fct_workforce_snapshot` tables (schemas per data-model.md "Source tables") seeded with: employee `EMP_A` (3-year history: hire → eligibility → enrollment → deferral_escalation → raise → termination, plus one match event/year, including two same-day events with distinct `event_sequence`), employee `EMP_B` (snapshot rows only, zero events), and one year where `EMP_A` has events but no snapshot row.

---

## Phase 2: Foundational (blocking all user stories)

**Purpose**: Shared models, service/router skeletons, registration, and frontend plumbing every story builds on.

- [X] T002 [P] Create Pydantic v2 models in `planalign_api/models/timeline.py`: `TimelineEvent`, `YearState`, `TimelineYear`, `EmployeeIdentity`, `EmployeeTimelineResponse`, `EmployeeSearchResult`, `EmployeeSearchResponse` — fields exactly per data-model.md.
- [X] T003 [P] Create `planalign_api/services/timeline_service.py` skeleton: `TimelineService` class taking `WorkspaceStorage` + optional `DatabasePathResolver` (constructor pattern copied from `planalign_api/services/winners_losers_service.py`), with a private `_connect(workspace_id, scenario_id)` helper that resolves the scenario DB and opens `duckdb.connect(path, read_only=True)`, raising a lookup error when unresolvable. Keep module < 600 lines, ≤ 8 public methods (Constitution II).
- [X] T004 Create `planalign_api/routers/timeline.py` with `APIRouter()`, `get_storage`/`get_timeline_service` dependencies (pattern from `planalign_api/routers/analytics.py`), and workspace/scenario 404 validation; register it in `planalign_api/main.py` with `prefix="/api/workspaces"`, tag "Timeline". No endpoints yet beyond the skeleton.
- [X] T005 [P] Add TypeScript interfaces mirroring T002's models plus client functions `searchEmployees(workspaceId, scenarioId, params)` and `getEmployeeTimeline(workspaceId, scenarioId, employeeId, params)` to `planalign_studio/services/api.ts`, using the existing `fetchWithAuth` helper.
- [X] T006 [P] Create page shell `planalign_studio/components/timeline/EmployeeTimelinePage.tsx` (scenario picker + placeholder body) and register routes in `planalign_studio/App.tsx`: `timeline` and `timeline/:workspaceId/:scenarioId/:employeeId` under the existing `Layout`; add a "Timeline" nav entry in `planalign_studio/components/Layout.tsx`.

**Checkpoint**: API boots with the empty router; Studio shows an empty Timeline page. All user stories can now proceed.

---

## Phase 3: User Story 1 — Look up an employee and read their event history (P1) 🎯 MVP

**Goal**: ID-autocomplete search → merged, deterministically ordered, year-grouped, paginated event timeline.

**Independent Test**: Search a known employee in a built scenario; rendered timeline matches a direct DuckDB query of both event stores exactly (order and values).

- [X] T007 [P] [US1] Write failing fast unit tests in `tests/test_timeline_service.py` (`@pytest.mark.fast`, using T001 fixture): merged events include both stores exactly once; ordering is `(year, effective_date, COALESCE(event_sequence,999), event_id)` and stable across calls; year pagination (`start_year`/`years`) returns only requested years while `available_years` lists all; unknown employee → `employee=None` with empty lists; employee_id normalization (whitespace/case); autocomplete prefix matching is case-insensitive, trimmed, capped at 20, and finds snapshot-only `EMP_B`.
- [X] T008 [P] [US1] Write failing API tests in `tests/test_timeline_api.py` (FastAPI TestClient against T001 fixture DB): `GET .../employees?q=` returns `EmployeeSearchResponse`; `GET .../employees/{id}/timeline` matches the contract's response shape and guarantees (contracts/timeline-api.md §2), including the not-found-as-200 case; unknown workspace/scenario → 404.
- [X] T009 [US1] Implement `TimelineService.get_timeline(...)` in `planalign_api/services/timeline_service.py`: UNION-shaped read of `fct_yearly_events` + `fct_employer_match_events` filtered by normalized `employee_id` (all values SQL-bound), ordered per FR-005, grouped into `TimelineYear`s (state left `None` for now), `available_years` from events ∪ snapshot years, `EmployeeIdentity` from the latest snapshot row, year pagination oldest-first with `years` default 3.
- [X] T010 [US1] Implement `TimelineService.search_employees(...)` autocomplete mode in `planalign_api/services/timeline_service.py`: `SELECT DISTINCT employee_id, employment_status, level_id, current_compensation, simulation_year FROM fct_workforce_snapshot WHERE upper(employee_id) LIKE upper(?) || '%'` against the latest (or given) year, ordered by `employee_id`, limit 20.
- [X] T011 [US1] Add the two GET endpoints to `planalign_api/routers/timeline.py` per contracts/timeline-api.md (`/employees` with `q/page/page_size` for now; `/employees/{employee_id}/timeline` with `start_year/years`), wiring T009/T010; make T007–T008 pass.
- [X] T012 [P] [US1] Implement `planalign_studio/components/timeline/EmployeeSearch.tsx`: debounced autocomplete input calling `searchEmployees` with `q`, suggestion list, selection navigates to `timeline/:workspaceId/:scenarioId/:employeeId`.
- [X] T013 [P] [US1] Implement `planalign_studio/components/timeline/TimelineYear.tsx` (one year's heading + vertical event list: type badge, effective date, event_details, comp/deferral/level fields per FR-004) and `planalign_studio/components/timeline/TimelineColumn.tsx` (fetches via `getEmployeeTimeline`, renders `TimelineYear`s oldest-first, "load more years" using `available_years`, distinct "no records found for this employee in this scenario" state per FR-009).
- [X] T014 [US1] Wire `EmployeeTimelinePage.tsx`: scenario picker + `EmployeeSearch` + single `TimelineColumn` driven by route params; loading and error states.

**Checkpoint**: US1 acceptance scenarios 1–3 pass end-to-end (quickstart.md "Verify in Studio" step 1). MVP shippable.

---

## Phase 4: User Story 2 — Eyeball event history against year-end state (P2)

**Goal**: Per-year state strip from `fct_workforce_snapshot` beside each year's events.

**Independent Test**: For an employee with ≥2 snapshot years, each year's strip matches a direct snapshot query; snapshot-only employee renders strips with an explicitly empty events area.

- [X] T015 [P] [US2] Extend `tests/test_timeline_service.py` with failing tests: `TimelineYear.state` populated from the snapshot per data-model.md `YearState` fields; event-only year → `state=None`; snapshot-only `EMP_B` → years render with `events=[]` and populated state (FR-008); identity fields (`employee_ssn` as stored, `employee_birth_date`) present per Clarification Q1.
- [X] T016 [US2] Implement the `YearState` query in `TimelineService.get_timeline(...)` (`planalign_api/services/timeline_service.py`): one snapshot read for the requested years, mapped into each `TimelineYear.state`; make T015 pass.
- [X] T017 [US2] Add the state strip to `planalign_studio/components/timeline/TimelineYear.tsx`: compact panel beside the year's events showing status, comp, level, age/tenure, eligibility, enrollment, deferral rate, escalation count, contribution totals, employer match/core amounts, IRS-limit flag; explicit "no events this year" marker when `events` is empty; identity header (SSN/birth/hire date) added to `TimelineColumn.tsx`.

**Checkpoint**: US2 acceptance scenarios pass (quickstart.md step 2 cross-check; SC-003 seeded-inconsistency check).

---

## Phase 5: User Story 3 — Deep-link into an employee's timeline (P3)

**Goal**: Stable shareable URL opens straight to a populated timeline.

**Independent Test**: Open `/#/timeline/<ws>/<scn>/<emp>` in a fresh tab → populated timeline; bad employee_id → FR-009 message.

- [X] T018 [US3] Harden route-driven loading in `planalign_studio/components/timeline/EmployeeTimelinePage.tsx`: on direct navigation, hydrate scenario context from route params (no prior page state assumed), URL-decode + trim `employeeId`, sync picker/search state from the URL, and keep the URL canonical when the user searches (navigate, don't just set state).
- [X] T019 [P] [US3] Add a reusable `timelineUrl(workspaceId, scenarioId, employeeId)` helper in `planalign_studio/services/api.ts` and a "copy link" affordance on the timeline page; use the helper anywhere an employee_id is rendered as a link (US4 list rows will consume it).

**Checkpoint**: US3 acceptance scenarios pass (quickstart.md step 3).

---

## Phase 6: User Story 4 — Find employees by filtering on attributes (P4)

**Goal**: Attribute filter list (status/level/year/enrolled/escalations) with pagination, rows click through to timelines.

**Independent Test**: A filter combination with a known population returns exactly the matching employees (verified against a direct snapshot query); clicking a row opens that timeline.

- [X] T020 [P] [US4] Extend `tests/test_timeline_service.py` + `tests/test_timeline_api.py` with failing tests: each filter param (`status`, `level`, `year`, `enrolled`, `has_escalations`) composes correctly and ANDs with `q`; `year` defaults to the latest snapshot year; pagination (`page`/`page_size`, `total`) is correct and deterministic (ordered by `employee_id`); no-match → `results=[], total=0`; `page_size` capped at 200.
- [X] T021 [US4] Extend `TimelineService.search_employees(...)` in `planalign_api/services/timeline_service.py` with bound-parameter filter composition, count query for `total`, and LIMIT/OFFSET pagination; add the filter query params to the `/employees` endpoint in `planalign_api/routers/timeline.py` per contracts/timeline-api.md §1; make T020 pass.
- [X] T022 [US4] Add the filter UI to `planalign_studio/components/timeline/EmployeeSearch.tsx` (or a sibling `EmployeeFilterList.tsx` if EmployeeSearch would exceed ~200 lines): filter controls, paginated result table with FR-014's identifying columns, plain no-match message, rows link via T019's `timelineUrl`.

**Checkpoint**: US4 acceptance scenarios pass (quickstart.md step 4; SC-006 under-one-minute walk).

---

## Phase 7: User Story 5 — Compare the same employee across two scenarios (P5)

**Goal**: Side-by-side two-scenario columns aligned by year, deep-linkable via `?compare=`.

**Independent Test**: Two scenarios from the same census with a seeded design difference: comparison shows both columns faithful to their own DBs, divergence identifiable at its year; employee absent from scenario B renders the not-found message in that column only.

- [X] T023 [US5] Add comparison mode to `planalign_studio/components/timeline/EmployeeTimelinePage.tsx`: a "compare with…" scenario picker (excluding the current scenario, and only offering completed scenarios), driven by/writing the `?compare=<scenarioId2>` query param; renders two labeled `TimelineColumn`s side by side (stacked on narrow viewports).
- [X] T024 [US5] Implement year alignment across the two columns: compute the union of both responses' `available_years` ascending, render each year row in both columns, and mark years present in only one scenario as "not simulated in this scenario"; per-column FR-009 message when `employee` is null in one response. Extract shared alignment logic into `planalign_studio/components/timeline/compareYears.ts` if it exceeds a trivial inline computation.
- [X] T025 [US5] Extend T019's URL helper + copy-link to include `compare` when active, and verify a pasted comparison URL reproduces the exact two-column view in a fresh session (FR-017).

**Checkpoint**: US5 acceptance scenarios pass (quickstart.md step 5; SC-007 seeded-divergence check).

---

## Phase 8: Polish & Cross-Cutting

- [ ] T026 [P] Run the full quickstart verification (`specs/114-employee-event-timeline/quickstart.md`) against two isolated scenario DBs built from the same census with a seeded plan-design difference; record the SC-002 exactness diff, SC-003 and SC-007 outcomes in the PR description.
- [ ] T027 [P] Performance check per SC-004/Constitution VI: time the timeline and filter endpoints against a full-size isolated DB (`planalign simulate 2025-2029`); confirm first-year page < 3s end-to-end and queries < 2s; if breached, bound the fix to query shape (no caching — research.md R8).
- [ ] T028 Run `pytest -m fast` (confirm suite still < 10s), full `pytest tests/test_timeline_service.py tests/test_timeline_api.py`, and frontend type-check (`cd planalign_studio && npx tsc --noEmit` or the project's existing check script); fix anything red.
- [ ] T029 Code quality pass: `timeline_service.py` < 600 lines / ≤ 8 public methods, cognitive complexity ≤ 15, no bare excepts, no `any` in new TypeScript; update `CHANGELOG.md` under the next unreleased version.

---

## Dependencies

```text
Phase 1 (T001) ──► Phase 2 (T002–T006) ──► US1 (T007–T014) ──► US2 (T015–T017)
                                                │                    │
                                                ├──► US3 (T018–T019) │
                                                │         │          │
                                                ├──► US4 (T020–T022, needs T019 for row links)
                                                │
                                                └──► US5 (T023–T025, needs US1's TimelineColumn;
                                                          US2's state strip enriches but doesn't block)
Polish (T026–T029) after all implemented stories.
```

- **US1 is the only hard prerequisite** for US2/US3/US5 (they extend its endpoint/components). US4's backend (T020–T021) depends only on Phase 2 + T010 and can proceed in parallel with US2/US3; its UI task T022 consumes T019.
- Within Phase 2: T002, T003, T005, T006 are parallel; T004 needs T003.

## Parallel Execution Examples

- **Phase 2**: T002 ∥ T003 ∥ T005 ∥ T006 (four different files).
- **US1**: T007 ∥ T008 (different test files) → T009 → T010 → T011; frontend T012 ∥ T013 while backend lands, then T014.
- **After US1**: US2 backend (T015–T016), US3 (T018), and US4 backend (T020–T021) are three independent streams touching disjoint code paths.

## Implementation Strategy

**MVP = Phase 1 + Phase 2 + US1 (T001–T014)**: a searchable, exact, paginated event timeline — already replaces the manual-query workflow. Ship/demo at that checkpoint.

Then increments in priority order: US2 (state strip → diagnostic tool), US3 (shareable links), US4 (attribute discovery), US5 (cross-scenario comparison). Each checkpoint is independently testable per its story's criteria; stop at any checkpoint with a coherent feature.

## Task Summary

| Phase | Tasks | Count |
|-------|-------|-------|
| Setup | T001 | 1 |
| Foundational | T002–T006 | 5 |
| US1 (P1, MVP) | T007–T014 | 8 |
| US2 (P2) | T015–T017 | 3 |
| US3 (P3) | T018–T019 | 2 |
| US4 (P4) | T020–T022 | 3 |
| US5 (P5) | T023–T025 | 3 |
| Polish | T026–T029 | 4 |
| **Total** | | **29** |
