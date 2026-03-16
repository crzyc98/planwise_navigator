# Quickstart: Remove Checkpoint/Resume System

**Branch**: `070-remove-checkpoint-system`

## What This Feature Does

Removes the unused checkpoint/resume system (~1,500 lines) from the simulation pipeline. Scenarios are fast enough to re-run from scratch, so the resume capability provides no value.

## Implementation Order

### Phase 1: Delete standalone files
1. Delete `planalign_orchestrator/checkpoint_manager.py`
2. Delete `planalign_orchestrator/recovery_orchestrator.py`
3. Delete `planalign_cli/commands/checkpoint.py`

### Phase 2: Trim StateManager
4. Remove `write_checkpoint()`, `find_last_checkpoint()`, `state_hash()`, `calculate_config_hash()` from `state_manager.py`
5. Remove `checkpoints_dir` constructor parameter

### Phase 3: Simplify PipelineOrchestrator
6. Remove checkpoint imports, constructor params, checkpoint methods
7. Remove `resume_from_checkpoint` parameter from `execute_multi_year_simulation()`
8. Remove `_save_year_checkpoint()`, `_write_legacy_checkpoint()`, `_calculate_config_hash()`

### Phase 4: Clean CLI
9. Remove checkpoint imports and command registration from `main.py`
10. Remove `--resume`/`--force-restart` from `simulate.py`
11. Remove `_resolve_start_year()` function
12. Clean up `cli.py` (legacy CLI)

### Phase 5: Clean OrchestratorWrapper
13. Remove checkpoint/recovery properties and methods from `orchestrator_wrapper.py`

### Phase 6: Update tests
14. Remove 10 checkpoint-specific test methods across 5 files
15. Run full test suite to verify

### Phase 7: Update documentation
16. Update CLAUDE.md references to checkpoints

## Verification

```bash
# Run tests
pytest -m fast
pytest --tb=short

# Verify CLI
planalign --help          # No "checkpoints" command
planalign simulate --help # No --resume/--force-restart

# Verify simulation still works
planalign simulate 2025 --dry-run
```

## Key Constraint

**DO NOT remove** `StateManager.maybe_clear_year_data()` or `StateManager.maybe_full_reset()` — these are essential for multi-year simulation correctness.
