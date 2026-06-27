#!/usr/bin/env python3
"""
Pipeline Orchestration Engine

Coordinates config, dbt execution, registries, validation, and reporting for
multi-year simulations.

Refactored to use modular pipeline components (Story S072-06).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import time

from .config import SimulationConfig, to_dbt_vars
from .orchestrator_setup import (
    setup_memory_manager,
    setup_parallelization,
    setup_hazard_cache,
    setup_performance_monitor,
)
from .dbt_runner import DbtRunner
from .registries import RegistryManager
from .reports.data_models import MultiYearSummary
from .reports.multi_year_reporter import MultiYearReporter
from .observability import ObservabilityManager
from .utils import DatabaseConnectionManager, ExecutionMutex, time_block
from .validation import DataValidator
from config.constants import (
    COL_EVENT_TYPE,
    COL_SIMULATION_YEAR,
    KEY_SUCCESS,
    TABLE_FCT_YEARLY_EVENTS,
)

# Import modular pipeline components
from .pipeline.workflow import (
    WorkflowBuilder,
    WorkflowStage,
    StageDefinition,
)
from .pipeline.state_manager import StateManager
from .pipeline.data_cleanup import DataCleanupManager
from .pipeline.hooks import HookManager, HookType
from .pipeline.telemetry_emitter import TelemetryEmitter
from .pipeline.year_executor import YearExecutor
from .pipeline.event_generation_executor import EventGenerationExecutor
from .pipeline.stage_validator import StageValidator

# Import model parallelization components
try:
    # Imported for availability detection only (sets the *_AVAILABLE flags below).
    from .parallel_execution_engine import ParallelExecutionEngine  # noqa: F401
    from .parallel_execution_engine import ExecutionContext  # noqa: F401
    from .model_dependency_analyzer import ModelDependencyAnalyzer  # noqa: F401
    from .resource_manager import ResourceManager  # noqa: F401
    from .logger import ProductionLogger  # noqa: F401

    MODEL_PARALLELIZATION_AVAILABLE = True
    RESOURCE_MANAGEMENT_AVAILABLE = True
except ImportError:
    MODEL_PARALLELIZATION_AVAILABLE = False
    RESOURCE_MANAGEMENT_AVAILABLE = False


logger = logging.getLogger(__name__)


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
        verbose: bool = False,
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
        logger.debug(
            "E068C Threading Configuration: dbt_threads=%d, event_shards=%d, max_parallel_years=%d",
            self.dbt_threads,
            self.event_shards,
            self.max_parallel_years,
        )
        logger.debug("Event Generation Mode: SQL")

        # Enhanced compensation parameter visibility
        self._log_compensation_parameters()
        self._validate_compensation_parameters()

        self.reports_dir = Path(reports_dir)
        self._seeded = False

        # Initialize observability (structured logs + performance metrics + run summary)
        self.observability: Optional[ObservabilityManager]
        try:
            self.observability = ObservabilityManager(log_level="INFO")
            # Record configuration for audit trail
            # BUG FIX #235: Use mode='json' to convert Decimal values to floats for JSON serialization
            # Without this, json.dumps() fails with: TypeError: Object of type Decimal is not JSON serializable
            try:
                self.observability.set_configuration(
                    self.config.model_dump(mode="json")
                )
            except Exception:
                pass
            logger.debug("Observability run_id: %s", self.observability.get_run_id())
        except Exception:
            # Proceed without observability if initialization fails
            self.observability = None

        # S063-08: Adaptive Memory Management
        self.memory_manager = setup_memory_manager(
            config=self.config, reports_dir=self.reports_dir, verbose=self.verbose
        )

        # S067-02: Model-level parallelization setup
        (
            self.parallel_execution_engine,
            self.parallelization_config,
            self.resource_manager,
            self.dependency_analyzer,
            self.model_parallelization_enabled,
        ) = setup_parallelization(
            config=self.config, dbt_runner=self.dbt_runner, verbose=self.verbose
        )

        # E068D: Initialize hazard cache manager for automatic change detection
        self.hazard_cache_manager = setup_hazard_cache(
            config=self.config, dbt_runner=self.dbt_runner, verbose=self.verbose
        )

        # E068E: Initialize DuckDB performance monitoring system
        self.duckdb_performance_monitor = setup_performance_monitor(
            db_manager=self.db_manager,
            reports_dir=self.reports_dir,
            verbose=self.verbose,
        )

        # Initialize modular pipeline components (Story S072-06)
        self.workflow_builder = WorkflowBuilder()
        self.state_manager = StateManager(
            db_manager=db_manager, dbt_runner=dbt_runner, config=config, verbose=verbose
        )
        self.cleanup_manager = DataCleanupManager(
            db_manager=db_manager, verbose=verbose
        )
        self.hook_manager = HookManager(verbose=verbose)

        # Feature 094: structured telemetry for PlanAlign Studio (env-gated)
        self.telemetry_emitter = TelemetryEmitter(db_manager=db_manager)
        if self.telemetry_emitter.enabled:
            self.telemetry_emitter.register(self.hook_manager)

        # Initialize stage validator (Story S034 - Orchestrator Modularization Phase 2)
        self.stage_validator = StageValidator(
            db_manager=db_manager,
            config=config,
            state_manager=self.state_manager,
            verbose=verbose,
        )

        # Initialize event generation executor
        self.event_generation_executor = EventGenerationExecutor(
            config=config,
            dbt_runner=dbt_runner,
            db_manager=db_manager,
            dbt_vars=self._dbt_vars,
            event_shards=self.event_shards,
            verbose=verbose,
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
            parallelization_config=self.parallelization_config,
        )

    def _cleanup_resources(self) -> None:
        """Cleanup resource management components"""
        try:
            # Cleanup database connection pool (E079 Phase 3A)
            if hasattr(self, "db_manager") and self.db_manager:
                try:
                    self.db_manager.close_all()
                    logger.info("Database connection pool closed")
                except Exception as e:
                    logger.warning("Error closing database connection pool: %s", e)

            # The parallel execution engine needs no teardown: its thread pools
            # are context-managed per stage and already closed by this point.

            # Cleanup resource manager
            if hasattr(self, "resource_manager") and self.resource_manager:
                try:
                    # Get final resource statistics
                    final_stats = self.resource_manager.get_resource_status()
                    logger.info(
                        "Final resource status: Memory=%.0fMB, CPU=%.1f%%",
                        final_stats["memory"]["usage_mb"],
                        final_stats["cpu"]["current_percent"],
                    )

                    self.resource_manager.stop_monitoring()
                    logger.info("Resource manager monitoring stopped")
                except Exception as e:
                    logger.warning("Error during resource manager cleanup: %s", e)

        except Exception as e:
            logger.warning("Error during resource cleanup: %s", e)

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
        fail_on_validation_error: bool = False,
        dry_run: bool = False,
    ) -> MultiYearSummary:
        start = start_year or self.config.simulation.start_year
        end = end_year or self.config.simulation.end_year

        # Execute PRE_SIMULATION hooks (e.g., self-healing database initialization)
        self.hook_manager.execute_hooks(
            HookType.PRE_SIMULATION,
            {"start_year": start, "end_year": end, "dry_run": dry_run},
        )

        # Enhanced multi-year simulation startup logging
        self._log_simulation_startup_summary(start, end)

        self._setup_monitoring()
        _run_ctx = self._create_observability_context(start, end)

        with _run_ctx:
            db_path = getattr(self.db_manager, "db_path", "default")
            lock_name = f"planalign_{hash(str(db_path)) % 10**8}"
            logger.debug("Acquiring execution lock: %s (db: %s)", lock_name, db_path)
            with ExecutionMutex(lock_name):
                self.state_manager.maybe_full_reset()
                self._initialize_registries(start)
                completed_years: List[int] = []
                simulation_start_time = time.time()

                try:
                    for year in range(start, end + 1):
                        year_start_time = time.time()
                        self.hook_manager.execute_hooks(
                            HookType.PRE_YEAR, {"year": year}
                        )
                        self._execute_year_with_monitoring(
                            year,
                            fail_on_validation_error=fail_on_validation_error,
                            dry_run=dry_run,
                        )
                        completed_years.append(year)
                        self.hook_manager.execute_hooks(
                            HookType.POST_YEAR,
                            {
                                "year": year,
                                "duration_seconds": time.time() - year_start_time,
                            },
                        )

                except Exception:
                    if self.memory_manager:
                        error_snapshot = self.memory_manager.force_memory_check(
                            "simulation_error"
                        )
                        logger.debug(
                            "Memory at error: %.1fMB (pressure: %s)",
                            error_snapshot.rss_mb,
                            error_snapshot.pressure_level.value,
                        )
                    raise

                finally:
                    self._finalize_monitoring()

        self.hook_manager.execute_hooks(
            HookType.POST_SIMULATION,
            {
                "completed_years": completed_years,
                "duration_seconds": time.time() - simulation_start_time,
            },
        )

        summary = self._build_multi_year_summary(completed_years)
        return self._finalize_simulation(summary, completed_years)

    def _setup_monitoring(self) -> None:
        """Start adaptive memory and DuckDB performance monitoring."""
        if self.memory_manager:
            self.memory_manager.start_monitoring()
            initial_snapshot = self.memory_manager.force_memory_check(
                "simulation_startup"
            )
            logger.debug(
                "Initial memory: %.1fMB (pressure: %s)",
                initial_snapshot.rss_mb,
                initial_snapshot.pressure_level.value,
            )

        if (
            hasattr(self, "duckdb_performance_monitor")
            and self.duckdb_performance_monitor
        ):
            self.duckdb_performance_monitor.start_monitoring()
            logger.debug("E068E DuckDB performance monitoring started")

    def _create_observability_context(self, start: int, end: int):
        """Create the observability tracking context manager."""
        if self.observability:
            return self.observability.track_operation(
                "multi_year_run", start_year=start, end_year=end
            )
        from contextlib import nullcontext

        return nullcontext()

    def _initialize_registries(self, start: int) -> None:
        """Ensure orchestrator-managed registries start clean for a new run."""
        try:
            er = self.registry_manager.get_enrollment_registry()
            dr = self.registry_manager.get_deferral_registry()
            er.create_table()
            dr.create_table()
            if start == self.config.simulation.start_year:
                er.reset()
                dr.reset()
                logger.debug("Cleared enrollment/deferral registries for fresh run")
        except Exception:
            pass

    def _execute_year_with_monitoring(
        self, year: int, *, fail_on_validation_error: bool, dry_run: bool
    ) -> None:
        """Execute a single year with memory and observability monitoring."""
        logger.info("Starting simulation year %d", year)

        if self.memory_manager:
            year_snapshot = self.memory_manager.force_memory_check(f"year_{year}_start")
            logger.debug(
                "Memory before year %d: %.1fMB (batch size: %d)",
                year,
                year_snapshot.rss_mb,
                self.memory_manager.get_current_batch_size(),
            )

        if self.observability:
            with self.observability.track_operation(
                f"year_simulation_{year}", year=year
            ):
                self._execute_year_workflow(
                    year,
                    fail_on_validation_error=fail_on_validation_error,
                    dry_run=dry_run,
                )
        else:
            self._execute_year_workflow(
                year, fail_on_validation_error=fail_on_validation_error, dry_run=dry_run
            )

        if self.memory_manager:
            post_year_snapshot = self.memory_manager.force_memory_check(
                f"year_{year}_complete"
            )
            logger.debug(
                "Memory after year %d: %.1fMB", year, post_year_snapshot.rss_mb
            )

    def _finalize_monitoring(self) -> None:
        """Stop memory monitoring and generate final report."""
        if not self.memory_manager:
            return

        self.memory_manager.stop_monitoring()
        stats = self.memory_manager.get_memory_statistics()
        recommendations = self.memory_manager.get_recommendations()

        logger.debug(
            "Adaptive Memory Management Summary: Peak=%sMB, GC=%s, BatchAdj=%s, Fallbacks=%s",
            stats["trends"]["peak_memory_mb"],
            stats["stats"]["total_gc_collections"],
            stats["stats"]["batch_size_adjustments"],
            stats["stats"]["automatic_fallbacks"],
        )

        if recommendations:
            logger.debug("Memory recommendations: %d", len(recommendations))
            for rec in recommendations[-3:]:
                logger.debug("  %s: %s", rec["type"], rec["description"])

        try:
            profile_path = self.memory_manager.export_memory_profile()
            logger.debug("Memory profile: %s", profile_path)
        except Exception:
            pass

    def _build_multi_year_summary(self, completed_years: List[int]) -> MultiYearSummary:
        """Build the final multi-year summary from completed years."""
        reporter = MultiYearReporter(self.db_manager)

        if len(completed_years) >= 2:
            summary = reporter.generate_summary(completed_years)
            reporter.display_comprehensive_multi_year_summary(completed_years)
            return summary

        if len(completed_years) == 1:
            return self._build_single_year_summary(reporter, completed_years[0])

        # No completed years - return empty summary
        return MultiYearSummary(
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
            generated_at=datetime.now(timezone.utc),
        )

    def _build_single_year_summary(
        self, reporter: "MultiYearReporter", year: int
    ) -> MultiYearSummary:
        """Construct a minimal single-year summary compatible with MultiYearSummary."""
        with self.db_manager.get_connection() as conn:
            progression = [reporter._workforce_breakdown(conn, year)]
            growth = {
                "start_active": progression[0].active_employees,
                "end_active": progression[0].active_employees,
                "cagr_pct": 0.0,
                "total_growth_pct": 0.0,
            }
            rows = conn.execute(
                f"""
                SELECT lower({COL_EVENT_TYPE}) AS et, COUNT(*)
                FROM {TABLE_FCT_YEARLY_EVENTS}
                WHERE {COL_SIMULATION_YEAR} = ?
                GROUP BY lower({COL_EVENT_TYPE})
                """,
                [year],
            ).fetchall()
            event_trends = {t: [c] for t, c in rows}
            participation_trends = [progression[0].participation_rate]

        return MultiYearSummary(
            start_year=year,
            end_year=year,
            workforce_progression=progression,
            growth_analysis=growth,
            event_trends=event_trends,
            participation_trends=participation_trends,
            generated_at=datetime.now(timezone.utc),
        )

    def _finalize_simulation(
        self, summary: MultiYearSummary, completed_years: List[int]
    ) -> MultiYearSummary:
        """Persist summary CSV, cleanup resources, finalize observability."""
        # Persist summary CSV
        if completed_years:
            out_csv = (
                self.reports_dir
                / f"multi_year_summary_{completed_years[0]}_{completed_years[-1]}.csv"
            )
            summary.export_csv(out_csv)
            try:
                logger.info("Multi-year CSV summary saved to: %s", out_csv)
            except Exception:
                pass

        self._cleanup_resources()

        try:
            if self.observability:
                self.observability.finalize_run("success")
        except Exception:
            pass

        if hasattr(summary, "__dict__"):
            # threading_config is not a declared MultiYearSummary field; it is
            # attached dynamically here for downstream consumers (e.g. reports).
            summary.threading_config = {  # type: ignore[attr-defined]
                "dbt_threads": self.dbt_threads,
                "event_shards": self.event_shards,
                "event_generation_mode": "sql",
            }

        return summary

    def _execute_year_workflow(
        self, year: int, *, fail_on_validation_error: bool, dry_run: bool = False
    ) -> None:
        """Execute workflow for a single simulation year using modular components."""
        workflow = self.workflow_builder.build_year_workflow(
            year=year, start_year=self.config.simulation.start_year
        )

        self.state_manager.maybe_clear_year_data(year)
        self.state_manager.clear_year_fact_rows(year)
        self._ensure_seeds_loaded()

        # Start-year specific initialization
        if year == self.config.simulation.start_year:
            self._run_start_year_setup(year)

        # Hazard cache rebuild runs `dbt build --select dim_*_hazards`, which reads
        # staging tables (e.g. stg_config_job_levels). It must run only after seeds
        # and the start-year staging models exist; otherwise a fresh scenario DB
        # emits a non-fatal but alarming "stg_config_job_levels does not exist"
        # warning before staging has been built.
        self._ensure_hazard_caches_current()

        for stage in workflow:
            logger.info("Executing stage: %s", stage.name.value)
            stage_start_time = time.time()
            self.hook_manager.execute_hooks(
                HookType.PRE_STAGE, {"year": year, "stage": stage.name}
            )
            self._record_performance_checkpoint(stage.name.value, year, "start")

            # Specialized stage handlers that skip generic execution
            if not self._execute_specialized_stage(stage, year):
                # Generic stage execution with resource/memory management
                self._execute_stage_with_monitoring(stage, year)

                self._record_performance_checkpoint(stage.name.value, year, "complete")

                if not dry_run:
                    self.stage_validator.validate_stage(
                        stage, year, fail_on_validation_error
                    )

            self.hook_manager.execute_hooks(
                HookType.POST_STAGE,
                {
                    "year": year,
                    "stage": stage.name,
                    "duration_seconds": time.time() - stage_start_time,
                },
            )

    def _ensure_hazard_caches_current(self) -> None:
        """E068D: Ensure hazard caches are current before workflow execution."""
        if not (hasattr(self, "hazard_cache_manager") and self.hazard_cache_manager):
            return
        try:
            logger.debug("Checking hazard cache currency...")
            self.hazard_cache_manager.ensure_hazard_caches_current()
        except Exception as e:
            logger.debug("Hazard cache check failed (non-critical): %s", e)
            logger.debug(
                "Hazard cache check skipped (will rebuild if needed during execution)"
            )

    def _ensure_seeds_loaded(self) -> None:
        """Ensure dbt seeds are loaded once, dropping stale schema tables first."""
        if self._seeded:
            return

        cleanup_manager = DataCleanupManager(self.db_manager, verbose=self.verbose)
        dropped = cleanup_manager.drop_seed_tables_with_schema_mismatch()
        if dropped:
            logging.getLogger(__name__).info(
                f"Dropped {len(dropped)} seed tables with schema mismatch: {dropped}"
            )
            logger.debug("Dropped %d seed table(s) with outdated schema", len(dropped))

        seed_res = self.dbt_runner.execute_command(["seed"], stream_output=True)
        if not seed_res.success:
            raise PipelineStageError(
                f"Dbt seed failed with code {seed_res.return_code}"
            )
        self._seeded = True

    def _run_start_year_setup(self, year: int) -> None:
        """Run staging models and seed registries for the start year."""
        logger.info("Building staging models for start year...")
        staging_res = self.dbt_runner.execute_command(
            ["run", "--select", "staging.*"],
            simulation_year=year,
            dbt_vars=self._dbt_vars,
            stream_output=True,
        )
        if not staging_res.success:
            raise PipelineStageError(
                f"Staging models failed with code {staging_res.return_code}"
            )

        self.registry_manager.get_enrollment_registry().create_for_year(year)
        self.registry_manager.get_deferral_registry().create_table()

    def _record_performance_checkpoint(
        self, stage_name: str, year: int, suffix: str
    ) -> None:
        """Record a DuckDB performance checkpoint if monitoring is available."""
        if (
            hasattr(self, "duckdb_performance_monitor")
            and self.duckdb_performance_monitor
        ):
            self.duckdb_performance_monitor.record_checkpoint(
                f"{stage_name}_{year}_{suffix}"
            )

    def _execute_specialized_stage(self, stage: "StageDefinition", year: int) -> bool:
        """Handle EVENT_GENERATION and STATE_ACCUMULATION stages. Returns True if handled."""
        if stage.name == WorkflowStage.EVENT_GENERATION:
            self._execute_event_generation_stage(stage, year)
            return True

        if stage.name == WorkflowStage.STATE_ACCUMULATION:
            stage_result = self.year_executor.execute_workflow_stage(stage, year)
            if not stage_result[KEY_SUCCESS]:
                raise PipelineStageError(
                    f"Stage {stage.name.value} failed: {stage_result.get('error', 'Unknown error')}"
                )
            self._record_performance_checkpoint(stage.name.value, year, "complete")
            return True

        return False

    def _execute_event_generation_stage(
        self, stage: "StageDefinition", year: int
    ) -> None:
        """Execute the hybrid event generation stage."""
        try:
            hybrid_result = (
                self.event_generation_executor.execute_hybrid_event_generation([year])
            )
            if not hybrid_result[KEY_SUCCESS]:
                raise PipelineStageError(
                    f"Hybrid event generation failed: {hybrid_result}"
                )

            mode = hybrid_result["mode"].upper()
            duration = hybrid_result["execution_time"]
            events = hybrid_result["total_events"]
            logger.info(
                "%s event generation completed: %s events in %.1fs",
                mode,
                f"{events:,}",
                duration,
            )
            if hybrid_result.get("fallback_used"):
                logger.warning("Used fallback mode due to primary mode failure")

            self._record_performance_checkpoint(stage.name.value, year, "complete")

        except Exception as e:
            raise PipelineStageError(
                f"Hybrid event generation failed for year {year}: {e}"
            )

    def _execute_stage_with_monitoring(
        self, stage: "StageDefinition", year: int
    ) -> None:
        """Execute a generic stage with resource management or legacy memory monitoring."""
        if hasattr(self, "resource_manager") and self.resource_manager:
            self._execute_stage_with_resource_manager(stage, year)
        else:
            self._execute_stage_with_legacy_memory(stage, year)

    def _execute_stage_with_resource_manager(
        self, stage: "StageDefinition", year: int
    ) -> None:
        """Execute stage with advanced resource management (S067-03)."""
        # Callers only invoke this method when self.resource_manager is truthy
        # (see _execute_stage_with_monitoring); narrow the type here.
        resource_manager = self.resource_manager
        assert resource_manager is not None

        if not resource_manager.check_resource_health():
            logger.warning(
                "Resource pressure detected before stage %s", stage.name.value
            )
            cleanup_result = resource_manager.trigger_resource_cleanup()
            logger.debug(
                "Resource cleanup: %+.1fMB freed", cleanup_result["memory_freed_mb"]
            )

        pre_stage_status = resource_manager.get_resource_status()
        logger.debug(
            "Pre-stage resources: %.0fMB memory, %.1f%% CPU",
            pre_stage_status["memory"]["usage_mb"],
            pre_stage_status["cpu"]["current_percent"],
        )

        with resource_manager.monitor_execution(f"stage_{stage.name.value}_{year}", 1):
            self._execute_stage_core(stage, year)

        post_stage_status = resource_manager.get_resource_status()
        memory_delta = (
            post_stage_status["memory"]["usage_mb"]
            - pre_stage_status["memory"]["usage_mb"]
        )
        logger.debug(
            "Post-stage resources: %.0fMB memory (%+.0fMB), %.1f%% CPU",
            post_stage_status["memory"]["usage_mb"],
            memory_delta,
            post_stage_status["cpu"]["current_percent"],
        )

        if (
            pre_stage_status["memory"]["pressure"]
            != post_stage_status["memory"]["pressure"]
        ):
            logger.warning(
                "Memory pressure changed: %s -> %s",
                pre_stage_status["memory"]["pressure"],
                post_stage_status["memory"]["pressure"],
            )

        if post_stage_status["memory"]["leak_detected"]:
            logger.warning("Memory leak detected during stage %s", stage.name.value)

    def _execute_stage_with_legacy_memory(
        self, stage: "StageDefinition", year: int
    ) -> None:
        """Execute stage with legacy memory management fallback."""
        pre_stage_snapshot = None
        if hasattr(self, "memory_manager") and self.memory_manager:
            pre_stage_snapshot = self.memory_manager.force_memory_check(
                f"{stage.name.value}_start"
            )

        self._execute_stage_core(stage, year)

        if hasattr(self, "memory_manager") and self.memory_manager:
            post_stage_snapshot = self.memory_manager.force_memory_check(
                f"{stage.name.value}_complete"
            )
            if pre_stage_snapshot:
                memory_change = post_stage_snapshot.rss_mb - pre_stage_snapshot.rss_mb
                logger.debug(
                    "Stage memory change: %+.1fMB (now: %.1fMB)",
                    memory_change,
                    post_stage_snapshot.rss_mb,
                )

                if (
                    post_stage_snapshot.pressure_level
                    != pre_stage_snapshot.pressure_level
                ):
                    logger.debug(
                        "Memory pressure changed: %s -> %s",
                        pre_stage_snapshot.pressure_level.value,
                        post_stage_snapshot.pressure_level.value,
                    )
                    logger.debug(
                        "Batch size: %d", self.memory_manager.get_current_batch_size()
                    )

    def _execute_stage_core(self, stage: "StageDefinition", year: int) -> None:
        """Execute a workflow stage with optional observability tracking."""
        if self.observability:
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

    def get_adaptive_batch_size(self) -> int:
        """Get current adaptive batch size from memory manager"""
        if hasattr(self, "memory_manager") and self.memory_manager:
            return self.memory_manager.get_current_batch_size()
        return 1000  # Default fallback

    def get_memory_recommendations(self) -> List[Dict[str, Any]]:
        """Get memory optimization recommendations"""
        if hasattr(self, "memory_manager") and self.memory_manager:
            return self.memory_manager.get_recommendations()
        return []

    def get_memory_statistics(self) -> Dict[str, Any]:
        """Get memory usage statistics"""
        if hasattr(self, "memory_manager") and self.memory_manager:
            return self.memory_manager.get_memory_statistics()
        return {}

    def _log_compensation_parameters(self) -> None:
        """Log compensation parameters for enhanced visibility"""
        try:
            comp = self.config.compensation
            logger.info(
                "Compensation Parameters: COLA=%.1f%%, Merit=%.1f%%, Promotion Lift=%.1f%%",
                comp.cola_rate * 100,
                comp.merit_budget * 100,
                comp.promotion_increase * 100,
            )
        except Exception:
            pass

    def _validate_compensation_parameters(self) -> None:
        """Validate compensation parameters are within reasonable ranges"""
        try:
            comp = self.config.compensation
            warnings = []

            if comp.cola_rate < 0.0 or comp.cola_rate > 0.1:
                warnings.append(
                    f"COLA rate {comp.cola_rate:.1%} is outside normal range [0%, 10%]"
                )

            if comp.merit_budget < 0.0 or comp.merit_budget > 0.15:
                warnings.append(
                    f"Merit budget {comp.merit_budget:.1%} is outside normal range [0%, 15%]"
                )

            if comp.promotion_increase < 0.0 or comp.promotion_increase > 0.25:
                warnings.append(
                    f"Promotion lift {comp.promotion_increase:.1%} is outside normal range [0%, 25%]"
                )

            for warning in warnings:
                logger.warning("Compensation parameter: %s", warning)
        except Exception:
            pass

    def _log_simulation_startup_summary(self, start_year: int, end_year: int) -> None:
        """Enhanced simulation startup logging"""
        logger.info(
            "PlanWise Navigator Multi-Year Simulation: Period=%d->%d (%d years), Seed=%s, Growth=%.1f%%",
            start_year,
            end_year,
            end_year - start_year + 1,
            self.config.simulation.random_seed,
            self.config.simulation.target_growth_rate * 100,
        )

    def update_compensation_parameters(
        self, *, cola_rate: Optional[float] = None, merit_budget: Optional[float] = None
    ) -> None:
        """Update compensation parameters dynamically (Streamlit integration)"""
        if cola_rate is not None:
            self.config.compensation.cola_rate = cola_rate
        if merit_budget is not None:
            self.config.compensation.merit_budget = merit_budget

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
                logger.info("Parameter models rebuilt successfully")
            else:
                logger.warning(
                    "Failed to rebuild parameter models: %s", result.return_code
                )
        except Exception as e:
            logger.warning("Error rebuilding parameter models: %s", e)
