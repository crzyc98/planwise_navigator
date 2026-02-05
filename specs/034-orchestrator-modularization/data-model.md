# Data Model: Orchestrator Modularization Phase 2

**Feature**: 034-orchestrator-modularization
**Date**: 2026-02-05

## Overview

This is a code refactoring feature with no new data entities. The data model documents the **code structure** being extracted rather than database entities.

## Extracted Modules

### Module 1: orchestrator_setup.py

**Purpose**: Factory functions for subsystem initialization

**Functions**:

| Function | Parameters | Return Type | Responsibility |
|----------|------------|-------------|----------------|
| `setup_memory_manager` | config, reports_dir, verbose | `Optional[AdaptiveMemoryManager]` | Initialize adaptive memory management |
| `setup_parallelization` | config, dbt_runner, verbose | `tuple[Optional[ParallelExecutionEngine], Optional[Any], Optional[ResourceManager]]` | Initialize model parallelization |
| `setup_hazard_cache` | db_manager, dbt_runner, verbose | `Optional[HazardCacheManager]` | Initialize hazard cache |
| `setup_performance_monitor` | db_manager, reports_dir, verbose | `Optional[DuckDBPerformanceMonitor]` | Initialize performance monitoring |

**Dependencies** (imports from):
- `planalign_orchestrator.adaptive_memory_manager`
- `planalign_orchestrator.parallel_execution_engine` (optional)
- `planalign_orchestrator.model_dependency_analyzer` (optional)
- `planalign_orchestrator.resource_manager` (optional)
- `planalign_orchestrator.hazard_cache_manager`
- `planalign_orchestrator.duckdb_performance_monitor`
- `planalign_orchestrator.logger`

### Module 2: pipeline/stage_validator.py

**Purpose**: Validation logic for pipeline stages

**Class: StageValidator**

| Attribute | Type | Description |
|-----------|------|-------------|
| `db_manager` | `DatabaseConnectionManager` | Database access for validation queries |
| `config` | `SimulationConfig` | Simulation configuration |
| `state_manager` | `StateManager` | State management (for verify_year_population) |
| `verbose` | `bool` | Enable verbose output |

| Method | Parameters | Return Type | Responsibility |
|--------|------------|-------------|----------------|
| `validate_stage` | stage, year, fail_on_error | `None` | Dispatch to stage-specific validation |
| `_validate_foundation` | year | `None` | Validate FOUNDATION stage outputs |
| `_validate_event_generation` | year | `None` | Validate EVENT_GENERATION stage outputs |
| `_validate_state_accumulation` | year | `None` | Validate STATE_ACCUMULATION stage outputs |
| `_safe_count` | conn, table, year | `int` | Safe row count query (handles missing tables) |

**Dependencies** (imports from):
- `planalign_orchestrator.utils.DatabaseConnectionManager`
- `planalign_orchestrator.config.SimulationConfig`
- `planalign_orchestrator.pipeline.state_manager.StateManager`
- `planalign_orchestrator.pipeline.workflow.WorkflowStage, StageDefinition`
- `planalign_orchestrator.pipeline.year_executor.PipelineStageError`

## State Transitions

N/A - This is a code refactoring with no runtime state changes.

## Validation Rules

### Setup Functions

1. Each setup function MUST return `None` on failure (not raise exceptions)
2. Each setup function MUST print a warning when verbose=True and initialization fails
3. Each setup function MUST preserve identical verbose output messages

### StageValidator

1. `validate_stage` MUST raise `PipelineStageError` for critical validation failures
2. `_safe_count` MUST return 0 for missing tables (not raise exceptions)
3. Validation output MUST match current `_run_stage_validation()` output exactly
