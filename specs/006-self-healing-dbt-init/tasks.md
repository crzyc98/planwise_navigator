# Tasks: Self-Healing dbt Initialization

**Input**: Design documents from `/specs/006-self-healing-dbt-init/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Tests are included per Constitution Principle III (Test-First Development).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Project Type**: Single project (monorepo with modular packages)
- **Orchestrator**: `planalign_orchestrator/`
- **Tests**: `tests/`
- **dbt**: `dbt/`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create new module structure and exception classes

- [x] T001 Create self_healing package directory at `planalign_orchestrator/self_healing/`
- [x] T002 [P] Create `planalign_orchestrator/self_healing/__init__.py` with module exports
- [x] T003 [P] Add InitializationError exception classes in `planalign_orchestrator/exceptions.py`
- [x] T004 [P] Add empty_database fixture in `tests/fixtures/database.py`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core data models and table checker that ALL user stories depend on

**CRITICAL**: No user story work can begin until this phase is complete

- [x] T005 Create InitializationState enum and TableTier enum in `planalign_orchestrator/self_healing/initialization_state.py`
- [x] T006 Create RequiredTable Pydantic model with REQUIRED_TABLES registry in `planalign_orchestrator/self_healing/initialization_state.py`
- [x] T007 Create InitializationStep Pydantic model in `planalign_orchestrator/self_healing/initialization_state.py`
- [x] T008 Create InitializationResult Pydantic model in `planalign_orchestrator/self_healing/initialization_state.py`
- [x] T009 Implement TableExistenceChecker class in `planalign_orchestrator/self_healing/table_checker.py`
- [x] T010 Verify `tag:FOUNDATION` exists on foundation models in `dbt/models/intermediate/` (already present)

**Checkpoint**: Foundation ready - TableExistenceChecker can detect missing tables ✅

---

## Phase 3: User Story 1 - First Simulation in New Workspace (Priority: P1)

**Goal**: Auto-detect missing tables and trigger dbt initialization before simulation

**Independent Test**: Create new workspace with no database, start simulation, verify tables created automatically

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T011 [P] [US1] Unit test TableExistenceChecker.is_initialized() returns False for empty DB in `tests/unit/orchestrator/test_self_healing.py`
- [x] T012 [P] [US1] Unit test TableExistenceChecker.get_missing_tables() returns all required tables for empty DB in `tests/unit/orchestrator/test_self_healing.py`
- [x] T013 [P] [US1] Unit test AutoInitializer.ensure_initialized() triggers dbt commands in `tests/unit/orchestrator/test_self_healing.py`
- [x] T014 [P] [US1] Integration test full initialization flow with mock dbt runner in `tests/integration/test_self_healing_integration.py`

### Implementation for User Story 1

- [x] T015 [US1] Implement AutoInitializer.__init__() in `planalign_orchestrator/self_healing/auto_initializer.py`
- [x] T016 [US1] Implement AutoInitializer.ensure_initialized() main entry point in `planalign_orchestrator/self_healing/auto_initializer.py`
- [x] T017 [US1] Implement AutoInitializer.run_initialization() with dbt seed + dbt run in `planalign_orchestrator/self_healing/auto_initializer.py`
- [x] T018 [US1] HookManager already supports PRE_SIMULATION hooks via existing HookType enum in `planalign_orchestrator/pipeline/hooks.py`
- [x] T019 [US1] HookManager.register_hook() already supports PRE_SIMULATION via HookType in `planalign_orchestrator/pipeline/hooks.py`
- [x] T020 [US1] HookManager.execute_hooks() already supports PRE_SIMULATION in `planalign_orchestrator/pipeline/hooks.py`
- [x] T021 [US1] Add auto_initialize parameter to create_orchestrator() in `planalign_orchestrator/factory.py`
- [x] T022 [US1] Register AutoInitializer hook in create_orchestrator() when auto_initialize=True in `planalign_orchestrator/factory.py`
- [x] T023 [US1] Call execute_hooks(HookType.PRE_SIMULATION) at start of execute_multi_year_simulation() in `planalign_orchestrator/pipeline_orchestrator.py`

**Checkpoint**: First simulation in new workspace auto-initializes database ✅

---

## Phase 4: User Story 2 - Progress Feedback During Initialization (Priority: P2)

**Goal**: Show clear progress messages during initialization steps

**Independent Test**: Observe CLI output during initialization, verify step messages appear

### Tests for User Story 2

- [x] T024 [P] [US2] Unit test InitializationStep.status property returns correct values in `tests/unit/orchestrator/test_self_healing.py`
- [x] T025 [P] [US2] Unit test AutoInitializer logs step start/complete with timing in `tests/unit/orchestrator/test_self_healing.py`

### Implementation for User Story 2

- [x] T026 [US2] Implement AutoInitializer._execute_step() with timing and logging in `planalign_orchestrator/self_healing/auto_initializer.py`
- [x] T027 [US2] Add Rich console progress output for verbose mode in `planalign_orchestrator/self_healing/auto_initializer.py`
- [x] T028 [US2] Implement structured logging per NFR-001/NFR-002 (step name, duration, success) in `planalign_orchestrator/self_healing/auto_initializer.py`
- [x] T029 [US2] Update exports in `planalign_orchestrator/self_healing/__init__.py` for InitializationStep

**Checkpoint**: Users see progress feedback during initialization ✅

---

## Phase 5: User Story 3 - Graceful Error Recovery (Priority: P3)

**Goal**: Provide actionable error messages and support clean retry

**Independent Test**: Simulate initialization failure, verify error message includes remediation steps

### Tests for User Story 3

- [x] T030 [P] [US3] Unit test InitializationError includes step and missing_tables context in `tests/unit/orchestrator/test_self_healing.py`
- [x] T031 [P] [US3] Unit test ConcurrentInitializationError when lock held in `tests/unit/orchestrator/test_self_healing.py`
- [x] T032 [P] [US3] Unit test retry succeeds after previous failure (clean state) in `tests/unit/orchestrator/test_self_healing.py`

### Implementation for User Story 3

- [x] T033 [US3] Add file-based mutex lock using ExecutionMutex in `planalign_orchestrator/self_healing/auto_initializer.py`
- [x] T034 [US3] Implement ConcurrentInitializationError handling in ensure_initialized() in `planalign_orchestrator/self_healing/auto_initializer.py`
- [x] T035 [US3] Implement InitializationTimeoutError with 60s timeout in `planalign_orchestrator/self_healing/auto_initializer.py`
- [x] T036 [US3] Add actionable error messages with remediation hints in `planalign_orchestrator/exceptions.py` (InitializationError has resolution_hint)
- [x] T037 [US3] Implement clean retry logic (detect incomplete init, restart from clean state) in `planalign_orchestrator/self_healing/auto_initializer.py`
- [x] T038 [US3] Add DatabaseCorruptionError detection and handling in `planalign_orchestrator/exceptions.py`

**Checkpoint**: Error recovery works gracefully with clear messages ✅

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, validation, and final integration

- [x] T039 [P] Update `planalign_orchestrator/self_healing/__init__.py` with all public exports
- [x] T040 [P] Add docstrings to all public classes and methods per existing codebase patterns
- [x] T041 Run quickstart.md validation scenarios manually (updated to reflect 7 required tables)
- [x] T042 Verify 60-second timeout meets SC-003 performance target (DEFAULT_TIMEOUT_SECONDS = 60.0)
- [x] T043 Update CLAUDE.md Active Technologies section if needed (no changes required - uses existing Python 3.11 + DuckDB)

**Checkpoint**: Feature complete - Self-healing dbt initialization ready for production ✅

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - User stories can proceed sequentially in priority order (P1 → P2 → P3)
  - Some parallelization possible between stories if different developers
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories
- **User Story 2 (P2)**: Depends on US1 implementation (uses AutoInitializer) but is independently testable
- **User Story 3 (P3)**: Depends on US1 implementation (uses AutoInitializer) but is independently testable

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Pydantic models before services
- Services before integration points
- Core implementation before error handling
- Story complete before moving to next priority

### Parallel Opportunities

- T002, T003, T004 can run in parallel (different files)
- T011-T014 (US1 tests) can run in parallel
- T024-T025 (US2 tests) can run in parallel
- T030-T032 (US3 tests) can run in parallel
- T039, T040 can run in parallel

---

## Parallel Example: User Story 1 Tests

```bash
# Launch all US1 tests together:
Task: "Unit test TableExistenceChecker.is_initialized() in tests/unit/orchestrator/test_self_healing.py"
Task: "Unit test TableExistenceChecker.get_missing_tables() in tests/unit/orchestrator/test_self_healing.py"
Task: "Unit test AutoInitializer.ensure_initialized() in tests/unit/orchestrator/test_self_healing.py"
Task: "Integration test full initialization flow in tests/integration/test_self_healing_integration.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1
4. **STOP and VALIDATE**: Test auto-initialization with empty database
5. Deploy/demo if ready - eliminates "table does not exist" errors

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy (MVP - auto-init works!)
3. Add User Story 2 → Test independently → Deploy (progress feedback)
4. Add User Story 3 → Test independently → Deploy (error recovery)
5. Each story adds value without breaking previous stories

### Recommended Approach

Single developer executing sequentially:

1. Phase 1 (Setup): ~15 minutes
2. Phase 2 (Foundational): ~45 minutes
3. Phase 3 (User Story 1): ~2 hours (including tests)
4. **Checkpoint**: Validate MVP works
5. Phase 4 (User Story 2): ~1 hour
6. Phase 5 (User Story 3): ~1.5 hours
7. Phase 6 (Polish): ~30 minutes

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing (TDD per Constitution Principle III)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Constitution compliance: All tasks align with modular architecture, test-first, structured logging
