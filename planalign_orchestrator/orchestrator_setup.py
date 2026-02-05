#!/usr/bin/env python3
"""
Orchestrator Setup Functions

Factory functions for initializing orchestrator subsystems (memory management,
parallelization, hazard cache, performance monitoring). Extracted from
PipelineOrchestrator to reduce complexity per Principle II (Modular Architecture).

These functions are stateless factories that return initialized subsystem objects
or None on failure. All verbose output messages are preserved exactly from the
original implementation for user consistency.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .adaptive_memory_manager import AdaptiveMemoryManager
    from .config import SimulationConfig
    from .dbt_runner import DbtRunner
    from .utils import DatabaseConnectionManager

# Import availability flags for optional components
try:
    from .parallel_execution_engine import ParallelExecutionEngine
    from .model_dependency_analyzer import ModelDependencyAnalyzer
    from .resource_manager import ResourceManager
    from .logger import ProductionLogger
    MODEL_PARALLELIZATION_AVAILABLE = True
    RESOURCE_MANAGEMENT_AVAILABLE = True
except ImportError:
    MODEL_PARALLELIZATION_AVAILABLE = False
    RESOURCE_MANAGEMENT_AVAILABLE = False
    ParallelExecutionEngine = None
    ModelDependencyAnalyzer = None
    ResourceManager = None
    ProductionLogger = None


def setup_memory_manager(
    config: "SimulationConfig",
    reports_dir: Path,
    verbose: bool = False
) -> Optional["AdaptiveMemoryManager"]:
    """
    Setup adaptive memory management system.

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
    try:
        from .adaptive_memory_manager import (
            AdaptiveMemoryManager,
            create_adaptive_memory_manager,
            OptimizationLevel,
            AdaptiveConfig,
            MemoryThresholds,
            BatchSizeConfig,
        )

        # Extract optimization config from simulation config
        optimization_config = getattr(config, 'optimization', None)

        if optimization_config and hasattr(optimization_config, 'adaptive_memory'):
            adaptive_config = optimization_config.adaptive_memory

            # Build adaptive config from simulation config
            amm_config = AdaptiveConfig(
                enabled=adaptive_config.enabled,
                monitoring_interval_seconds=adaptive_config.monitoring_interval_seconds,
                history_size=adaptive_config.history_size,
                thresholds=MemoryThresholds(
                    moderate_mb=adaptive_config.thresholds.moderate_mb,
                    high_mb=adaptive_config.thresholds.high_mb,
                    critical_mb=adaptive_config.thresholds.critical_mb,
                    gc_trigger_mb=adaptive_config.thresholds.gc_trigger_mb,
                    fallback_trigger_mb=adaptive_config.thresholds.fallback_trigger_mb
                ),
                batch_sizes=BatchSizeConfig(
                    low=adaptive_config.batch_sizes.low,
                    medium=adaptive_config.batch_sizes.medium,
                    high=adaptive_config.batch_sizes.high,
                    fallback=adaptive_config.batch_sizes.fallback
                ),
                auto_gc_enabled=adaptive_config.auto_gc_enabled,
                fallback_enabled=adaptive_config.fallback_enabled,
                profiling_enabled=adaptive_config.profiling_enabled,
                recommendation_window_minutes=adaptive_config.recommendation_window_minutes,
                min_samples_for_recommendation=adaptive_config.min_samples_for_recommendation,
                leak_detection_enabled=adaptive_config.leak_detection_enabled,
                leak_threshold_mb=adaptive_config.leak_threshold_mb,
                leak_window_minutes=adaptive_config.leak_window_minutes
            )

            # Import logger
            from .logger import ProductionLogger
            logger = ProductionLogger("AdaptiveMemoryManager")

            memory_manager = AdaptiveMemoryManager(
                amm_config,
                logger,
                reports_dir=reports_dir / "memory"
            )

            if verbose:
                print("🧠 Adaptive Memory Manager initialized")
                print(f"   Thresholds: {adaptive_config.thresholds.moderate_mb}MB / {adaptive_config.thresholds.high_mb}MB / {adaptive_config.thresholds.critical_mb}MB")
                print(f"   Batch sizes: {adaptive_config.batch_sizes.fallback}-{adaptive_config.batch_sizes.high}")
                print(f"   Auto-GC: {adaptive_config.auto_gc_enabled}, Fallback: {adaptive_config.fallback_enabled}")

            return memory_manager
        else:
            # Create default adaptive memory manager for backward compatibility
            memory_manager = create_adaptive_memory_manager(
                optimization_level=OptimizationLevel.MEDIUM,
                memory_limit_gb=4.0  # Default for work laptops
            )
            if verbose:
                print("🧠 Adaptive Memory Manager initialized (default configuration)")

            return memory_manager

    except Exception as e:
        # Fallback to None - orchestrator will work without adaptive memory management
        if verbose:
            print(f"⚠️ Failed to initialize Adaptive Memory Manager: {e}")
            print("   Continuing without adaptive memory management")
        return None


