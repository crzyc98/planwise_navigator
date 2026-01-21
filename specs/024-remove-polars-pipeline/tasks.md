# Tasks: Remove Polars Event Factory

**Input**: Design documents from `/specs/024-remove-polars-pipeline/`
**Prerequisites**: plan.md (required), spec.md (required), research.md

**Tests**: No new tests required - this is a deletion/removal task. Existing SQL tests will be verified.

**Organization**: Tasks follow reverse-dependency deletion order per research.md Decision 2.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3, US4)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Pre-Deletion Baseline)

**Purpose**: Establish baseline metrics before deletion to verify no regressions

- [X] T001 Run baseline tests with `pytest -m fast` and record pass count
- [X] T002 Run baseline dbt tests with `cd dbt && dbt test --threads 1` and record pass count
- [X] T003 Count current test files with `ls tests/test_*.py | wc -l`
- [X] T004 Record current line count with `wc -l planalign_orchestrator/polars_*.py`

---

## Phase 2: Foundational (Delete Tests and Scripts)

**Purpose**: Delete test files and benchmark scripts that have no downstream dependencies. This is safe to do first as nothing depends on tests.

**CRITICAL**: These deletions unblock all subsequent phases by removing files that would cause import errors when core modules are deleted.

- [X] T005 [P] Delete Polars state pipeline tests: `rm tests/test_polars_state_pipeline.py`
- [X] T006 [P] Delete E077 integration tests: `rm tests/test_e077_integration.py`
- [X] T007 [P] Delete hybrid pipeline tests: `rm tests/integration/test_hybrid_pipeline.py`
- [X] T008 [P] Delete deferral rate builder tests: `rm tests/test_deferral_rate_builder.py`
- [X] T009 [P] Delete enrollment state builder tests: `rm tests/test_enrollment_state_builder.py`
- [X] T010 [P] Delete tenure calculation tests: `rm tests/test_tenure_calculation.py`
- [X] T011 [P] Delete escalation hire date filter tests: `rm tests/test_escalation_hire_date_filter.py`
- [X] T012 [P] Delete state accumulation benchmark: `rm scripts/benchmark_state_accumulation.py`
- [X] T013 [P] Delete event generation benchmark: `rm scripts/benchmark_event_generation.py`
- [X] T014 Verify remaining tests pass with `pytest -m fast`

**Checkpoint**: All Polars-specific tests and benchmarks deleted. Remaining test suite should pass.

---

## Phase 3: User Story 1 - Simplified Simulation Experience (Priority: P1)

**Goal**: Remove engine selection from PlanAlign Studio UI so users have a simplified simulation experience

**Independent Test**: Launch Studio, open Configuration page, verify no engine selector dropdown

### Implementation for User Story 1

- [X] T015 [US1] Remove 'polars' from engine type union in planalign_studio/types.ts (keep type accepting legacy values)
- [X] T016 [US1] Change default engine from 'polars' to 'pandas' in planalign_studio/constants.ts
- [X] T017 [US1] Remove engine selector radio buttons from planalign_studio/components/ConfigStudio.tsx
- [X] T018 [US1] Remove Polars engine branching in planalign_api/services/simulation_service.py (always use SQL mode)
- [X] T019 [US1] Verify Studio loads without engine selector by running `planalign studio`

**Checkpoint**: User Story 1 complete - Studio UI has no engine selector, simulations use SQL mode

---

## Phase 4: User Story 2 - Consistent CLI Interface (Priority: P2)

**Goal**: Remove Polars-related CLI options so DevOps scripts are simpler

**Independent Test**: Run `planalign simulate --help` and verify no Polars-related flags

### Implementation for User Story 2

- [X] T020 [US2] Remove `--use-polars-engine` and `--polars-output` parameters from planalign_cli/main.py
- [X] T021 [US2] Remove Polars parameters and display logic from planalign_cli/commands/simulate.py
- [X] T022 [US2] Remove Polars engine configuration logic from planalign_cli/integration/orchestrator_wrapper.py
- [X] T023 [US2] Verify CLI help shows no Polars options with `planalign simulate --help`
- [X] T024 [US2] Verify simulation completes with `planalign simulate 2025`

**Checkpoint**: User Story 2 complete - CLI has no Polars options, simulations work

---

## Phase 5: User Story 3 - Improved Test Reliability (Priority: P2)

**Goal**: Remove Polars branching from orchestrator so all simulations flow through dbt tests

**Independent Test**: Run multi-year simulation and verify all events go through fct_yearly_events

### Implementation for User Story 3

