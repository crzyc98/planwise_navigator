# Feature Specification: Orchestrator Modularization Phase 2

**Feature Branch**: `034-orchestrator-modularization`
**Created**: 2026-02-05
**Status**: Draft
**Input**: User description: "Extract setup and validation concerns from pipeline_orchestrator.py (1,218 lines) into focused modules while preserving the public API."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Developer Maintains Orchestrator Code (Priority: P1)

As a developer working on the PlanAlign Engine, I want the orchestrator code to be modular and focused so that I can understand, modify, and debug individual concerns without navigating a 1,200+ line file.

**Why this priority**: Developer productivity directly impacts feature velocity. A complex, monolithic file increases cognitive load, extends onboarding time, and increases bug risk during modifications.

**Independent Test**: Can be fully tested by running the existing test suite and verifying all 256+ tests pass after extraction. Delivers immediate value by reducing file complexity.

**Acceptance Scenarios**:

1. **Given** the current `pipeline_orchestrator.py` with 1,218 lines, **When** the extraction is complete, **Then** the file is reduced to ~650-700 lines containing only core coordination logic.

2. **Given** a new developer onboarding to the codebase, **When** they need to understand memory management setup, **Then** they can find it in a dedicated `orchestrator_setup.py` module (~250 lines) rather than searching a 1,200+ line file.

3. **Given** a developer debugging validation failures, **When** they trace validation logic, **Then** they find it in a dedicated `pipeline/stage_validator.py` module (~150 lines) with clear, focused responsibility.

---

### User Story 2 - Simulation Runs Successfully After Refactoring (Priority: P1)

As a financial analyst running multi-year simulations, I want the orchestrator refactoring to be completely transparent so that my simulation results are identical before and after the change.

**Why this priority**: Zero regression is mandatory for a code refactoring task. The refactoring must be behavior-preserving.

**Independent Test**: Run `planalign simulate 2025-2027` before and after refactoring. Outputs (events, snapshots, summaries) must be byte-identical given the same random seed.

**Acceptance Scenarios**:

1. **Given** a simulation configuration with random seed 42, **When** I run `planalign simulate 2025-2027` before and after the refactoring, **Then** the `fct_yearly_events` table contains identical rows.

2. **Given** the public API `PipelineOrchestrator(config, db_manager, dbt_runner, registry_manager, validator, *, reports_dir, checkpoints_dir, verbose, enhanced_checkpoints)`, **When** I instantiate the orchestrator, **Then** it accepts the same constructor signature without changes.

3. **Given** external code accessing `.config`, `.db_manager`, `.hook_manager`, `.state_manager`, `.memory_manager` properties, **When** that code runs after refactoring, **Then** it retrieves the same objects as before.

---

### User Story 3 - Test Suite Validates Refactoring (Priority: P2)

As a code reviewer, I want the existing test suite to validate the refactoring so that I can have confidence the extraction maintains correctness.

**Why this priority**: Test coverage provides automated verification. Passing tests after extraction demonstrates behavior preservation.

**Independent Test**: Run `pytest -m fast` (87 tests) and full integration tests. All must pass without modification.

**Acceptance Scenarios**:

1. **Given** the current test suite with 256+ tests, **When** I run `pytest` after extraction, **Then** all tests pass (excluding any new tests added for the extracted modules).

2. **Given** tests that import from `planalign_orchestrator`, **When** I run them after refactoring, **Then** import paths remain unchanged (imports still work from `planalign_orchestrator`).

---

### User Story 4 - New Modules Are Testable in Isolation (Priority: P3)

As a developer adding new setup or validation logic, I want the extracted modules to be independently testable so that I can write focused unit tests without setting up the entire orchestrator.

**Why this priority**: Testability improves long-term maintainability and enables faster test cycles during development.

**Independent Test**: New unit tests can instantiate `setup_memory_manager()` or `StageValidator` directly without creating a full `PipelineOrchestrator`.

**Acceptance Scenarios**:

1. **Given** the extracted `setup_memory_manager()` function, **When** I call it with a mock config, **Then** it returns a properly configured `AdaptiveMemoryManager` without requiring a database connection.

