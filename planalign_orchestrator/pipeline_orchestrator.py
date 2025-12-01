#!/usr/bin/env python3
"""
Pipeline Orchestration Engine

Coordinates config, dbt execution, registries, validation, and reporting for
multi-year simulations with basic checkpoint/restart support.

Refactored to use modular pipeline components (Story S072-06).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
import time

from .adaptive_memory_manager import AdaptiveMemoryManager, create_adaptive_memory_manager, OptimizationLevel
from .checkpoint_manager import CheckpointManager
from .config import SimulationConfig, to_dbt_vars, PolarsEventSettings, get_database_path
from .dbt_runner import DbtResult, DbtRunner
from .recovery_orchestrator import RecoveryOrchestrator
from .registries import RegistryManager
from .reports import MultiYearReporter, MultiYearSummary, YearAuditor
from .observability import ObservabilityManager
from .utils import DatabaseConnectionManager, ExecutionMutex, time_block
from .validation import DataValidator

# Import modular pipeline components
from .pipeline.workflow import WorkflowBuilder, WorkflowStage, StageDefinition, WorkflowCheckpoint
from .pipeline.state_manager import StateManager
from .pipeline.data_cleanup import DataCleanupManager
from .pipeline.hooks import HookManager
from .pipeline.year_executor import YearExecutor
from .pipeline.event_generation_executor import EventGenerationExecutor

# Import Polars cohort generation (E077)
from .polars_integration import execute_polars_cohort_generation

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
        checkpoints_dir: Path | str = Path(".planalign_checkpoints"),
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

        # Initialize modular pipeline components (Story S072-06)
        self.workflow_builder = WorkflowBuilder()
        self.state_manager = StateManager(
            db_manager=db_manager,
            dbt_runner=dbt_runner,
            config=config,
            checkpoints_dir=checkpoints_dir,
            verbose=verbose
        )
        self.cleanup_manager = DataCleanupManager(db_manager=db_manager, verbose=verbose)
        self.hook_manager = HookManager(verbose=verbose)

        # Initialize event generation executor
        self.event_generation_executor = EventGenerationExecutor(
            config=config,
            dbt_runner=dbt_runner,
            db_manager=db_manager,
            dbt_vars=self._dbt_vars,
            event_shards=self.event_shards,
            verbose=verbose
        )

        # Initialize year executor with optional parallelization support
        parallel_execution_engine = getattr(self, 'parallel_execution_engine', None) if MODEL_PARALLELIZATION_AVAILABLE else None
        model_parallelization_enabled = getattr(self, 'model_parallelization_enabled', False)
        parallelization_config = getattr(self, 'parallelization_config', None)

        self.year_executor = YearExecutor(
            config=config,
            dbt_runner=dbt_runner,
            db_manager=db_manager,
            dbt_vars=self._dbt_vars,
            dbt_threads=self.dbt_threads,
            event_shards=self.event_shards,
            verbose=verbose,
            parallel_execution_engine=parallel_execution_engine,
            model_parallelization_enabled=model_parallelization_enabled,
            parallelization_config=parallelization_config
        )

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
                from .logger import ProductionLogger
                logger = ProductionLogger("ModelParallelization")

                manifest_path = Path("dbt/target/manifest.json")
                if not manifest_path.exists():
                    if self.verbose:
                        print("⚠️ dbt manifest not found - run 'dbt compile' first")
                        print("   Model parallelization will not be available")
                    self.model_parallelization_enabled = False
                    self.parallel_execution_engine = None
                    self.parallelization_config = None
                    self.resource_manager = None
                    return

                # Initialize dependency analyzer
                self.dependency_analyzer = ModelDependencyAnalyzer(str(manifest_path))

                # Initialize resource manager if available
                if resource_mgmt_config and RESOURCE_MANAGEMENT_AVAILABLE:
                    self.resource_manager = self._create_resource_manager(resource_mgmt_config)
                else:
                    self.resource_manager = None

                # Initialize parallel execution engine
                self.parallel_execution_engine = ParallelExecutionEngine(
                    dbt_runner=self.dbt_runner,
                    dependency_analyzer=self.dependency_analyzer,
                    max_workers=parallelization_config.max_parallel_models,
                    logger=logger,
                    resource_manager=self.resource_manager
                )

                self.model_parallelization_enabled = True
                self.parallelization_config = parallelization_config

                if self.verbose:
                    print("⚡ Model-level parallelization enabled")
                    print(f"   Max parallel models: {parallelization_config.max_parallel_models}")
                    print(f"   Dependency-aware scheduling: {parallelization_config.dependency_aware_scheduling}")
                    if self.resource_manager:
                        print("   Advanced resource management: enabled")
            else:
                self.model_parallelization_enabled = False
                self.parallel_execution_engine = None
                self.parallelization_config = None
                self.resource_manager = None

        except Exception as e:
            # Fallback to sequential execution
            self.model_parallelization_enabled = False
            self.parallel_execution_engine = None
            self.parallelization_config = None
            self.resource_manager = None
            if self.verbose:
                print(f"⚠️ Failed to initialize model parallelization: {e}")
                print("   Falling back to sequential execution")

    def _create_resource_manager(self, config) -> Optional[ResourceManager]:
        """Create resource manager with configuration"""
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

            if self.verbose:
                print(f"📊 Resource Manager initialized:")
                print(f"   Memory limit: {config.memory_limit_mb}MB")
                print(f"   CPU limit: {config.cpu_limit_percent}%")
                print(f"   Auto GC on pressure: {config.enable_gc_on_pressure}")
                print(f"   Connection pooling: {config.enable_connection_pooling} (pool size: {config.connection_pool_size})")

            return resource_manager

        except Exception as e:
            if self.verbose:
                print(f"⚠️ Failed to create resource manager: {e}")
            return None

    def _setup_hazard_cache_manager(self) -> None:
        """Initialize E068D hazard cache manager for automatic change detection"""
        try:
            from .hazard_cache_manager import HazardCacheManager

            # Extract dbt project path from runner
            dbt_project_path = getattr(self.dbt_runner, 'project_dir', Path('dbt'))

            self.hazard_cache_manager = HazardCacheManager(
                db_manager=self.db_manager,
                dbt_runner=self.dbt_runner,
                dbt_project_path=dbt_project_path,
                verbose=self.verbose
            )

            if self.verbose:
                print("🗄️ E068D Hazard Cache Manager initialized")
                print(f"   SHA256 parameter fingerprinting enabled")
                print(f"   Automatic cache invalidation on parameter changes")

        except ImportError:
            self.hazard_cache_manager = None
            if self.verbose:
                print("ℹ️ E068D Hazard Cache Manager not available (module not found)")
        except Exception as e:
            self.hazard_cache_manager = None
            if self.verbose:
                print(f"⚠️ Failed to initialize Hazard Cache Manager: {e}")

    def _setup_performance_monitoring(self) -> None:
        """Initialize E068E DuckDB performance monitoring system"""
        try:
            from .duckdb_performance_monitor import DuckDBPerformanceMonitor

            self.duckdb_performance_monitor = DuckDBPerformanceMonitor(
                db_manager=self.db_manager,
                reports_dir=self.reports_dir / "duckdb_performance",
                verbose=self.verbose
            )

            if self.verbose:
                print("📊 E068E DuckDB Performance Monitor initialized")
                print(f"   Query profiling enabled")
                print(f"   Reports directory: {self.reports_dir / 'duckdb_performance'}")

            # Setup hybrid performance monitoring for E068G integration
            self._setup_hybrid_performance_monitoring()

        except ImportError:
            self.duckdb_performance_monitor = None
            if self.verbose:
                print("ℹ️ E068E DuckDB Performance Monitor not available (module not found)")
        except Exception as e:
            self.duckdb_performance_monitor = None
            if self.verbose:
                print(f"⚠️ Failed to initialize DuckDB Performance Monitor: {e}")

    def _setup_hybrid_performance_monitoring(self) -> None:
        """Setup hybrid performance monitoring for E068G"""
        try:
            from .hybrid_performance_monitor import HybridPerformanceMonitor

            self.hybrid_performance_monitor = HybridPerformanceMonitor(
                reports_dir=self.reports_dir / "hybrid_performance",
                verbose=self.verbose
            )

            if self.verbose:
                print("📊 E068G Hybrid Performance Monitor initialized")
        except ImportError:
            self.hybrid_performance_monitor = None
        except Exception as e:
            self.hybrid_performance_monitor = None
            if self.verbose:
                print(f"⚠️ Failed to initialize Hybrid Performance Monitor: {e}")

    def _cleanup_resources(self) -> None:
        """Cleanup resource management components"""
        try:
            # Cleanup database connection pool (E079 Phase 3A)
            if hasattr(self, 'db_manager') and self.db_manager:
                try:
                    self.db_manager.close_all()
                    if self.verbose:
                        print("✅ Database connection pool closed")
                except Exception as e:
                    if self.verbose:
                        print(f"⚠️ Error closing database connection pool: {e}")

            # Cleanup parallel execution engine
            if hasattr(self, 'parallel_execution_engine') and self.parallel_execution_engine:
                try:
                    self.parallel_execution_engine.shutdown()
                    if self.verbose:
                        print("✅ Parallel execution engine shutdown complete")
                except Exception as e:
                    if self.verbose:
                        print(f"⚠️ Error during parallel execution engine shutdown: {e}")

            # Cleanup resource manager
            if hasattr(self, 'resource_manager') and self.resource_manager:
                try:
                    # Get final resource statistics
                    final_stats = self.resource_manager.get_resource_status()
                    if self.verbose:
                        print(f"📊 Final resource status:")
                        print(f"   Memory: {final_stats['memory']['usage_mb']:.0f}MB")
                        print(f"   CPU: {final_stats['cpu']['current_percent']:.1f}%")

                    self.resource_manager.cleanup()
                    if self.verbose:
                        print("✅ Resource manager cleanup complete")
                except Exception as e:
                    if self.verbose:
                        print(f"⚠️ Error during resource manager cleanup: {e}")

        except Exception as e:
            if self.verbose:
                print(f"⚠️ Error during resource cleanup: {e}")

    def __del__(self):
        """Cleanup on deletion"""
        try:
            self._cleanup_resources()
        except Exception:
            pass

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
            ckpt = self.state_manager.find_last_checkpoint()
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
            # Use database-specific lock to allow parallel execution of different scenarios
            # Each scenario has its own database, so they can run concurrently
            db_path = getattr(self.db_manager, "db_path", "default")
            lock_name = f"planalign_{hash(str(db_path)) % 10**8}"
            if self.verbose:
                print(f"🔒 Acquiring execution lock: {lock_name} (db: {db_path})")
            with ExecutionMutex(lock_name):
                # Optional one-time full reset before the yearly loop
                self.state_manager.maybe_full_reset()
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
                                self.state_manager.write_checkpoint(
                                    WorkflowCheckpoint(
                                        year,
                                        WorkflowStage.CLEANUP,
                                        datetime.utcnow().isoformat(),
                                        self.state_manager.state_hash(year),
                                    )
                                )
                        else:
                            # Legacy checkpoint system
                            self.state_manager.write_checkpoint(
                                WorkflowCheckpoint(
                                    year,
                                    WorkflowStage.CLEANUP,
                                    datetime.utcnow().isoformat(),
                                    self.state_manager.state_hash(year),
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

    def _execute_year_workflow(
        self, year: int, *, fail_on_validation_error: bool
    ) -> None:
        """Execute workflow for a single simulation year using modular components."""
        # Build year workflow using WorkflowBuilder
        workflow = self.workflow_builder.build_year_workflow(
            year=year,
            start_year=self.config.simulation.start_year
        )

        # Optional: clear existing rows for this year based on config.setup
        self.state_manager.maybe_clear_year_data(year)

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

            # E077: Generate Polars cohorts AFTER FOUNDATION stage completes
            if stage.name == WorkflowStage.FOUNDATION:
                # First, execute the FOUNDATION stage using standard logic (handled below)
                pass

            # E068G: Use hybrid event generation for EVENT_GENERATION stage
            if stage.name == WorkflowStage.EVENT_GENERATION:
                try:
                    hybrid_result = self.event_generation_executor.execute_hybrid_event_generation([year])
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

            # E068C: Use YearExecutor for supported stages
            elif stage.name in (WorkflowStage.STATE_ACCUMULATION,):
                stage_result = self.year_executor.execute_workflow_stage(stage, year)
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
                                self.year_executor.execute_workflow_stage(stage, year)
                    else:
                        with time_block(f"stage:{stage.name.value}"):
                            self.year_executor.execute_workflow_stage(stage, year)

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
                            self.year_executor.execute_workflow_stage(stage, year)
                else:
                    with time_block(f"stage:{stage.name.value}"):
                        self.year_executor.execute_workflow_stage(stage, year)

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

            # Run stage validation using existing logic
            self._run_stage_validation(stage, year, fail_on_validation_error)

            # E077: Generate Polars cohorts AFTER FOUNDATION stage completes and validates
            if stage.name == WorkflowStage.FOUNDATION and self.config.is_cohort_engine_enabled():
                try:
                    if self.verbose:
                        print(f"   ⚡ E077: Generating Polars cohorts for year {year}...")

                    scenario_id = getattr(self.config, 'scenario_id', 'default') or 'default'
                    cohort_output_dir = self.config.get_cohort_output_dir()

                    cohorts = execute_polars_cohort_generation(
                        config=self.config,
                        simulation_year=year,
                        scenario_id=scenario_id,
                        output_dir=cohort_output_dir
                    )

                    if self.verbose:
                        print(f"   ✓ Polars cohorts generated successfully")
                        print(f"      Output: {cohort_output_dir / scenario_id}_{year}")

                except Exception as e:
                    # Log error but don't fail - fall back to SQL-based hiring
                    if self.verbose:
                        print(f"   ⚠️ Polars cohort generation failed: {e}")
                        print("      Falling back to SQL-based hiring")

    def _run_stage_validation(
        self, stage: StageDefinition, year: int, fail_on_validation_error: bool
    ) -> None:
        """Run validation checks for a completed workflow stage."""
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
        elif stage.name == WorkflowStage.EVENT_GENERATION:

            def _ev_chk(conn):
                hires = conn.execute(
                    "SELECT COUNT(*) FROM int_hiring_events WHERE simulation_year = ?",
                    [year],
                ).fetchone()[0]
                demand = conn.execute(
                    "SELECT COALESCE(SUM(hires_needed),0) FROM int_workforce_needs_by_level WHERE simulation_year = ?",
                    [year],
                ).fetchone()[0]
                return int(hires), int(demand)

            hires_cnt, demand_cnt = self.db_manager.execute_with_retry(_ev_chk)
            print(f"   📊 Event generation validation for year {year}:")
            print(f"      int_hiring_events: {hires_cnt} rows")
            print(f"      hiring_demand (sum_by_level): {demand_cnt}")
            if hires_cnt == 0 and demand_cnt > 0:
                raise PipelineStageError(
                    f"CRITICAL: Hiring demand={demand_cnt} but 0 int_hiring_events rows for {year}. Check hiring logic."
                )

        # Verify population (snapshots and events exist) after STATE_ACCUMULATION
        elif stage.name == WorkflowStage.STATE_ACCUMULATION:
            self.state_manager.verify_year_population(year)

    def get_adaptive_batch_size(self) -> int:
        """Get current adaptive batch size from memory manager"""
        if hasattr(self, 'memory_manager') and self.memory_manager:
            return self.memory_manager.get_current_batch_size()
        return 1000  # Default fallback

    def get_memory_recommendations(self) -> List[Dict[str, Any]]:
        """Get memory optimization recommendations"""
        if hasattr(self, 'memory_manager') and self.memory_manager:
            return self.memory_manager.get_recommendations()
        return []

    def get_memory_statistics(self) -> Dict[str, Any]:
        """Get memory usage statistics"""
        if hasattr(self, 'memory_manager') and self.memory_manager:
            return self.memory_manager.get_memory_statistics()
        return {}

    def _calculate_config_hash(self) -> str:
        """Calculate hash of current configuration for checkpoint validation"""
        import hashlib

        # Try to hash the configuration file
        config_path = Path("config/simulation_config.yaml")
        if config_path.exists():
            try:
                content = config_path.read_bytes()
                return hashlib.sha256(content).hexdigest()[:16]
            except Exception:
                pass

        # Fallback: hash the config object
        try:
            config_str = json.dumps(self.config.model_dump(), sort_keys=True)
            return hashlib.sha256(config_str.encode()).hexdigest()[:16]
        except Exception:
            return "unknown"

    def _log_compensation_parameters(self) -> None:
        """Log compensation parameters for enhanced visibility"""
        try:
            comp = self.config.compensation
            print("\n💰 Compensation Parameters:")
            print(f"   Base COLA Rate: {comp.base_cola_rate:.1%}")
            print(f"   Merit Budget: {comp.base_merit_budget:.1%}")
            print(f"   Promotion Lift: {comp.promotion_lift_pct:.1%}")
        except Exception:
            pass

    def _validate_compensation_parameters(self) -> None:
        """Validate compensation parameters are within reasonable ranges"""
        try:
            comp = self.config.compensation
            warnings = []

            if comp.base_cola_rate < 0.0 or comp.base_cola_rate > 0.1:
                warnings.append(f"COLA rate {comp.base_cola_rate:.1%} is outside normal range [0%, 10%]")

            if comp.base_merit_budget < 0.0 or comp.base_merit_budget > 0.15:
                warnings.append(f"Merit budget {comp.base_merit_budget:.1%} is outside normal range [0%, 15%]")

            if comp.promotion_lift_pct < 0.0 or comp.promotion_lift_pct > 0.25:
                warnings.append(f"Promotion lift {comp.promotion_lift_pct:.1%} is outside normal range [0%, 25%]")

            if warnings and self.verbose:
                print("\n⚠️ Compensation Parameter Warnings:")
                for warning in warnings:
                    print(f"   {warning}")
        except Exception:
            pass

    def _log_simulation_startup_summary(self, start_year: int, end_year: int) -> None:
        """Enhanced simulation startup logging"""
        print(f"\n🚀 PlanWise Navigator Multi-Year Simulation")
        print(f"   Period: {start_year} → {end_year} ({end_year - start_year + 1} years)")
        print(f"   Random Seed: {self.config.simulation.random_seed}")
        print(f"   Target Growth: {self.config.simulation.target_growth_rate:.1%}")

    def update_compensation_parameters(
        self, *, cola_rate: Optional[float] = None, merit_budget: Optional[float] = None
    ) -> None:
        """Update compensation parameters dynamically (Streamlit integration)"""
        if cola_rate is not None:
            self.config.compensation.base_cola_rate = cola_rate
        if merit_budget is not None:
            self.config.compensation.base_merit_budget = merit_budget

        # Rebuild parameter models to reflect changes
        self._rebuild_parameter_models()

    def _rebuild_parameter_models(self) -> None:
        """Rebuild parameter models after dynamic updates"""
        try:
            # Update dbt vars with new parameters
            self._dbt_vars = to_dbt_vars(self.config)

            # Rebuild int_effective_parameters
            result = self.dbt_runner.execute_command(
                ["run", "--select", "int_effective_parameters"],
                dbt_vars=self._dbt_vars,
                stream_output=True,
            )
            if result.success:
                print("✅ Parameter models rebuilt successfully")
            else:
                print(f"⚠️ Failed to rebuild parameter models: {result.return_code}")
        except Exception as e:
            print(f"⚠️ Error rebuilding parameter models: {e}")
