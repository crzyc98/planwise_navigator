# Tasks: New-Hire Cohort Isolation for Cost Comparison

**Input**: Design documents from `/specs/134-new-hire-cohort/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/api-contract.md, contracts/ui-contract.md, quickstart.md

**Tests**: Included. `plan.md`'s Constitution Check commits to contract tests (Principle III), and spec.md's Success Criteria (SC-002, SC-003) explicitly require the cost-sum invariant and the `cohort=all` regression to be "verified by an automated test."

**Organization**: Tasks are grouped by user story (US1/US2/US3, from spec.md's priorities) to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies on incomplete tasks)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- File paths are exact and repo-relative

## Path Conventions

Existing web-application split — no new top-level directories:
- Backend: `planalign_api/routers/`, `planalign_api/services/`, `planalign_api/models/`
- Frontend: `planalign_studio/services/`, `planalign_studio/components/`
- Tests: `tests/`, `tests/api/`

---

## Phase 1: Setup

**Not applicable.** This feature adds a query parameter and threads it through four existing files plus tests — no new dependencies, scaffolding, or project structure changes (per plan.md's "Structure Decision").

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Backend cohort-predicate machinery and the API client plumbing that every user story's UI/tests build on.

**⚠️ CRITICAL**: No user story work can begin until this phase is complete.

- [X] T001 [P] Add `_cohort_predicate(cohort, first_year)` and `_combine_where(*fragments)` static helper methods to `AnalyticsService` in `planalign_api/services/analytics_service.py` (research.md R2) — `_cohort_predicate` returns `""` / `employee_hire_date >= DATE '{first_year}-01-01'` / `employee_hire_date < DATE '{first_year}-01-01'` for `all`/`new_hires`/`baseline`; `_combine_where` joins non-empty fragments with `AND`, prefixing `WHERE`/`AND` correctly

- [X] T002 Add `_resolve_first_simulation_year(conn, workspace_id, scenario_id)` method to `AnalyticsService` in `planalign_api/services/analytics_service.py` (research.md R1) — runs `SELECT MIN(simulation_year) FROM fct_workforce_snapshot` as the classification source of truth, cross-checks against `SELECT start_year FROM run_metadata ORDER BY run_timestamp DESC LIMIT 1` when that table exists, and `logger.warning(...)` (with both values and workspace/scenario ids) on mismatch — never raises and never overrides the classification value; skip the cross-check silently if `run_metadata` doesn't exist (pre-Feature-109 databases)

- [X] T003 Thread `cohort: Literal["all", "new_hires", "baseline"] = "all"` through `get_dc_plan_analytics`, `_get_participation_summary`, and `_get_contribution_by_year` in `planalign_api/services/analytics_service.py` (`analytics_service.py:109-334`), composing the cohort predicate (T001) with each method's existing `active_only`/`status_filter` fragment via `_combine_where` — depends on T001, T002

- [X] T004 [P] Add `resolved_first_simulation_year: int` field to the `DCPlanAnalytics` Pydantic model in `planalign_api/models/analytics.py` (`analytics.py:105-181`), per data-model.md

- [X] T005 Populate `resolved_first_simulation_year` (from T002) on the `DCPlanAnalytics` object constructed in `get_dc_plan_analytics` (`planalign_api/services/analytics_service.py:146-173`) — always populated regardless of requested `cohort` — depends on T002, T003, T004

- [X] T006 Add `cohort: Literal["all", "new_hires", "baseline"] = Query("all")` to both `get_dc_plan_analytics` and `compare_dc_plan_analytics` endpoints in `planalign_api/routers/analytics.py` (`:35-92`, `:99-182`), passed straight through to `AnalyticsService.get_dc_plan_analytics(..., cohort=cohort)` — matches the existing `active_only`/`effective_rate` pattern; FastAPI's `Literal` validation rejects out-of-enum values with 422 for free (FR-013) — depends on T003

- [X] T007 [P] Add `resolved_first_simulation_year: number` field to the `DCPlanAnalytics` TS interface in `planalign_studio/services/api.ts` (`:1477-1504`)

- [X] T008 Add a `cohort: 'all' | 'new_hires' | 'baseline' = 'all'` parameter to `getDCPlanAnalytics()` and `compareDCPlanAnalytics()` in `planalign_studio/services/api.ts` (`:1512-1543`), appended to the query string only when not `'all'` (mirrors the existing `if (activeOnly) params.set(...)` omit-when-default pattern — required for FR-007's byte-identical-URL guarantee) — depends on T006, T007

**Checkpoint**: Backend accepts and applies `cohort`; frontend API client can request it. User story implementation can now begin.

---

## Phase 3: User Story 1 - Isolate the cost of new hires under a plan design change (Priority: P1) 🎯 MVP

**Goal**: A user can select the "Hired during the simulation" or "Starting census" cohort in Cost Comparison and see the cost matrix, incremental-cost chart, and methodology panel reflect only that cohort, with the selection persisted across reload — including the single-scenario DC Plan Analytics view (FR-006).

**Independent Test**: Open Cost Comparison for two completed scenarios, switch the cohort control through all three values, confirm reported employer cost/rate/participation numbers shift accordingly for every scenario and year; reload the page and confirm the cohort selection is restored.

### Tests for User Story 1

- [X] T009 [US1] Contract tests in `tests/api/test_dc_plan_analytics_contract.py` (new file, follows the `tests/api/test_*_contract.py` convention from feature 115): (a) a request with no `cohort` param and a request with `cohort=all` produce byte-identical JSON except for the new `resolved_first_simulation_year` field (FR-007, api-contract.md "Regression guard"); (b) `cohort=not_a_real_value` returns `422` on both endpoints (FR-013) — depends on Foundational (T006)

### Implementation for User Story 1

- [X] T010 [P] [US1] Add `cohort` state (default `'all'`) to `ScenarioCostComparison.tsx`, and add it to the `fetchComparison` `useCallback` dependency array so changing cohort triggers a full re-fetch and replace of `comparisonData` for every selected scenario (FR-014)

- [X] T011 [US1] Add a segmented cohort control ("All employees" / "New hires" / "Starting census") to `ScenarioCostComparison.tsx`, in the same row as the existing Annual/Cumulative toggle (`:927-941`), reusing its `bg-gray-100 p-1 rounded-lg` styling — wired to the `cohort` state from T010 — depends on T010

- [X] T012 [US1] Pass `cohort` into the `compareDCPlanAnalytics()` call inside `fetchComparison` in `ScenarioCostComparison.tsx` — depends on T010, T008

- [X] T013 [US1] Persist `cohort` in the `saveComparisonPrefs`/`loadComparisonPrefs` JSON blob (`ScenarioCostComparison.tsx:63-83`, key `planalign_comparison_{workspaceId}`) — additive to `{ selectedIds, anchorId }`; on load, treat a stored `cohort` that isn't one of the three recognized strings as absent and fall back to `'all'` without throwing or blocking `selectedIds`/`anchorId` restoration (FR-008) — depends on T010

- [X] T014 [P] [US1] Add `cohort` state and the same segmented control to the single-scenario `DCPlanAnalytics.tsx` view, threading it into its `getDCPlanAnalytics()` call (`DCPlanAnalytics.tsx:223`) so the single-scenario view supports the same cohort filter as Cost Comparison (FR-006) — depends on T008

**Checkpoint**: User Story 1 is fully functional — cohort selection re-fetches and displays cohort-scoped data in both views, and persists across reload.

---

## Phase 4: User Story 2 - Trust that cohort figures are internally consistent (Priority: P1)

**Goal**: New-hire cost + starting-census cost sum exactly to the all-employees cost for every scenario/year, and every rate is recomputed within the selected cohort rather than sliced from population-wide totals — proven by automated tests, not just visual inspection.

**Independent Test**: For a given scenario/year, sum new-hire and starting-census employer cost and confirm it equals the all-employees cost; confirm participation rate, average deferral rate, and contribution-rate percentages differ between cohorts.

### Tests for User Story 2

- [X] T015 [P] [US2] Unit tests in `tests/test_analytics_service.py` for `_cohort_predicate`, `_combine_where`, and `_resolve_first_simulation_year`: correct SQL fragment per cohort value; `run_metadata`/`fct_workforce_snapshot` mismatch logs a warning and still returns the snapshot-derived year (never raises, never silently switches source); missing `run_metadata` table skips the cross-check silently — depends on Foundational (T001, T002)

- [X] T016 [US2] Contract test in `tests/api/test_dc_plan_analytics_contract.py`: for every simulation year in a multi-year fixture scenario, `contribution_by_year[year].total_employer_cost` for `cohort=new_hires` plus `cohort=baseline` equals `cohort=all`, within `abs(delta) < 0.01` (FR-005, SC-002, api-contract.md invariant) — depends on T009

- [X] T017 [US2] Contract test in `tests/api/test_dc_plan_analytics_contract.py`: `participation_rate`, `average_deferral_rate`, and the four `*_contribution_rate` fields differ between `cohort=new_hires` and `cohort=baseline` responses for the same scenario/year — proves per-cohort recomputation rather than a shared-aggregate slice (FR-004) — depends on T009

**Checkpoint**: The cost-sum invariant and per-cohort rate recomputation are guarded by automated tests — both P1 stories are independently verified.

---

## Phase 5: User Story 3 - Understand what's being shown (Priority: P2)

**Goal**: Any cohort-filtered figure — on screen or in a TSV export — is visibly labeled as filtered, and a zero-employee cohort cell renders an explicit empty state instead of a misleading `$0`.

**Independent Test**: With a non-default cohort active, confirm a badge appears on the cost matrix and incremental-cost chart, the methodology panel names the cohort, copy-to-TSV includes the cohort label, and a scenario/year with zero cohort-matching employees shows an explicit empty state.

### Tests for User Story 3

- [X] T018 [P] [US3] Contract test in `tests/api/test_dc_plan_analytics_contract.py`: a scenario/year with `total_eligible_count == 0` for the selected cohort is distinguishable in the response from a cohort with eligible employees but `$0` cost (FR-012) — depends on T009

### Implementation for User Story 3

- [X] T019 [US3] Add a cohort badge/pill in `ScenarioCostComparison.tsx`, shown only when `cohort !== 'all'`, styled like the existing chip pattern (`:900-905`, distinct from that anchor/baseline chip style per ui-contract.md); render next to the "Employer Cost Trends" title (`:923`) and the "Incremental Costs vs. {anchor}" title (`:1018-1020`), reading `Hired during the simulation ({resolved_first_simulation_year}+)` for `new_hires` or `Starting census` for `baseline` — depends on T011

- [X] T020 [US3] Render the same cohort badge next to the "Multi-Year Cost Matrix" header (`ScenarioCostComparison.tsx:1083`) — depends on T019

- [X] T021 [US3] Update the "How these figures are measured" methodology panel (`ScenarioCostComparison.tsx:1276-1297`) to insert one sentence naming the active cohort and its definition when `cohort !== 'all'` (FR-010) — depends on T011

- [X] T022 [US3] Prepend a `# Cohort: {label}` comment line to `tableToTSV()` output (`ScenarioCostComparison.tsx:598-634`) when `cohort !== 'all'`, before the existing header row (FR-011) — depends on T011

