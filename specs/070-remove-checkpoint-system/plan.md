# Implementation Plan: Remove Checkpoint/Resume System

**Branch**: `070-remove-checkpoint-system` | **Date**: 2026-03-15 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/070-remove-checkpoint-system/spec.md`

## Summary

Remove the unused checkpoint/resume system (~1,500 lines across 9 source files) from the simulation pipeline. The system includes `CheckpointManager`, `RecoveryOrchestrator`, checkpoint CLI commands, and resume logic integrated into the pipeline orchestrator. `StateManager` is retained in reduced form for essential database cleanup operations. No new functionality is added.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: Typer (CLI), Rich (display), Pydantic v2 (config)
**Storage**: DuckDB (unchanged — no schema modifications)
**Testing**: pytest with `@patch()` mocks for checkpoint tests
**Target Platform**: Linux server / work laptop
**Project Type**: CLI + orchestration engine
**Performance Goals**: N/A (code removal only)
**Constraints**: Must preserve `StateManager` database cleanup methods; must not break existing simulations
**Scale/Scope**: ~1,500 lines removed across 9 source files + 10 test methods across 5 test files

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Event Sourcing & Immutability | PASS | No event store changes |
| II. Modular Architecture | PASS | Reduces module count (removes 3 files); StateManager stays under 300 lines |
| III. Test-First Development | PASS | Checkpoint tests removed alongside code; non-checkpoint tests preserved |
| IV. Enterprise Transparency | PASS | No audit trail changes; error catalog updated |
| V. Type-Safe Configuration | PASS | No config schema changes |
| VI. Performance & Scalability | PASS | Removes overhead (checkpoint file I/O, gzip compression, hash computation) |

**Post-design re-check**: All gates still PASS. This is a pure simplification — no new complexity introduced.

## Project Structure

### Documentation (this feature)

```text
specs/070-remove-checkpoint-system/
├── spec.md              # Feature specification
├── plan.md              # This file
├── research.md          # Dependency map and impact analysis
├── data-model.md        # Entity removal/modification tracking
├── quickstart.md        # Implementation order and verification
├── checklists/
│   └── requirements.md  # Spec quality checklist
└── tasks.md             # (created by /speckit.tasks)
```

### Source Code Changes

```text
# FILES TO DELETE (3 files, ~1,090 lines)
planalign_orchestrator/checkpoint_manager.py     # 563 lines — full delete
planalign_orchestrator/recovery_orchestrator.py  # 328 lines — full delete
planalign_cli/commands/checkpoint.py             # 199 lines — full delete

# FILES TO MODIFY (6 files, ~500 lines removed)
planalign_orchestrator/pipeline_orchestrator.py  # Remove checkpoint integration
planalign_orchestrator/pipeline/state_manager.py # Remove checkpoint methods, keep DB cleanup
planalign_cli/integration/orchestrator_wrapper.py # Remove checkpoint properties
planalign_cli/commands/simulate.py               # Remove --resume/--force-restart
planalign_cli/main.py                            # Remove checkpoint command registration
planalign_orchestrator/cli.py                    # Remove checkpoint logic (legacy CLI)

# TEST FILES TO MODIFY (5 files, ~83 lines removed)
tests/test_orchestrator_wrapper.py               # Remove 3 checkpoint test methods
tests/test_simulate_command.py                   # Remove TestResolveStartYear class (3 methods)
tests/unit/cli/test_cli.py                       # Remove test_cli_checkpoint_listing
tests/test_error_catalog.py                      # Remove checkpoint error pattern test
tests/unit/test_year_dependency_validator.py      # Remove 2 checkpoint dependency tests

# DOCUMENTATION TO UPDATE
CLAUDE.md                                        # Remove checkpoint references
```

**Structure Decision**: No new directories or files created. This is strictly a deletion and trimming operation on existing files.

## Complexity Tracking

> No constitution violations — no entries needed.

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| (none) | — | — |
