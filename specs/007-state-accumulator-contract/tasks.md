# Tasks: Temporal State Accumulator Contract

**Input**: Design documents from `/specs/007-state-accumulator-contract/`
**Prerequisites**: plan.md (required), spec.md (required for user stories), research.md, data-model.md, contracts/

**Tests**: Tests are included as the spec mentions test-first development (Constitution Principle III) and test suite requirements (FR-008, US4).

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `planalign_orchestrator/`, `tests/` at repository root
- Paths based on plan.md structure for this feature

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create the state_accumulator module structure and base files

- [x] T001 Create state_accumulator module directory at planalign_orchestrator/state_accumulator/
- [x] T002 [P] Create __init__.py with public API exports in planalign_orchestrator/state_accumulator/__init__.py
- [x] T003 [P] Create test fixtures file at tests/fixtures/state_accumulator.py

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [x] T004 Add YearDependencyError exception class to planalign_orchestrator/exceptions.py
- [x] T005 [P] Implement StateAccumulatorContract Pydantic model in planalign_orchestrator/state_accumulator/contract.py
- [x] T006 [P] Implement StateAccumulatorRegistry singleton in planalign_orchestrator/state_accumulator/registry.py
- [x] T007 Register initial accumulators (enrollment, deferral_rate) in planalign_orchestrator/state_accumulator/__init__.py
- [x] T008 [P] Create unit test for StateAccumulatorContract in tests/unit/test_state_accumulator_contract.py
- [x] T009 [P] Create unit test for StateAccumulatorRegistry in tests/unit/test_state_accumulator_registry.py
- [x] T010 Verify tests pass: run `pytest -m fast tests/unit/test_state_accumulator_*.py`

**Checkpoint**: Foundation ready - user story implementation can now begin

---

## Phase 3: User Story 1 - Runtime Year Dependency Validation (Priority: P1) 🎯 MVP

**Goal**: Pipeline fails fast with clear error messages when year dependencies are violated

**Independent Test**: Attempt to execute year 2027 directly (without 2026) and verify the pipeline fails with a descriptive error before any models run

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T011 [P] [US1] Unit test for YearDependencyValidator in tests/unit/test_year_dependency_validator.py
- [x] T012 [P] [US1] Unit test for YearDependencyError formatting in tests/unit/test_year_dependency_error.py
- [x] T013 [P] [US1] Integration test for validation in year_executor in tests/integration/test_year_dependency_validation.py

### Implementation for User Story 1

- [x] T014 [US1] Implement YearDependencyValidator class in planalign_orchestrator/state_accumulator/validator.py
- [x] T015 [US1] Implement validate_year_dependencies(year) method with database queries in planalign_orchestrator/state_accumulator/validator.py
- [x] T016 [US1] Implement get_missing_years(year) helper method in planalign_orchestrator/state_accumulator/validator.py
- [x] T017 [US1] Add YearDependencyValidator to YearExecutor.__init__() in planalign_orchestrator/pipeline/year_executor.py
- [x] T018 [US1] Add validation call before STATE_ACCUMULATION stage in YearExecutor.execute_workflow_stage() in planalign_orchestrator/pipeline/year_executor.py
- [x] T019 [US1] Update planalign_orchestrator/state_accumulator/__init__.py to export YearDependencyValidator
- [x] T020 [US1] Verify all US1 tests pass: run `pytest tests/unit/test_year_dependency_*.py tests/integration/test_year_dependency_validation.py`

**Checkpoint**: Runtime year dependency validation is functional - out-of-order execution now fails fast with clear error messages

---

## Phase 4: User Story 2 - State Accumulator Model Registration (Priority: P2)

**Goal**: Developers can register new accumulator models with a clear contract interface

**Independent Test**: Create a test accumulator model, register it with the registry, and verify registration validates all required contract elements

### Tests for User Story 2