def setup_parallelization(
    config: "SimulationConfig",
    dbt_runner: "DbtRunner",
    verbose: bool = False
) -> tuple[Optional[Any], Optional[Any], Optional[Any], Optional[Any], bool]:
    """
    Setup model-level parallelization system with advanced resource management.

    Args:
        config: Simulation configuration with parallelization settings
        dbt_runner: DbtRunner for accessing project directory
        verbose: Enable verbose output

    Returns:
        Tuple of (parallel_execution_engine, parallelization_config, resource_manager,
                  dependency_analyzer, model_parallelization_enabled)
        Returns (None, None, None, None, False) if initialization fails or disabled

    Behavior:
        - Checks for dbt manifest before enabling
        - On success: Returns configured components, prints status if verbose
        - On failure/disabled: Returns (None, None, None, None, False), prints warning if verbose
        - Never raises exceptions
    """
    try:
        # Check if model parallelization is enabled in config
        threading_config = getattr(config, 'orchestrator', None)
        if threading_config and hasattr(threading_config, 'threading'):
            parallelization_config = threading_config.threading.parallelization
            resource_mgmt_config = threading_config.threading.resource_management
        else:
            # Fallback: check if enabled via optimization config
            optimization_config = getattr(config, 'optimization', None)
            parallelization_config = None
            resource_mgmt_config = None
            if optimization_config and hasattr(optimization_config, 'model_parallelization'):
                parallelization_config = optimization_config.model_parallelization

        if (parallelization_config and
            parallelization_config.enabled and
            MODEL_PARALLELIZATION_AVAILABLE):

            # Initialize dependency analyzer
            from .logger import ProductionLogger
            logger = ProductionLogger("ModelParallelization")

            manifest_path = Path("dbt/target/manifest.json")
            if not manifest_path.exists():
                if verbose:
                    print("⚠️ dbt manifest not found - run 'dbt compile' first")
                    print("   Model parallelization will not be available")
                return None, None, None, None, False

            # Initialize dependency analyzer
            dependency_analyzer = ModelDependencyAnalyzer(str(manifest_path))

            # Initialize resource manager if available
            if resource_mgmt_config and RESOURCE_MANAGEMENT_AVAILABLE:
                resource_manager = _create_resource_manager(resource_mgmt_config, verbose)
            else:
                resource_manager = None

            # Initialize parallel execution engine
            parallel_execution_engine = ParallelExecutionEngine(
                dbt_runner=dbt_runner,
                dependency_analyzer=dependency_analyzer,
                max_workers=parallelization_config.max_parallel_models,
                logger=logger,
                resource_manager=resource_manager
            )

            if verbose:
                print("⚡ Model-level parallelization enabled")
                print(f"   Max parallel models: {parallelization_config.max_parallel_models}")
                print(f"   Dependency-aware scheduling: {parallelization_config.dependency_aware_scheduling}")
                if resource_manager:
                    print("   Advanced resource management: enabled")

            return parallel_execution_engine, parallelization_config, resource_manager, dependency_analyzer, True
        else:
            return None, None, None, None, False

    except Exception as e:
        # Fallback to sequential execution
        if verbose:
            print(f"⚠️ Failed to initialize model parallelization: {e}")
            print("   Falling back to sequential execution")
        return None, None, None, None, False


