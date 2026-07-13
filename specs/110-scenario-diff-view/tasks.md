# Tasks: Studio Two-Scenario Diff View

**Input**: Design documents from `/specs/110-scenario-diff-view/`
**Prerequisites**: `plan.md`, `spec.md`, `research.md`, `data-model.md`, `contracts/comparison-api.yaml`, `quickstart.md`

**Tests**: Required by the feature request and project constitution. Write each listed test first and confirm it fails for the intended missing behavior before implementing that behavior.

**Organization**: Tasks are grouped by user story so each story can be implemented and validated as a coherent increment.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel with adjacent marked tasks because it changes different files and has no dependency on their incomplete work.
- **[Story]**: Maps the task to User Story 1, 2, or 3.
- Every task names the exact file or validation document it affects.

## Phase 1: Setup (Shared Test Infrastructure)

**Purpose**: Establish deterministic, isolated fixtures without adding dependencies or touching the shared development database.

- [X] T001 Create reusable temporary workspace, scenario, snapshot/event-table, and optional `run_metadata` fixture builders in `tests/fixtures/scenario_diff.py`, ensuring every DuckDB path is under pytest `tmp_path` and connections are closed explicitly

---

## Phase 2: Foundational (Blocking Typed Contracts)

**Purpose**: Define and test the shared response shapes consumed by all three stories.

**Critical**: Complete this phase before user-story implementation.

- [X] T002 Write failing Pydantic contract tests for additive `avg_compensation`, configuration deltas, nullable provenance, `seeds_match`, and drift reasons in `tests/test_comparison_api.py`
- [X] T003 [P] Add `avg_compensation`, `ConfigDelta`, `ScenarioProvenance`, and `ConfigDiffResponse` Pydantic models and exports in `planalign_api/models/comparison.py` and `planalign_api/models/__init__.py` to match `specs/110-scenario-diff-view/contracts/comparison-api.yaml`
- [X] T004 [P] Replace the comparison payload `any` fields with explicit workforce, event, DC-plan, summary-delta, config-delta, and provenance TypeScript interfaces in `planalign_studio/services/api.ts`, and add the typed config-diff client signature without changing existing callers

**Checkpoint**: Backend and frontend share an additive, typed contract; no scenario behavior has been implemented yet.

---

## Phase 3: User Story 1 - Understand What Changed Between Two Scenarios (Priority: P1) — MVP

**Goal**: Show effective setting differences beside five year-by-year A-vs-B metric panels, with scenario A as the baseline and no client-side metric re-aggregation.

**Independent Test**: Compare two completed scenarios that differ only in `employer_match.active_formula`; verify exactly that effective-setting delta appears, employer-match cost diverges by year, and headcount plus active-employee average compensation have zero deltas for every common year.

### Tests for User Story 1

- [X] T005 [P] [US1] Extend temporary snapshot coverage with failing active-only average-compensation value and B-minus-A delta assertions, including terminated rows and a year with no active employees, in `tests/test_comparison_dc_plan.py`
- [X] T006 [P] [US1] Write failing service tests for exact merged-config reuse, nested mapping differences, `changed`/`only_a`/`only_b`, atomic sequence comparison, deterministic path sorting, cosmetic exclusions, identical-config empty state, and unchanged-leaf counting in `tests/test_config_diff_service.py`
- [X] T007 [P] [US1] Write failing endpoint tests for the config-diff success contract plus duplicate IDs, missing workspace/scenario, cross-workspace lookup, and incomplete scenario 400/404 behavior in `tests/test_comparison_api.py`

### Implementation for User Story 1

- [X] T008 [P] [US1] Add the active-only `AVG(prorated_annual_compensation)` query, zero fallback, annual values, baseline zeros, and B-minus-A delta wiring in `planalign_api/services/comparison_service.py`
- [X] T009 [P] [US1] Implement mapping-only deep diff, atomic sequence handling, cosmetic-path filtering, lexical ordering, unchanged counting, and `WorkspaceStorage.get_merged_config()` reuse in new `planalign_api/services/config_diff_service.py`, returning unavailable provenance placeholders until User Story 2
- [X] T010 [US1] Add `ConfigDiffService` dependency injection and the workspace-scoped `/comparison/config-diff` endpoint with distinct/completed scenario validation in `planalign_api/routers/comparison.py`
- [X] T011 [US1] Build `planalign_studio/components/ScenarioDiff.tsx` to load `compareScenarios(workspaceId, [a,b], a)` and config diff data, render friendly labels plus exact dotted paths, handle empty/only-A/only-B/missing-year states, and display paired annual charts with final-year B-minus-A chips for headcount, average compensation, participation, employer match, and total employer cost
- [X] T012 [US1] Register `/analytics/diff?a=<id>&b=<id>` and workspace-context rendering for `ScenarioDiff` in `planalign_studio/App.tsx`
- [X] T013 [US1] Run the User Story 1 targeted pytest commands and Studio production build from `specs/110-scenario-diff-view/quickstart.md`, fixing only US1-scoped failures in the files changed by T005-T012

