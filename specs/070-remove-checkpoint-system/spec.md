# Feature Specification: Remove Checkpoint/Resume System

**Feature Branch**: `070-remove-checkpoint-system`
**Created**: 2026-03-15
**Status**: Draft
**Input**: GitHub Issue #227 — Remove unused checkpoint/resume system to reduce pipeline complexity

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Simplified Simulation Execution (Priority: P1)

As a simulation operator, I want to run simulations without checkpoint overhead so that the pipeline is faster and the codebase is easier to understand and maintain.

**Why this priority**: The checkpoint system adds ~1,500 lines of code across 5 files that are never used in practice. Removing it directly reduces maintenance burden and cognitive load for every developer touching the pipeline.

**Independent Test**: Run a multi-year simulation (`planalign simulate 2025-2027`) and verify it completes successfully without any checkpoint-related code executing.

**Acceptance Scenarios**:

1. **Given** a clean simulation environment, **When** a user runs `planalign simulate 2025-2027`, **Then** the simulation completes successfully with no checkpoint files created and no checkpoint-related log messages.
2. **Given** a simulation fails mid-run on Year 2, **When** the user re-runs `planalign simulate 2025-2027`, **Then** the simulation starts fresh from Year 1 (the expected behavior today).

---

### User Story 2 - Cleaned Up CLI Interface (Priority: P2)

As a CLI user, I want the `planalign` command to only show relevant commands so that I'm not confused by checkpoint management options I never use.

**Why this priority**: Removing dead CLI surface area improves discoverability of useful commands and eliminates user confusion.

**Independent Test**: Run `planalign --help` and verify that checkpoint-related commands and flags are absent.

**Acceptance Scenarios**:

1. **Given** the updated CLI, **When** a user runs `planalign --help`, **Then** no `checkpoints` subcommand group appears.
2. **Given** the updated CLI, **When** a user runs `planalign simulate --help`, **Then** no `--resume` or `--force-restart` flags appear.
3. **Given** a user tries `planalign checkpoints list`, **When** the command is executed, **Then** the CLI returns an appropriate "unknown command" error.

---

### User Story 3 - Simplified Pipeline Orchestrator (Priority: P3)

As a developer maintaining the pipeline, I want the orchestrator to have a straightforward execution flow without checkpoint save/load branching so that I can reason about the pipeline more easily.

**Why this priority**: The pipeline orchestrator currently has conditional logic for checkpoint creation, resume detection, and fallback between enhanced and legacy checkpoint formats. Removing this simplifies the execution path.

**Independent Test**: Review the pipeline orchestrator code and verify there are no references to checkpoint saving, loading, or resume logic. Run the full test suite to confirm nothing breaks.

**Acceptance Scenarios**:

1. **Given** the refactored pipeline orchestrator, **When** a developer reads the year execution loop, **Then** there is no checkpoint save/load logic — just sequential stage execution.
2. **Given** the refactored codebase, **When** the full test suite runs, **Then** all non-checkpoint tests pass without modification.

---

### Edge Cases

- What happens to the `StateManager` database cleanup functions (`maybe_clear_year_data`, `maybe_full_reset`)? These are still needed for multi-year simulation correctness and must be preserved.
- What happens if users have existing `.planalign_checkpoints/` directories from prior runs? These become inert artifacts — no action needed, they can be manually deleted.
- What happens to the `OrchestratorWrapper` properties that lazy-load checkpoint/recovery managers? These must be removed along with their CLI consumers.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The system MUST remove the `CheckpointManager` class and its compressed checkpoint file operations (~563 lines).
- **FR-002**: The system MUST remove the `RecoveryOrchestrator` class and its resume/validation logic (~328 lines).
- **FR-003**: The system MUST remove the checkpoint CLI commands (`list`, `status`, `cleanup`, `validate`) from the CLI interface.
- **FR-004**: The system MUST remove the `--resume` and `--force-restart` flags from the `simulate` command.
- **FR-005**: The system MUST preserve `StateManager` database cleanup functionality (`maybe_clear_year_data()`, `maybe_full_reset()`), as these handle necessary data management between simulation years.
- **FR-006**: The system MUST remove checkpoint save/load logic from the pipeline orchestrator, including year checkpoint methods and enhanced checkpoint initialization.
- **FR-007**: The system MUST remove checkpoint/recovery properties from `OrchestratorWrapper`.
- **FR-008**: The system MUST update or remove all tests that specifically test checkpoint/recovery behavior while preserving tests for database state management.
- **FR-009**: The system MUST remove legacy checkpoint writing from `StateManager` (`write_checkpoint()`, `find_last_checkpoint()`) while preserving database state operations.

### Key Entities

- **StateManager**: Partially retained — database cleanup methods preserved, checkpoint methods removed.
- **CheckpointManager**: Fully removed.
- **RecoveryOrchestrator**: Fully removed.
- **PipelineOrchestrator**: Simplified — checkpoint integration points removed from initialization and year execution loop.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: At least 1,000 lines of checkpoint-specific code removed from the codebase (currently ~1,500 lines across checkpoint_manager.py, recovery_orchestrator.py, checkpoint CLI, and related integration code).
- **SC-002**: All existing non-checkpoint tests continue to pass without modification.
- **SC-003**: Multi-year simulations complete successfully after removal.
- **SC-004**: The `simulate` command no longer accepts `--resume` or `--force-restart` flags.
- **SC-005**: The `checkpoints` command group no longer exists in the CLI.
- **SC-006**: No checkpoint files are created during simulation runs.

## Assumptions

- The `StateManager` class will be retained in a reduced form (database cleanup only) rather than being fully removed, since `maybe_clear_year_data()` is essential for multi-year simulation correctness.
- Existing `.planalign_checkpoints/` directories on user machines are harmless and do not need automated cleanup.
- The legacy CLI (`planalign_orchestrator/cli.py`) checkpoint integration will also be cleaned up as part of this work.
- No external systems or APIs depend on checkpoint file formats or the recovery orchestrator interface.

## Scope Boundaries

**In scope**:
- Removing checkpoint_manager.py, recovery_orchestrator.py
- Removing checkpoint CLI commands
- Removing --resume/--force-restart flags
- Simplifying pipeline_orchestrator.py
- Cleaning up OrchestratorWrapper
- Updating/removing checkpoint-specific tests
- Trimming StateManager to database-cleanup-only

**Out of scope**:
- Removing StateManager entirely (database cleanup is still needed)
- Adding any new features or replacement functionality
- Modifying simulation logic or dbt models
- Cleaning up user-side checkpoint directories
