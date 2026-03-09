#!/usr/bin/env python3
"""
Year Execution Module

Handles execution of workflow stages for individual simulation years.
Extracted from PipelineOrchestrator to provide focused year-level execution
with support for parallel stage execution and model-level parallelization.

This module encapsulates:
- Workflow stage execution with optimal threading
- Parallel stage execution using dbt tag-based selection
- Optional model-level parallelization for advanced performance
- Integration with parallel execution engine and resource management
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from config.constants import (
    MODEL_FCT_YEARLY_EVENTS,
    TABLE_FCT_WORKFORCE_SNAPSHOT,
)
from planalign_orchestrator.config import SimulationConfig, get_database_path
from planalign_orchestrator.dbt_runner import DbtResult, DbtRunner
from planalign_orchestrator.state_accumulator import YearDependencyValidator
from planalign_orchestrator.utils import DatabaseConnectionManager

from .workflow import StageDefinition, WorkflowStage

logger = logging.getLogger(__name__)

# Import model parallelization components (optional)
try:
    from planalign_orchestrator.parallel_execution_engine import (
        ParallelExecutionEngine,
        ExecutionContext,
    )
    MODEL_PARALLELIZATION_AVAILABLE = True
except ImportError:
    MODEL_PARALLELIZATION_AVAILABLE = False


class PipelineStageError(RuntimeError):
    """Exception raised when a pipeline stage execution fails."""
    pass


class YearExecutor:
    """Executes workflow stages for a specific simulation year.

    This class handles the execution of individual workflow stages with support for:
    - Sequential model execution with dependency ordering
    - Parallel stage execution using dbt tag-based selection
    - Optional model-level parallelization for advanced performance
    - Event generation with sharding support for large datasets
    - Integration with resource management and adaptive scaling

    The executor supports both basic dbt-level parallelization and advanced
    model-level parallelization through the ParallelExecutionEngine when enabled.

    Attributes:
        config: Simulation configuration
        dbt_runner: dbt command executor
        db_manager: Database connection manager
        dbt_vars: dbt variables for template rendering
        dbt_threads: Number of threads for dbt execution
        event_shards: Number of shards for event generation
        verbose: Enable verbose logging
        parallel_execution_engine: Optional advanced parallelization engine
        model_parallelization_enabled: Whether model parallelization is active
        parallelization_config: Configuration for model parallelization
    """

    def __init__(
        self,
        config: SimulationConfig,
        dbt_runner: DbtRunner,
        db_manager: DatabaseConnectionManager,
        dbt_vars: Dict[str, Any],
        dbt_threads: int,
        start_year: int,
        event_shards: int = 1,
        verbose: bool = False,
        parallel_execution_engine: Optional[Any] = None,
        model_parallelization_enabled: bool = False,
        parallelization_config: Optional[Any] = None,
        progress_callback: Optional[Any] = None,
    ):
        """Initialize the year executor.

        Args:
            config: Simulation configuration
            dbt_runner: dbt command executor
            db_manager: Database connection manager
            dbt_vars: dbt variables for template rendering
            dbt_threads: Number of threads for dbt execution
            start_year: The configured simulation start year for dependency validation
            event_shards: Number of shards for event generation (default: 1)
            verbose: Enable verbose logging (default: False)
            parallel_execution_engine: Optional ParallelExecutionEngine for advanced parallelization
            model_parallelization_enabled: Whether model-level parallelization is enabled
            parallelization_config: Configuration object for parallelization settings
            progress_callback: Optional callback for progress updates (LiveProgressTracker or similar)
        """
        self.config = config
        self.dbt_runner = dbt_runner
        self.db_manager = db_manager
        self._dbt_vars = dbt_vars
        self.dbt_threads = dbt_threads
        self.start_year = start_year
        self.event_shards = event_shards
        self.verbose = verbose
        self.parallel_execution_engine = parallel_execution_engine
        self.model_parallelization_enabled = model_parallelization_enabled
        self.parallelization_config = parallelization_config
        self.progress_callback = progress_callback

        # Initialize year dependency validator for temporal state accumulator validation
        self._year_validator = YearDependencyValidator(db_manager, start_year=start_year)

    def execute_workflow_stage(
        self,
        stage: StageDefinition,
        year: int
    ) -> Dict[str, Any]:
        """Execute a workflow stage with optimal threading (E068C).

        This method orchestrates the execution of a workflow stage, selecting
        the appropriate execution strategy based on stage characteristics:

        - EVENT_GENERATION: Uses parallel execution with tag-based selection
        - STATE_ACCUMULATION: Runs sequentially to prevent transaction conflicts
        - Other stages: Uses sequential execution or model parallelization

        Args:
            stage: Stage definition with models and metadata
            year: Simulation year to execute

        Returns:
            Dictionary with execution results:
                - stage: Stage name
                - year: Simulation year
                - success: Whether execution succeeded
                - execution_time: Duration in seconds
                - results: List of dbt results (if applicable)
                - error: Error message (if failed)

        Notes:
            - EVENT_GENERATION can be parallelized safely with tag-based selection
            - STATE_ACCUMULATION must run sequentially due to delete+insert conflicts
            - Model-level parallelization is used when enabled and appropriate
        """
        start_time = time.time()

        try:
            if self.verbose:
                print(f"   📋 Starting {stage.name.value} with {self.dbt_threads} threads")

            # Signal stage start to progress callback
            if self.progress_callback and hasattr(self.progress_callback, 'update_stage'):
                self.progress_callback.update_stage(stage.name.value)

            results = self._dispatch_stage_execution(stage, year)

            execution_time = time.time() - start_time
            if self.verbose:
                print(f"   ✅ Completed {stage.name.value} in {execution_time:.1f}s")

            # Signal stage completion to progress callback
            if self.progress_callback and hasattr(self.progress_callback, 'stage_completed'):
                self.progress_callback.stage_completed(stage.name.value, execution_time)

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

    def _dispatch_stage_execution(self, stage: StageDefinition, year: int) -> List[DbtResult]:
        """Dispatch to the appropriate execution strategy for the stage.

        Args:
            stage: Stage definition with models and metadata
            year: Simulation year

        Returns:
            List of dbt results (empty list for non-parallel stages)
        """
        if stage.name == WorkflowStage.EVENT_GENERATION:
            return self._execute_parallel_stage(stage, year)

        if stage.name == WorkflowStage.STATE_ACCUMULATION:
            # Validate year dependencies before state accumulation
            # This prevents silent data corruption from out-of-order year execution
            self._year_validator.validate_year_dependencies(year)
            if self.verbose:
                print("   🔒 Running STATE_ACCUMULATION with dbt (sequential)")

        self._run_stage_models(stage, year)
        return []

    def _execute_parallel_stage(
        self,
        stage: StageDefinition,
        year: int
    ) -> List[DbtResult]:
        """Execute stage with dbt parallelization using tag-based selection (E068C).

        This method executes a stage using dbt's built-in parallelization with
        tag-based model selection. For EVENT_GENERATION stages with sharding enabled,
        it delegates to sharded execution.

        Args:
            stage: Stage definition with models and metadata
            year: Simulation year to execute

        Returns:
            List of dbt execution results

        Raises:
            PipelineStageError: If stage execution fails

        Notes:
            - Uses tag-based selection for efficient parallel execution
            - Supports event sharding for large datasets
            - Thread count controlled by dbt_threads attribute
        """
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
        """Execute event generation with optional sharding for large datasets (E068C).

        This method enables horizontal sharding of event generation for improved
        performance on large datasets. Each shard processes a subset of employees
        and writes to a shard-specific model, which are then unioned together.

        Args:
            year: Simulation year to execute

        Returns:
            List of dbt results for all shards and union operation

        Raises:
            PipelineStageError: If any shard or union operation fails

        Notes:
            - Each shard runs in parallel with dedicated dbt vars
            - Final union model combines all shards into fct_yearly_events
            - Shard count controlled by event_shards attribute
        """
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
            ["run", "--select", MODEL_FCT_YEARLY_EVENTS],
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

    def _run_stage_models(self, stage: StageDefinition, year: int) -> None:
        """Execute stage models with optional model-level parallelization.

        This is the main entry point for stage model execution. It determines
        whether to use advanced model-level parallelization or fall back to
        legacy sequential/basic parallel execution.

        Args:
            stage: Stage definition with models to execute
            year: Simulation year

        Notes:
            - Model parallelization is used when enabled and appropriate
            - Falls back to legacy execution if parallelization is unavailable
            - Respects stage-specific parallelization constraints
        """
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
        """Determine if a stage should use model-level parallelization.

        This method applies safety gates and heuristics to determine whether
        advanced model-level parallelization is appropriate for a stage.

        Args:
            stage: Stage definition to evaluate

        Returns:
            True if model parallelization should be used, False otherwise

        Notes:
            - DuckDB single-file databases do not support concurrent writers
            - EVENT_GENERATION and STATE_ACCUMULATION require careful handling
            - Validation is performed when safety checks are enabled
            - Stages with single models don't benefit from parallelization
        """
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
            if self.parallelization_config and hasattr(self.parallelization_config, 'safety'):
                if self.parallelization_config.safety.validate_execution_safety:
                    # Only use if validation passes
                    validation = self.parallel_execution_engine.validate_stage_parallelization(stage.models)
                    return validation.get("parallelizable", False) and validation.get("safety_score", 0) > 80
            return False

        # Use for other stages if they have multiple models
        return len(stage.models) > 1

    def _run_stage_with_model_parallelization(self, stage: StageDefinition, year: int) -> None:
        """Run stage using sophisticated model-level parallelization.

        This method uses the ParallelExecutionEngine to execute stage models
        with advanced dependency analysis, resource management, and adaptive scaling.

        Args:
            stage: Stage definition with models to execute
            year: Simulation year

        Raises:
            PipelineStageError: If parallelization fails

        Notes:
            - Creates unique execution context with UUID
            - Provides detailed progress and performance metrics
            - Supports conditional parallelization based on resource availability
        """
        if self.verbose:
            print(f"   🚀 Using model-level parallelization for stage {stage.name.value}")

        # Create execution context
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
            print("   📊 Parallelization results:")
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
        """Legacy stage execution logic (sequential/basic parallel).

        This method implements the traditional stage execution approach with
        sequential execution for critical stages and basic parallelization for
        parallel-safe stages.

        Args:
            stage: Stage definition with models to execute
            year: Simulation year

        Raises:
            PipelineStageError: If model execution fails

        Notes:
            - EVENT_GENERATION and STATE_ACCUMULATION run sequentially
            - Special handling for fct_workforce_snapshot to avoid concurrency issues
            - Full refresh applied to specific models with schema issues
            - FOUNDATION stage uses full refresh on first year or when configured
        """
        # Run event generation and state accumulation sequentially to enforce order
        if stage.name in (
            WorkflowStage.EVENT_GENERATION,
            WorkflowStage.STATE_ACCUMULATION,
        ):
            self._run_sequential_event_models(stage, year)
            return

        self._run_parallel_or_single(stage, year)

    def _run_sequential_event_models(self, stage: StageDefinition, year: int) -> None:
        """Run event/accumulation stage models sequentially to enforce ordering.

        Args:
            stage: Stage definition with models to execute
            year: Simulation year

        Raises:
            PipelineStageError: If any model execution fails
        """
        force_full_refresh = self._is_force_full_refresh()

        for model in stage.models:
            self._clear_snapshot_rows_if_needed(model, year)
            selection = ["run", "--select", model]
            self._append_full_refresh_if_needed(selection, model, force_full_refresh, year)
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

    def _is_force_full_refresh(self) -> bool:
        """Check if setup config requires forced full refresh for all models."""
        setup = getattr(self.config, "setup", None)
        return bool(
            isinstance(setup, dict)
            and setup.get("clear_tables")
            and setup.get("clear_mode", "all").lower() == "all"
        )

    def _clear_snapshot_rows_if_needed(self, model: str, year: int) -> None:
        """Clear fct_workforce_snapshot rows for the year before rebuild.

        This avoids dbt pre-hook concurrency issues when rebuilding the snapshot.

        Args:
            model: Model name to check
            year: Simulation year whose rows should be cleared
        """
        if model != TABLE_FCT_WORKFORCE_SNAPSHOT:
            return
        try:
            def _clear(conn):
                conn.execute(
                    f"DELETE FROM {TABLE_FCT_WORKFORCE_SNAPSHOT} WHERE simulation_year = ?",
                    [year],
                )
                return True

            self.db_manager.execute_with_retry(_clear)
            if self.verbose:
                print(
                    f"   🧹 Cleared {TABLE_FCT_WORKFORCE_SNAPSHOT} for simulation_year={year} before rebuild"
                )
        except Exception:
            # Non-fatal; proceed with dbt incremental upsert
            pass

    def _append_full_refresh_if_needed(
        self, selection: List[str], model: str, force_full_refresh: bool, year: int
    ) -> None:
        """Append --full-refresh flag for models that require it.

        Args:
            selection: dbt command list to potentially modify in place
            model: Current model name
            force_full_refresh: Whether config forces full refresh for all models
            year: Simulation year (for verbose logging)
        """
        needs_refresh = (
            model in [
                "int_workforce_snapshot_optimized",
                "int_deferral_rate_escalation_events",
            ]
            or force_full_refresh
        )
        if not needs_refresh:
            return

        selection.append("--full-refresh")
        if self.verbose:
            reason = self._get_full_refresh_reason(model)
            print(
                f"   🔄 Rebuilding {model} with --full-refresh ({reason}) for year {year}"
            )

    def _get_full_refresh_reason(self, model: str) -> str:
        """Return a human-readable reason for full refresh based on model name.

        Args:
            model: Model name

        Returns:
            String describing why full refresh is needed
        """
        reasons = {
            "int_workforce_snapshot_optimized": "schema compatibility",
            "int_deferral_rate_escalation_events": "self-reference incremental",
        }
        return reasons.get(model, "clear_mode=all")

    def _run_parallel_or_single(self, stage: StageDefinition, year: int) -> None:
        """Execute stage models in parallel or as a single dbt selection.

        Args:
            stage: Stage definition with models to execute
            year: Simulation year

        Raises:
            PipelineStageError: If model execution fails
        """
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
            return

        # Run as a single selection for consistent dependency behavior
        selection = ["run", "--select", " ".join(stage.models)]
        if self._should_full_refresh_foundation(stage, year):
            selection.append("--full-refresh")
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

    def _should_full_refresh_foundation(self, stage: StageDefinition, year: int) -> bool:
        """Determine if the FOUNDATION stage should use --full-refresh.

        Full refresh is used on the first simulation year or when clear_mode is 'all'.

        Args:
            stage: Stage definition to check
            year: Current simulation year

        Returns:
            True if --full-refresh should be appended
        """
        if stage.name != WorkflowStage.FOUNDATION:
            return False

        setup = getattr(self.config, "setup", None)
        clear_mode = (
            isinstance(setup, dict) and setup.get("clear_mode", "all").lower()
        ) or "all"
        should_refresh = year == self.config.simulation.start_year or clear_mode == "all"

        if should_refresh and self.verbose:
            print(
                f"   🔄 Running {stage.name.value} with --full-refresh (year={year}, clear_mode={clear_mode})"
            )

        return should_refresh