- [ ] T021 [P] [US2] Unit test for contract validation rules in tests/unit/test_state_accumulator_contract.py (extend T008)
- [ ] T022 [P] [US2] Unit test for duplicate registration rejection in tests/unit/test_state_accumulator_registry.py (extend T009)
- [ ] T023 [P] [US2] Unit test for invalid model_name prefix validation in tests/unit/test_state_accumulator_contract.py

### Implementation for User Story 2

- [ ] T024 [US2] Add field_validator for model_name prefix (must start with 'int_') in planalign_orchestrator/state_accumulator/contract.py
- [ ] T025 [US2] Add duplicate registration check with clear error in StateAccumulatorRegistry.register() in planalign_orchestrator/state_accumulator/registry.py
- [ ] T026 [US2] Add get() method with helpful KeyError message listing available models in planalign_orchestrator/state_accumulator/registry.py
- [ ] T027 [US2] Add list_all() and get_registered_tables() methods in planalign_orchestrator/state_accumulator/registry.py
- [ ] T028 [US2] Add clear() method for testing in planalign_orchestrator/state_accumulator/registry.py
- [ ] T029 [US2] Add metadata comments to int_enrollment_state_accumulator.sql in dbt/models/intermediate/int_enrollment_state_accumulator.sql
- [ ] T030 [US2] Add metadata comments to int_deferral_rate_state_accumulator.sql in dbt/models/intermediate/int_deferral_rate_state_accumulator.sql
- [ ] T031 [US2] Verify all US2 tests pass: run `pytest tests/unit/test_state_accumulator_*.py`

**Checkpoint**: Model registration system is complete - developers can register new accumulators with validated contracts

---

## Phase 5: User Story 3 - Checkpoint-Based Recovery with Dependency Awareness (Priority: P3)

**Goal**: Checkpoint recovery validates dependency chain integrity before resuming

**Independent Test**: Create a checkpoint at year 2026, delete 2025 state data, and verify that resume correctly identifies the broken dependency chain

### Tests for User Story 3

- [ ] T032 [P] [US3] Unit test for validate_checkpoint_dependencies() in tests/unit/test_year_dependency_validator.py (extend T011)
- [ ] T033 [P] [US3] Integration test for checkpoint resume with broken chain in tests/integration/test_checkpoint_dependency_validation.py

### Implementation for User Story 3

- [ ] T034 [US3] Implement validate_checkpoint_dependencies(checkpoint_year) method in planalign_orchestrator/state_accumulator/validator.py
- [ ] T035 [US3] Add dependency chain validation in StateManager checkpoint recovery flow in planalign_orchestrator/pipeline/state_manager.py
- [ ] T036 [US3] Update pipeline_orchestrator to call checkpoint validation before resume in planalign_orchestrator/pipeline_orchestrator.py
- [ ] T037 [US3] Verify all US3 tests pass: run `pytest tests/unit/test_year_dependency_validator.py tests/integration/test_checkpoint_dependency_validation.py`

**Checkpoint**: Checkpoint recovery with dependency awareness is complete - broken dependency chains are detected before resume

---

## Phase 6: User Story 4 - Test Suite for Temporal Ordering Invariants (Priority: P3)

**Goal**: Test suite validates temporal ordering invariants across all registered accumulators

**Independent Test**: Run the temporal invariant test suite against the current codebase and verify all registered accumulators pass

### Tests for User Story 4

- [ ] T038 [P] [US4] Create temporal ordering invariant test suite in tests/integration/test_temporal_ordering_invariants.py
- [ ] T039 [P] [US4] Add test for start year behavior (no prior dependency) in tests/integration/test_temporal_ordering_invariants.py
- [ ] T040 [P] [US4] Add test for contract violation detection in tests/integration/test_temporal_ordering_invariants.py

### Implementation for User Story 4

- [ ] T041 [US4] Implement invariant assertions for registered accumulators in tests/integration/test_temporal_ordering_invariants.py
- [ ] T042 [US4] Add test fixture that creates intentionally violating accumulator for negative testing in tests/fixtures/state_accumulator.py
- [ ] T043 [US4] Verify all US4 tests pass: run `pytest tests/integration/test_temporal_ordering_invariants.py`

