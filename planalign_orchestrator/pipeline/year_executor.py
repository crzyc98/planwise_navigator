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
import secrets
import time
from typing import Any, Dict, List, Optional

from planalign_core.constants import (
    TABLE_FCT_WORKFORCE_SNAPSHOT,
)
from planalign_orchestrator.config import SimulationConfig
from planalign_orchestrator.dbt_runner import DbtResult, DbtRunner
from planalign_orchestrator.state_accumulator import YearDependencyValidator
from planalign_orchestrator.utils import DatabaseConnectionManager

from .workflow import StageDefinition, WorkflowStage
from .stage_execution_strategies import (
    PipelineStageError,
    execute_model_parallelization,
    execute_sharded_events,
    execute_tagged_stage,
    should_use_model_parallelization,
)

logger = logging.getLogger(__name__)


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
        self._year_validator = YearDependencyValidator(
            db_manager, start_year=start_year
        )

    def execute_workflow_stage(
        self, stage: StageDefinition, year: int
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
        correlation_id = secrets.token_hex(4)

        try:
            if self.verbose:
                logger.debug(
                    "Starting %s with %d threads", stage.name.value, self.dbt_threads
                )

            # Signal stage start to progress callback
            if self.progress_callback and hasattr(
                self.progress_callback, "update_stage"
            ):
                self.progress_callback.update_stage(stage.name.value)

            results = self._dispatch_stage_execution(stage, year)

            execution_time = time.time() - start_time
            if self.verbose:
                logger.info("Completed %s in %.1fs", stage.name.value, execution_time)

            # Signal stage completion to progress callback
            if self.progress_callback and hasattr(
                self.progress_callback, "stage_completed"
            ):
                self.progress_callback.stage_completed(stage.name.value, execution_time)

            return {
                "stage": stage.name.value,
                "year": year,
                "success": True,
                "execution_time": execution_time,
                "results": results,
                "correlation_id": correlation_id,
            }

        except Exception as e:
            execution_time = time.time() - start_time
            if self.verbose:
                logger.error(
                    "Failed %s after %.1fs: %s", stage.name.value, execution_time, e
                )

            return {
                "stage": stage.name.value,
                "year": year,
                "success": False,
                "execution_time": execution_time,
                "error": str(e),
                "correlation_id": correlation_id,
            }

    def _dispatch_stage_execution(
        self, stage: StageDefinition, year: int
    ) -> List[DbtResult]:
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
            self.validate_year_dependencies(year)
            if self.verbose:
                logger.debug("Running STATE_ACCUMULATION with dbt (sequential)")

        self._run_stage_models(stage, year)
        return []

    def _execute_parallel_stage(
        self, stage: StageDefinition, year: int
    ) -> List[DbtResult]:
        """Execute one broad-tag selection or delegate optional event sharding."""
        if stage.name == WorkflowStage.EVENT_GENERATION and self.event_shards > 1:
            return self._execute_sharded_event_generation(year)
        return execute_tagged_stage(self, stage, year)

    def _execute_sharded_event_generation(self, year: int) -> List[DbtResult]:
        """Execute optional event shards followed by one union writer."""
        return execute_sharded_events(self, year)

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
        if (
            self.model_parallelization_enabled
            and self.parallel_execution_engine
            and self._should_use_model_parallelization(stage)
        ):
            self._run_stage_with_model_parallelization(stage, year)
            return

        # Fallback to existing sequential/parallel execution logic
        self._run_stage_models_legacy(stage, year)

    def _should_use_model_parallelization(self, stage: StageDefinition) -> bool:
        """Return whether the optional model-parallel strategy is safe."""
        return should_use_model_parallelization(self, stage)

    def _run_stage_with_model_parallelization(
        self, stage: StageDefinition, year: int
    ) -> None:
        """Delegate to the extracted optional parallel execution strategy."""
        execute_model_parallelization(self, stage, year)

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
        for model in stage.models:
            self._clear_snapshot_rows_if_needed(model, year)
        selection = ["run", "--select", *stage.models]
        res = self.dbt_runner.execute_command(
            selection,
            simulation_year=year,
            dbt_vars=self._dbt_vars,
            stream_output=True,
        )
        if not res.success:
            raise PipelineStageError(
                f"Dbt failed on models [{', '.join(stage.models)}] in stage "
                f"{stage.name.value} for year {year} with code {res.return_code}"
            )

    def validate_year_dependencies(self, year: int) -> None:
        """Validate prior-year state before any consumer reads it."""
        self._year_validator.validate_year_dependencies(year)

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
                logger.debug(
                    "Cleared %s for simulation_year=%d before rebuild",
                    TABLE_FCT_WORKFORCE_SNAPSHOT,
                    year,
                )
        except Exception:
            # Non-fatal; proceed with dbt incremental upsert
            pass

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

    def _should_full_refresh_foundation(
        self, stage: StageDefinition, year: int
    ) -> bool:
        """Determine if the FOUNDATION stage should use --full-refresh.

        Full refresh is used only on the first simulation year.

        Args:
            stage: Stage definition to check
            year: Current simulation year

        Returns:
            True if --full-refresh should be appended
        """
        if stage.name != WorkflowStage.FOUNDATION:
            return False

        should_refresh = year == self.config.simulation.start_year

        if should_refresh and self.verbose:
            logger.debug(
                "Running %s with --full-refresh (start year=%d)",
                stage.name.value,
                year,
            )

        return should_refresh
