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

from .checkpoint_manager import CheckpointManager
from .config import SimulationConfig, to_dbt_vars, get_database_path
from .orchestrator_setup import (
    setup_memory_manager,
    setup_parallelization,
    setup_hazard_cache,
    setup_performance_monitor,
)
from .dbt_runner import DbtResult, DbtRunner
from .recovery_orchestrator import RecoveryOrchestrator
from .registries import RegistryManager
from .reports.data_models import MultiYearSummary
from .reports.multi_year_reporter import MultiYearReporter
from .reports.year_auditor import YearAuditor
from .observability import ObservabilityManager
from .utils import DatabaseConnectionManager, ExecutionMutex, time_block
from .validation import DataValidator

# Import modular pipeline components
from .pipeline.workflow import WorkflowBuilder, WorkflowStage, StageDefinition, WorkflowCheckpoint
from .pipeline.state_manager import StateManager
from .pipeline.data_cleanup import DataCleanupManager
from .pipeline.hooks import HookManager, HookType
from .pipeline.year_executor import YearExecutor
from .pipeline.event_generation_executor import EventGenerationExecutor
from .pipeline.stage_validator import StageValidator

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

        # E068G: Event generation mode is always SQL
        self.event_generation_mode = "sql"

        # Log E068C threading configuration
        if self.verbose:
            print(f"🧵 E068C Threading Configuration:")
            print(f"   dbt_threads: {self.dbt_threads}")
            print(f"   event_shards: {self.event_shards}")
            print(f"   max_parallel_years: {self.max_parallel_years}")
            print(f"🔄 Event Generation Mode: SQL")

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
        self.memory_manager = setup_memory_manager(
            config=self.config,
            reports_dir=self.reports_dir,
            verbose=self.verbose
        )

        # S067-02: Model-level parallelization setup
        (
            self.parallel_execution_engine,
            self.parallelization_config,
            self.resource_manager,
            self.dependency_analyzer,
            self.model_parallelization_enabled,
        ) = setup_parallelization(
            config=self.config,
            dbt_runner=self.dbt_runner,
            verbose=self.verbose
        )

        # E068D: Initialize hazard cache manager for automatic change detection
        self.hazard_cache_manager = setup_hazard_cache(
            db_manager=self.db_manager,
            dbt_runner=self.dbt_runner,
            verbose=self.verbose
        )

        # E068E: Initialize DuckDB performance monitoring system
        self.duckdb_performance_monitor = setup_performance_monitor(
            db_manager=self.db_manager,
            reports_dir=self.reports_dir,
            verbose=self.verbose
        )

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

        # Initialize stage validator (Story S034 - Orchestrator Modularization Phase 2)
        self.stage_validator = StageValidator(
            db_manager=db_manager,
            config=config,
            state_manager=self.state_manager,
            verbose=verbose
        )

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
        self.year_executor = YearExecutor(
            config=config,
            dbt_runner=dbt_runner,
            db_manager=db_manager,
            dbt_vars=self._dbt_vars,
            dbt_threads=self.dbt_threads,
            start_year=config.simulation.start_year,
            event_shards=self.event_shards,
            verbose=verbose,
            parallel_execution_engine=self.parallel_execution_engine,
            model_parallelization_enabled=self.model_parallelization_enabled,
            parallelization_config=self.parallelization_config
        )

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
        dry_run: bool = False,
    ) -> MultiYearSummary:
        start = start_year or self.config.simulation.start_year
        end = end_year or self.config.simulation.end_year

        # Execute PRE_SIMULATION hooks (e.g., self-healing database initialization)
        self.hook_manager.execute_hooks(
            HookType.PRE_SIMULATION,
            {"start_year": start, "end_year": end, "dry_run": dry_run}
        )

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
                                    year, fail_on_validation_error=fail_on_validation_error, dry_run=dry_run
                                )
                        else:
                            self._execute_year_workflow(
                                year, fail_on_validation_error=fail_on_validation_error, dry_run=dry_run
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
                "event_generation_mode": "sql",
            }

        return summary

    def _execute_year_workflow(
        self, year: int, *, fail_on_validation_error: bool, dry_run: bool = False
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
            # E026: Drop seed tables with schema mismatch before loading
            # This prevents DuckDB CSV sniffing errors when seed files gain new columns
            cleanup_manager = DataCleanupManager(self.db_manager, verbose=self.verbose)
            dropped = cleanup_manager.drop_seed_tables_with_schema_mismatch()
            if dropped:
                logging.getLogger(__name__).info(
                    f"Dropped {len(dropped)} seed tables with schema mismatch: {dropped}"
                )
                if self.verbose:
                    print(f"   🔄 Dropped {len(dropped)} seed table(s) with outdated schema")

            seed_res = self.dbt_runner.execute_command(["seed"], stream_output=True)
            if not seed_res.success:
                raise PipelineStageError(
                    f"Dbt seed failed with code {seed_res.return_code}"
                )
            self._seeded = True

        # FIX: For start_year, explicitly run staging models before foundation
        # This ensures stg_census_data is built with correct census_parquet_path
        if year == self.config.simulation.start_year:
            print("   📦 Building staging models for start year...")
            staging_res = self.dbt_runner.execute_command(
                ["run", "--select", "staging.*"],
                simulation_year=year,
                dbt_vars=self._dbt_vars,
                stream_output=True
            )
            if not staging_res.success:
                raise PipelineStageError(
                    f"Staging models failed with code {staging_res.return_code}"
                )

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

            # E068G: Use event generation for EVENT_GENERATION stage
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

            # Run stage validation using StageValidator (skip in dry-run mode)
            if not dry_run:
                self.stage_validator.validate_stage(stage, year, fail_on_validation_error)

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