**Checkpoint**: Test suite for temporal ordering invariants is complete - all registered accumulators are validated

---

## Phase 7: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T044 [P] Update quickstart.md with any implementation adjustments in specs/007-state-accumulator-contract/quickstart.md
- [ ] T045 [P] Add docstrings to all public methods in planalign_orchestrator/state_accumulator/*.py
- [ ] T046 [P] Add type hints to all function signatures in planalign_orchestrator/state_accumulator/*.py
- [ ] T047 Run full test suite: `pytest -m fast && pytest tests/integration/test_*dependency*.py tests/integration/test_temporal*.py`
- [ ] T048 Verify existing simulation behavior unchanged: run `planalign simulate 2025-2027 --verbose` and confirm identical results
- [ ] T049 Update CLAUDE.md to document the state accumulator contract pattern in CLAUDE.md

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-6)**: All depend on Foundational phase completion
  - User stories can proceed in priority order (P1 → P2 → P3 → P3)
  - US3 and US4 can run in parallel (both P3 priority)
- **Polish (Phase 7)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational (Phase 2) - No dependencies on other stories - **MVP**
- **User Story 2 (P2)**: Can start after Foundational (Phase 2) - Enhances US1 but independently testable
- **User Story 3 (P3)**: Depends on US1 for YearDependencyValidator - Extends validation to checkpoint flow
- **User Story 4 (P3)**: Depends on US1 and US2 for registry and validation - Creates comprehensive test suite

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- Contract/Model before Registry before Validator
- Core implementation before integration hooks
- Story complete before moving to next priority

### Parallel Opportunities

- T002, T003 can run in parallel (different files)
- T005, T006, T008, T009 can run in parallel (different files)
- T011, T012, T013 can run in parallel (different test files)
- T021, T022, T023 can run in parallel (extending existing test files)
- T032, T033 can run in parallel (different test files)
- T038, T039, T040 can run in parallel (same test file but independent test cases)
- T044, T045, T046 can run in parallel (different files)

---

## Parallel Example: Foundational Phase

```bash
# Launch model and registry implementation in parallel:
Task: "Implement StateAccumulatorContract Pydantic model in planalign_orchestrator/state_accumulator/contract.py"
Task: "Implement StateAccumulatorRegistry singleton in planalign_orchestrator/state_accumulator/registry.py"

# Launch tests in parallel:
Task: "Create unit test for StateAccumulatorContract in tests/unit/test_state_accumulator_contract.py"
Task: "Create unit test for StateAccumulatorRegistry in tests/unit/test_state_accumulator_registry.py"
```

---

## Parallel Example: User Story 1

```bash
# Launch all tests for User Story 1 together:
Task: "Unit test for YearDependencyValidator in tests/unit/test_year_dependency_validator.py"
Task: "Unit test for YearDependencyError formatting in tests/unit/test_year_dependency_error.py"
Task: "Integration test for validation in year_executor in tests/integration/test_year_dependency_validation.py"
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Runtime Validation)
4. **STOP and VALIDATE**: Test out-of-order year execution fails with clear error
5. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 1 → Test independently → Deploy/Demo (MVP!)
3. Add User Story 2 → Test independently → Deploy/Demo
4. Add User Story 3 → Test independently → Deploy/Demo
5. Add User Story 4 → Test independently → Deploy/Demo
6. Each story adds value without breaking previous stories

### Full Implementation

1. Phase 1: Setup (T001-T003)
2. Phase 2: Foundational (T004-T010)
3. Phase 3: US1 - Runtime Validation (T011-T020) 🎯 **MVP Complete**
4. Phase 4: US2 - Model Registration (T021-T031)
5. Phase 5: US3 - Checkpoint Recovery (T032-T037)
6. Phase 6: US4 - Test Suite (T038-T043)
7. Phase 7: Polish (T044-T049)

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Verify tests fail before implementing
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Fast tests target: <10 seconds for unit tests (Constitution Principle III)
