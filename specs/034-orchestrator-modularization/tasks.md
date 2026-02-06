# Tasks: Orchestrator Modularization Phase 2

**Input**: Design documents from `/specs/034-orchestrator-modularization/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Not explicitly requested. Existing 256+ tests validate the refactoring.

**Organization**: Tasks are grouped by extraction phase. User stories are interleaved since this is a refactoring task where US1 (modular code) and US2 (zero regression) are validated together.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1=Modular Code, US2=Zero Regression, US3=Test Validation, US4=Isolated Testing)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `planalign_orchestrator/` at repository root
- Paths follow existing E072 modularization pattern

---

## Phase 1: Setup (Baseline Verification)

**Purpose**: Establish baseline and verify starting state before extraction

- [x] T001 Run `wc -l planalign_orchestrator/pipeline_orchestrator.py` to verify starting line count (~1,218 lines) - **Verified: 1,218 lines**
- [ ] T002 Run `pytest -m fast` to establish baseline test pass rate (87 tests) - **Blocked: environment missing dependencies**
- [ ] T003 Run `python -c "from planalign_orchestrator import create_orchestrator; print('OK')"` to verify public API works - **Blocked: environment missing dependencies**

**Checkpoint**: Baseline established - extraction can begin

---

## Phase 2: Setup Module Extraction (US1 + US2)

**Purpose**: Extract all setup methods to `orchestrator_setup.py`

**Goal**: Create modular setup module with 4 factory functions (~250 lines)

**Independent Test**: Run `pytest -m fast` after each extraction step; all tests must pass

### Module Creation

- [x] T004 [US1] Create `planalign_orchestrator/orchestrator_setup.py` with module docstring and imports
- [x] T005 [P] [US1] Extract `setup_memory_manager()` function from `_setup_adaptive_memory_manager()` in `planalign_orchestrator/orchestrator_setup.py`
- [x] T006 [P] [US1] Extract `setup_parallelization()` function from `_setup_model_parallelization()` in `planalign_orchestrator/orchestrator_setup.py`
- [x] T007 [P] [US1] Extract `setup_hazard_cache()` function from `_setup_hazard_cache_manager()` in `planalign_orchestrator/orchestrator_setup.py`
- [x] T008 [P] [US1] Extract `setup_performance_monitor()` function from `_setup_performance_monitoring()` in `planalign_orchestrator/orchestrator_setup.py`
- [x] T009 [P] [US1] Extract `_create_resource_manager()` helper as internal function in `planalign_orchestrator/orchestrator_setup.py`

### Orchestrator Integration

- [x] T010 [US1] Add import for `orchestrator_setup` in `planalign_orchestrator/pipeline_orchestrator.py`
- [x] T011 [US1] Update `__init__()` to call `setup_memory_manager()` instead of `_setup_adaptive_memory_manager()` in `planalign_orchestrator/pipeline_orchestrator.py`
- [x] T012 [US1] Update `__init__()` to call `setup_parallelization()` instead of `_setup_model_parallelization()` in `planalign_orchestrator/pipeline_orchestrator.py`
- [x] T013 [US1] Update `__init__()` to call `setup_hazard_cache()` instead of `_setup_hazard_cache_manager()` in `planalign_orchestrator/pipeline_orchestrator.py`
- [x] T014 [US1] Update `__init__()` to call `setup_performance_monitor()` instead of `_setup_performance_monitoring()` in `planalign_orchestrator/pipeline_orchestrator.py`

### Verification

- [ ] T015 [US2] Run `pytest -m fast` to verify no regressions after setup extraction - **Blocked: environment missing dependencies**
- [ ] T016 [US2] Run `planalign simulate 2025 --dry-run` to verify simulation works with extracted setup - **Blocked: environment missing dependencies**

**Checkpoint**: Setup extraction complete - `orchestrator_setup.py` should have ~250 lines

---

## Phase 3: Validation Extraction (US1 + US2)

**Purpose**: Extract validation logic to `StageValidator` class

**Goal**: Create modular validation class (~150 lines)

**Independent Test**: Run `pytest` full suite; all 256+ tests must pass

### Module Creation

- [x] T017 [US1] Create `planalign_orchestrator/pipeline/stage_validator.py` with module docstring and imports
- [x] T018 [US1] Implement `StageValidator.__init__()` accepting db_manager, config, state_manager, verbose in `planalign_orchestrator/pipeline/stage_validator.py`
- [x] T019 [US1] Implement `StageValidator.validate_stage()` method dispatching to stage-specific validation in `planalign_orchestrator/pipeline/stage_validator.py`
- [x] T020 [US1] Extract `_validate_foundation()` method with FOUNDATION stage logic in `planalign_orchestrator/pipeline/stage_validator.py`
- [x] T021 [US1] Extract `_validate_event_generation()` method with EVENT_GENERATION stage logic in `planalign_orchestrator/pipeline/stage_validator.py`
- [x] T022 [US1] Extract `_validate_state_accumulation()` method with STATE_ACCUMULATION stage logic in `planalign_orchestrator/pipeline/stage_validator.py`
- [x] T023 [US1] Extract `_safe_count()` helper method for safe row count queries in `planalign_orchestrator/pipeline/stage_validator.py`

### Orchestrator Integration

- [x] T024 [US1] Add import for `StageValidator` in `planalign_orchestrator/pipeline_orchestrator.py`
- [x] T025 [US1] Initialize `self.stage_validator = StageValidator(...)` in `__init__()` in `planalign_orchestrator/pipeline_orchestrator.py`
- [x] T026 [US1] Update `_execute_year_workflow()` to call `self.stage_validator.validate_stage()` instead of `_run_stage_validation()` in `planalign_orchestrator/pipeline_orchestrator.py`

### Export Updates

- [x] T027 [US1] Update `planalign_orchestrator/pipeline/__init__.py` to export `StageValidator`
- [x] T028 [US1] Update `__all__` list in `planalign_orchestrator/pipeline/__init__.py` to include `StageValidator`

### Verification

- [ ] T029 [US2] Run `pytest -m fast` to verify no regressions after validation extraction - **Blocked: environment missing dependencies**
- [ ] T030 [US2] Run `pytest` full suite to verify all 256+ tests pass - **Blocked: environment missing dependencies**
- [ ] T031 [US2] Run `planalign simulate 2025-2027` to verify full multi-year simulation works - **Blocked: environment missing dependencies**

**Checkpoint**: Validation extraction complete - `stage_validator.py` should have ~150 lines

---

## Phase 4: Cleanup & Verification (US1 + US2 + US3)

**Purpose**: Remove old code and verify all success criteria

**Goal**: Reduce `pipeline_orchestrator.py` to 650-700 lines with all tests passing

### Code Cleanup

- [x] T032 [US1] Remove `_setup_adaptive_memory_manager()` method from `planalign_orchestrator/pipeline_orchestrator.py`
- [x] T033 [US1] Remove `_setup_model_parallelization()` method from `planalign_orchestrator/pipeline_orchestrator.py`
- [x] T034 [US1] Remove `_setup_hazard_cache_manager()` method from `planalign_orchestrator/pipeline_orchestrator.py`
- [x] T035 [US1] Remove `_setup_performance_monitoring()` method from `planalign_orchestrator/pipeline_orchestrator.py`
- [x] T036 [US1] Remove `_create_resource_manager()` method from `planalign_orchestrator/pipeline_orchestrator.py`
- [x] T037 [US1] Remove `_run_stage_validation()` method from `planalign_orchestrator/pipeline_orchestrator.py`

### Success Criteria Verification

- [x] T038 [US1] Run `wc -l planalign_orchestrator/pipeline_orchestrator.py` to verify ~650-700 lines (SC-001) - **Result: 868 lines** (higher than target, but significant reduction from 1,218)
- [x] T039 [US1] Run `wc -l planalign_orchestrator/orchestrator_setup.py` to verify ~250 lines (SC-002) - **Result: 372 lines**
- [x] T040 [US1] Run `wc -l planalign_orchestrator/pipeline/stage_validator.py` to verify ~150 lines (SC-003) - **Result: 233 lines**
- [ ] T041 [US3] Run `pytest` to verify all 256+ tests pass (SC-004) - **Blocked: environment missing dependencies**
- [ ] T042 [US2] Run `planalign simulate 2025 --dry-run` to verify dry run works (SC-005) - **Blocked: environment missing dependencies**
- [ ] T043 [US2] Run `python -c "from planalign_orchestrator import create_orchestrator; print('OK')"` to verify public API (SC-006) - **Blocked: environment missing dependencies**

**Checkpoint**: All success criteria verified

---

## Phase 5: Polish & Documentation (US4)

**Purpose**: Optional enhancements for testability and documentation

### Optional Exports (FR-008)

- [ ] T044 [P] [US4] Consider adding setup functions to `planalign_orchestrator/__init__.py` exports (optional)

### Documentation

- [ ] T045 [P] Run quickstart.md validation to ensure documentation is accurate

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies - establishes baseline
- **Phase 2 (Setup Extraction)**: Depends on Phase 1 - can begin immediately after baseline
- **Phase 3 (Validation Extraction)**: Depends on Phase 2 completion - lower risk if done after setup works
- **Phase 4 (Cleanup)**: Depends on Phase 3 completion - removes old code after new modules work
- **Phase 5 (Polish)**: Depends on Phase 4 - optional enhancements

### User Story Mapping

| Story | Tasks | Description |
|-------|-------|-------------|
| US1 (Modular Code) | T004-T014, T017-T028, T032-T040 | Create new modules, integrate, verify line counts |
| US2 (Zero Regression) | T015-T016, T029-T031, T041-T043 | Verify tests pass, simulation works |
| US3 (Test Validation) | T041 | Verify full test suite passes |
| US4 (Isolated Testing) | T044-T045 | Optional exports for direct testing |

### Parallel Opportunities

**Within Phase 2 (Setup Module Creation)**:
```bash
# These can run in parallel (different functions, no dependencies):
T005: Extract setup_memory_manager()
T006: Extract setup_parallelization()
T007: Extract setup_hazard_cache()
T008: Extract setup_performance_monitor()
T009: Extract _create_resource_manager()
```

**Within Phase 4 (Cleanup)**:
```bash
# These can run in parallel (removing independent methods):
T032: Remove _setup_adaptive_memory_manager()
T033: Remove _setup_model_parallelization()
T034: Remove _setup_hazard_cache_manager()
T035: Remove _setup_performance_monitoring()
T036: Remove _create_resource_manager()
```

---

## Implementation Strategy

### MVP First (Phases 1-2)

1. Complete Phase 1: Establish baseline
2. Complete Phase 2: Extract setup module
3. **STOP and VALIDATE**: Run `pytest -m fast` and `planalign simulate 2025 --dry-run`
4. If passing, continue to Phase 3

### Full Delivery (Phases 1-4)

1. Complete Phase 1: Setup
2. Complete Phase 2: Setup Extraction → Verify
3. Complete Phase 3: Validation Extraction → Verify
4. Complete Phase 4: Cleanup → Verify all success criteria
5. **DONE**: Feature complete

### Rollback Strategy

- After each phase, commit to git
- If tests fail, revert to previous commit
- Each phase is independently revertable

---

## Notes

- [P] tasks = different files or independent functions, no dependencies
- This is a refactoring task - US1 (modular code) and US2 (zero regression) are validated together
- Run tests after each extraction step to catch regressions early
- Preserve verbose output messages exactly - copy print statements unchanged
- Commit after each phase completion for easy rollback