- [X] T023 [US3] Prepend a `# Cohort: {label}` comment line to `compensationTableToTSV()` output (`ScenarioCostComparison.tsx:644-680`) when `cohort !== 'all'` (FR-011) — depends on T011

- [X] T024 [US3] Render an explicit empty-state indicator ("—" / "No employees in cohort") — distinguishable from a computed `$0` — in the cost matrix cells and chart data points where `total_eligible_count === 0` for the selected cohort, in `ScenarioCostComparison.tsx` (FR-012) — depends on T011

**Checkpoint**: All cohort-filtered surfaces (screen + export) are visibly labeled; zero-cohort cells never read as a computed total.

---

## Phase 6: Polish & Cross-Cutting Concerns

- [X] T025 Run `quickstart.md` end-to-end: `planalign batch --scenarios baseline generous_match --clean`, confirm DuckDB ground truth (step 2), API responses across all three cohort values including the `422` case (step 3), and the Studio UI badge/persistence/TSV behavior (step 4) — depends on all prior phases

- [X] T026 Run `pytest tests/test_analytics_service.py tests/api/test_dc_plan_analytics_contract.py -v` and `pytest -m fast` to confirm no regression in existing `active_only`/`effective_rate` behavior — depends on T025

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: N/A
- **Foundational (Phase 2)**: No dependencies — BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational — no dependency on US2/US3
- **User Story 2 (Phase 4)**: Depends on Foundational only (its tests exercise the backend predicate directly; does not require US1's UI) — can run in parallel with US1
- **User Story 3 (Phase 5)**: Depends on Foundational **and** US1's cohort control (T010, T011) since the badge/methodology/TSV/empty-state tasks all extend the same `cohort` state and control US1 introduces
- **Polish (Phase 6)**: Depends on US1 + US2 + US3 complete

### User Story Dependencies

- **US1 (P1)**: Can start after Foundational. No dependency on US2 or US3.
- **US2 (P1)**: Can start after Foundational, in parallel with US1 — its tests hit the API/service directly and don't require US1's frontend control to exist.
- **US3 (P2)**: Can start after Foundational, but its tasks build on US1's `cohort` state/control (T010, T011) in the same file — start after US1's Implementation tasks land.

### Within Each User Story

- Tests before/alongside implementation (all contract/unit tests here assert backend behavior that Foundational already implements, so they can be written immediately after Phase 2)
- Same-file tasks (e.g. all of US1's and US3's `ScenarioCostComparison.tsx` edits) run sequentially, not in parallel, to avoid conflicting edits — only genuinely different-file tasks are marked `[P]`

### Parallel Opportunities

- T001, T004, T007 (three different files) can start together once Phase 2 begins
- US1 and US2 can be worked in parallel once Foundational is done (different files: frontend components vs. backend/unit tests)
- T010 and T014 (`ScenarioCostComparison.tsx` vs. `DCPlanAnalytics.tsx`) can run in parallel within US1
- T015 (unit tests) can run in parallel with T016/T017 (contract tests) within US2 — different files

---

## Parallel Example: Foundational Phase

```bash
# Launch independent-file foundational tasks together:
Task: "Add _cohort_predicate and _combine_where helpers in planalign_api/services/analytics_service.py"
Task: "Add resolved_first_simulation_year field to DCPlanAnalytics in planalign_api/models/analytics.py"
Task: "Add resolved_first_simulation_year field to DCPlanAnalytics TS interface in planalign_studio/services/api.ts"
```

## Parallel Example: User Story 1 + User Story 2

```bash
# Once Foundational is complete, these can run in parallel (different files):
Task: "Add cohort state + segmented control to ScenarioCostComparison.tsx" (US1)
Task: "Unit tests for _cohort_predicate/_combine_where/_resolve_first_simulation_year in tests/test_analytics_service.py" (US2)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 2: Foundational (backend predicate + API client plumbing)
2. Complete Phase 3: User Story 1 (cohort control, re-fetch, persistence, single-scenario view)
3. **STOP and VALIDATE**: Switch cohort in Cost Comparison, confirm numbers shift and survive reload
4. This alone satisfies SC-001 and SC-005

### Incremental Delivery

1. Foundational → backend/API-client ready, no user-visible change yet (still `cohort=all` byte-identical, FR-007)
2. Add US1 → cohort selection works end-to-end → demo-able MVP
3. Add US2 → automated tests prove the sum invariant and per-cohort rate recomputation (can land alongside or right after US1; no UI dependency)
4. Add US3 → badges, methodology copy, TSV labeling, empty states → closes the "misread risk" gap
5. Polish → quickstart.md full run + regression suite

### Parallel Team Strategy

1. One person completes Foundational (Phase 2) — small, sequential-heavy on `analytics_service.py`
2. Once done: Developer A takes US1 (frontend cohort control), Developer B takes US2 (backend/contract tests) in parallel
3. Developer A continues into US3 once US1's `cohort` state/control land (US3 depends on that same file's state)

---

## Notes

- `[P]` tasks touch different files with no dependency on an incomplete task
- Every `analytics_service.py` and `ScenarioCostComparison.tsx` edit within a phase is sequential (same file) even when not explicitly noted as depending on the prior task's line numbers
- `cohort=all` must remain byte-identical to pre-feature behavior end-to-end (FR-007) — T009 is the regression guard; do not let any Foundational or US1 task special-case `all` differently from "no predicate"
- Commit after each task or logical group; stop at each phase checkpoint to validate independently