**Checkpoint**: The focused diff is directly addressable and independently demonstrates the issue's core “what changed and what moved” workflow.

---

## Phase 4: User Story 2 - Trust the Comparison Provenance (Priority: P2)

**Goal**: Surface timestamps, fingerprints, seeds, unavailable provenance, seed noise, post-run config drift, and mixed-generation risk without writing to scenario artifacts.

**Independent Test**: Compare different-seed scenarios and see a persistent seed-noise warning; compare matching-seed scenarios and see no seed warning; remove legacy `run_metadata` and confirm the comparison remains usable with provenance marked unavailable.

### Tests for User Story 2

- [X] T014 [P] [US2] Write failing service tests for latest provenance, 12-character fingerprints, matching/different/unavailable seeds, current-config and current-seed mismatch reasons, latest-versus-previous mixed-generation detection, full-reset/calibration suppression, legacy missing-table degradation, and unchanged database checksums in `tests/test_config_diff_service.py`
- [X] T015 [P] [US2] Write failing endpoint serialization tests for per-scenario provenance, nullable `seeds_match`, top-level drift aggregation, and graceful missing metadata in `tests/test_comparison_api.py`

### Implementation for User Story 2

- [X] T016 [US2] Extend `planalign_api/services/config_diff_service.py` to resolve each database through `DatabasePathResolver`, open it with `read_only=True`, read the latest two `run_metadata` rows, reuse `compute_config_fingerprint()`, derive documented drift reasons and suppression rules, and degrade DuckDB/config validation errors to unavailable provenance
- [X] T017 [US2] Add run timestamp, short fingerprint, and seed badges plus distinct seed-noise, mixed-generation/current-config drift, and unavailable-provenance messaging to `planalign_studio/components/ScenarioDiff.tsx`
- [X] T018 [US2] Run the provenance fixture scenarios and read-only assertions in `specs/110-scenario-diff-view/quickstart.md`, fixing only US2-scoped failures in `planalign_api/services/config_diff_service.py`, `planalign_api/routers/comparison.py`, and `planalign_studio/components/ScenarioDiff.tsx`

**Checkpoint**: Analysts can assess whether displayed differences are attributable to levers or may include seed/config-generation noise.

---

## Phase 5: User Story 3 - Reach the Diff from Existing Comparison Workflows (Priority: P3)

**Goal**: Make the focused diff discoverable from the scenario list and existing two-scenario comparison while preserving A/B order and rejecting invalid direct navigation clearly.

**Independent Test**: Select exactly two completed scenarios and open “Diff A vs B”; repeat from an existing two-scenario comparison and verify query order is preserved; verify fewer/more/incomplete selections do not offer the action and an invalid direct URL shows guidance.

### Implementation for User Story 3

- [X] T019 [P] [US3] Add a “Diff A vs B” action for exactly two selected completed scenarios, preserving selection order and leaving the existing batch action intact, in `planalign_studio/components/ScenariosPage.tsx`
- [X] T020 [P] [US3] Add a focused-diff link when exactly two scenario IDs are present, preserving their current URL order, in `planalign_studio/components/ScenarioComparison.tsx`
- [X] T021 [US3] Add duplicate, missing, extra, incomplete, and cross-workspace query-state guidance without issuing invalid comparison requests in `planalign_studio/components/ScenarioDiff.tsx`
- [X] T022 [US3] Validate both navigation paths, invalid direct links, and the production build using the workflow in `specs/110-scenario-diff-view/quickstart.md`, fixing only US3-scoped failures in `planalign_studio/App.tsx` and the three comparison/scenario components

**Checkpoint**: All three user stories are independently functional and the focused diff is discoverable from normal analyst workflows.

---

## Phase 6: Polish & Cross-Cutting Validation

**Purpose**: Confirm quality gates, contract alignment, performance, and the real isolated-scenario acceptance case.

