#!/usr/bin/env python3
"""
Pipeline Orchestration Engine

Coordinates config, dbt execution, registries, validation, and reporting for
multi-year simulations with basic checkpoint/restart support.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from navigator_orchestrator.config import get_database_path
from pathlib import Path
from typing import Any, Dict, List, Optional
import time
import json

from .adaptive_memory_manager import AdaptiveMemoryManager, create_adaptive_memory_manager, OptimizationLevel
from .checkpoint_manager import CheckpointManager
from .config import SimulationConfig, to_dbt_vars, PolarsEventSettings
from .dbt_runner import DbtResult, DbtRunner
from .recovery_orchestrator import RecoveryOrchestrator
from .registries import RegistryManager
from .reports import MultiYearReporter, MultiYearSummary, YearAuditor
from .observability import ObservabilityManager
from .utils import DatabaseConnectionManager, ExecutionMutex, time_block
from .validation import DataValidator

# Import model parallelization components
try:
    from .parallel_execution_engine import ParallelExecutionEngine, ExecutionContext
    from .model_dependency_analyzer import ModelDependencyAnalyzer
    from .resource_manager import ResourceManager
    from .logger import ProductionLogger
    MODEL_PARALLELIZATION_AVAILABLE = True
    RESOURCE_MANAGEMENT_AVAILABLE = True
except ImportError:
    MODEL_PARALLELIZATION_AVAILABLE = False
    RESOURCE_MANAGEMENT_AVAILABLE = False


class PipelineStageError(RuntimeError):
    pass


class WorkflowStage(Enum):
    INITIALIZATION = "initialization"
    FOUNDATION = "foundation"
    EVENT_GENERATION = "event_generation"
    STATE_ACCUMULATION = "state_accumulation"
    VALIDATION = "validation"
    REPORTING = "reporting"
    CLEANUP = "cleanup"


@dataclass
class StageDefinition:
    name: WorkflowStage
    dependencies: List[WorkflowStage]
    models: List[str]
    validation_rules: List[str]
    parallel_safe: bool = False
    checkpoint_enabled: bool = True


@dataclass
class WorkflowCheckpoint:
    year: int
    stage: WorkflowStage
    timestamp: str
    state_hash: str


class PipelineOrchestrator:
    def __init__(
        self,
        config: SimulationConfig,
        db_manager: DatabaseConnectionManager,
        dbt_runner: DbtRunner,
        registry_manager: RegistryManager,
        validator: DataValidator,
        *,
        reports_dir: Path | str = Path("reports"),
        checkpoints_dir: Path | str = Path(".navigator_checkpoints"),
        verbose: bool = False,
        enhanced_checkpoints: bool = True,
    ):
        self.config = config
        self.db_manager = db_manager
        self.dbt_runner = dbt_runner
        self.registry_manager = registry_manager
        self.validator = validator
        self.verbose = verbose
        self._dbt_vars = to_dbt_vars(config)

        # E068C: Extract threading configuration from new structured config
        e068c_config = config.get_e068c_threading_config()
        self.dbt_threads = e068c_config.dbt_threads
        self.event_shards = e068c_config.event_shards
        self.max_parallel_years = e068c_config.max_parallel_years

        # E068G: Extract event generation configuration
        self.event_generation_mode = config.get_event_generation_mode()
        self.polars_settings = config.get_polars_settings()
        self.is_polars_enabled = config.is_polars_mode_enabled()

        # Log E068C threading configuration
        if self.verbose:
            print(f"🧵 E068C Threading Configuration:")
            print(f"   dbt_threads: {self.dbt_threads}")
            print(f"   event_shards: {self.event_shards}")
            print(f"   max_parallel_years: {self.max_parallel_years}")

            # E068G: Log event generation configuration
            print(f"🔄 E068G Event Generation Configuration:")
            print(f"   mode: {self.event_generation_mode}")
            if self.event_generation_mode == "polars":
                print(f"   polars_enabled: {self.is_polars_enabled}")
                print(f"   max_threads: {self.polars_settings.max_threads}")
                print(f"   batch_size: {self.polars_settings.batch_size:,}")
                print(f"   output_path: {self.polars_settings.output_path}")
                print(f"   fallback_on_error: {self.polars_settings.fallback_on_error}")

        # Enhanced compensation parameter visibility
        self._log_compensation_parameters()
        self._validate_compensation_parameters()

        # Debug (optional): show dbt vars derived from config
        if self.verbose:
            try:
                import json as _json

                print("\n🔎 Navigator Orchestrator dbt_vars (from config):")
                print(_json.dumps(self._dbt_vars, indent=2, sort_keys=True))
            except Exception:
                pass
        self.reports_dir = Path(reports_dir)
        self.checkpoints_dir = Path(checkpoints_dir)
        self.checkpoints_dir.mkdir(exist_ok=True)
        self._seeded = False

        # Initialize observability (structured logs + performance metrics + run summary)
        try:
            self.observability = ObservabilityManager(log_level="INFO")
            # Record configuration for audit trail
            try:
                self.observability.set_configuration(self.config.model_dump())
            except Exception:
                pass
            if self.verbose:
                print(f"🧭 Observability run_id: {self.observability.get_run_id()}")
        except Exception:
            # Proceed without observability if initialization fails
            self.observability = None

        # S063-08: Adaptive Memory Management
        self._setup_adaptive_memory_manager()

        # S067-02: Model-level parallelization setup
        self._setup_model_parallelization()

        # E068D: Initialize hazard cache manager for automatic change detection
        self._setup_hazard_cache_manager()

        # E068E: Initialize DuckDB performance monitoring system
        self._setup_performance_monitoring()

        # Enhanced checkpoint system
        self.enhanced_checkpoints = enhanced_checkpoints
        if enhanced_checkpoints:
            # Determine database path from db_manager
            db_path = getattr(db_manager, "db_path", str(get_database_path()))
            self.checkpoint_manager = CheckpointManager(
                checkpoint_dir=str(checkpoints_dir), db_path=str(db_path)
            )
            self.recovery_orchestrator = RecoveryOrchestrator(self.checkpoint_manager)
            self.config_hash = self._calculate_config_hash()
        else:
            self.checkpoint_manager = None
            self.recovery_orchestrator = None
            self.config_hash = None

    def _setup_adaptive_memory_manager(self) -> None:
        """Setup adaptive memory management system"""
        try:
            # Extract optimization config from simulation config
            optimization_config = getattr(self.config, 'optimization', None)

            if optimization_config and hasattr(optimization_config, 'adaptive_memory'):
                adaptive_config = optimization_config.adaptive_memory

                # Create adaptive memory manager with config
                from .adaptive_memory_manager import AdaptiveConfig, MemoryThresholds, BatchSizeConfig

                # Build adaptive config from simulation config
                config = AdaptiveConfig(
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

                self.memory_manager = AdaptiveMemoryManager(
                    config,
                    logger,
                    reports_dir=self.reports_dir / "memory"
                )

                if self.verbose:
                    print("🧠 Adaptive Memory Manager initialized")
                    print(f"   Thresholds: {adaptive_config.thresholds.moderate_mb}MB / {adaptive_config.thresholds.high_mb}MB / {adaptive_config.thresholds.critical_mb}MB")
                    print(f"   Batch sizes: {adaptive_config.batch_sizes.fallback}-{adaptive_config.batch_sizes.high}")
                    print(f"   Auto-GC: {adaptive_config.auto_gc_enabled}, Fallback: {adaptive_config.fallback_enabled}")
            else:
                # Create default adaptive memory manager for backward compatibility
                self.memory_manager = create_adaptive_memory_manager(
                    optimization_level=OptimizationLevel.MEDIUM,
                    memory_limit_gb=4.0  # Default for work laptops
                )
                if self.verbose:
                    print("🧠 Adaptive Memory Manager initialized (default configuration)")

        except Exception as e:
            # Fallback to None - orchestrator will work without adaptive memory management
            self.memory_manager = None
            if self.verbose:
                print(f"⚠️ Failed to initialize Adaptive Memory Manager: {e}")
                print("   Continuing without adaptive memory management")

    def _setup_model_parallelization(self) -> None:
        """Setup model-level parallelization system with advanced resource management"""
        try:
            # Check if model parallelization is enabled in config
            threading_config = getattr(self.config, 'orchestrator', None)
            if threading_config and hasattr(threading_config, 'threading'):
                parallelization_config = threading_config.threading.parallelization
                resource_mgmt_config = threading_config.threading.resource_management
            else:
                # Fallback: check if enabled via optimization config
                optimization_config = getattr(self.config, 'optimization', None)
                parallelization_config = None
                resource_mgmt_config = None
                if optimization_config and hasattr(optimization_config, 'model_parallelization'):
                    parallelization_config = optimization_config.model_parallelization

            if (parallelization_config and
                parallelization_config.enabled and
                MODEL_PARALLELIZATION_AVAILABLE):

                # Initialize dependency analyzer
                working_dir = getattr(self.dbt_runner, 'working_dir', Path('dbt'))
                dependency_analyzer = ModelDependencyAnalyzer(working_dir)

                # Setup advanced resource management (S067-03)
                resource_manager = None
                if (resource_mgmt_config and
                    resource_mgmt_config.enabled and
                    RESOURCE_MANAGEMENT_AVAILABLE):
                    resource_manager = self._create_resource_manager(resource_mgmt_config)

                # Setup logger for resource management
                logger = None
                try:
                    logger = ProductionLogger(log_level="INFO")
                except Exception:
                    pass  # Fallback to no logging

                # Initialize parallel execution engine with advanced resource management
                # DETERMINISM FIX: Always enable deterministic execution for reproducible results
                deterministic = parallelization_config.deterministic_execution
                if deterministic is None:
                    deterministic = True  # Default to deterministic for production safety

                parallel_engine = ParallelExecutionEngine(
                    dbt_runner=self.dbt_runner,
                    dependency_analyzer=dependency_analyzer,
                    max_workers=parallelization_config.max_workers,
                    resource_monitoring=parallelization_config.resource_monitoring,
                    deterministic_execution=deterministic,
                    memory_limit_mb=parallelization_config.memory_limit_mb,
                    verbose=self.verbose,
                    resource_manager=resource_manager,
                    logger=logger,
                    enable_adaptive_scaling=resource_mgmt_config.adaptive_scaling_enabled if resource_mgmt_config else False
                )

                if self.verbose and deterministic:
                    print("🔐 Deterministic execution enabled for reproducible results")

                # Store parallelization components
                self.model_parallelization_enabled = True
                self.parallel_execution_engine = parallel_engine
                self.dependency_analyzer = dependency_analyzer
                self.parallelization_config = parallelization_config
                self.resource_manager = resource_manager

                # Start resource monitoring if enabled
                if resource_manager:
                    resource_manager.start_monitoring()
                    if self.verbose:
                        print("📊 Advanced resource management enabled")
                        print(f"   Memory monitoring: {resource_mgmt_config.memory_monitoring.enabled}")
                        print(f"   CPU monitoring: {resource_mgmt_config.cpu_monitoring.enabled}")
                        print(f"   Adaptive scaling: {resource_mgmt_config.adaptive_scaling_enabled}")
                        print(f"   Thread range: {resource_mgmt_config.min_threads}-{resource_mgmt_config.max_threads}")

                if self.verbose:
                    print("🚀 Model-level parallelization engine initialized:")
                    print(f"   Max workers: {parallelization_config.max_workers}")
                    print(f"   Memory limit: {parallelization_config.memory_limit_mb}MB")
                    print(f"   Conditional parallelization: {parallelization_config.enable_conditional_parallelization}")
                    print(f"   Deterministic execution: {parallelization_config.deterministic_execution}")
                    print(f"   Resource management: {'enabled' if resource_manager else 'disabled'}")

                    # Display parallelization statistics
                    stats = parallel_engine.get_parallelization_statistics()
                    print(f"   Parallel-safe models: {stats['parallel_safe']}/{stats['total_models']}")
                    print(f"   Max theoretical speedup: {stats['max_theoretical_speedup']:.1f}x")

            else:
                # Model parallelization disabled or not available
                self.model_parallelization_enabled = False
                self.parallel_execution_engine = None
                self.dependency_analyzer = None
                self.parallelization_config = None
                self.resource_manager = None

                if self.verbose and parallelization_config and parallelization_config.enabled:
                    if not MODEL_PARALLELIZATION_AVAILABLE:
                        print("⚠️ Model parallelization requested but components not available")
                    else:
                        print("ℹ️ Model parallelization disabled in configuration")

        except Exception as e:
            # Fallback to disabled state
            self.model_parallelization_enabled = False
            self.parallel_execution_engine = None
            self.dependency_analyzer = None
            self.parallelization_config = None
            self.resource_manager = None

            if self.verbose:
                print(f"⚠️ Failed to initialize model parallelization: {e}")
                print("   Continuing with sequential execution")

    def _create_resource_manager(self, config) -> Optional[ResourceManager]:
        """Create ResourceManager instance from configuration (S067-03)"""
        try:
            if not RESOURCE_MANAGEMENT_AVAILABLE:
                return None

            # Build resource manager configuration
            resource_config = {
                "memory": {
                    "monitoring_interval": config.memory_monitoring.monitoring_interval_seconds,
                    "history_size": config.memory_monitoring.history_size,
                    "thresholds": {
                        "moderate_mb": config.memory_monitoring.thresholds.moderate_mb,
                        "high_mb": config.memory_monitoring.thresholds.high_mb,
                        "critical_mb": config.memory_monitoring.thresholds.critical_mb,
                        "gc_trigger_mb": config.memory_monitoring.thresholds.gc_trigger_mb,
                        "fallback_trigger_mb": config.memory_monitoring.thresholds.fallback_trigger_mb
                    }
                },
                "cpu": {
                    "monitoring_interval": config.cpu_monitoring.monitoring_interval_seconds,
                    "history_size": config.cpu_monitoring.history_size,
                    "thresholds": {
                        "moderate_percent": config.cpu_monitoring.thresholds.moderate_percent,
                        "high_percent": config.cpu_monitoring.thresholds.high_percent,
                        "critical_percent": config.cpu_monitoring.thresholds.critical_percent
                    }
                }
            }

            # Setup logger if available
            logger = None
            try:
                logger = ProductionLogger(log_level="INFO")
            except Exception:
                pass  # Continue without logger

            # Create resource manager
            resource_manager = ResourceManager(
                config=resource_config,
                logger=logger
            )

            # Configure adaptive thread adjuster
            if hasattr(resource_manager, 'thread_adjuster'):
                resource_manager.thread_adjuster.min_threads = config.min_threads
                resource_manager.thread_adjuster.max_threads = config.max_threads
                resource_manager.thread_adjuster.adjustment_cooldown = config.adjustment_cooldown_seconds

            return resource_manager

        except Exception as e:
            if self.verbose:
                print(f"⚠️ Failed to create resource manager: {e}")
            return None

    def _setup_hazard_cache_manager(self) -> None:
        """Setup hazard cache manager for automatic change detection (E068D)"""
        try:
            from .hazard_cache_manager import HazardCacheManager

            # Initialize hazard cache manager
            self.hazard_cache_manager = HazardCacheManager(
                config=self.config,
                dbt_runner=self.dbt_runner,
                logger=logging.getLogger(f"{__name__}.HazardCacheManager")
            )

            if self.verbose:
                print("🗄️ Hazard Cache Manager initialized")
                # Display cache status for debugging
                try:
                    cache_status = self.hazard_cache_manager.get_cache_status()
                    current_hash = cache_status.get('current_params_hash', 'N/A')
                    cached_hash = cache_status.get('cached_params_hash', 'N/A')
                    needs_rebuild = cache_status.get('needs_rebuild', True)

                    print(f"   Current params hash: {current_hash[:16] if current_hash != 'N/A' else 'N/A'}...")
                    print(f"   Cached params hash: {cached_hash[:16] if cached_hash != 'N/A' else 'N/A'}...")
                    print(f"   Cache rebuild needed: {needs_rebuild}")
                    print(f"   Cache models: {len(cache_status.get('cache_models', []))}")
                except Exception as e:
                    print(f"   ⚠️ Could not get cache status: {e}")

        except ImportError as e:
            if self.verbose:
                print(f"⚠️ Hazard cache manager not available: {e}")
            self.hazard_cache_manager = None
        except Exception as e:
            if self.verbose:
                print(f"⚠️ Failed to initialize hazard cache manager: {e}")
            self.hazard_cache_manager = None

    def _setup_performance_monitoring(self) -> None:
        """Setup E068E DuckDB performance monitoring system"""
        try:
            from .performance_monitor import DuckDBPerformanceMonitor

            # Get database path from db_manager or use default
            db_path = getattr(self.db_manager, "db_path", get_database_path())

            # Initialize DuckDB performance monitor
            self.duckdb_performance_monitor = DuckDBPerformanceMonitor(
                database_path=db_path,
                logger=logging.getLogger(f"{__name__}.DuckDBPerformanceMonitor"),
                reports_dir=self.reports_dir / "performance"
            )

            if self.verbose:
                print("📊 E068E DuckDB Performance Monitor initialized")
                print(f"   Database: {db_path}")
                print(f"   Reports: {self.reports_dir / 'performance'}")
                print(f"   Target: 15-25% performance improvement")

        except Exception as e:
            if self.verbose:
                print(f"⚠️ Failed to initialize DuckDB performance monitoring: {e}")
                print("   Continuing without E068E performance monitoring")
            self.duckdb_performance_monitor = None

    def _setup_hybrid_performance_monitoring(self) -> None:
        """Setup E068G hybrid performance monitoring system for SQL/Polars comparison"""
        try:
            # Initialize hybrid performance monitor
            self.hybrid_performance_monitor = HybridPerformanceMonitor(
                reports_dir=self.reports_dir / "hybrid_performance"
            )

            if self.verbose:
                print("🔄 E068G Hybrid Performance Monitor initialized")
                print(f"   Mode switching: {self.event_generation_mode}")
                print(f"   Reports: {self.reports_dir / 'hybrid_performance'}")
                if self.is_polars_enabled:
                    print(f"   Polars target: ≤60s for multi-year generation")
                    print(f"   Fallback enabled: {self.polars_settings.fallback_on_error}")

        except Exception as e:
            if self.verbose:
                print(f"⚠️ Failed to initialize hybrid performance monitoring: {e}")
                print("   Continuing without E068G performance monitoring")
            self.hybrid_performance_monitor = None

    def _cleanup_resources(self) -> None:
        """Cleanup resource management components (S067-03) and E068E performance monitoring"""
        try:
            # E068E: Stop DuckDB performance monitoring and generate final report
            if hasattr(self, 'duckdb_performance_monitor') and self.duckdb_performance_monitor:
                try:
                    self.duckdb_performance_monitor.stop_monitoring()

                    # Generate and save final performance report
                    report = self.duckdb_performance_monitor.generate_report()
                    if self.verbose and report:
                        print("\n📊 E068E DuckDB Performance Summary:")
                        # Print first few lines of the report
                        report_lines = report.split('\n')
                        for line in report_lines[:15]:  # First 15 lines
                            print(f"   {line}")
                        if len(report_lines) > 15:
                            print("   ... (full report saved to performance directory)")

                    # Export detailed performance data
                    try:
                        export_path = self.duckdb_performance_monitor.export_performance_data()
                        if self.verbose:
                            print(f"   📁 Performance data exported: {export_path}")
                    except Exception as e:
                        if self.verbose:
                            print(f"   ⚠️ Failed to export performance data: {e}")

                except Exception as e:
                    if self.verbose:
                        print(f"⚠️ Error stopping DuckDB performance monitoring: {e}")

            if hasattr(self, 'resource_manager') and self.resource_manager:
                # Stop resource monitoring
                self.resource_manager.stop_monitoring()

                if self.verbose:
                    # Log final resource statistics
                    final_status = self.resource_manager.get_resource_status()
                    print("📊 Final Resource Statistics:")
                    print(f"   Memory: {final_status['memory']['usage_mb']:.0f}MB")
                    print(f"   CPU: {final_status['cpu']['current_percent']:.1f}%")

                    # Memory leak detection summary
                    if final_status['memory']['leak_detected']:
                        print("   🔍 Memory leaks detected during execution")

                    # Thread adjustment summary
                    if hasattr(self.resource_manager, 'thread_adjuster'):
                        history = self.resource_manager.thread_adjuster.adjustment_history
                        if history:
                            print(f"   🔧 Thread adjustments made: {len(history)}")
                            for adj in history[-3:]:  # Show last 3 adjustments
                                print(f"      {adj['old_thread_count']} → {adj['new_thread_count']} ({adj['reason']})")

        except Exception as e:
            if self.verbose:
                print(f"⚠️ Error cleaning up resources: {e}")

    def __del__(self):
        """Ensure resources are cleaned up when orchestrator is destroyed"""
        try:
            self._cleanup_resources()
        except Exception:
            pass  # Ignore cleanup errors in destructor

    def execute_multi_year_simulation(
        self,
        *,
        start_year: Optional[int] = None,
        end_year: Optional[int] = None,
        resume_from_checkpoint: bool = False,
        fail_on_validation_error: bool = False,
    ) -> MultiYearSummary:
        start = start_year or self.config.simulation.start_year
        end = end_year or self.config.simulation.end_year

        # Enhanced multi-year simulation startup logging
        self._log_simulation_startup_summary(start, end)

        if resume_from_checkpoint:
            ckpt = self._find_last_checkpoint()
            if ckpt:
                start = max(start, ckpt.year)

        # Start adaptive memory monitoring
        if self.memory_manager:
            self.memory_manager.start_monitoring()
            if self.verbose:
                initial_snapshot = self.memory_manager.force_memory_check("simulation_startup")
                print(f"🧠 Initial memory: {initial_snapshot.rss_mb:.1f}MB (pressure: {initial_snapshot.pressure_level.value})")

        # E068E: Start DuckDB performance monitoring
        if hasattr(self, 'duckdb_performance_monitor') and self.duckdb_performance_monitor:
            self.duckdb_performance_monitor.start_monitoring()
            if self.verbose:
                print("📊 E068E DuckDB performance monitoring started")

        # Wrap the entire run in a performance-tracked operation when observability is enabled
        if self.observability:
            from contextlib import ExitStack
            _run_ctx = self.observability.track_operation(
                "multi_year_run", start_year=start, end_year=end
            )
        else:
            from contextlib import nullcontext
            _run_ctx = nullcontext()

        with _run_ctx:
            with ExecutionMutex("navigator_orchestrator"):
                # Optional one-time full reset before the yearly loop
                self._maybe_full_reset()
                # Ensure orchestrator-managed registries start clean for a new run
                # These tables are not year-partitioned; stale state can block auto-enrollment
                if not resume_from_checkpoint:
                    try:
                        er = self.registry_manager.get_enrollment_registry()
                        dr = self.registry_manager.get_deferral_registry()
                        er.create_table()
                        dr.create_table()
                        # Reset only when starting at configured first year (fresh simulation)
                        if start == self.config.simulation.start_year:
                            er.reset()
                            dr.reset()
                            if self.verbose:
                                print(
                                    "🧹 Cleared enrollment/deferral registries for fresh run"
                                )
                    except Exception:
                        # Non-fatal; proceed even if reset fails
                        pass
                completed_years: List[int] = []

                try:
                    for year in range(start, end + 1):
                        print(f"\n🔄 Starting simulation year {year}")

                        # Memory check before year processing
                        if self.memory_manager:
                            year_snapshot = self.memory_manager.force_memory_check(f"year_{year}_start")
                            if self.verbose:
                                print(f"🧠 Memory before year {year}: {year_snapshot.rss_mb:.1f}MB (batch size: {self.memory_manager.get_current_batch_size()})")

                        if self.observability:
                            # Track end-to-end year execution with performance metrics (unique per year)
                            with self.observability.track_operation(
                                f"year_simulation_{year}", year=year
                            ):
                                self._execute_year_workflow(
                                    year, fail_on_validation_error=fail_on_validation_error
                                )
                        else:
                            self._execute_year_workflow(
                                year, fail_on_validation_error=fail_on_validation_error
                            )

                        # Memory check after year processing
                        if self.memory_manager:
                            post_year_snapshot = self.memory_manager.force_memory_check(f"year_{year}_complete")
                            if self.verbose:
                                print(f"🧠 Memory after year {year}: {post_year_snapshot.rss_mb:.1f}MB")

                        # Create checkpoint using enhanced system if available
                        if (
                            self.enhanced_checkpoints
                            and self.checkpoint_manager
                            and self.config_hash
                        ):
                            try:
                                run_id = (
                                    f"multiyear_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}"
                                )
                                checkpoint_data = self.checkpoint_manager.save_checkpoint(
                                    year, run_id, self.config_hash
                                )
                                if self.verbose:
                                    print(f"   ✅ Enhanced checkpoint saved for year {year}")
                            except Exception as e:
                                print(f"   ⚠️ Enhanced checkpoint failed for year {year}: {e}")
                                # Fall back to legacy checkpoint
                                self._write_checkpoint(
                                    WorkflowCheckpoint(
                                        year,
                                        WorkflowStage.CLEANUP,
                                        datetime.utcnow().isoformat(),
                                        self._state_hash(year),
                                    )
                                )
                        else:
                            # Legacy checkpoint system
                            self._write_checkpoint(
                                WorkflowCheckpoint(
                                    year,
                                    WorkflowStage.CLEANUP,
                                    datetime.utcnow().isoformat(),
                                    self._state_hash(year),
                                )
                            )

                        # Track completed year regardless of checkpoint system used
                        completed_years.append(year)

                except Exception as e:
                    # Log memory state on error
                    if self.memory_manager:
                        error_snapshot = self.memory_manager.force_memory_check("simulation_error")
                        print(f"🧠 Memory at error: {error_snapshot.rss_mb:.1f}MB (pressure: {error_snapshot.pressure_level.value})")
                    raise

                finally:
                    # Stop memory monitoring and generate final report
                    if self.memory_manager:
                        self.memory_manager.stop_monitoring()

                        # Generate memory statistics and recommendations
                        stats = self.memory_manager.get_memory_statistics()
                        recommendations = self.memory_manager.get_recommendations()

                        if self.verbose:
                            print("\n🧠 Adaptive Memory Management Summary:")
                            print(f"   Peak Memory: {stats['trends']['peak_memory_mb']}MB")
                            print(f"   GC Collections: {stats['stats']['total_gc_collections']}")
                            print(f"   Batch Adjustments: {stats['stats']['batch_size_adjustments']}")
                            print(f"   Fallback Events: {stats['stats']['automatic_fallbacks']}")

                            if recommendations:
                                print(f"   Recommendations: {len(recommendations)}")
                                for rec in recommendations[-3:]:  # Show last 3
                                    print(f"     • {rec['type']}: {rec['description']}")

                        # Export memory profile
                        try:
                            profile_path = self.memory_manager.export_memory_profile()
                            if self.verbose:
                                print(f"   Memory profile: {profile_path}")
                        except Exception:
                            pass

        # Final multi-year summary using reporter
        reporter = MultiYearReporter(self.db_manager)

        # Handle single-year runs gracefully to avoid raising an error
        if len(completed_years) >= 2:
            summary = reporter.generate_summary(completed_years)

            # Display comprehensive multi-year summary (matching monolithic script)
            reporter.display_comprehensive_multi_year_summary(completed_years)
        elif len(completed_years) == 1:
            # Construct a minimal single-year summary compatible with MultiYearSummary
            year = completed_years[0]
            with self.db_manager.get_connection() as conn:
                # Workforce breakdown for the single year
                progression = [reporter._workforce_breakdown(conn, year)]
                # Growth analysis is zeroed for single-year context
                growth = {
                    "start_active": progression[0].active_employees,
                    "end_active": progression[0].active_employees,
                    "cagr_pct": 0.0,
                    "total_growth_pct": 0.0,
                }
                # Event trends for the single year
                rows = conn.execute(
                    """
                    SELECT lower(event_type) AS et, COUNT(*)
                    FROM fct_yearly_events
                    WHERE simulation_year = ?
                    GROUP BY lower(event_type)
                    """,
                    [year],
                ).fetchall()
                event_trends = {t: [c] for t, c in rows}
                participation_trends = [progression[0].participation_rate]

            summary = MultiYearSummary(
                start_year=year,
                end_year=year,
                workforce_progression=progression,
                growth_analysis=growth,
                event_trends=event_trends,
                participation_trends=participation_trends,
                generated_at=datetime.utcnow(),
            )
        else:
            # No completed years – return an empty single-year shaped summary
            # This should not normally occur, but protects the pipeline contract.
            summary = MultiYearSummary(
                start_year=self.config.simulation.start_year,
                end_year=self.config.simulation.start_year,
                workforce_progression=[],
                growth_analysis={
                    "start_active": 0,
                    "end_active": 0,
                    "cagr_pct": 0.0,
                    "total_growth_pct": 0.0,
                },
                event_trends={},
                participation_trends=[],
                generated_at=datetime.utcnow(),
            )

        # Persist summary CSV (works for single or multi-year)
        out_csv = (
            self.reports_dir
            / f"multi_year_summary_{completed_years[0]}_{completed_years[-1]}.csv"
        )
        summary.export_csv(out_csv)
        # Announce where the CSV summary was saved for discoverability
        try:
            print(f"📄 Multi-year CSV summary saved to: {out_csv}")
        except Exception:
            pass

        # Generate and save hybrid performance report (E068G)
        if hasattr(self, 'hybrid_performance_monitor') and self.hybrid_performance_monitor:
            try:
                report_path = self.hybrid_performance_monitor.save_performance_report()
                if self.verbose:
                    print(f"📊 Hybrid performance report saved: {report_path}")
            except Exception as e:
                if self.verbose:
                    print(f"⚠️ Failed to save hybrid performance report: {e}")

        # Cleanup resource management components (S067-03)
        self._cleanup_resources()

        # Finalize observability (saves artifacts under artifacts/runs/<run_id>/)
        try:
            if self.observability:
                final_status = "success"
                self.observability.finalize_run(final_status)
        except Exception:
            pass

        # E068C: Add threading configuration to summary
        if hasattr(summary, '__dict__'):
            summary.threading_config = {
                "dbt_threads": self.dbt_threads,
                "event_shards": self.event_shards,
                "event_generation_mode": self.config.get_event_generation_mode(),
                "polars_enabled": self.config.is_polars_mode_enabled()
            }

        return summary

    def execute_workflow_stage(
        self,
        stage: StageDefinition,
        year: int
    ) -> Dict[str, Any]:
        """Execute a workflow stage with optimal threading (E068C)."""
        start_time = time.time()

        try:
            if self.verbose:
                print(f"   📋 Starting {stage.name.value} with {self.dbt_threads} threads")

            # Execute stage with appropriate threading strategy
            if stage.name == WorkflowStage.EVENT_GENERATION:
                # EVENT_GENERATION can be parallelized safely
                results = self._execute_parallel_stage(stage, year)
            elif stage.name == WorkflowStage.STATE_ACCUMULATION:
                # STATE_ACCUMULATION must run sequentially due to delete+insert transaction conflicts
                if self.verbose:
                    print(f"   🔒 Running STATE_ACCUMULATION sequentially to prevent transaction conflicts")
                self._run_stage_models(stage, year)
                results = []
            else:
                # Use existing sequential execution for other stages
                self._run_stage_models(stage, year)
                results = []

            execution_time = time.time() - start_time
            if self.verbose:
                print(f"   ✅ Completed {stage.name.value} in {execution_time:.1f}s")

            return {
                "stage": stage.name.value,
                "year": year,
                "success": True,
                "execution_time": execution_time,
                "results": results
            }

        except Exception as e:
            execution_time = time.time() - start_time
            if self.verbose:
                print(f"   ❌ Failed {stage.name.value} after {execution_time:.1f}s: {e}")

            return {
                "stage": stage.name.value,
                "year": year,
                "success": False,
                "execution_time": execution_time,
                "error": str(e)
            }

    def _execute_parallel_stage(
        self,
        stage: StageDefinition,
        year: int
    ) -> List[DbtResult]:
        """Execute stage with dbt parallelization using tag-based selection (E068C)."""

        if stage.name == WorkflowStage.EVENT_GENERATION and self.event_shards > 1:
            return self._execute_sharded_event_generation(year)
        else:
            # Single parallel execution per stage using tags
            tag_name = stage.name.value.upper()

            if self.verbose:
                print(f"   🚀 Executing tag:{tag_name} with {self.dbt_threads} threads")

            result = self.dbt_runner.execute_command(
                ["run", "--select", f"tag:{tag_name}"],
                simulation_year=year,
                dbt_vars=self._dbt_vars,
                stream_output=True
            )

            if not result.success:
                raise PipelineStageError(
                    f"Parallel stage {stage.name.value} failed with code {result.return_code}"
                )

            return [result]

    def _execute_sharded_event_generation(self, year: int) -> List[DbtResult]:
        """Execute event generation with optional sharding for large datasets (E068C)."""
        results = []

        if self.verbose:
            print(f"   🔀 Executing event generation with {self.event_shards} shards")

        # Execute sharded event generation in parallel
        for shard_id in range(self.event_shards):
            shard_vars = self._dbt_vars.copy()
            shard_vars.update({
                "shard_id": shard_id,
                "total_shards": self.event_shards
            })

            result = self.dbt_runner.execute_command(
                ["run", "--select", f"events_y{year}_shard{shard_id}"],
                simulation_year=year,
                dbt_vars=shard_vars,
                stream_output=True
            )
            results.append(result)

            if not result.success:
                raise PipelineStageError(
                    f"Event shard {shard_id} failed with code {result.return_code}"
                )

        # Execute final union writer
        union_result = self.dbt_runner.execute_command(
            ["run", "--select", "fct_yearly_events"],
            simulation_year=year,
            dbt_vars=self._dbt_vars,
            stream_output=True
        )
        results.append(union_result)

        if not union_result.success:
            raise PipelineStageError(
                f"Event union writer failed with code {union_result.return_code}"
            )

        return results

    def _execute_hybrid_event_generation(
        self, years: List[int]
    ) -> Dict[str, Any]:
        """
        Execute event generation using either SQL or Polars mode based on configuration.

        This method implements the hybrid pipeline integration that supports both
        SQL-based (traditional dbt models) and Polars-based (bulk factory) event generation.
        """
        event_mode = self.config.get_event_generation_mode()
        start_time = time.time()

        if self.verbose:
            print(f"🔄 Executing event generation in {event_mode.upper()} mode for years {years}")

        try:
            if event_mode == "polars" and self.config.is_polars_mode_enabled():
                return self._execute_polars_event_generation(years, start_time)
            else:
                return self._execute_sql_event_generation(years, start_time)
        except Exception as e:
            # Check if fallback is enabled for Polars mode
            polars_settings = self.config.get_polars_settings()
            if event_mode == "polars" and polars_settings.fallback_on_error:
                if self.verbose:
                    print(f"⚠️ Polars event generation failed: {e}")
                    print("🔄 Falling back to SQL mode...")
                return self._execute_sql_event_generation(years, start_time, fallback=True)
            else:
                raise

    def _execute_polars_event_generation(
        self, years: List[int], start_time: float, fallback: bool = False
    ) -> Dict[str, Any]:
        """
        Execute event generation using Polars bulk event factory.

        This provides high-performance vectorized event generation using Polars
        with target performance of ≤60s for 5k employees × 5 years.
        """
        try:
            from .polars_event_factory import PolarsEventGenerator, EventFactoryConfig
        except ImportError as e:
            if fallback:
                raise ImportError(f"Polars event factory not available for fallback: {e}")
            raise ImportError(f"Polars event factory not available: {e}. Install polars>=1.0.0")

        polars_settings = self.config.get_polars_settings()

        # Configure Polars event factory
        factory_config = EventFactoryConfig(
            start_year=min(years),
            end_year=max(years),
            output_path=Path(polars_settings.output_path),
            scenario_id=getattr(self.config, 'scenario_id', 'default'),
            plan_design_id=getattr(self.config, 'plan_design_id', 'default'),
            random_seed=self.config.simulation.random_seed,
            batch_size=polars_settings.batch_size,
            enable_profiling=polars_settings.enable_profiling,
            enable_compression=polars_settings.enable_compression,
            compression_level=polars_settings.compression_level,
            max_memory_gb=polars_settings.max_memory_gb,
            lazy_evaluation=polars_settings.lazy_evaluation,
            streaming=polars_settings.streaming,
            parallel_io=polars_settings.parallel_io
        )

        if self.verbose:
            print(f"📊 Polars event generation configuration:")
            print(f"   Max threads: {polars_settings.max_threads}")
            print(f"   Batch size: {polars_settings.batch_size:,}")
            print(f"   Output path: {polars_settings.output_path}")
            print(f"   Memory limit: {polars_settings.max_memory_gb}GB")
            print(f"   Compression: {'enabled' if polars_settings.enable_compression else 'disabled'}")

        # Set Polars thread count
        import os
        os.environ['POLARS_MAX_THREADS'] = str(polars_settings.max_threads)

        # Generate events using Polars
        generator = PolarsEventGenerator(factory_config)
        generator.generate_multi_year_events()

        polars_duration = time.time() - start_time
        total_events = generator.stats.get('total_events_generated', 0)

        if self.verbose:
            print(f"✅ Polars event generation completed in {polars_duration:.1f}s")
            print(f"📊 Generated {total_events:,} events")
            if polars_duration > 0:
                print(f"⚡ Performance: {total_events/polars_duration:.0f} events/second")

            # Performance assessment
            if polars_duration <= 60 and len(years) >= 3:
                print("🎯 PERFORMANCE TARGET MET: ≤60s for multi-year generation")
            elif polars_duration <= 60:
                print("🎯 Performance target met for available years")
            else:
                print(f"⏰ Performance target missed: {polars_duration:.1f}s (target: ≤60s)")

        # Update dbt variables to point to Polars output
        self._dbt_vars.update({
            'polars_events_path': str(factory_config.output_path),
            'event_generation_mode': 'polars',
            'polars_enabled': True
        })

        return {
            'mode': 'polars',
            'success': True,
            'execution_time': polars_duration,
            'total_events': total_events,
            'output_path': str(factory_config.output_path),
            'performance_target_met': polars_duration <= 60,
            'fallback_used': fallback
        }

    def _execute_sql_event_generation(
        self, years: List[int], start_time: float, fallback: bool = False
    ) -> Dict[str, Any]:
        """
        Execute event generation using traditional SQL-based dbt models.

        This uses the existing dbt event generation models with optional
        threading and sharding optimizations.
        """
        if fallback and self.verbose:
            print("🔄 Executing SQL event generation (fallback mode)")

        total_events = 0
        successful_years = []

        # Execute event generation for each year using existing workflow
        for year in years:
            try:
                # Use existing event generation stage execution
                event_stage = StageDefinition(
                    name=WorkflowStage.EVENT_GENERATION,
                    dependencies=[WorkflowStage.FOUNDATION],
                    models=self._get_event_generation_models(year),
                    validation_rules=["hire_termination_ratio", "event_sequence"],
                    parallel_safe=False
                )

                # Execute the stage using existing logic
                if self.event_shards > 1:
                    results = self._execute_sharded_event_generation(year)
                else:
                    # Single execution per stage using tags
                    # Exclude STATE_ACCUMULATION models that were incorrectly tagged EVENT_GENERATION via directory-level config
                    # These models depend on STATE_ACCUMULATION outputs that don't exist yet during EVENT_GENERATION:
                    # - int_employee_contributions: depends on int_deferral_rate_state_accumulator_v2
                    # - int_employee_match_calculations: depends on int_employee_contributions
                    # - int_promotion_events_optimized: depends on fct_workforce_snapshot
                    result = self.dbt_runner.execute_command(
                        ["run", "--select", "tag:EVENT_GENERATION",
                         "--exclude", "int_employee_contributions",
                         "--exclude", "int_employee_match_calculations",
                         "--exclude", "int_promotion_events_optimized"],
                        simulation_year=year,
                        dbt_vars=self._dbt_vars,
                        stream_output=True
                    )
                    results = [result]

                if all(r.success for r in results):
                    successful_years.append(year)
                    # Count events from database
                    def _count_events(conn):
                        return conn.execute(
                            "SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year = ?",
                            [year]
                        ).fetchone()[0]

                    year_events = self.db_manager.execute_with_retry(_count_events)
                    total_events += year_events
                else:
                    raise PipelineStageError(
                        f"SQL event generation failed for year {year}"
                    )

            except Exception as e:
                if fallback:
                    raise PipelineStageError(f"SQL fallback failed for year {year}: {e}")
                raise

        sql_duration = time.time() - start_time

        if self.verbose:
            print(f"✅ SQL event generation completed in {sql_duration:.1f}s")
            print(f"📊 Generated {total_events:,} events across {len(successful_years)} years")
            if sql_duration > 0:
                print(f"⚡ Performance: {total_events/sql_duration:.0f} events/second")

        return {
            'mode': 'sql',
            'success': len(successful_years) == len(years),
            'execution_time': sql_duration,
            'total_events': total_events,
            'successful_years': successful_years,
            'fallback_used': fallback
        }

    def _get_event_generation_models(self, year: int) -> List[str]:
        """
        Get the list of event generation models for a specific year.

        This matches the existing workflow definition logic.
        """
        models = [
            # E049: Ensure synthetic baseline enrollment events are built in the first year
            *([
                "int_synthetic_baseline_enrollment_events"
            ] if year == self.config.simulation.start_year else []),
            "int_termination_events",
            "int_hiring_events",
            "int_new_hire_termination_events",
            "int_employer_eligibility",
            "int_hazard_promotion",
            "int_hazard_merit",
            "int_promotion_events",
            "int_merit_events",
            "int_eligibility_determination",
            "int_voluntary_enrollment_decision",
            "int_proactive_voluntary_enrollment",
            "int_enrollment_events",
            "int_deferral_rate_escalation_events",
        ]
        return models

    def _execute_year_workflow(
        self, year: int, *, fail_on_validation_error: bool
    ) -> None:
        workflow = self._define_year_workflow(year)

        # Optional: clear existing rows for this year based on config.setup
        self._maybe_clear_year_data(year)

        # E068D: Ensure hazard caches are current before workflow execution
        if hasattr(self, 'hazard_cache_manager') and self.hazard_cache_manager:
            try:
                if self.verbose:
                    print("🗄️ Checking hazard cache currency...")
                self.hazard_cache_manager.ensure_hazard_caches_current()
            except Exception as e:
                # Log error but continue execution (non-fatal for backward compatibility)
                # Hazard caches will rebuild on next model execution if needed
                logging.getLogger(__name__).debug(f"Hazard cache check failed (non-critical): {e}")
                if self.verbose:
                    print("   ℹ️ Hazard cache check skipped (will rebuild if needed during execution)")

        # Ensure seeds are loaded once
        if not self._seeded:
            seed_res = self.dbt_runner.execute_command(["seed"], stream_output=True)
            if not seed_res.success:
                raise PipelineStageError(
                    f"Dbt seed failed with code {seed_res.return_code}"
                )
            self._seeded = True

        # Year 1 registry seeding
        if year == self.config.simulation.start_year:
            self.registry_manager.get_enrollment_registry().create_for_year(year)
            self.registry_manager.get_deferral_registry().create_table()

        for stage in workflow:
            print(f"   📋 Executing stage: {stage.name.value}")

            # E068E: Record performance checkpoint before stage execution
            if hasattr(self, 'duckdb_performance_monitor') and self.duckdb_performance_monitor:
                checkpoint_name = f"{stage.name.value}_{year}_start"
                self.duckdb_performance_monitor.record_checkpoint(checkpoint_name)

            # E068G: Use hybrid event generation for EVENT_GENERATION stage
            if stage.name == WorkflowStage.EVENT_GENERATION:
                try:
                    hybrid_result = self._execute_hybrid_event_generation([year])
                    if not hybrid_result['success']:
                        raise PipelineStageError(f"Hybrid event generation failed: {hybrid_result}")

                    if self.verbose:
                        mode = hybrid_result['mode'].upper()
                        duration = hybrid_result['execution_time']
                        events = hybrid_result['total_events']
                        print(f"✅ {mode} event generation completed: {events:,} events in {duration:.1f}s")
                        if hybrid_result.get('fallback_used'):
                            print("⚡ Used fallback mode due to primary mode failure")

                    # E068E: Record performance checkpoint after stage completion
                    if hasattr(self, 'duckdb_performance_monitor') and self.duckdb_performance_monitor:
                        checkpoint_name = f"{stage.name.value}_{year}_complete"
                        self.duckdb_performance_monitor.record_checkpoint(checkpoint_name)

                    # Skip the rest of the existing stage execution logic
                    continue

                except Exception as e:
                    raise PipelineStageError(f"Hybrid event generation failed for year {year}: {e}")

            # E068C: Use new workflow stage execution method for other supported stages
            elif stage.name in (WorkflowStage.STATE_ACCUMULATION,):
                stage_result = self.execute_workflow_stage(stage, year)
                if not stage_result["success"]:
                    raise PipelineStageError(f"Stage {stage.name.value} failed: {stage_result.get('error', 'Unknown error')}")

                # E068E: Record performance checkpoint after stage completion
                if hasattr(self, 'duckdb_performance_monitor') and self.duckdb_performance_monitor:
                    checkpoint_name = f"{stage.name.value}_{year}_complete"
                    self.duckdb_performance_monitor.record_checkpoint(checkpoint_name)

                # Skip the rest of the existing stage execution logic
                continue

            # Advanced resource management hooks (S067-03)
            if hasattr(self, 'resource_manager') and self.resource_manager:
                # Check resource health before stage execution
                if not self.resource_manager.check_resource_health():
                    if self.verbose:
                        print(f"   ⚠️ Resource pressure detected before stage {stage.name.value}")

                    # Trigger resource cleanup
                    cleanup_result = self.resource_manager.trigger_resource_cleanup()
                    if self.verbose:
                        print(f"   🧹 Resource cleanup: {cleanup_result['memory_freed_mb']:+.1f}MB freed")

                # Get initial resource status
                pre_stage_status = self.resource_manager.get_resource_status()
                if self.verbose:
                    print(f"   📊 Pre-stage resources: {pre_stage_status['memory']['usage_mb']:.0f}MB memory, {pre_stage_status['cpu']['current_percent']:.1f}% CPU")

                # Monitor stage execution with resource tracking
                with self.resource_manager.monitor_execution(f"stage_{stage.name.value}_{year}", 1):
                    if self.observability:
                        # Per-stage performance tracking
                        with self.observability.track_operation(
                            f"stage_{stage.name.value}_{year}",
                            stage=stage.name.value,
                            year=year,
                        ):
                            with time_block(f"stage:{stage.name.value}"):
                                self._run_stage_models(stage, year)
                    else:
                        with time_block(f"stage:{stage.name.value}"):
                            self._run_stage_models(stage, year)

                # Get post-stage resource status and analysis
                post_stage_status = self.resource_manager.get_resource_status()
                if self.verbose:
                    memory_delta = post_stage_status['memory']['usage_mb'] - pre_stage_status['memory']['usage_mb']
                    print(f"   📈 Post-stage resources: {post_stage_status['memory']['usage_mb']:.0f}MB memory ({memory_delta:+.0f}MB), {post_stage_status['cpu']['current_percent']:.1f}% CPU")

                    # Report resource pressure changes
                    if pre_stage_status['memory']['pressure'] != post_stage_status['memory']['pressure']:
                        print(f"   🚨 Memory pressure changed: {pre_stage_status['memory']['pressure']} → {post_stage_status['memory']['pressure']}")

                    # Memory leak detection
                    if post_stage_status['memory']['leak_detected']:
                        print(f"   🔍 Memory leak detected during stage {stage.name.value}")

            else:
                # Fallback to existing memory management
                # Memory check before stage
                if hasattr(self, 'memory_manager') and self.memory_manager:
                    pre_stage_snapshot = self.memory_manager.force_memory_check(f"{stage.name.value}_start")

                if self.observability:
                    # Per-stage performance tracking
                    with self.observability.track_operation(
                        f"stage_{stage.name.value}_{year}",
                        stage=stage.name.value,
                        year=year,
                    ):
                        with time_block(f"stage:{stage.name.value}"):
                            self._run_stage_models(stage, year)
                else:
                    with time_block(f"stage:{stage.name.value}"):
                        self._run_stage_models(stage, year)

                # Memory check after stage
                if hasattr(self, 'memory_manager') and self.memory_manager:
                    post_stage_snapshot = self.memory_manager.force_memory_check(f"{stage.name.value}_complete")
                    if self.verbose:
                        memory_change = post_stage_snapshot.rss_mb - pre_stage_snapshot.rss_mb
                        print(f"   🧠 Stage memory change: {memory_change:+.1f}MB (now: {post_stage_snapshot.rss_mb:.1f}MB)")

                        # Check if we need to adjust batch size based on this stage
                        if post_stage_snapshot.pressure_level != pre_stage_snapshot.pressure_level:
                            print(f"   🧠 Memory pressure changed: {pre_stage_snapshot.pressure_level.value} → {post_stage_snapshot.pressure_level.value}")
                            print(f"   🧠 Batch size: {self.memory_manager.get_current_batch_size()}")

            # E068E: Record performance checkpoint after stage completion (for non-specialized stages)
            if hasattr(self, 'duckdb_performance_monitor') and self.duckdb_performance_monitor:
                checkpoint_name = f"{stage.name.value}_{year}_complete"
                self.duckdb_performance_monitor.record_checkpoint(checkpoint_name)

            # Comprehensive validation for foundation models
            if stage.name == WorkflowStage.FOUNDATION:
                start_year = self.config.simulation.start_year

                def _chk(conn):
                    baseline = conn.execute(
                        "SELECT COUNT(*) FROM int_baseline_workforce WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    # For years > start_year, baseline lives in start_year; fetch preserved baseline rows
                    preserved_baseline = conn.execute(
                        "SELECT COUNT(*) FROM int_baseline_workforce WHERE simulation_year = ?",
                        [start_year],
                    ).fetchone()[0]
                    compensation = conn.execute(
                        "SELECT COUNT(*) FROM int_employee_compensation_by_year WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    wn = conn.execute(
                        "SELECT COUNT(*) FROM int_workforce_needs WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    wnbl = conn.execute(
                        "SELECT COUNT(*) FROM int_workforce_needs_by_level WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    # Epic E039: Employer contribution model validation (eligibility may not be built in FOUNDATION)
                    try:
                        employer_elig = conn.execute(
                            "SELECT COUNT(*) FROM int_employer_eligibility WHERE simulation_year = ?",
                            [year],
                        ).fetchone()[0]
                    except Exception:
                        employer_elig = 0
                    # int_employer_core_contributions is built in STATE_ACCUMULATION, not FOUNDATION
                    try:
                        employer_core = conn.execute(
                            "SELECT COUNT(*) FROM int_employer_core_contributions WHERE simulation_year = ?",
                            [year],
                        ).fetchone()[0]
                    except Exception:
                        # Table doesn't exist yet (expected in foundation stage)
                        employer_core = 0
                    # Diagnostics: hiring demand
                    total_hires_needed = conn.execute(
                        "SELECT COALESCE(MAX(total_hires_needed), 0) FROM int_workforce_needs WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    level_hires_needed = conn.execute(
                        "SELECT COALESCE(SUM(hires_needed), 0) FROM int_workforce_needs_by_level WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    return (
                        int(baseline),
                        int(preserved_baseline),
                        int(compensation),
                        int(wn),
                        int(wnbl),
                        int(employer_elig or 0),
                        int(employer_core or 0),
                        int(total_hires_needed or 0),
                        int(level_hires_needed or 0),
                    )

                (
                    baseline_cnt,
                    preserved_baseline_cnt,
                    comp_cnt,
                    wn_cnt,
                    wnbl_cnt,
                    employer_elig_cnt,
                    employer_core_cnt,
                    total_hires_needed,
                    level_hires_needed,
                ) = self.db_manager.execute_with_retry(_chk)
                print(f"   📊 Foundation model validation for year {year}:")
                if year == start_year:
                    print(f"      int_baseline_workforce: {baseline_cnt} rows")
                else:
                    # Baseline is only populated in start_year; show preserved baseline for clarity
                    print(
                        f"      int_baseline_workforce: {baseline_cnt} rows (current year); preserved baseline {preserved_baseline_cnt} rows (start_year={start_year})"
                    )
                print(f"      int_employee_compensation_by_year: {comp_cnt} rows")
                print(f"      int_workforce_needs: {wn_cnt} rows")
                print(f"      int_workforce_needs_by_level: {wnbl_cnt} rows")
                print(
                    f"      int_employer_eligibility: {employer_elig_cnt} rows (not built in FOUNDATION)"
                )
                print(
                    f"      int_employer_core_contributions: {employer_core_cnt} rows (built later in STATE_ACCUMULATION)"
                )
                print(f"      hiring_demand.total_hires_needed: {total_hires_needed}")
                print(f"      hiring_demand.sum_by_level: {level_hires_needed}")

                # Epic E042 Fix: Only validate baseline workforce for first year
                if baseline_cnt == 0 and year == self.config.simulation.start_year:
                    raise PipelineStageError(
                        f"CRITICAL: int_baseline_workforce has 0 rows for year {year}. Check census data processing."
                    )
                elif baseline_cnt == 0 and year > self.config.simulation.start_year:
                    print(
                        f"ℹ️ int_baseline_workforce has 0 rows for year {year} (expected). Baseline is preserved in start_year={start_year} with {preserved_baseline_cnt} rows."
                    )
                if comp_cnt == 0:
                    raise PipelineStageError(
                        f"CRITICAL: int_employee_compensation_by_year has 0 rows for year {year}. Foundation models are broken."
                    )
                if wn_cnt == 0 or wnbl_cnt == 0:
                    raise PipelineStageError(
                        f"CRITICAL: workforce_needs rows={wn_cnt}, by_level rows={wnbl_cnt} for {year}. Hiring will fail."
                    )
                if employer_elig_cnt == 0:
                    print(
                        f"ℹ️ int_employer_eligibility has 0 rows for year {year} (expected before EVENT_GENERATION)."
                    )
                if employer_core_cnt == 0:
                    print(
                        f"ℹ️ int_employer_core_contributions has 0 rows for year {year} (expected; built during STATE_ACCUMULATION)."
                    )
                if total_hires_needed == 0 or level_hires_needed == 0:
                    print(
                        "⚠️ Hiring demand calculated as 0; new hire events will not be generated. Verify target_growth_rate and termination rates."
                    )

            # Post event-generation sanity check: ensure hires materialized and have compensation
            if stage.name == WorkflowStage.EVENT_GENERATION:

                def _ev_chk(conn):
                    hires = conn.execute(
                        "SELECT COUNT(*) FROM int_hiring_events WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    demand = conn.execute(
                        "SELECT COALESCE(SUM(hires_needed),0) FROM int_workforce_needs_by_level WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    null_comp_hires = conn.execute(
                        "SELECT COUNT(*) FROM int_hiring_events WHERE simulation_year = ? AND compensation_amount IS NULL",
                        [year],
                    ).fetchone()[0]
                    return int(hires), int(demand or 0), int(null_comp_hires)

                (
                    hires_cnt,
                    demand_cnt,
                    null_comp_cnt,
                ) = self.db_manager.execute_with_retry(_ev_chk)
                if demand_cnt > 0 and hires_cnt == 0:
                    print(
                        f"⚠️ Detected 0 hiring events but demand={demand_cnt}. Rebuilding hiring models."
                    )
                    self.dbt_runner.execute_command(
                        [
                            "run",
                            "--select",
                            "int_hiring_events int_new_hire_termination_events",
                            "--full-refresh",
                        ],
                        simulation_year=year,
                        dbt_vars=self._dbt_vars,
                        stream_output=True,
                    )
                if hires_cnt > 0 and null_comp_cnt > 0:
                    print(
                        f"⚠️ Detected {null_comp_cnt} hire(s) with NULL compensation. Rebuilding needs_by_level -> hiring."
                    )
                    self.dbt_runner.execute_command(
                        [
                            "run",
                            "--select",
                            "int_workforce_needs_by_level int_hiring_events",
                            "--full-refresh",
                        ],
                        simulation_year=year,
                        dbt_vars=self._dbt_vars,
                        stream_output=True,
                    )

            # Post state accumulation check: ensure hires landed in yearly events and match events exist
            if stage.name == WorkflowStage.STATE_ACCUMULATION:

                def _events_chk(conn):
                    hires_in_fact = conn.execute(
                        "SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year = ? AND lower(event_type) = 'hire'",
                        [year],
                    ).fetchone()[0]
                    hires_src = conn.execute(
                        "SELECT COUNT(*) FROM int_hiring_events WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    null_comp_hires = conn.execute(
                        "SELECT COUNT(*) FROM int_hiring_events WHERE simulation_year = ? AND compensation_amount IS NULL",
                        [year],
                    ).fetchone()[0]
                    # Check employer match events
                    contrib_with_deferrals = conn.execute(
                        "SELECT COUNT(*) FROM int_employee_contributions WHERE simulation_year = ? AND annual_contribution_amount > 0",
                        [year],
                    ).fetchone()[0]
                    match_events = conn.execute(
                        "SELECT COUNT(*) FROM fct_employer_match_events WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    return (
                        int(hires_in_fact),
                        int(hires_src),
                        int(null_comp_hires),
                        int(contrib_with_deferrals),
                        int(match_events),
                    )

                (
                    hires_in_fact,
                    hires_src,
                    null_comp_cnt,
                    contrib_with_deferrals,
                    match_events,
                ) = self.db_manager.execute_with_retry(_events_chk)

                if hires_src > 0 and hires_in_fact == 0:
                    print(
                        "⚠️ fct_yearly_events missing hire rows; forcing targeted refresh of hires and facts."
                    )
                    # Ensure snapshot year rows are cleared before rebuild
                    try:
                        def _clear(conn):
                            conn.execute(
                                "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?",
                                [year],
                            )
                            return True
                        self.db_manager.execute_with_retry(_clear)
                    except Exception:
                        pass
                    self.dbt_runner.execute_command(
                        [
                            "run",
                            "--select",
                            "int_hiring_events fct_yearly_events fct_workforce_snapshot",
                            "--full-refresh",
                        ],
                        simulation_year=year,
                        dbt_vars=self._dbt_vars,
                        stream_output=True,
                    )
                if null_comp_cnt > 0:
                    # After fixing compensation, make sure downstream facts/snapshots reflect it
                    try:
                        def _clear(conn):
                            conn.execute(
                                "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?",
                                [year],
                            )
                            return True
                        self.db_manager.execute_with_retry(_clear)
                    except Exception:
                        pass
                    self.dbt_runner.execute_command(
                        [
                            "run",
                            "--select",
                            "fct_yearly_events fct_workforce_snapshot",
                            "--full-refresh",
                        ],
                        simulation_year=year,
                        dbt_vars=self._dbt_vars,
                        stream_output=True,
                    )

                # Check employer match events
                if contrib_with_deferrals > 0 and match_events == 0:
                    print(
                        f"⚠️ Found {contrib_with_deferrals} employees with contributions but 0 match events."
                    )
                    print("   Suggested checks:")
                    print("   - Verify dbt vars: active_match_formula, match_formulas")
                    print(
                        "   - Check int_employee_match_calculations for non-zero employer_match_amount"
                    )
                    print(
                        "   - Rebuild: dbt run --select int_employee_match_calculations fct_employer_match_events"
                    )

                # Epic E042 Guardrail: ensure contributions are populated when deferral state exists
                def _contrib_guard(conn):
                    dr_cnt = conn.execute(
                        "SELECT COUNT(*) FROM int_deferral_rate_state_accumulator_v2 WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    comp_cnt = conn.execute(
                        "SELECT COUNT(*) FROM int_employee_compensation_by_year WHERE simulation_year = ?",
                        [year],
                    ).fetchone()[0]
                    overlap = conn.execute(
                        """
                        WITH dr AS (
                          SELECT employee_id FROM int_deferral_rate_state_accumulator_v2 WHERE simulation_year = ?
                        ), wf AS (
                          SELECT employee_id FROM int_employee_compensation_by_year WHERE simulation_year = ?
                        )
                        SELECT COUNT(*) FROM (
                          SELECT employee_id FROM dr INTERSECT SELECT employee_id FROM wf
                        )
                        """,
                        [year, year],
                    ).fetchone()[0]
                    contrib_rows, contrib_sum = conn.execute(
                        "SELECT COUNT(*), COALESCE(SUM(annual_contribution_amount), 0) FROM int_employee_contributions WHERE simulation_year = ?",
                        [year],
                    ).fetchone()
                    return (
                        int(dr_cnt),
                        int(comp_cnt),
                        int(overlap),
                        int(contrib_rows),
                        float(contrib_sum or 0.0),
                    )

                (
                    dr_cnt,
                    comp_cnt,
                    overlap_cnt,
                    contrib_rows,
                    contrib_sum,
                ) = self.db_manager.execute_with_retry(_contrib_guard)

                if dr_cnt > 0 and (
                    overlap_cnt == 0 or contrib_rows == 0 or contrib_sum == 0.0
                ):
                    print(
                        f"⚠️ Detected deferral state ({dr_cnt}) but no contribution output (rows={contrib_rows}, sum={contrib_sum:.2f}, overlap={overlap_cnt}). Rebuilding staging → compensation → deferral_state → contributions."
                    )
                    # Ensure Year 1 NH staging is present, then rebuild compensation and contributions
                    self.dbt_runner.execute_command(
                        [
                            "run",
                            "--select",
                            "int_new_hire_compensation_staging int_employee_compensation_by_year",
                        ],
                        simulation_year=year,
                        dbt_vars=self._dbt_vars,
                        stream_output=True,
                    )
                    self.dbt_runner.execute_command(
                        [
                            "run",
                            "--select",
                            "int_deferral_rate_state_accumulator_v2",
                        ],
                        simulation_year=year,
                        dbt_vars=self._dbt_vars,
                        stream_output=True,
                    )
                    self.dbt_runner.execute_command(
                        [
                            "run",
                            "--select",
                            "int_employee_contributions fct_workforce_snapshot",
                        ],
                        simulation_year=year,
                        dbt_vars=self._dbt_vars,
                        stream_output=True,
                    )

            # Registry updates after events/state accumulation
            if stage.name == WorkflowStage.EVENT_GENERATION:
                self.registry_manager.get_enrollment_registry().update_post_year(year)
            if stage.name == WorkflowStage.STATE_ACCUMULATION:
                self.registry_manager.get_deferral_registry().update_post_year(year)

            # Stage-level validation hook
            if stage.name in (
                WorkflowStage.STATE_ACCUMULATION,
                WorkflowStage.VALIDATION,
            ):
                dv_results = self.validator.validate_year_results(year)
                if fail_on_validation_error and any(
                    (not r.passed and r.severity.value == "error") for r in dv_results
                ):
                    raise PipelineStageError(
                        f"Validation errors detected for year {year}"
                    )

        # Reporting per year
        auditor = YearAuditor(self.db_manager, self.validator)
        report = auditor.generate_report(year)
        report.export_json(self.reports_dir / f"year_{year}.json")

        # Display detailed year audit (matching monolithic script)
        auditor.generate_detailed_year_audit(year)

        # Final sanity checks handled by reporting/validator

    def get_adaptive_batch_size(self) -> int:
        """Get current adaptive batch size for dbt operations"""
        if self.memory_manager:
            return self.memory_manager.get_current_batch_size()
        else:
            # Fallback to configured batch size or default
            optimization_config = getattr(self.config, 'optimization', None)
            if optimization_config:
                return optimization_config.batch_size
            return 1000  # Default batch size

    def get_memory_recommendations(self) -> List[Dict[str, Any]]:
        """Get current memory optimization recommendations"""
        if self.memory_manager:
            return self.memory_manager.get_recommendations()
        return []

    def get_memory_statistics(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics"""
        if self.memory_manager:
            return self.memory_manager.get_memory_statistics()
        return {
            "current": {"memory_mb": 0, "optimization_level": "unknown"},
            "stats": {},
            "monitoring_active": False
        }

    def _run_stage_models(self, stage: StageDefinition, year: int) -> None:
        if not stage.models:
            return

        # Try to use model-level parallelization if enabled and appropriate
        if (self.model_parallelization_enabled and
            self.parallel_execution_engine and
            self._should_use_model_parallelization(stage)):

            self._run_stage_with_model_parallelization(stage, year)
            return

        # Fallback to existing sequential/parallel execution logic
        self._run_stage_models_legacy(stage, year)

    def _should_use_model_parallelization(self, stage: StageDefinition) -> bool:
        """Determine if a stage should use model-level parallelization."""

        # Safety gate: DuckDB single-file databases do not support concurrent writer
        # processes. Running multiple dbt processes in parallel will contend on the
        # database file lock and fail. Detect this environment and disable
        # model-level parallelization entirely.
        try:
            db_path = getattr(self.db_manager, "db_path", None)
            if db_path and str(db_path).endswith(".duckdb"):
                return False
        except Exception:
            # If detection fails, fall through to conservative defaults below
            pass

        # Don't use for stages that require strict sequencing
        sequential_stages = {
            WorkflowStage.EVENT_GENERATION,
            WorkflowStage.STATE_ACCUMULATION
        }

        if stage.name in sequential_stages:
            # These stages may have some parallelizable models but need careful handling
            if self.parallelization_config.safety.validate_execution_safety:
                # Only use if validation passes
                validation = self.parallel_execution_engine.validate_stage_parallelization(stage.models)
                return validation.get("parallelizable", False) and validation.get("safety_score", 0) > 80
            return False

        # Use for other stages if they have multiple models
        return len(stage.models) > 1

    def _run_stage_with_model_parallelization(self, stage: StageDefinition, year: int) -> None:
        """Run stage using sophisticated model-level parallelization."""

        if self.verbose:
            print(f"   🚀 Using model-level parallelization for stage {stage.name.value}")

        # Create execution context
        import uuid
        context = ExecutionContext(
            simulation_year=year,
            dbt_vars=self._dbt_vars,
            stage_name=stage.name.value,
            execution_id=str(uuid.uuid4())[:8]
        )

        # Execute with parallelization engine
        result = self.parallel_execution_engine.execute_stage_with_parallelization(
            stage.models,
            context,
            enable_conditional_parallelization=self.parallelization_config.enable_conditional_parallelization
        )

        if self.verbose:
            print(f"   📊 Parallelization results:")
            print(f"      Success: {result.success}")
            print(f"      Models executed: {len(result.model_results)}")
            print(f"      Execution time: {result.execution_time:.1f}s")
            print(f"      Parallelism achieved: {result.parallelism_achieved}x")

            if result.errors:
                print(f"      Errors: {len(result.errors)}")
                for error in result.errors[:3]:  # Show first 3 errors
                    print(f"        - {error}")

        if not result.success:
            if result.errors:
                error_msg = "; ".join(result.errors[:2])  # Show first 2 errors
                raise PipelineStageError(
                    f"Model-level parallelization failed in stage {stage.name.value}: {error_msg}"
                )
            else:
                raise PipelineStageError(
                    f"Model-level parallelization failed in stage {stage.name.value}"
                )

    def _run_stage_models_legacy(self, stage: StageDefinition, year: int) -> None:
        """Legacy stage execution logic (sequential/basic parallel)."""

        # Run event generation and state accumulation sequentially to enforce order
        if stage.name in (
            WorkflowStage.EVENT_GENERATION,
            WorkflowStage.STATE_ACCUMULATION,
        ):
            setup = getattr(self.config, "setup", None)
            force_full_refresh = bool(
                isinstance(setup, dict)
                and setup.get("clear_tables")
                and setup.get("clear_mode", "all").lower() == "all"
            )

            for model in stage.models:
                # If building the snapshot, clear the year's rows first to avoid dbt pre-hook concurrency
                if model == "fct_workforce_snapshot":
                    try:
                        def _clear(conn):
                            conn.execute(
                                "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?",
                                [year],
                            )
                            return True

                        self.db_manager.execute_with_retry(_clear)
                        if self.verbose:
                            print(
                                f"   🧹 Cleared fct_workforce_snapshot for simulation_year={year} before rebuild"
                            )
                    except Exception:
                        # Non-fatal; proceed with dbt incremental upsert
                        pass
                selection = ["run", "--select", model]
                # Special case: always full-refresh models that have schema issues or self-references
                if (
                    model
                    in [
                        "int_workforce_snapshot_optimized",
                        "int_deferral_rate_escalation_events",
                    ]
                    or force_full_refresh
                ):
                    selection.append("--full-refresh")
                    if self.verbose:
                        if model == "int_workforce_snapshot_optimized":
                            reason = "schema compatibility"
                        elif model == "int_deferral_rate_escalation_events":
                            reason = "self-reference incremental"
                        else:
                            reason = "clear_mode=all"
                        print(
                            f"   🔄 Rebuilding {model} with --full-refresh ({reason}) for year {year}"
                        )
                res = self.dbt_runner.execute_command(
                    selection,
                    simulation_year=year,
                    dbt_vars=self._dbt_vars,
                    stream_output=True,
                )
                if not res.success:
                    raise PipelineStageError(
                        f"Dbt failed on model {model} in stage {stage.name.value} with code {res.return_code}"
                    )
            return

        if stage.parallel_safe and len(stage.models) > 1:
            results = self.dbt_runner.run_models(
                stage.models,
                parallel=True,
                simulation_year=year,
                dbt_vars=self._dbt_vars,
            )
            if not all(r.success for r in results):
                failed = [r for r in results if not r.success]
                raise PipelineStageError(
                    f"Some models failed in stage {stage.name.value}: {[f.command for f in failed]}"
                )
        else:
            # Run as a single selection for consistent dependency behavior
            selection = ["run", "--select", " ".join(stage.models)]
            # Optimization: Only use --full-refresh for FOUNDATION on first year or when clear_mode == 'all'
            if stage.name == WorkflowStage.FOUNDATION:
                setup = getattr(self.config, "setup", None)
                clear_mode = (
                    isinstance(setup, dict) and setup.get("clear_mode", "all").lower()
                ) or "all"
                if year == self.config.simulation.start_year or clear_mode == "all":
                    selection.append("--full-refresh")
                    if self.verbose:
                        print(
                            f"   🔄 Running {stage.name.value} with --full-refresh (year={year}, clear_mode={clear_mode})"
                        )
            res = self.dbt_runner.execute_command(
                selection,
                simulation_year=year,
                dbt_vars=self._dbt_vars,
                stream_output=True,
            )
            if not res.success:
                raise PipelineStageError(
                    f"Dbt failed in stage {stage.name.value} with code {res.return_code}"
                )

    def _maybe_clear_year_data(self, year: int) -> None:
        """Clear year-scoped data for idempotent re-runs when configured.

        Respects config.setup.clear_tables and config.setup.clear_table_patterns.
        Only deletes rows for the given simulation_year when the column exists.
        """
        setup = getattr(self.config, "setup", None)
        if not isinstance(setup, dict):
            return
        if not setup.get("clear_tables"):
            return
        # Respect clear_mode setting; skip year-level clears if full reset is requested
        clear_mode = setup.get("clear_mode", "all").lower()
        if clear_mode == "all":
            return
        patterns = setup.get("clear_table_patterns", ["int_", "fct_"])

        def _should_clear(name: str) -> bool:
            return any(name.startswith(p) for p in patterns)

        def _run(conn):
            tables = [
                r[0]
                for r in conn.execute(
                    """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main'
                ORDER BY table_name
                """
                ).fetchall()
            ]
            cleared = 0
            for t in tables:
                if not _should_clear(t):
                    continue
                # check if table has simulation_year column
                has_col = conn.execute(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='main' AND table_name = ? AND column_name = 'simulation_year'
                    LIMIT 1
                    """,
                    [t],
                ).fetchone()
                if has_col:
                    conn.execute(f"DELETE FROM {t} WHERE simulation_year = ?", [year])
                    cleared += 1
            return cleared

        cleared = self.db_manager.execute_with_retry(_run)
        if cleared:
            print(
                f"🧹 Cleared year {year} rows in {cleared} table(s) per setup.clear_table_patterns"
            )

    def _maybe_full_reset(self) -> None:
        """If configured, clear all rows from matching tables before yearly processing.

        Controlled by:
          setup.clear_tables: true/false
          setup.clear_mode: 'all' (default) or 'year'
          setup.clear_table_patterns: list of prefixes (default ['int_', 'fct_'])
        """
        setup = getattr(self.config, "setup", None)
        if not isinstance(setup, dict) or not setup.get("clear_tables"):
            return
        clear_mode = setup.get("clear_mode", "all").lower()
        if clear_mode != "all":
            return
        patterns = setup.get("clear_table_patterns", ["int_", "fct_"])

        def _should_clear(name: str) -> bool:
            return any(name.startswith(p) for p in patterns)

        def _run(conn):
            tables = [
                r[0]
                for r in conn.execute(
                    """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
                ORDER BY table_name
                """
                ).fetchall()
            ]
            cleared = 0
            for t in tables:
                if not _should_clear(t):
                    continue
                conn.execute(f"DELETE FROM {t}")
                cleared += 1
            return cleared

        cleared = self.db_manager.execute_with_retry(_run)
        if cleared:
            print(
                f"🧹 Full reset: cleared all rows in {cleared} table(s) per setup.clear_table_patterns"
            )

    def _clear_year_fact_rows(self, year: int) -> None:
        """Idempotency guard: remove current-year rows in core fact tables before rebuild.

        This avoids duplicate events/snapshots when event sequencing changes between runs.
        """

        def _run(conn):
            for table in (
                "fct_yearly_events",
                "fct_workforce_snapshot",
                "fct_employer_match_events",
            ):
                try:
                    conn.execute(
                        f"DELETE FROM {table} WHERE simulation_year = ?", [year]
                    )
                except Exception:
                    # Table may not exist yet; ignore
                    pass
            return True

        try:
            self.db_manager.execute_with_retry(_run)
        except Exception:
            pass

    def _define_year_workflow(self, year: int) -> List[StageDefinition]:
        # Align initialization with working runner: broader staging on first year
        if year == self.config.simulation.start_year:
            initialization_models = [
                "staging.*",
                "int_baseline_workforce",
            ]
        else:
            initialization_models = [
                "int_active_employees_prev_year_snapshot",
            ]

        # Epic E042 Fix: Conditional foundation models to preserve historical data
        if year == self.config.simulation.start_year:
            # Year 1: Include baseline workforce (created from census)
            # Ensure new-hire staging is built so NH_YYYY_* appear in compensation
            foundation_models = [
                "int_baseline_workforce",
                "int_new_hire_compensation_staging",
                "int_employee_compensation_by_year",
                "int_effective_parameters",
                "int_workforce_needs",
                "int_workforce_needs_by_level",
            ]
        else:
            # Year 2+: Skip baseline workforce (use incremental data preservation)
            # int_baseline_workforce is incremental and preserves Year 1 data
            foundation_models = [
                "int_employee_compensation_by_year",
                "int_effective_parameters",
                "int_workforce_needs",
                "int_workforce_needs_by_level",
            ]

        return [
            StageDefinition(
                name=WorkflowStage.INITIALIZATION,
                dependencies=[],
                models=initialization_models,
                validation_rules=["data_freshness_check"],
            ),
            StageDefinition(
                name=WorkflowStage.FOUNDATION,
                dependencies=[WorkflowStage.INITIALIZATION],
                models=foundation_models,
                validation_rules=["row_count_drift", "compensation_reasonableness"],
            ),
            StageDefinition(
                name=WorkflowStage.EVENT_GENERATION,
                dependencies=[WorkflowStage.FOUNDATION],
                # Match working runner ordering exactly for determinism
                models=[
                    # E049: Ensure synthetic baseline enrollment events are built in the first year
                    # so census deferral rates feed the state accumulator and snapshot participation.
                    *(
                        ["int_synthetic_baseline_enrollment_events"]
                        if year == self.config.simulation.start_year
                        else []
                    ),
                    "int_termination_events",
                    "int_hiring_events",
                    "int_new_hire_termination_events",
                    # Build employer eligibility after new-hire terminations to ensure flags are available
                    "int_employer_eligibility",
                    "int_hazard_promotion",
                    "int_hazard_merit",
                    "int_promotion_events",
                    "int_merit_events",
                    "int_eligibility_determination",
                    "int_voluntary_enrollment_decision",
                    "int_proactive_voluntary_enrollment",
                    "int_enrollment_events",
                    "int_deferral_rate_escalation_events",
                ],
                validation_rules=["hire_termination_ratio", "event_sequence"],
                parallel_safe=False,
            ),
            StageDefinition(
                name=WorkflowStage.STATE_ACCUMULATION,
                dependencies=[WorkflowStage.EVENT_GENERATION],
                models=[
                    "fct_yearly_events",
                    # Epic E068B: Build employee state accumulator early for O(1) state access
                    "int_employee_state_by_year",
                    # Build proration snapshot before contributions so all bases are prorated
                    "int_workforce_snapshot_optimized",
                    "int_enrollment_state_accumulator",
                    "int_deferral_rate_state_accumulator_v2",
                    "int_deferral_escalation_state_accumulator",
                    # Build employer contributions after contributions are computed to ensure proration
                    "int_employee_contributions",
                    "int_employer_core_contributions",
                    "int_employee_match_calculations",
                    "fct_employer_match_events",
                    "fct_workforce_snapshot",
                ],
                validation_rules=["state_consistency", "accumulator_integrity"],
                parallel_safe=False,  # Ensure proper sequencing of state models
            ),
            StageDefinition(
                name=WorkflowStage.VALIDATION,
                dependencies=[WorkflowStage.STATE_ACCUMULATION],
                models=[
                    "dq_employee_contributions_validation",
                ],
                validation_rules=["dq_suite"],
            ),
            StageDefinition(
                name=WorkflowStage.REPORTING,
                dependencies=[WorkflowStage.VALIDATION],
                models=[
                    # Future: Add reporting models here
                ],
                validation_rules=[],
            ),
        ]

    def _state_hash(self, year: int) -> str:
        # Lightweight placeholder hash combining year and timestamp
        return f"{year}:{datetime.utcnow().isoformat()}"

    def _verify_year_population(self, year: int) -> None:
        """Verify critical tables have rows for the given year; attempt one retry if empty."""

        def _counts(conn):
            snap = conn.execute(
                "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?",
                [year],
            ).fetchone()[0]
            events = conn.execute(
                "SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year = ?",
                [year],
            ).fetchone()[0]
            return int(snap), int(events)

        snap_count, event_count = self.db_manager.execute_with_retry(_counts)
        if snap_count == 0 and event_count > 0:
            # Attempt targeted rebuild of snapshot once
            try:
                def _clear(conn):
                    conn.execute(
                        "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?",
                        [year],
                    )
                    return True
                self.db_manager.execute_with_retry(_clear)
            except Exception:
                pass
            res = self.dbt_runner.execute_command(
                ["run", "--select", "fct_workforce_snapshot"],
                simulation_year=year,
                dbt_vars=self._dbt_vars,
                stream_output=True,
            )
            if not res.success:
                print(f"⚠️ Retry build of fct_workforce_snapshot failed for {year}")
            else:
                snap_count, _ = self.db_manager.execute_with_retry(_counts)
        if snap_count == 0:
            print(
                f"⚠️ fct_workforce_snapshot has 0 rows for {year}; verify upstream models and vars"
            )

    def _write_checkpoint(self, ckpt: WorkflowCheckpoint) -> None:
        path = self.checkpoints_dir / f"year_{ckpt.year}.json"
        with open(path, "w") as fh:
            json.dump(
                {
                    "year": ckpt.year,
                    "stage": ckpt.stage.value,
                    "timestamp": ckpt.timestamp,
                    "state_hash": ckpt.state_hash,
                },
                fh,
            )

    def _find_last_checkpoint(self) -> Optional[WorkflowCheckpoint]:
        files = sorted(self.checkpoints_dir.glob("year_*.json"))
        if not files:
            return None
        latest = files[-1]
        data = json.loads(latest.read_text())
        return WorkflowCheckpoint(
            year=int(data["year"]),
            stage=WorkflowStage(data["stage"]),
            timestamp=data["timestamp"],
            state_hash=data.get("state_hash", ""),
        )

    def _calculate_config_hash(self) -> str:
        """Calculate hash of current configuration for checkpoint validation"""
        import hashlib

        # Try to hash the configuration file
        config_path = Path("config/simulation_config.yaml")
        if config_path.exists():
            try:
                config_content = config_path.read_text()
                return hashlib.sha256(config_content.encode("utf-8")).hexdigest()
            except Exception:
                pass

        # Fallback: hash the config object's dump
        try:
            config_dict = self.config.model_dump()
            config_str = json.dumps(config_dict, sort_keys=True)
            return hashlib.sha256(config_str.encode("utf-8")).hexdigest()
        except Exception:
            return "unknown"

    def _log_compensation_parameters(self) -> None:
        """Log compensation parameters with enhanced visibility for user verification."""
        cola_rate = self._dbt_vars.get('cola_rate', self.config.compensation.cola_rate)
        merit_budget = self._dbt_vars.get('merit_budget', self.config.compensation.merit_budget)

        # Determine source of values
        cola_source = "from configuration" if 'cola_rate' in self._dbt_vars else "using default"
        merit_source = "from configuration" if 'merit_budget' in self._dbt_vars else "using default"

        print("\n🔎 Navigator Orchestrator compensation parameters:")
        print(f"   cola_rate: {cola_rate:.3f} ({cola_rate * 100:.1f}%) - {cola_source}")
        print(f"   merit_budget: {merit_budget:.3f} ({merit_budget * 100:.1f}%) - {merit_source}")

    def _validate_compensation_parameters(self) -> None:
        """Validate compensation parameters and log warnings for unusual values."""
        cola_rate = self._dbt_vars.get('cola_rate', self.config.compensation.cola_rate)
        merit_budget = self._dbt_vars.get('merit_budget', self.config.compensation.merit_budget)

        warnings = []

        # Validate cola_rate
        if cola_rate < 0 or cola_rate > 0.2:
            warnings.append(f"cola_rate ({cola_rate:.3f}) outside typical range [0.0, 0.2]")
        elif cola_rate > 0.1:
            warnings.append(f"cola_rate ({cola_rate:.3f}) is unusually high (>10%)")

        # Validate merit_budget
        if merit_budget < 0 or merit_budget > 0.2:
            warnings.append(f"merit_budget ({merit_budget:.3f}) outside typical range [0.0, 0.2]")
        elif merit_budget > 0.15:
            warnings.append(f"merit_budget ({merit_budget:.3f}) is unusually high (>15%)")

        # Log any warnings
        if warnings:
            print("\n⚠️ Compensation parameter validation warnings:")
            for warning in warnings:
                print(f"   - {warning}")
            print("   Please verify these values are intentional.")

    def _log_simulation_startup_summary(self, start_year: int, end_year: int) -> None:
        """Log a comprehensive summary of key simulation parameters at startup."""
        print(f"\n🚀 Starting multi-year simulation ({start_year} - {end_year})")
        print("📊 Key simulation parameters:")

        # Compensation parameters
        cola_rate = self._dbt_vars.get('cola_rate', self.config.compensation.cola_rate)
        merit_budget = self._dbt_vars.get('merit_budget', self.config.compensation.merit_budget)
        print(f"   Compensation:")
        print(f"     • COLA Rate: {cola_rate:.1%}")
        print(f"     • Merit Budget: {merit_budget:.1%}")

        # Growth and workforce parameters
        target_growth = self._dbt_vars.get('target_growth_rate', self.config.simulation.target_growth_rate)
        total_term_rate = self._dbt_vars.get('total_termination_rate', getattr(self.config.workforce, 'total_termination_rate', 0.12))
        nh_term_rate = self._dbt_vars.get('new_hire_termination_rate', getattr(self.config.workforce, 'new_hire_termination_rate', 0.25))
        print(f"   Workforce modeling:")
        print(f"     • Target Growth Rate: {target_growth:.1%}")
        print(f"     • Total Termination Rate: {total_term_rate:.1%}")
        print(f"     • New Hire Termination Rate: {nh_term_rate:.1%}")

        # Other key parameters
        random_seed = self._dbt_vars.get('random_seed', self.config.simulation.random_seed)
        print(f"   Other settings:")
        print(f"     • Random Seed: {random_seed}")
        print(f"     • Years: {end_year - start_year + 1} ({start_year}-{end_year})")

        print("")

    def update_compensation_parameters(self, *, cola_rate: Optional[float] = None, merit_budget: Optional[float] = None) -> None:
        """Update compensation parameters during runtime if needed.

        Args:
            cola_rate: New COLA rate (optional)
            merit_budget: New merit budget (optional)
        """
        updated = False

        if cola_rate is not None:
            if cola_rate < 0 or cola_rate > 1:
                raise ValueError(f"cola_rate must be between 0 and 1, got {cola_rate}")
            self._dbt_vars['cola_rate'] = cola_rate
            self.config.compensation.cola_rate = cola_rate
            updated = True
            print(f"✓ Updated cola_rate to {cola_rate:.3f} ({cola_rate * 100:.1f}%)")

        if merit_budget is not None:
            if merit_budget < 0 or merit_budget > 1:
                raise ValueError(f"merit_budget must be between 0 and 1, got {merit_budget}")
            self._dbt_vars['merit_budget'] = merit_budget
            self.config.compensation.merit_budget = merit_budget
            updated = True
            print(f"✓ Updated merit_budget to {merit_budget:.3f} ({merit_budget * 100:.1f}%)")

        if updated:
            # Re-validate after updates
            self._validate_compensation_parameters()
            # Force rebuild of parameter models to ensure changes take effect
            print("🔄 Rebuilding parameter models to apply changes...")
            self._rebuild_parameter_models()

    def _rebuild_parameter_models(self) -> None:
        """Force rebuild parameter models when compensation values change.

        This is necessary because int_effective_parameters is materialized as a table
        and needs --full-refresh to pick up new parameter values from config.
        """
        try:
            # Get current simulation year from config or use start year
            current_year = getattr(self.config.simulation, 'start_year', 2025)

            print("   📋 Rebuilding int_effective_parameters with --full-refresh")
            res = self.dbt_runner.execute_command(
                ["run", "--select", "int_effective_parameters", "--full-refresh"],
                simulation_year=current_year,
                dbt_vars=self._dbt_vars,
                stream_output=True
            )

            if res.success:
                print("   ✅ int_effective_parameters rebuilt successfully")
            else:
                print(f"   ❌ Failed to rebuild int_effective_parameters: {res.return_code}")

            # Also rebuild merit events to ensure they use new parameters
            print("   📋 Rebuilding int_merit_events with new parameters")
            merit_res = self.dbt_runner.execute_command(
                ["run", "--select", "int_merit_events", "--full-refresh"],
                simulation_year=current_year,
                dbt_vars=self._dbt_vars,
                stream_output=True
            )

            if merit_res.success:
                print("   ✅ int_merit_events rebuilt successfully")
            else:
                print(f"   ❌ Failed to rebuild int_merit_events: {merit_res.return_code}")

        except Exception as e:
            print(f"   ⚠️ Error during parameter model rebuild: {e}")
            print("   Manual rebuild may be required: dbt run --select int_effective_parameters int_merit_events --full-refresh")
