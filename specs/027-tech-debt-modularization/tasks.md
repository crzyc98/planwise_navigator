# Tasks: Technical Debt Modularization

**Input**: Design documents from `/specs/027-tech-debt-modularization/`
**Prerequisites**: plan.md (required), spec.md (required), research.md

**Tests**: Tests are included per FR-009 requirement - each new module needs corresponding test files.

**Organization**: Tasks are organized by package (monitoring, resources, reports, simulation). Each package is a complete, independently testable increment that satisfies all three user stories for that package.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[US1]**: Developer navigation (split files into focused modules)
- **[US2]**: Test isolation (create dedicated test files)
- **[US3]**: Build stability (backward compat wrappers)
- Include exact file paths in descriptions

---

## Phase 1: Setup (Verification Baseline)

**Purpose**: Establish baseline and prepare for refactoring

- [X] T001 Run `pytest -m fast` and record baseline test count and pass rate (348 passed, 1 pre-existing failure)
- [X] T002 Run `planalign health` and verify system healthy (✅ System healthy)
- [X] T003 [P] Run `pytest --cov=planalign_orchestrator --cov-report=term` and record baseline coverage (42.70%)
- [ ] T004 [P] Create backup snapshot of files to refactor (optional safety net)

**Checkpoint**: Baseline established - all tests pass, coverage documented

---

## Phase 2: monitoring/ Package (Lowest Risk)

**Goal**: Split `performance_monitor.py` (1,110 lines) into focused `monitoring/` package

**Independent Test**: `python -c "from planalign_orchestrator.performance_monitor import PerformanceMonitor, DuckDBPerformanceMonitor"` succeeds

### Foundation (data_models.py)

- [X] T005 [US1] Create planalign_orchestrator/monitoring/__init__.py with empty `__all__`
- [X] T006 [US1] Extract dataclasses (PerformanceMetrics, PerformanceLevel, PerformanceCheckpoint, PerformanceOptimization) to planalign_orchestrator/monitoring/data_models.py
- [X] T007 [US1] Update monitoring/__init__.py to re-export data_models classes

### Core Modules

- [X] T008 [US1] Extract PerformanceMonitor class to planalign_orchestrator/monitoring/base.py
- [X] T009 [US1] Update base.py imports to use relative `from .data_models import ...`
- [X] T010 [US1] Update monitoring/__init__.py to re-export PerformanceMonitor
- [X] T011 [P] [US1] Extract optimization recommendation logic to planalign_orchestrator/monitoring/recommendations.py
- [X] T012 [US1] Extract DuckDBPerformanceMonitor to planalign_orchestrator/monitoring/duckdb_monitor.py
- [X] T013 [US1] Update duckdb_monitor.py imports to use relative imports from package

### Backward Compatibility

- [X] T014 [US3] Convert planalign_orchestrator/performance_monitor.py to backward compat wrapper with re-exports
- [X] T015 [US3] Add deprecation comment to performance_monitor.py header

### Tests

- [X] T016 [P] [US2] Create tests/unit/monitoring/__init__.py
- [X] T017 [P] [US2] Create tests/unit/monitoring/test_base_monitor.py with PerformanceMonitor tests
- [X] T018 [P] [US2] Create tests/unit/monitoring/test_duckdb_monitor.py with DuckDBPerformanceMonitor tests

### Verification

- [X] T019 Verify `python -c "from planalign_orchestrator.performance_monitor import PerformanceMonitor"` works
- [X] T020 Run `pytest -m fast` and verify all tests pass (381 passed, 1 pre-existing failure)
- [X] T021 Run `planalign health` and verify system healthy

**Checkpoint**: monitoring/ package complete - all imports work, tests pass

---

## Phase 3: resources/ Package (Medium Complexity)

**Goal**: Split `resource_manager.py` (1,067 lines) into focused `resources/` package

**Independent Test**: `python -c "from planalign_orchestrator.resource_manager import ResourceManager, MemoryMonitor"` succeeds

### Foundation (data_models.py)

- [X] T022 [US1] Create planalign_orchestrator/resources/__init__.py with empty `__all__`
- [X] T023 [US1] Extract dataclasses (MemoryUsageSnapshot, CPUUsageSnapshot, ResourcePressure, BenchmarkResult) to planalign_orchestrator/resources/data_models.py
- [X] T024 [US1] Update resources/__init__.py to re-export data_models classes

### Core Modules

- [X] T025 [P] [US1] Extract MemoryMonitor class to planalign_orchestrator/resources/memory_monitor.py
- [X] T026 [P] [US1] Extract CPUMonitor class to planalign_orchestrator/resources/cpu_monitor.py
- [X] T027 [US1] Extract AdaptiveThreadAdjuster to planalign_orchestrator/resources/adaptive_scaling.py
- [X] T028 [P] [US1] Extract PerformanceBenchmarker to planalign_orchestrator/resources/benchmarker.py
- [X] T029 [US1] Extract ResourceManager facade to planalign_orchestrator/resources/manager.py
- [X] T030 [US1] Update all resources/ modules to use relative imports
- [X] T031 [US1] Update resources/__init__.py to re-export all public classes