- [X] T023 [P] Reconcile implemented response fields, nullability, status enums, and error codes with `specs/110-scenario-diff-view/contracts/comparison-api.yaml` and update the contract only where implementation uncovered a documented design correction
- [X] T024 Run targeted `ruff`, `mypy`, pytest fast-suite, and `npm run build` gates exactly as documented in `specs/110-scenario-diff-view/quickstart.md`, recording any intentional limitation in that file
- [X] T025 Execute the deliberate matching-seed `planalign batch --scenarios a b --clean --threads 1` acceptance workflow using only `/tmp/planalign-110` artifacts, verify the match-only config delta plus flat headcount/average-compensation panels and divergent match cost, and record the observed result in `specs/110-scenario-diff-view/quickstart.md`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 — Setup**: Starts immediately.
- **Phase 2 — Foundational**: Depends on T001 and blocks all user stories.
- **Phase 3 — US1**: Depends on Phase 2 and delivers the MVP.
- **Phase 4 — US2**: Depends on the config-diff service and page from US1; its tests can be prepared once Phase 2 completes.
- **Phase 5 — US3**: Depends on the route/page from US1 but not on US2; it may run in parallel with US2 after US1.
- **Phase 6 — Polish**: Depends on every story selected for release; T025 requires all three stories.

### User Story Dependency Graph

```text
Setup → Foundation → US1 (MVP)
                       ├──→ US2 (provenance)
                       └──→ US3 (entry points)
US2 + US3 ─────────────────→ Polish / isolated E2E
```

### Within Each User Story

- Write the story's tests and confirm the intended failure before implementation.
- Complete models/contracts before services, services before endpoints, and endpoints/types before UI integration.
- Re-run the story's independent test at its checkpoint before starting dependent work.
- Do not use `dbt/simulation.duckdb` for any behavioral validation.

### Parallel Opportunities

- After T002, T003 and T004 can run in parallel.
- US1 tests T005-T007 can run in parallel; after the contract exists, T008 and T009 can run in parallel.
- US2 tests T014 and T015 can run in parallel.
- After US1, US2 and US3 can proceed in parallel.
- Within US3, T019 and T020 can run in parallel because they modify different components.
- Contract reconciliation T023 can run in parallel with early quality checks, but T024 must run after code changes settle.

## Parallel Examples

### User Story 1

```text
Parallel test work:
- T005: average-compensation SQL/delta fixture tests
- T006: effective-config deep-diff service tests
- T007: config-diff endpoint contract/error tests

Parallel implementation after tests fail as expected:
- T008: comparison metric aggregation
- T009: effective-config diff service
```

### User Story 2

```text
Parallel test work:
- T014: provenance and read-only service behavior
- T015: provenance endpoint serialization

Then sequentially:
- T016: provenance service implementation
- T017: Studio trust signals
```

### User Story 3

```text
Parallel entry-point work after US1:
- T019: scenario-list action
- T020: existing comparison link

Then:
- T021: invalid direct-link guidance
- T022: navigation/build validation
```

## Implementation Strategy

### MVP First

1. Complete T001-T004 for isolated fixtures and shared typed contracts.
2. Complete T005-T013 for User Story 1.
3. Stop and run the US1 independent test: one employer-match lever, corresponding cost movement, flat headcount and average compensation.
4. Demo the focused view directly at `/analytics/diff`; provenance badges and entry-point polish can follow without changing the core metric/config result.

### Incremental Delivery

1. **US1**: Effective settings plus annual outcome movements—the core analyst value.
2. **US2**: Provenance and warnings—the interpretation/trust layer.
3. **US3**: Scenario-list and comparison entry points—the discoverability layer.
4. **Polish**: Full gates and real isolated A/B acceptance validation.

### Parallel Team Strategy

After US1 establishes the page and service seams, one developer can implement provenance (US2) while another adds navigation entry points (US3). Shared-file conflicts remain limited to `ScenarioDiff.tsx`; sequence T017 before T021 if both branches touch its header/error states.

## Notes

- `[P]` tasks use different files or isolated sections and have no dependency on unfinished adjacent tasks.
- New Python behavior follows PEP 8, mandatory type hints, functions under roughly 40 lines, explicit exceptions, and cognitive complexity <=15.
- New frontend contract code must introduce no `any`; existing unrelated `any` usage is out of scope.
- Config diff and provenance stay out of the already-large `ComparisonService`; only `avg_compensation` belongs there.
- No task creates a table, writes to a scenario database, refactors `ScenarioComparison`, or changes the shared development database.

## Phase 7: Convergence

- [X] T026 Wire the active `DatabaseConnectionManager` into `DbtRunner` in `planalign_orchestrator/factory.py` and add regression coverage in `tests/integration/test_self_healing_integration.py` so isolated batch dbt subprocesses release parent-process DuckDB locks per T025 (partial)
- [X] T027 Re-run the matching-seed isolated batch and verify actual A/B database outputs through `ComparisonService` and `ConfigDiffService`, recording successful evidence in `specs/110-scenario-diff-view/quickstart.md` per T025 and SC-001 (partial)
- [X] T028 Render explicit `changed`/`only_a`/`only_b` badges and replace the non-functional unchanged toggle with an accurate count summary in `planalign_studio/components/ScenarioDiff.tsx` per FR-004 and FR-007 (partial)
