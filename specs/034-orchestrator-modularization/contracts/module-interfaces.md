# Module Interface Contracts

**Feature**: 034-orchestrator-modularization
**Date**: 2026-02-05

## Overview

This document defines the interface contracts for the extracted modules. Since this is a Python refactoring (not an API), contracts are defined as function/class signatures.

## orchestrator_setup.py

### setup_memory_manager

```python
def setup_memory_manager(
    config: SimulationConfig,
    reports_dir: Path,
    verbose: bool = False
) -> Optional[AdaptiveMemoryManager]:
    """
    Initialize adaptive memory management system.

    Args:
        config: Simulation configuration with optimization settings
        reports_dir: Directory for memory reports
        verbose: Enable verbose output

    Returns:
        Configured AdaptiveMemoryManager, or None if initialization fails

    Behavior:
        - On success: Returns configured manager, prints status if verbose
        - On failure: Returns None, prints warning if verbose
        - Never raises exceptions
    """
```

### setup_parallelization

```python
def setup_parallelization(
    config: SimulationConfig,
    dbt_runner: DbtRunner,
    verbose: bool = False
) -> tuple[Optional[ParallelExecutionEngine], Optional[Any], Optional[ResourceManager]]:
    """
    Initialize model-level parallelization system.

    Args:
        config: Simulation configuration with parallelization settings
        dbt_runner: DbtRunner for accessing project directory
        verbose: Enable verbose output

    Returns:
        Tuple of (parallel_execution_engine, parallelization_config, resource_manager)
        Returns (None, None, None) if initialization fails or disabled

    Behavior:
        - Checks for dbt manifest before enabling
        - On success: Returns configured components, prints status if verbose
        - On failure/disabled: Returns (None, None, None), prints warning if verbose
        - Never raises exceptions
    """
```

### setup_hazard_cache

```python
def setup_hazard_cache(
    db_manager: DatabaseConnectionManager,
    dbt_runner: DbtRunner,
    verbose: bool = False
) -> Optional[HazardCacheManager]:
    """
    Initialize hazard cache manager for automatic change detection.

    Args:
        db_manager: Database connection manager
        dbt_runner: DbtRunner for project path
        verbose: Enable verbose output

    Returns:
        Configured HazardCacheManager, or None if initialization fails

    Behavior:
        - On success: Returns configured manager, prints status if verbose
        - On failure: Returns None, prints warning if verbose
        - Never raises exceptions
    """
```

### setup_performance_monitor

```python
def setup_performance_monitor(
    db_manager: DatabaseConnectionManager,
    reports_dir: Path,
    verbose: bool = False
) -> Optional[DuckDBPerformanceMonitor]:
    """
    Initialize DuckDB performance monitoring system.

    Args:
        db_manager: Database connection manager
        reports_dir: Directory for performance reports
        verbose: Enable verbose output

    Returns:
        Configured DuckDBPerformanceMonitor, or None if initialization fails

    Behavior:
        - On success: Returns configured monitor, prints status if verbose
        - On failure: Returns None, prints warning if verbose
        - Never raises exceptions
    """
```

## pipeline/stage_validator.py

### StageValidator

```python
class StageValidator:
    """
    Validates pipeline stage completion with diagnostic output.

    Provides stage-specific validation for FOUNDATION, EVENT_GENERATION,
    and STATE_ACCUMULATION stages with detailed row count reporting.
    """

    def __init__(
        self,
        db_manager: DatabaseConnectionManager,
        config: SimulationConfig,
        state_manager: StateManager,
        verbose: bool = False
    ):
        """
        Initialize stage validator.

        Args:
            db_manager: Database connection manager for queries
            config: Simulation configuration (for start_year reference)
            state_manager: State manager (for verify_year_population)
            verbose: Enable verbose output
        """

    def validate_stage(
        self,
        stage: StageDefinition,
        year: int,
        fail_on_error: bool = False
    ) -> None:
        """
        Run validation checks for a completed workflow stage.

        Args:
            stage: Stage definition with stage.name indicating which validation
            year: Simulation year being validated
            fail_on_error: If True, raise PipelineStageError on validation failure

        Raises:
            PipelineStageError: On critical validation failures when fail_on_error=True

        Behavior:
            - FOUNDATION: Validates row counts in foundation models
            - EVENT_GENERATION: Validates hire events vs demand
            - STATE_ACCUMULATION: Delegates to state_manager.verify_year_population
            - Always prints diagnostic output
        """
```

## Contract Guarantees

1. **Setup functions never raise exceptions** - They return None on failure
2. **Verbose output is preserved** - Same messages as current implementation
3. **Return types are explicit** - Optional types clearly indicate failure modes
4. **StageValidator raises only on critical failures** - And only when fail_on_error=True