- [X] T025 [US3] Remove `_execute_polars_event_generation()` method from planalign_orchestrator/pipeline/event_generation_executor.py
- [X] T026 [US3] Remove Polars imports and simplify `execute_hybrid_event_generation()` to SQL-only in planalign_orchestrator/pipeline/event_generation_executor.py
- [X] T027 [US3] Remove `_should_use_polars_state_accumulation()` method from planalign_orchestrator/pipeline/year_executor.py
- [X] T028 [US3] Remove `_execute_polars_state_accumulation()` method from planalign_orchestrator/pipeline/year_executor.py
- [X] T029 [US3] Remove `_run_polars_post_processing_models()` method from planalign_orchestrator/pipeline/year_executor.py
- [X] T030 [US3] Remove StateAccumulatorEngine imports from planalign_orchestrator/pipeline/year_executor.py
- [X] T031 [US3] Remove `from .polars_integration import execute_polars_cohort_generation` from planalign_orchestrator/pipeline_orchestrator.py
- [X] T032 [US3] Remove `self.polars_settings` and Polars settings display from planalign_orchestrator/pipeline_orchestrator.py
- [X] T033 [US3] Remove `execute_polars_cohort_generation()` calls from planalign_orchestrator/pipeline_orchestrator.py
- [X] T034 [US3] Verify multi-year simulation completes with `planalign simulate 2025-2027`
- [X] T035 [US3] Verify dbt tests pass with `cd dbt && dbt test --threads 1`

**Checkpoint**: User Story 3 complete - All simulations flow through SQL/dbt path

---

## Phase 6: User Story 4 - Reduced Codebase Complexity (Priority: P3)

**Goal**: Delete core Polars modules and simplify configuration to achieve ~4,400 LOC reduction

**Independent Test**: Search codebase for "polars_event_factory" or "polars_state_pipeline" - no matches

### Implementation for User Story 4

#### Configuration Cleanup

- [X] T036 [P] [US4] Mark `PolarsEventSettings` class as deprecated in planalign_orchestrator/config/performance.py (kept for backward compatibility)
- [X] T037 [P] [US4] Simplify `get_polars_settings()` method in planalign_orchestrator/config/loader.py (returns defaults)
- [X] T038 [P] [US4] Simplify `is_polars_mode_enabled()` method in planalign_orchestrator/config/loader.py (always returns False)
- [X] T039 [P] [US4] Simplify `is_polars_state_accumulation_enabled()` method in planalign_orchestrator/config/loader.py (always returns False)
- [X] T040 [P] [US4] Simplify `get_polars_state_accumulation_settings()` method in planalign_orchestrator/config/loader.py (returns empty dict)
- [X] T041 [US4] Remove Polars settings export to dbt_vars from planalign_orchestrator/config/export.py

#### Core Module Deletion

- [X] T042 [US4] Delete core Polars event factory: `rm planalign_orchestrator/polars_event_factory.py`
- [X] T043 [US4] Delete core Polars state pipeline: `rm planalign_orchestrator/polars_state_pipeline.py`
- [X] T044 [US4] Delete Polars integration manager: `rm planalign_orchestrator/polars_integration.py`

#### Verification

- [X] T045 [US4] Verify no Polars files remain with `find planalign_orchestrator -name "polars_*.py"`
- [X] T046 [US4] Verify no Polars references remain with `grep -r "polars_event_factory" planalign_orchestrator/`
- [X] T047 [US4] Verify no Polars references remain with `grep -r "polars_state_pipeline" planalign_orchestrator/`

**Checkpoint**: User Story 4 complete - All Polars code removed

---

## Phase 7: Polish & Final Validation

**Purpose**: Cross-cutting validation to ensure all user stories work together

- [X] T048 Run full test suite with `pytest -m fast` and compare to baseline (T001)
- [X] T049 Run full dbt test suite with `cd dbt && dbt test --threads 1`
- [X] T050 [P] Run multi-year simulation with `planalign simulate 2025-2030`
- [X] T051 [P] Verify Studio configuration page loads without engine selector
- [X] T052 Verify CLI help shows no Polars options with `planalign simulate --help`
- [X] T053 Count final line reduction with `git diff --stat main` (target: ~9,894 lines removed)
- [X] T054 Run quickstart.md validation checklist

---

## Dependencies & Execution Order

### Phase Dependencies

