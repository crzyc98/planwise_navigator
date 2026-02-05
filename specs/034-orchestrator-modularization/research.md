# Research: Orchestrator Modularization Phase 2

**Feature**: 034-orchestrator-modularization
**Date**: 2026-02-05

## Overview

This research documents the analysis performed to support extracting setup and validation code from `pipeline_orchestrator.py`.

## Research Questions

### RQ-1: What are the exact dependencies of each setup method?

**Decision**: Setup methods can be extracted as standalone functions with explicit parameter injection.

**Findings**:

| Method | Input Dependencies | Output | Side Effects |
|--------|-------------------|--------|--------------|
| `_setup_adaptive_memory_manager()` | `self.config`, `self.reports_dir`, `self.verbose` | `AdaptiveMemoryManager` or `None` | Prints status messages |
| `_setup_model_parallelization()` | `self.config`, `self.dbt_runner`, `self.verbose` | Sets `self.model_parallelization_enabled`, `self.parallel_execution_engine`, `self.parallelization_config`, `self.resource_manager` | Prints status messages |
| `_setup_hazard_cache_manager()` | `self.db_manager`, `self.dbt_runner`, `self.verbose` | `HazardCacheManager` or `None` | Prints status messages |
| `_setup_performance_monitoring()` | `self.db_manager`, `self.reports_dir`, `self.verbose` | `DuckDBPerformanceMonitor` or `None` | Prints status messages |

**Rationale**: All setup methods follow the same pattern: take config/managers as input, return initialized subsystem or None on failure, print verbose messages. This is ideal for extraction to standalone factory functions.

**Alternatives considered**:
- Keep as private methods: Rejected because it doesn't reduce orchestrator complexity
- Extract to a SetupManager class: Rejected as over-engineering; stateless functions are simpler

### RQ-2: What are the exact dependencies of validation logic?

**Decision**: Validation logic extracts cleanly into a `StageValidator` class.

**Findings**:

The `_run_stage_validation()` method depends on:
- `self.db_manager.execute_with_retry()` - for database queries
- `self.config.simulation.start_year` - for year comparison logic
- `self.state_manager.verify_year_population()` - for STATE_ACCUMULATION stage
- `self.verbose` - for conditional output
- `PipelineStageError` - for raising validation failures

**Rationale**: These dependencies can all be injected via constructor, making the class independently testable.

**Alternatives considered**:
- Extract as standalone functions: Rejected because validation shares state (db_manager, config) and benefits from method grouping
- Keep inline: Rejected because 145 lines of validation obscures the main workflow

### RQ-3: Are there any circular dependency risks?

**Decision**: No circular dependency risks identified.

**Findings**:

Dependency flow analysis:
```
orchestrator_setup.py
  ← imports: AdaptiveMemoryManager, ParallelExecutionEngine, HazardCacheManager, etc.
  ← no imports from: pipeline_orchestrator.py

pipeline/stage_validator.py
  ← imports: DatabaseConnectionManager, SimulationConfig, StateManager, StageDefinition
  ← no imports from: pipeline_orchestrator.py

pipeline_orchestrator.py
  ← imports: orchestrator_setup (new)
  ← imports: pipeline/stage_validator (new)
```

**Rationale**: The extracted modules only import from lower-level modules (config, utils, managers). They do not import from `pipeline_orchestrator.py`, so no cycles are possible.

### RQ-4: What is the E072 extraction pattern?

**Decision**: Follow the established E072 pattern for module extraction.

**Findings**:

E072 (Oct 2025) extracted the following from `pipeline_orchestrator.py`:
- `pipeline/workflow.py` - WorkflowBuilder, stage definitions
- `pipeline/state_manager.py` - StateManager for checkpoints
- `pipeline/year_executor.py` - YearExecutor for stage execution
- `pipeline/event_generation_executor.py` - Hybrid event generation
- `pipeline/hooks.py` - HookManager for callbacks
- `pipeline/data_cleanup.py` - DataCleanupManager

Pattern observed:
1. Create new module with clear responsibility
2. Copy code with minimal modifications
3. Update imports in `__init__.py`
4. Update orchestrator to use new module
5. Run tests after each step

**Rationale**: Following the established pattern reduces risk and maintains consistency.

## Technical Constraints

### TC-1: Public API Preservation

The following MUST NOT change:
- Constructor signature: `PipelineOrchestrator(config, db_manager, dbt_runner, registry_manager, validator, *, reports_dir, checkpoints_dir, verbose, enhanced_checkpoints)`
- Public properties: `.config`, `.db_manager`, `.hook_manager`, `.state_manager`, `.memory_manager`
- Public method: `execute_multi_year_simulation()` with same return type

### TC-2: Verbose Output Preservation

All setup and validation methods print status messages when `verbose=True`. These messages MUST remain identical after extraction to avoid confusion for users who rely on verbose output for debugging.

### TC-3: Error Handling Preservation

Setup methods return `None` on failure and print warnings. Validation raises `PipelineStageError` on critical failures. This behavior MUST be preserved exactly.

## Recommendations

1. **Extract setup first** (Phase 1) - Lower risk because setup only runs at initialization
2. **Extract validation second** (Phase 2) - Higher touchpoint because called during workflow execution
3. **Run tests incrementally** - After each function extraction, run fast tests
4. **Preserve verbose messages** - Copy print statements exactly to maintain user expectations
