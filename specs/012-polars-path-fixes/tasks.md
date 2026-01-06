# Tasks: Polars Mode Path Handling Fixes

**Input**: Design documents from `/specs/012-polars-path-fixes/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are included as Constitution Principle III requires test-first development.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Files to modify (from plan.md):
- `planalign_orchestrator/pipeline/event_generation_executor.py` - POSIX path conversion
- `planalign_cli/commands/simulate.py` - CLI option
- `planalign_api/services/simulation_service.py` - Workspace isolation
- `tests/unit/test_path_handling.py` - Unit tests (new)

---

## Phase 1: Setup (No Tasks Required)

**Purpose**: Project initialization and basic structure

This is a bug fix in an existing codebase. No setup tasks required - the project structure already exists.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Create the path normalization utility function that all user stories depend on

**⚠️ CRITICAL**: US1 and US3 both need path normalization; US2 needs the CLI option from US3

- [x] T001 Create `normalize_path_for_duckdb()` helper function in planalign_orchestrator/pipeline/event_generation_executor.py

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Windows Path Compatibility (Priority: P1) 🎯 MVP

**Goal**: Fix Windows backslash incompatibility so Polars mode works on Windows

**Independent Test**: Run `planalign simulate 2025 --use-polars-engine` on Windows - simulation should complete without path errors

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T002 [P] [US1] Unit test for POSIX path conversion in tests/unit/test_path_handling.py
- [x] T003 [P] [US1] Unit test for absolute-to-relative path conversion in tests/unit/test_path_handling.py
- [x] T004 [P] [US1] Unit test for paths with spaces in tests/unit/test_path_handling.py

### Implementation for User Story 1

- [x] T005 [US1] Update `_execute_polars_event_generation()` to use `.as_posix()` at line ~292-301 in planalign_orchestrator/pipeline/event_generation_executor.py
- [x] T006 [US1] Handle absolute path conversion to dbt-relative path with POSIX format in planalign_orchestrator/pipeline/event_generation_executor.py
- [x] T007 [US1] Add debug logging for path conversions in planalign_orchestrator/pipeline/event_generation_executor.py

**Checkpoint**: At this point, Polars simulations should work on Windows

---

## Phase 4: User Story 3 - Custom Polars Output Path (Priority: P2)

**Goal**: Add `--polars-output` CLI option for custom parquet output directory

**Independent Test**: Run `planalign simulate 2025 --use-polars-engine --polars-output ./custom` and verify parquet files appear in `./custom`

> **Note**: US3 is implemented before US2 because US2 (Studio workspace isolation) depends on the `--polars-output` CLI option

### Tests for User Story 3

- [x] T008 [P] [US3] Unit test for `--polars-output` option parsing in tests/unit/test_path_handling.py
- [x] T009 [P] [US3] Unit test for warning when `--polars-output` used without `--use-polars-engine` in tests/unit/test_path_handling.py

### Implementation for User Story 3

- [x] T010 [US3] Add `--polars-output` option to `run_simulation()` in planalign_cli/commands/simulate.py
- [x] T011 [US3] Pass `polars_output` parameter to `OrchestratorWrapper` in planalign_cli/commands/simulate.py
- [x] T012 [US3] Update `OrchestratorWrapper` to accept and propagate `polars_output` parameter in planalign_cli/integration/orchestrator_wrapper.py
- [x] T013 [US3] Add warning when `--polars-output` specified without `--use-polars-engine` in planalign_cli/commands/simulate.py
- [x] T014 [US3] Create output directory if it doesn't exist using `mkdir(parents=True, exist_ok=True)` in planalign_cli/integration/orchestrator_wrapper.py

**Checkpoint**: At this point, CLI users can specify custom Polars output paths

---

## Phase 5: User Story 2 - Studio Workspace Isolation (Priority: P1)

**Goal**: Ensure Studio-launched Polars simulations store parquet files in workspace-specific directories

**Independent Test**: Launch Studio, run Polars simulation, verify parquet files in `{workspace}/{scenario}/data/parquet/events/`

### Tests for User Story 2

- [x] T015 [P] [US2] Unit test for workspace-specific path construction in tests/unit/test_path_handling.py

### Implementation for User Story 2

- [x] T016 [US2] Calculate workspace-specific Polars output path (`scenario_path / "data" / "parquet" / "events"`) in planalign_api/services/simulation_service.py
- [x] T017 [US2] Pass `--polars-output` argument to CLI subprocess when Polars engine enabled in planalign_api/services/simulation_service.py
- [x] T018 [US2] Add logging for workspace-specific path selection in planalign_api/services/simulation_service.py

**Checkpoint**: At this point, Studio simulations have isolated parquet output

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [x] T019 [P] Run existing Polars test suite to verify no regression in tests/
- [x] T020 [P] Update quickstart.md validation - verify documented commands work
- [ ] T021 Manual test on Windows (if available) or document for QA

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No tasks - existing project
- **Foundational (Phase 2)**: No dependencies - can start immediately
- **User Story 1 (Phase 3)**: Depends on Foundational (T001)
- **User Story 3 (Phase 4)**: Depends on Foundational (T001) - also provides infrastructure for US2
- **User Story 2 (Phase 5)**: Depends on User Story 3 (needs `--polars-output` CLI option)
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

```
Phase 2: Foundational
     │
     ├──────────┬──────────┐
     │          │          │
     ▼          │          │
Phase 3: US1   │          │
(Windows fix)  │          │
               ▼          │
          Phase 4: US3    │
          (CLI option)    │
               │          │
               ▼          │
          Phase 5: US2 ◄──┘
          (Studio isolation)
               │
               ▼
          Phase 6: Polish
```

- **US1**: Independent - only needs T001
- **US3**: Independent - only needs T001, but must complete before US2
- **US2**: Depends on US3 - needs `--polars-output` option to pass to CLI

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Implementation tasks in order listed
- Story complete before moving to dependent stories

### Parallel Opportunities

- **Phase 3 Tests**: T002, T003, T004 can run in parallel
- **Phase 4 Tests**: T008, T009 can run in parallel
- **Phase 6**: T019, T020 can run in parallel
- **US1 and US3**: Can be developed in parallel after T001 (if team capacity allows)

---

## Parallel Example: User Story 1 Tests

```bash
# Launch all tests for User Story 1 together:
Task: "Unit test for POSIX path conversion in tests/unit/test_path_handling.py"
Task: "Unit test for absolute-to-relative path conversion in tests/unit/test_path_handling.py"
Task: "Unit test for paths with spaces in tests/unit/test_path_handling.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 2: Foundational (T001)
2. Complete Phase 3: User Story 1 (T002-T007)
3. **STOP and VALIDATE**: Test on Windows - Polars simulation should complete
4. Deploy/demo if ready - Windows users unblocked

### Full Delivery

1. Complete Foundational + US1 → Windows fix deployed
2. Add US3 (CLI option) → Test independently → Power users have flexibility
3. Add US2 (Studio isolation) → Test independently → Studio users have isolation
4. Polish phase → Full validation

### Recommended Sequence (Single Developer)

```
T001 → T002-T004 (parallel tests) → T005-T007 → [MVP Complete]
     → T008-T009 (parallel tests) → T010-T014 → [US3 Complete]
     → T015 → T016-T018 → [US2 Complete]
     → T019-T021 (parallel) → [Feature Complete]
```

---

## Notes

- This is a bug fix with ~50 lines of changes across 3 files
- Constitution Principle III requires tests first
- US2 depends on US3 (needs CLI option), so US3 implemented first despite both being P1
- [P] tasks = different files, no dependencies
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