2. **Given** the extracted `StageValidator` class, **When** I instantiate it with mocked dependencies, **Then** I can test validation logic in isolation.

---

### Edge Cases

- What happens when optional subsystems (parallelization, hazard cache, performance monitoring) fail to initialize?
  - The system logs a warning and continues without that subsystem (existing behavior preserved).

- How does the system handle missing dbt manifest during parallelization setup?
  - Logs a warning and disables model parallelization (existing behavior preserved).

- What if validation queries fail on tables that don't exist yet?
  - Returns 0 count safely and logs informational message (existing `_safe_count` behavior preserved).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST extract all setup methods (`_setup_adaptive_memory_manager`, `_setup_model_parallelization`, `_setup_hazard_cache_manager`, `_setup_performance_monitoring`) into a new `orchestrator_setup.py` module as standalone functions.

- **FR-002**: System MUST extract `_run_stage_validation()` method into a new `StageValidator` class in `pipeline/stage_validator.py`.

- **FR-003**: System MUST preserve the exact public constructor signature: `PipelineOrchestrator(config, db_manager, dbt_runner, registry_manager, validator, *, reports_dir, checkpoints_dir, verbose, enhanced_checkpoints)`.

- **FR-004**: System MUST preserve all publicly accessible properties: `.config`, `.db_manager`, `.hook_manager`, `.state_manager`, `.memory_manager`.

- **FR-005**: System MUST maintain the exact behavior of `execute_multi_year_simulation()` including return type `MultiYearSummary`.

- **FR-006**: Extracted setup functions MUST return the initialized subsystem objects (or `None` on failure) with identical fallback behavior to current implementation.

- **FR-007**: Extracted `StageValidator` MUST accept the same parameters as the current validation logic and produce identical validation output (prints, exceptions).

- **FR-008**: System MUST export new components from `planalign_orchestrator/__init__.py` for optional direct usage while maintaining backward compatibility.

- **FR-009**: System MUST update `planalign_orchestrator/pipeline/__init__.py` to export `StageValidator`.

### Key Entities

- **OrchestratorSetup Module**: Collection of stateless factory functions that create and configure subsystems (memory manager, parallelization engine, hazard cache, performance monitor).

- **StageValidator Class**: Encapsulates stage-specific validation logic for FOUNDATION, EVENT_GENERATION, and STATE_ACCUMULATION stages. Holds references to `db_manager`, `config`, and `verbose` flag.

- **PipelineOrchestrator (slimmed)**: Coordinator class reduced to ~650 lines, delegating setup to factory functions and validation to `StageValidator`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: `pipeline_orchestrator.py` is reduced from 1,218 lines to 650-700 lines (42-46% reduction).

- **SC-002**: New `orchestrator_setup.py` contains ~250 lines of extracted setup functions.

- **SC-003**: New `pipeline/stage_validator.py` contains ~150 lines of extracted validation logic.

- **SC-004**: All 256+ existing tests pass without modification after extraction.

- **SC-005**: `planalign simulate 2025 --dry-run` completes successfully with identical output behavior.

- **SC-006**: Public API verification command `python -c "from planalign_orchestrator import create_orchestrator; print('OK')"` executes successfully.

- **SC-007**: No changes to any file outside `planalign_orchestrator/` directory (except potentially `CLAUDE.md` documentation updates).

## Assumptions

- The current 1,218-line count is accurate based on the file content read during specification.
- The setup methods (`_setup_*`) are internally cohesive and can be extracted as standalone functions without circular dependencies.
- The validation logic in `_run_stage_validation()` depends only on `db_manager`, `config`, `state_manager`, and `verbose` - all injectable.
- The existing test suite provides sufficient coverage to detect behavioral regressions.
- No new external dependencies are required for the extraction.
- The extraction will be done in two phases (setup first, validation second) to minimize risk.

## Out of Scope

- Performance optimization of the orchestrator
- Adding new functionality to the orchestrator
- Changing the public API
- Modifying dbt models or SQL logic
- Updating CLI commands or Studio frontend
- Creating new tests beyond basic smoke tests for extracted modules