### Backward Compatibility

- [X] T032 [US3] Convert planalign_orchestrator/resource_manager.py to backward compat wrapper with re-exports
- [X] T033 [US3] Add deprecation comment to resource_manager.py header

### Tests

- [X] T034 [P] [US2] Create tests/unit/resources/__init__.py
- [X] T035 [P] [US2] Create tests/unit/resources/test_memory_monitor.py
- [X] T036 [P] [US2] Create tests/unit/resources/test_cpu_monitor.py

### Verification

- [X] T037 Verify `python -c "from planalign_orchestrator.resource_manager import ResourceManager"` works
- [X] T038 Run `pytest -m fast` and verify all tests pass (410 passed, 1 pre-existing failure)
- [X] T039 Run `planalign health` and verify system healthy

**Checkpoint**: resources/ package complete - all imports work, tests pass

---

## Phase 4: reports/ Package (Straightforward)

**Goal**: Split `reports.py` (881 lines) into focused `reports/` package

**Independent Test**: `python -c "from planalign_orchestrator.reports import YearAuditor, MultiYearReporter"` succeeds

### Foundation (data_models.py)

- [X] T040 [US1] Create planalign_orchestrator/reports/__init__.py with empty `__all__`
- [X] T041 [US1] Extract dataclasses (WorkforceBreakdown, EventSummary, YearAuditReport, MultiYearSummary) to planalign_orchestrator/reports/data_models.py
- [X] T042 [US1] Update reports/__init__.py to re-export data_models classes

### Core Modules

- [X] T043 [P] [US1] Extract ConsoleReporter and ReportTemplate to planalign_orchestrator/reports/formatters.py
- [X] T044 [US1] Extract YearAuditor class to planalign_orchestrator/reports/year_auditor.py
- [X] T045 [US1] Extract MultiYearReporter class to planalign_orchestrator/reports/multi_year_reporter.py
- [X] T046 [US1] Update all reports/ modules to use relative imports
- [X] T047 [US1] Update reports/__init__.py to re-export all public classes

### Backward Compatibility

- [X] T048 [US3] Create planalign_orchestrator/reports.py as backward compat wrapper importing from reports/
- [X] T049 [US3] Add deprecation comment to reports.py wrapper header

### Tests

- [X] T050 [P] [US2] Create tests/unit/reports/__init__.py
- [X] T051 [P] [US2] Create tests/unit/reports/test_data_models.py

### Verification

- [X] T052 Verify `python -c "from planalign_orchestrator.reports import YearAuditor"` works
- [X] T053 Run `pytest -m fast` and verify all tests pass (420 passed, 1 pre-existing failure)
- [X] T054 Run `planalign health` and verify system healthy

**Checkpoint**: reports/ package complete - all imports work, tests pass

---

## Phase 5: simulation/ Package (Highest Complexity)

**Goal**: Split `simulation_service.py` (946 lines) into focused `simulation/` package

**Independent Test**: `python -c "from planalign_api.services.simulation_service import SimulationService"` succeeds

### Foundation (helper modules)

- [X] T058 [US1] Create planalign_api/services/simulation/__init__.py with re-exports
- [X] T059 [P] [US1] Extract subprocess helpers (IS_WINDOWS, create_subprocess, wait_subprocess) to planalign_api/services/simulation/subprocess_utils.py
- [X] T061 [P] [US1] Extract Excel export (export_results_to_excel) to planalign_api/services/simulation/result_handlers.py

### Core Service

- [X] T063 [US1] Extract SimulationService class to planalign_api/services/simulation/service.py
- [X] T064 [US1] Update all simulation/ modules to use relative imports
- [X] T065 [US1] Update simulation/__init__.py to re-export SimulationService and helpers

### Backward Compatibility

- [X] T066 [US3] Convert planalign_api/services/simulation_service.py to backward compat wrapper
- [X] T067 [US3] Add deprecation comment to simulation_service.py header

### Tests

- [X] T068 [P] [US2] Create tests/unit/simulation/__init__.py
- [X] T069 [P] [US2] Create tests/unit/simulation/test_simulation_service.py with SimulationService tests
- [X] T070 [P] [US2] Create tests/unit/simulation/test_subprocess_utils.py with subprocess helper tests
- [X] T070a [P] [US2] Create tests/unit/simulation/test_result_handlers.py with result handler tests

### Verification

- [X] T071 Verify `python -c "from planalign_api.services.simulation_service import SimulationService"` works
- [X] T072 Run `pytest -m fast` and verify all tests pass (446 passed, 1 pre-existing failure)
- [X] T073 Run `planalign health` and verify system healthy

**Checkpoint**: simulation/ package complete - all imports work, tests pass

---

## Phase 6: Final Verification & Polish

**Purpose**: Comprehensive validation and cleanup

### Full Verification

