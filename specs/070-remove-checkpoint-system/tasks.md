# Tasks: Remove Checkpoint/Resume System

**Input**: Design documents from `/specs/070-remove-checkpoint-system/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, quickstart.md

**Tests**: No new tests are created. Existing checkpoint-specific tests are removed alongside their code.

**Organization**: Tasks are grouped by user story. Since this is a code removal feature, the stories map to logical removal phases rather than new functionality.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Delete standalone checkpoint files that are fully removed — no surgical editing needed

- [x] T001 [P] Delete checkpoint manager module at planalign_orchestrator/checkpoint_manager.py (FR-001, ~563 lines)
- [x] T002 [P] Delete recovery orchestrator module at planalign_orchestrator/recovery_orchestrator.py (FR-002, ~328 lines)
- [x] T003 [P] Delete checkpoint CLI commands module at planalign_cli/commands/checkpoint.py (FR-003, ~199 lines)

**Checkpoint**: Three standalone files deleted (~1,090 lines). Codebase will have import errors until Phase 2 resolves references.

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Remove all imports and references to deleted modules so the codebase compiles cleanly

**CRITICAL**: These tasks resolve broken imports from Phase 1 deletions. Must complete before user story work.

- [x] T004 Remove CheckpointManager and RecoveryOrchestrator imports and initialization from planalign_orchestrator/pipeline_orchestrator.py — remove imports (lines ~21, 30), constructor params (checkpoints_dir, enhanced_checkpoints), and checkpoint system initialization block (~lines 115-180)
- [x] T005 [P] Remove CheckpointManager and RecoveryOrchestrator imports and lazy-load properties from planalign_cli/integration/orchestrator_wrapper.py — remove imports (~lines 16, 20), property initializers (~lines 42-43), checkpoint_manager/recovery_orchestrator properties (~lines 70-82)
- [x] T006 [P] Remove checkpoint import and checkpoints command registration from planalign_cli/main.py — remove checkpoint command import (~line 24), checkpoint command function imports (~line 84), and checkpoints command handler (~lines 222-242)
- [x] T007 [P] Remove CheckpointManager and RecoveryOrchestrator imports from planalign_orchestrator/cli.py — remove imports (~lines 15, 19)
- [x] T008 Run pytest to verify all import errors are resolved and non-checkpoint tests pass

**Checkpoint**: Codebase compiles cleanly. All imports to deleted modules are removed.

---

## Phase 3: User Story 1 - Simplified Simulation Execution (Priority: P1)

**Goal**: Remove checkpoint save/load logic from the pipeline orchestrator so simulations run without checkpoint overhead

**Independent Test**: Run `planalign simulate 2025 --dry-run` and verify no checkpoint files are created and no checkpoint log messages appear

### Implementation for User Story 1

- [x] T009 [US1] Remove checkpoint methods from planalign_orchestrator/pipeline_orchestrator.py — delete `_save_year_checkpoint()`, `_write_legacy_checkpoint()`, `_calculate_config_hash()` methods and remove `resume_from_checkpoint` parameter from `execute_multi_year_simulation()`
- [x] T010 [US1] Remove checkpoint save call from year execution loop in planalign_orchestrator/pipeline_orchestrator.py — remove the checkpoint save call after each year completes (~line 322) and any resume-from-checkpoint branching (~lines 299-302)
- [x] T011 [US1] Trim StateManager in planalign_orchestrator/pipeline/state_manager.py — remove `write_checkpoint()`, `find_last_checkpoint()`, `state_hash()`, `calculate_config_hash()` methods and `checkpoints_dir` constructor parameter. PRESERVE: `maybe_clear_year_data()`, `maybe_full_reset()`, `clear_year_fact_rows()`, `verify_year_population()` (FR-005, FR-009)
- [x] T012 [US1] Remove checkpoint section from `get_system_status()` in planalign_cli/integration/orchestrator_wrapper.py — remove the try/except block that queries checkpoint_manager.list_checkpoints() and recovery status (~lines 143-158)
- [x] T013 [US1] Remove `get_checkpoint_info()` method from planalign_cli/integration/orchestrator_wrapper.py (~lines 299-316)
- [x] T014 [US1] Run pytest -m fast to verify simulation-related tests still pass

**Checkpoint**: Pipeline orchestrator runs simulations without any checkpoint logic. StateManager retains only database cleanup methods.

---

## Phase 4: User Story 2 - Cleaned Up CLI Interface (Priority: P2)

**Goal**: Remove all checkpoint-related CLI commands and flags so the CLI only shows relevant options

**Independent Test**: Run `planalign --help` and verify no checkpoints command; run `planalign simulate --help` and verify no --resume/--force-restart flags

### Implementation for User Story 2

- [x] T015 [US2] Remove `--resume` and `--force-restart` flags and `_resolve_start_year()` function from planalign_cli/commands/simulate.py — remove flag definitions (~lines 56-61), resume logic (~lines 109-113), `_resolve_start_year()` helper (~lines 227-258), and corresponding params in `default()` (~lines 352-371) (FR-004)
- [x] T016 [US2] Remove resume/restart arguments and checkpoint subparser from legacy CLI in planalign_orchestrator/cli.py — remove `--resume`/`--force-restart` args from run subparser (~lines 280-291), resume logic in `cmd_run()` (~lines 76-104), entire `cmd_checkpoint()` function (~lines 141-218), and checkpoint subparser setup (~lines 300-316)
- [x] T017 [US2] Run pytest to verify CLI tests pass and no checkpoint commands are registered

**Checkpoint**: CLI interface is clean — no checkpoint commands or resume flags visible to users.

---

## Phase 5: User Story 3 - Simplified Pipeline Orchestrator (Priority: P3)

**Goal**: Clean up all remaining checkpoint test code and error catalog references so the codebase has zero checkpoint artifacts

**Independent Test**: Run full test suite (`pytest --tb=short`); grep codebase for "checkpoint_manager", "recovery_orchestrator", "CheckpointManager", "RecoveryOrchestrator" and verify zero hits in source files

### Implementation for User Story 3

- [x] T018 [P] [US3] Remove 3 checkpoint lazy-load test methods from tests/test_orchestrator_wrapper.py — remove `test_checkpoint_manager_lazy_loads`, `test_recovery_orchestrator_lazy_loads`, `test_get_checkpoint_info_error` (FR-008)
- [x] T019 [P] [US3] Remove `TestResolveStartYear` test class (3 methods) from tests/test_simulate_command.py (FR-008)
- [x] T020 [P] [US3] Remove `test_cli_checkpoint_listing` test from tests/unit/cli/test_cli.py (FR-008)
- [x] T021 [P] [US3] Remove checkpoint error pattern test from tests/test_error_catalog.py (FR-008)
- [x] T022 [P] [US3] Remove 2 checkpoint dependency validation tests from tests/unit/test_year_dependency_validator.py (FR-008)
- [x] T023 [US3] Remove checkpoint-specific error patterns from error catalog in planalign_orchestrator/error_catalog.py if any exist
- [x] T024 [US3] Run full test suite (`pytest --tb=short`) to verify all remaining tests pass (SC-002)

**Checkpoint**: Zero checkpoint artifacts remain in source code or tests. Full test suite passes.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation updates and final verification

- [x] T025 Update CLAUDE.md — remove checkpoint references from Section 3 (Quick Start: `planalign checkpoints` commands), Section 5 (Directory Structure: state_manager.py description), Section 6 (Pipeline Orchestration: StateManager reference), and Section 10 (Critical Patterns: checkpoint CLI examples)
- [x] T026 Verify line count reduction meets SC-001 target (at least 1,000 lines removed) by comparing git diff stats
- [x] T027 Run quickstart.md verification commands: `pytest -m fast`, `pytest --tb=short`, verify `planalign --help` and `planalign simulate --help` output

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies — delete standalone files immediately
- **Phase 2 (Foundational)**: Depends on Phase 1 — resolves broken imports
- **Phase 3 (US1)**: Depends on Phase 2 — modifies files that reference deleted modules
- **Phase 4 (US2)**: Depends on Phase 2 — can run in parallel with Phase 3
- **Phase 5 (US3)**: Depends on Phase 3 and Phase 4 — cleans up test references to removed code
- **Phase 6 (Polish)**: Depends on Phase 5 — final documentation and verification

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Phase 2. Removes core checkpoint logic from orchestrator.
- **User Story 2 (P2)**: Can start after Phase 2. Independent of US1 — removes CLI surface area.
- **User Story 3 (P3)**: Depends on US1 and US2 completion — removes test code that references removed source code.

### Within Each User Story

- Source code changes before test verification
- Preserve critical methods (StateManager cleanup) while removing checkpoint methods
- Run tests after each story to catch regressions early

### Parallel Opportunities

**Phase 1** — All 3 deletions (T001, T002, T003) are independent:
```
T001 (checkpoint_manager.py) || T002 (recovery_orchestrator.py) || T003 (checkpoint.py)
```

**Phase 2** — Import cleanup tasks (T005, T006, T007) are independent:
```
T004 (pipeline_orchestrator.py) first, then T005 || T006 || T007, then T008
```

**Phase 3 + Phase 4** — US1 and US2 can run in parallel after Phase 2:
```
US1: T009 → T010 → T011 → T012 → T013 → T014
US2: T015 → T016 → T017
```

**Phase 5** — All 5 test removal tasks (T018-T022) are independent:
```
T018 || T019 || T020 || T021 || T022, then T023, then T024
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Delete standalone files
2. Complete Phase 2: Resolve broken imports
3. Complete Phase 3: Remove checkpoint logic from orchestrator
4. **STOP and VALIDATE**: Run `planalign simulate 2025 --dry-run`, verify no checkpoint artifacts
5. The pipeline is already simplified at this point

### Incremental Delivery

1. Phase 1 + Phase 2 → Codebase compiles, ~1,090 lines deleted
2. Add US1 (Phase 3) → Pipeline orchestrator simplified → Validate simulations work
3. Add US2 (Phase 4) → CLI cleaned up → Validate CLI output
4. Add US3 (Phase 5) → Tests cleaned up → Full test suite passes
5. Phase 6 → Documentation updated → Feature complete

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- **Key constraint**: NEVER remove `StateManager.maybe_clear_year_data()` or `StateManager.maybe_full_reset()` — these are essential for multi-year simulation correctness
- Performance monitoring checkpoints (`PerformanceCheckpoint` in `test_duckdb_monitor.py`) are a different concept — DO NOT remove those
- Already-skipped legacy tests (`test_multi_year_coordination.py`, `test_orchestrator_dbt_end_to_end.py`) need no changes
- Total tasks: 27