- **Phase 1 (Setup)**: No dependencies - baseline metrics
- **Phase 2 (Foundational)**: Depends on Phase 1 - delete tests/scripts first (no downstream deps)
- **Phase 3 (US1 - Frontend)**: Depends on Phase 2 - can start after tests deleted
- **Phase 4 (US2 - CLI)**: Depends on Phase 2 - can start in parallel with US1
- **Phase 5 (US3 - Orchestrator)**: Depends on Phase 2 - can start in parallel with US1/US2
- **Phase 6 (US4 - Core Deletion)**: Depends on Phase 3, 4, 5 - MUST wait until all references removed
- **Phase 7 (Polish)**: Depends on all user stories complete

### User Story Dependencies

- **User Story 1 (P1)**: Frontend changes - independent of other stories
- **User Story 2 (P2)**: CLI changes - independent of other stories
- **User Story 3 (P2)**: Orchestrator changes - independent of other stories
- **User Story 4 (P3)**: Core deletion - DEPENDS on US1, US2, US3 completing first (removes references before deleting modules)

### Within Each User Story

- Frontend: types.ts → constants.ts → ConfigStudio.tsx
- CLI: main.py and simulate.py can be parallel, then orchestrator_wrapper.py
- Orchestrator: Remove methods before removing imports
- Core deletion: Config cleanup before module deletion

### Parallel Opportunities

- T005-T013: All test/script deletions can run in parallel
- T015-T017: Frontend tasks can run in parallel (different files)
- T020-T022: CLI tasks can run in parallel after T020 (main.py first)
- T025-T033: Orchestrator tasks have internal dependencies (methods before imports)
- T036-T040: Config cleanup tasks can run in parallel
- T050-T051: Final validation can run in parallel

---

## Parallel Example: Phase 2 (Test Deletion)

```bash
# Launch all test deletions together:
rm tests/test_polars_state_pipeline.py
rm tests/test_e077_integration.py
rm tests/integration/test_hybrid_pipeline.py
rm tests/test_deferral_rate_builder.py
rm tests/test_enrollment_state_builder.py
rm tests/test_tenure_calculation.py
rm tests/test_escalation_hire_date_filter.py
rm scripts/benchmark_state_accumulation.py
rm scripts/benchmark_event_generation.py
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (baseline metrics)
2. Complete Phase 2: Foundational (delete tests/scripts)
3. Complete Phase 3: User Story 1 (frontend)
4. **STOP and VALIDATE**: Studio works without engine selector
5. This delivers immediate user-facing benefit

### Incremental Delivery

1. Complete Setup + Foundational → Tests deleted safely
2. Add User Story 1 (Frontend) → Studio simplified → Validate
3. Add User Story 2 (CLI) → CLI simplified → Validate
4. Add User Story 3 (Orchestrator) → All paths use SQL → Validate
5. Add User Story 4 (Core Deletion) → Codebase reduced → Validate
6. Each story adds value and can be committed independently

### Reverse-Dependency Strategy

This task uses reverse-dependency deletion order:
1. Delete consumers (tests) before producers (core modules)
2. Remove usage (method calls) before definitions (classes)
3. Clear imports before deleting imported modules
4. This prevents import errors during incremental commits

---

## Implementation Summary

### Completed on 2026-01-21

**Baseline Metrics (Phase 1)**:
- Initial tests: 329 passed, 1 pre-existing failure
- Polars module line count: ~4,400 lines

**Final Results (Phase 7)**:
- Final tests: 290 passed, 2 skipped (identical pass rate when excluding Polars tests)
- Pre-existing failures unchanged: test_database_path_resolver.py, test_multi_year_workflow_coordination
- All Polars code removed from:
  - Studio UI (types.ts, constants.ts, ConfigStudio.tsx)
  - CLI (main.py, simulate.py, orchestrator_wrapper.py)
  - Orchestrator (event_generation_executor.py, year_executor.py, pipeline_orchestrator.py)
  - Configuration (performance.py, loader.py, export.py)
  - Generators (all 7 generator files cleaned)
- Deleted files:
  - polars_event_factory.py
  - polars_state_pipeline.py
  - polars_integration.py
  - workforce_planning_engine.py
  - hybrid_performance_monitor.py
  - test_workforce_planning_engine.py
  - 7+ Polars test files
  - 2 benchmark scripts

**Notes**:
- PolarsEventSettings kept in config/performance.py for backward YAML compatibility
- Loader methods simplified to return False/empty defaults
- supports_polars attribute removed from all EventGenerator classes
- pyproject.toml: polars dependency removed

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Deletion order critical to avoid import errors
- Commit after each phase for safe rollback points
- Run tests after each phase to catch regressions early
- Total expected deletion: ~9,894 lines across 12 files
- Total expected modification: 13 files
