---
description: "Task list for Feature 123 — Match-Response Deferral Events in Client/Studio Simulations"
---

# Tasks: Match-Response Deferral Events in Client/Studio Simulations

**Input**: Design documents from `/specs/123-match-response-events/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, contracts/ ✅, quickstart.md ✅

**Tests**: REQUIRED. The specification requires regression coverage for the Studio/workspace resolution path and the authoritative fact-table result; Constitution III requires test-first development. All behavioral simulation tests must use a newly allocated isolated DuckDB database, never `dbt/simulation.duckdb`.

**Organization**: The workspace-resolution bridge is the shared prerequisite for the event behavior. Work remains grouped by user story in priority order, with tests authored before the scoped implementation or verification they govern.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel because it changes different files and has no dependency on an incomplete task.
- **[Story]**: `[US1]`, `[US2]`, or `[US3]`; setup, foundational, and polish tasks have no story label.
- Every path is repository-relative. dbt commands run from `dbt/` with `--threads 1`.

---

## Phase 1: Setup (Shared Test Inputs)

**Purpose**: Establish a small, PII-safe Studio-shaped configuration and census fixture with an active employer match and eligible below-threshold enrolled participants.

- [X] T001 Create deterministic Studio-shaped enabled, disabled, and new-hire fixture inputs with a match ceiling and fixed seed in `tests/fixtures/match_response_workspace_config.yaml` and `tests/fixtures/match_response_workspace_census.csv`.

**Checkpoint**: Fixtures provide a known eligible population and contain no client census data.

---

## Phase 2: Foundational (Workspace Resolution Seam)

**Purpose**: Identify the existing workspace-storage test seam that constructs `Workspace` and `Scenario` objects without filesystem side effects.

**⚠️ CRITICAL**: Complete this phase before the story tests so they exercise the real Studio/workspace merge path instead of a hand-built typed configuration.

- [X] T002 Add reusable in-memory workspace/scenario factories for Studio-shaped merge tests in `tests/unit/storage/test_workspace_storage.py`.

**Checkpoint**: Story tests can invoke `WorkspaceStorage._merge_config` directly and independently of persisted workspace state.

---

## Phase 3: User Story 1 — Configured match response runs for a client scenario (Priority: P1) 🎯 MVP

**Goal**: An enabled Studio/workspace scenario reaches the existing event generator and produces authoritative first-year match-response events.

**Independent Test**: Run a Studio-shaped 2025–2026 scenario with the enabled fixture against a fresh database; `fct_yearly_events` contains the deterministic expected number of 2025 `deferral_match_response` rows, each with `match_response` category and `Match response:` details.

### Tests for User Story 1 (write first, must fail)

- [X] T003 [US1] Add an isolated-DB integration test for an enabled `dc_plan.deferral_match_response` Studio scenario, asserting first-year authoritative event presence, exact deterministic responder count, category, details prefix, and CLI/top-level parity in `tests/integration/test_match_response_fact_integration.py`.

### Implementation for User Story 1

- [X] T004 [US1] Reconcile `dc_plan.deferral_match_response` into the typed top-level `deferral_match_response` block during workspace merge while preserving legacy top-level input and a disabled default in `planalign_api/storage/workspace_storage.py`.
- [X] T005 [US1] Run the enabled Studio and top-level CLI-parity cases from `tests/integration/test_match_response_fact_integration.py` against separate fresh `DATABASE_PATH` databases and retain only test assertions, not database artifacts, in `tests/integration/test_match_response_fact_integration.py`.

**Checkpoint**: The first projection year produces correctly shaped match-response facts through the Studio path; no dbt model has changed.

---

## Phase 4: User Story 2 — Enabled/disabled state is visible in resolved configuration (Priority: P2)

**Goal**: The effective configuration explicitly says whether match response is on or off and exports that state plus the match ceiling to dbt.

**Independent Test**: Unit-resolve enabled, legacy-top-level, conflicting, and absent inputs; each result contains `deferral_match_response.enabled`, validates as `SimulationConfig`, and exports the expected boolean and configured employer-match ceiling.

### Tests for User Story 2 (write first, must fail)

- [X] T006 [P] [US2] Add resolution-contract cases A1–A5 for Studio enablement, legacy parity, `dc_plan` precedence, explicit absent-block false, and `SimulationConfig` validation in `tests/unit/storage/test_workspace_storage.py`.
- [X] T007 [P] [US2] Extend dbt-var export tests for resolved enabled/disabled values and an always-on employer-match ceiling in `tests/unit/orchestrator/test_config_export.py` and `tests/test_config_export_match_magnet.py`.

### Implementation for User Story 2

- [X] T008 [US2] Refine the match-response normalization helper and its merge call site to guarantee a complete explicit `deferral_match_response` mapping without implicitly enabling the feature in `planalign_api/storage/workspace_storage.py`.
- [X] T009 [US2] Verify the resolved configuration passed to simulation remains the merged explicit mapping and that `to_dbt_vars` receives it unchanged in `tests/unit/storage/test_workspace_storage.py` and `tests/unit/orchestrator/test_config_export.py`.

**Checkpoint**: Operators can distinguish enabled from omitted/disabled solely from the configuration a run consumes, and the match ceiling remains available to the existing model.

---

## Phase 5: User Story 3 — Correct suppression: disabled, later years, and new hires (Priority: P2)

**Goal**: The fix retains the existing first-year-only, disabled, and new-hire eligibility boundaries.

**Independent Test**: On fresh multi-year databases, the enabled run has no post-2025 response events and no `NH_2025_%` responders; the disabled run has none in any year; repeated fixed-seed runs yield the same responder IDs and count.

### Tests for User Story 3 (write first, must fail)

- [ ] T010 [US3] Extend the isolated fact-table integration suite with disabled-all-years, later-year-zero, current-year-new-hire exclusion, and repeated-run responder-set determinism assertions in `tests/integration/test_match_response_fact_integration.py`.

### Implementation Verification for User Story 3

- [ ] T011 [US3] Execute the enabled and disabled multi-year integration cases with distinct fresh `DATABASE_PATH` locations and keep the feature bounded to existing workspace configuration code in `tests/integration/test_match_response_fact_integration.py` and `planalign_api/storage/workspace_storage.py`.

**Checkpoint**: The configuration fix makes the intended behavior reachable without broadening its participant or temporal scope.

---

## Phase 6: Polish & Cross-Cutting Validation

**Purpose**: Confirm the implementation remains minimal, follows the documented isolated-DB workflow, and does not regress existing config/export behavior.

- [X] T012 [P] Run the focused fast workspace-storage and config-export suites, including existing match-magnet tests, in `tests/unit/storage/test_workspace_storage.py`, `tests/unit/orchestrator/test_config_export.py`, and `tests/test_config_export_match_magnet.py`.
- [X] T013 [P] Run `ruff check planalign_api/storage/workspace_storage.py tests/unit/storage/test_workspace_storage.py tests/integration/test_match_response_fact_integration.py` and record any required style-only fixes in those files.
- [X] T014 Execute the isolated commands in `specs/123-match-response-events/quickstart.md`, confirming the enabled, omitted/disabled, later-year, and new-hire pass criteria without touching `dbt/simulation.duckdb`.

**Checkpoint**: The feature is ready for review with test-first config-path and fact-table coverage, no shared development database validation, and no dbt-model change.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies; T001 creates the PII-safe deterministic test inputs.
- **Foundational (Phase 2)**: Depends on T001; T002 establishes the WorkspaceStorage test seam and blocks story test work.
- **US1 (Phase 3)**: Depends on T001–T002; T003 must be red before T004, then T005 proves the first independently shippable increment.
- **US2 (Phase 4)**: Depends on T004 because it formalizes and verifies the same merged configuration contract; T006 and T007 can start in parallel.
- **US3 (Phase 5)**: Depends on T004 and the US1 fixture/integration harness; it verifies the existing model's intended boundaries without changing that model.
- **Polish (Phase 6)**: Depends on all user-story tasks.

### User Story Dependencies

- **US1 (P1)**: Depends only on setup/foundational test inputs; it is the suggested MVP.
- **US2 (P2)**: Shares the workspace bridge delivered in US1 and documents/enforces its full resolution and export contract.
- **US3 (P2)**: Shares the same bridge and validates that it has not altered the existing model's suppression invariants.

### Parallel Opportunities

- T006 and T007 can be authored in parallel because they cover different modules.
- T012 and T013 can run in parallel after the implementation and integration suite are stable.
- Do not run the two integration test database targets concurrently if they share a database path; each run must receive a distinct newly allocated path.

## Parallel Example: User Story 2

```text
Task T006: "Add workspace resolution-contract cases in tests/unit/storage/test_workspace_storage.py"
Task T007: "Extend dbt-var export cases in tests/unit/orchestrator/test_config_export.py and tests/test_config_export_match_magnet.py"
```

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete T001–T002 to create deterministic Studio-shaped inputs and test factories.
2. Write T003 and observe the enabled Studio run fail because its flag is not resolved.
3. Implement T004, then run T005 against a fresh isolated database.
4. Stop and validate the first-year fact-table contract before taking on transparency edge cases.

### Incremental Delivery

1. Deliver US1: enabled Studio scenarios generate existing match-response facts.
2. Deliver US2: resolution is explicit for enabled, disabled, legacy, and precedence cases.
3. Deliver US3: retain disabled, later-year, new-hire, and deterministic-selection invariants.
4. Finish focused fast, lint, and quickstart validation.

## Notes

- No task modifies `dbt/models/intermediate/events/int_deferral_match_response_events.sql` or the event exporter; research established them as correct.
- `dc_plan` wins when it conflicts with the legacy top-level block; absence explicitly resolves to `enabled: false`.
- Store no generated DuckDB files, census outputs, or run artifacts in version control.