def _create_resource_manager(config: Any, verbose: bool = False) -> Optional[Any]:
    """
    Create resource manager with configuration.

    Args:
        config: Resource management configuration
        verbose: Enable verbose output

    Returns:
        Configured ResourceManager, or None if initialization fails
    """
    try:
        if not RESOURCE_MANAGEMENT_AVAILABLE:
            return None

        from .logger import ProductionLogger
        logger = ProductionLogger("ResourceManager")

        # Create resource manager with config
        resource_manager = ResourceManager(
            memory_limit_mb=config.memory_limit_mb,
            cpu_limit_percent=config.cpu_limit_percent,
            enable_gc_on_pressure=config.enable_gc_on_pressure,
            enable_connection_pooling=config.enable_connection_pooling,
            connection_pool_size=config.connection_pool_size,
            enable_memory_profiling=config.enable_memory_profiling,
            logger=logger
        )

        if verbose:
            print(f"📊 Resource Manager initialized:")
            print(f"   Memory limit: {config.memory_limit_mb}MB")
            print(f"   CPU limit: {config.cpu_limit_percent}%")
            print(f"   Auto GC on pressure: {config.enable_gc_on_pressure}")
            print(f"   Connection pooling: {config.enable_connection_pooling} (pool size: {config.connection_pool_size})")

        return resource_manager

    except Exception as e:
        if verbose:
            print(f"⚠️ Failed to create resource manager: {e}")
        return None


def setup_hazard_cache(
    db_manager: "DatabaseConnectionManager",
    dbt_runner: "DbtRunner",
    verbose: bool = False
) -> Optional[Any]:
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
    try:
        from .hazard_cache_manager import HazardCacheManager

        # Extract dbt project path from runner
        dbt_project_path = getattr(dbt_runner, 'project_dir', Path('dbt'))

        hazard_cache_manager = HazardCacheManager(
            db_manager=db_manager,
            dbt_runner=dbt_runner,
            dbt_project_path=dbt_project_path,
            verbose=verbose
        )

        if verbose:
            print("🗄️ E068D Hazard Cache Manager initialized")
            print(f"   SHA256 parameter fingerprinting enabled")
            print(f"   Automatic cache invalidation on parameter changes")

        return hazard_cache_manager

    except ImportError:
        if verbose:
            print("ℹ️ E068D Hazard Cache Manager not available (module not found)")
        return None
    except Exception as e:
        if verbose:
            print(f"⚠️ Failed to initialize Hazard Cache Manager: {e}")
        return None


def setup_performance_monitor(
    db_manager: "DatabaseConnectionManager",
    reports_dir: Path,
    verbose: bool = False
) -> Optional[Any]:
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
    try:
        from .duckdb_performance_monitor import DuckDBPerformanceMonitor

        duckdb_performance_monitor = DuckDBPerformanceMonitor(
            db_manager=db_manager,
            reports_dir=reports_dir / "duckdb_performance",
            verbose=verbose
        )

        if verbose:
            print("📊 E068E DuckDB Performance Monitor initialized")
            print(f"   Query profiling enabled")
            print(f"   Reports directory: {reports_dir / 'duckdb_performance'}")

        return duckdb_performance_monitor

    except ImportError:
        if verbose:
            print("ℹ️ E068E DuckDB Performance Monitor not available (module not found)")
        return None
    except Exception as e:
        if verbose:
            print(f"⚠️ Failed to initialize DuckDB Performance Monitor: {e}")
        return None