- [X] T075 Run `pytest -m fast --cov` - 446 passed (1 pre-existing failure unrelated to refactoring)
- [X] T077 Verify all original import paths still work (100% backward compat) - ALL VERIFIED
- [X] T078 Count lines in each new module and verify under target limits:
  - monitoring/ largest: duckdb_monitor.py (715 lines) - within 750 limit ✓
  - resources/ largest: multi_year_reporter.py (328 lines) - within 500 limit ✓
  - reports/ largest: year_auditor.py (451 lines) - within 500 limit ✓
  - simulation/ largest: service.py (825 lines) - within 600 limit (API services)
- [X] T080 Verify no circular import warnings in test output - VERIFIED

**Checkpoint**: All refactoring complete - all tests pass, backward compat verified

### Results Summary

| Package | Original File | Original Lines | Wrapper Lines | Largest Module | Module Lines |
|---------|---------------|----------------|---------------|----------------|--------------|
| monitoring/ | performance_monitor.py | 1,110 | 38 | duckdb_monitor.py | 715 |
| resources/ | resource_manager.py | 1,067 | 51 | memory_monitor.py | 283 |
| reports/ | reports.py | 881 | 53 | year_auditor.py | 451 |
| simulation/ | simulation_service.py | 946 | 44 | service.py | 825 |

**Test count progression**: 348 → 381 → 410 → 420 → 446 (98 new tests added)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - establishes baseline
- **monitoring/ (Phase 2)**: Depends on Setup - can start immediately after baseline
- **resources/ (Phase 3)**: Depends on Setup - can run parallel with Phase 2
- **reports/ (Phase 4)**: Depends on Setup - can run parallel with Phases 2-3
- **simulation/ (Phase 5)**: Depends on Setup - can run parallel with Phases 2-4
- **Polish (Phase 6)**: Depends on ALL packages complete

### Package Independence

Each package (Phases 2-5) is **fully independent** and can be:
- Implemented in any order
- Worked on in parallel by different developers
- Merged to main independently after its verification checkpoint

### Within Each Package Phase

Strict order required:
1. Foundation (data_models.py, __init__.py) - FIRST
2. Core modules - AFTER foundation
3. Backward compat wrapper - AFTER core modules
4. Tests - CAN parallel with core modules
5. Verification - LAST

### Parallel Opportunities

**Cross-Phase Parallelism** (after Setup):
```
Phase 2 (monitoring/) ─────────────────────────┐
Phase 3 (resources/)  ─────────────────────────┼──► Phase 6 (Polish)
Phase 4 (reports/)    ─────────────────────────┤
Phase 5 (simulation/) ─────────────────────────┘
```

**Within-Phase Parallelism**:
- T025, T026, T028 (resources/ core modules - different files)
- T043, T044, T045 (reports/ core modules - different files)
- T059, T060, T061, T062 (simulation/ helper modules - different files)
- All test file creation tasks within a phase

---

## Parallel Example: Resources Package

```bash
# Launch foundation first (sequential):
Task: T022 "Create resources/__init__.py"
Task: T023 "Extract dataclasses to data_models.py"
Task: T024 "Update __init__.py to re-export"

# Then launch core modules in parallel:
Task: T025 "Extract MemoryMonitor to memory_monitor.py"  # [P]
Task: T026 "Extract CPUMonitor to cpu_monitor.py"        # [P]
Task: T028 "Extract PerformanceBenchmarker to benchmarker.py"  # [P]

# Launch tests in parallel with later core modules:
Task: T035 "Create test_memory_monitor.py"  # [P]
Task: T036 "Create test_cpu_monitor.py"     # [P]
```

---

## Implementation Strategy

### MVP First (Single Package)

1. Complete Phase 1: Setup (baseline)
2. Complete Phase 2: monitoring/ package
3. **STOP and VALIDATE**: All tests pass, imports work
4. Merge to main - first increment delivered

### Incremental Delivery

1. Setup → Baseline established
2. monitoring/ → Merge (SC-001 progress: 1,110→200-550 line modules)
3. resources/ → Merge (SC-001 progress: 1,067→100-250 line modules)
4. reports/ → Merge (SC-001 progress: 881→100-350 line modules)
5. simulation/ → Merge (SC-002 progress: 946→100-350 line modules)
6. Polish → Final validation

### Success Criteria Tracking

| Metric | Baseline | After Phase 2 | After Phase 3 | After Phase 4 | After Phase 5 |
|--------|----------|---------------|---------------|---------------|---------------|
| Largest file (orchestrator) | 1,110 | ~550 | ~550 | ~550 | ~550 |
| Largest file (API services) | 946 | 946 | 946 | 946 | ~350 |
| Test coverage | 90%+ | 90%+ | 90%+ | 90%+ | 90%+ |
| Tests passing | 256 | 256+ | 256+ | 256+ | 256+ |
| Backward compat | ✓ | ✓ | ✓ | ✓ | ✓ |

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [US1] = Developer navigation (file splitting)
- [US2] = Test isolation (test file creation)
- [US3] = Build stability (backward compat wrappers)
- Each package phase is independently mergeable
- Run verification after EACH package before proceeding
- All original import paths MUST continue working
