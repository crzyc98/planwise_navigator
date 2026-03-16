# Research: Remove Checkpoint/Resume System

**Date**: 2026-03-15
**Branch**: `070-remove-checkpoint-system`

## R1: Checkpoint System Dependency Map

**Decision**: The checkpoint system is moderately coupled but cleanly removable. All integration points are in well-defined locations.

**Rationale**: Codebase audit reveals checkpoint code touches 9 source files and 5 test files, but all references are import-based with no runtime discovery or dynamic loading. Removal is a straightforward delete-and-trim operation.

**Alternatives considered**:
- Feature-flag the checkpoint system (rejected: adds complexity rather than removing it)
- Keep checkpoint infrastructure but disable by default (rejected: dead code is still maintenance burden)

### Files to DELETE entirely (2 files, ~891 lines)

| File | Lines | Purpose |
|------|-------|---------|
| `planalign_orchestrator/checkpoint_manager.py` | 563 | Compressed checkpoint save/load with integrity validation |
| `planalign_orchestrator/recovery_orchestrator.py` | 328 | Resume validation, config drift detection |

### Files to DELETE CLI command (1 file, ~199 lines)

| File | Lines | Purpose |
|------|-------|---------|
| `planalign_cli/commands/checkpoint.py` | 199 | list/status/cleanup/validate CLI commands |

### Files to MODIFY (6 files, ~500 lines removed)

| File | Remove | Preserve |
|------|--------|----------|
| `pipeline_orchestrator.py` | Checkpoint imports, constructor params, `_save_year_checkpoint()`, `_write_legacy_checkpoint()`, `_calculate_config_hash()`, resume logic | All workflow execution, monitoring, stage handling |
| `state_manager.py` | `write_checkpoint()`, `find_last_checkpoint()`, `state_hash()`, `calculate_config_hash()`, `checkpoints_dir` param | `maybe_clear_year_data()`, `maybe_full_reset()`, `clear_year_fact_rows()`, `verify_year_population()` |
| `orchestrator_wrapper.py` | `checkpoint_manager`/`recovery_orchestrator` properties, `get_checkpoint_info()`, checkpoint section in `get_system_status()` | Health checks, orchestrator creation, batch runner |
| `simulate.py` | `--resume`/`--force-restart` flags, `_resolve_start_year()`, resume parameter passing | Progress tracking, summary display, core simulation flow |
| `main.py` | Checkpoint imports, `checkpoints` command registration | All other commands |
| `cli.py` (legacy) | Checkpoint imports, resume logic in `cmd_run()`, `cmd_checkpoint()`, checkpoint subparser | Core run/validate/batch commands |

## R2: StateManager Preservation Strategy

**Decision**: Retain `StateManager` with checkpoint methods removed. Do NOT rename or relocate the class.

**Rationale**: `StateManager` serves dual purposes: (1) database cleanup between years (essential) and (2) checkpoint persistence (being removed). After removal, the class still has 4 meaningful methods and its name remains accurate — it manages simulation state (clearing, resetting, verifying population).

**Alternatives considered**:
- Rename to `DatabaseCleanupManager` (rejected: unnecessary churn, current name is still accurate)
- Inline methods into PipelineOrchestrator (rejected: violates single-responsibility, StateManager is already a focused module)

### Methods to PRESERVE

| Method | Lines | Purpose |
|--------|-------|---------|
| `maybe_clear_year_data()` | ~60 | Idempotency guard for year-specific data clearing |
| `maybe_full_reset()` | ~40 | Configuration-driven full database reset |
| `clear_year_fact_rows()` | ~50 | Clears fact table rows for a specific year |
| `verify_year_population()` | ~60 | Data quality validation after year execution |

### Methods to REMOVE

| Method | Lines | Purpose |
|--------|-------|---------|
| `write_checkpoint()` | ~30 | Legacy JSON checkpoint writing |
| `find_last_checkpoint()` | ~30 | Legacy checkpoint discovery |
| `state_hash()` | ~20 | Hash for legacy checkpoint verification |
| `calculate_config_hash()` | ~35 | Config drift detection hash |

## R3: Test Impact Analysis

**Decision**: Surgical removal of 10 test methods across 5 files. No entire test files deleted (all are mixed).

**Rationale**: No dedicated checkpoint test files exist. All checkpoint tests are shallow mocks using `@patch()` decorators. No checkpoint-specific fixtures exist in `tests/fixtures/`.

### Tests to REMOVE (10 methods, ~83 lines)

| File | Tests | Lines |
|------|-------|-------|
| `test_orchestrator_wrapper.py` | 3 methods (lazy-load tests) | ~22 |
| `test_simulate_command.py` | 3 methods (`TestResolveStartYear` class) | ~21 |
| `test_cli.py` | 1 method (`test_cli_checkpoint_listing`) | ~10 |
| `test_error_catalog.py` | 1 method (checkpoint error pattern) | ~8 |
| `test_year_dependency_validator.py` | 2 methods (checkpoint dependency validation) | ~22 |

### Tests to KEEP (different concept)

| File | Why |
|------|-----|
| `test_duckdb_monitor.py` | Tests `PerformanceCheckpoint` (monitoring), NOT recovery checkpoints |
| `test_pipeline.py` | No checkpoint references |
| `test_self_healing.py` | No checkpoint references |

### Already-skipped legacy tests (no action needed)

- `test_multi_year_coordination.py` — marked `pytest.mark.skip`
- `test_orchestrator_dbt_end_to_end.py` — marked `pytest.mark.skip`

## R4: Error Catalog Cleanup

**Decision**: Remove checkpoint-specific error patterns from `ErrorCatalog` if they exist.

**Rationale**: Error patterns like "Checkpoint file is corrupted" are dead code after checkpoint removal.

## R5: Documentation Updates

**Decision**: Update CLAUDE.md sections that reference checkpoints.

**Rationale**: CLAUDE.md Section 5 (Directory Structure) references `state_manager.py` as "Checkpoint and state management", Section 10 mentions `planalign checkpoints list/status`, and Section 3 (Quick Start) shows checkpoint CLI commands. These must be updated to reflect the simplified system.
