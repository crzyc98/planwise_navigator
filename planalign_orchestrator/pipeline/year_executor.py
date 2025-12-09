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
- E076: Polars state accumulation pipeline integration with fallback
"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

from planalign_orchestrator.config import SimulationConfig, get_database_path
from planalign_orchestrator.dbt_runner import DbtResult, DbtRunner
from planalign_orchestrator.utils import DatabaseConnectionManager

from .workflow import StageDefinition, WorkflowStage

# E076: Import Polars state accumulation engine
try:
    from planalign_orchestrator.polars_state_pipeline import (
        StateAccumulatorEngine,
        StateAccumulatorConfig,
    )
    POLARS_STATE_PIPELINE_AVAILABLE = True
except ImportError:
    POLARS_STATE_PIPELINE_AVAILABLE = False

# Module logger for E076
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
        event_shards: int = 1,
        verbose: bool = False,
        parallel_execution_engine: Optional[Any] = None,
        model_parallelization_enabled: bool = False,
        parallelization_config: Optional[Any] = None,
    ):
        """Initialize the year executor.

        Args:
            config: Simulation configuration
            dbt_runner: dbt command executor
            db_manager: Database connection manager
            dbt_vars: dbt variables for template rendering
            dbt_threads: Number of threads for dbt execution
            event_shards: Number of shards for event generation (default: 1)
            verbose: Enable verbose logging (default: False)
            parallel_execution_engine: Optional ParallelExecutionEngine for advanced parallelization
            model_parallelization_enabled: Whether model-level parallelization is enabled
            parallelization_config: Configuration object for parallelization settings
        """
        self.config = config
        self.dbt_runner = dbt_runner
        self.db_manager = db_manager
        self._dbt_vars = dbt_vars
        self.dbt_threads = dbt_threads
        self.event_shards = event_shards
        self.verbose = verbose
        self.parallel_execution_engine = parallel_execution_engine
        self.model_parallelization_enabled = model_parallelization_enabled
        self.parallelization_config = parallelization_config

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

            # Execute stage with appropriate threading strategy
            if stage.name == WorkflowStage.EVENT_GENERATION:
                # EVENT_GENERATION can be parallelized safely
                results = self._execute_parallel_stage(stage, year)
            elif stage.name == WorkflowStage.STATE_ACCUMULATION:
                # E076: Try Polars state accumulation if enabled
                polars_success = False
                if self._should_use_polars_state_accumulation():
                    polars_success = self._execute_polars_state_accumulation(stage, year)

                # Fall back to dbt if Polars not used or failed
                if not polars_success:
                    if self.verbose:
                        print(f"   🔒 Running STATE_ACCUMULATION with dbt (sequential)")
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

    # =========================================================================
    # E076: Polars State Accumulation Pipeline Integration
    # =========================================================================

    def _should_use_polars_state_accumulation(self) -> bool:
        """Determine if Polars state accumulation should be used.

        Returns True only when:
        1. Polars state pipeline module is available
        2. Polars mode is enabled in configuration
        3. state_accumulation_enabled is True

        Returns:
            True if Polars state accumulation should be attempted
        """
        # Check if module is available
        if not POLARS_STATE_PIPELINE_AVAILABLE:
            if self.verbose:
                logger.debug("Polars state pipeline module not available")
            return False

        # Check if enabled in config
        if hasattr(self.config, 'is_polars_state_accumulation_enabled'):
            return self.config.is_polars_state_accumulation_enabled()

        # Fallback: Check polars settings directly
        try:
            polars_settings = self.config.get_polars_settings()
            is_polars_mode = self.config.is_polars_mode_enabled()
            return is_polars_mode and polars_settings.state_accumulation_enabled
        except (AttributeError, KeyError):
            return False

    def _execute_polars_state_accumulation(
        self,
        stage: StageDefinition,
        year: int
    ) -> bool:
        """Execute state accumulation using E076 Polars pipeline.

        Attempts to run state accumulation using the Polars-based pipeline
        for 60-75% performance improvement. Falls back to dbt on error
        if fallback_on_error is enabled.

        Args:
            stage: Stage definition (STATE_ACCUMULATION)
            year: Simulation year

        Returns:
            True if Polars execution succeeded, False if fallback to dbt needed
        """
        start_time = time.time()
        state_config = self.config.get_polars_state_accumulation_settings()

        if self.verbose:
            print(f"   ⚡ E076: Attempting Polars state accumulation for year {year}")

        try:
            # Get scenario and plan design from dbt vars
            scenario_id = self._dbt_vars.get('scenario_id', 'baseline')
            plan_design_id = self._dbt_vars.get('plan_design_id', 'standard_401k')

            # Get events path from polars settings
            polars_settings = self.config.get_polars_settings()
            events_path = Path(polars_settings.output_path) if polars_settings.output_path else None

            # E096 FIX: Use db_manager.db_path for scenario-specific database
            # instead of get_database_path() which returns the default dbt path
            db_path = getattr(self.db_manager, 'db_path', None) or get_database_path()

            # Create Polars state accumulator config
            polars_config = StateAccumulatorConfig(
                simulation_year=year,
                scenario_id=scenario_id,
                plan_design_id=plan_design_id,
                database_path=db_path,
                events_path=events_path,
                enable_validation=state_config.get('validate_results', False),
            )

            # Initialize and run the state accumulator engine
            engine = StateAccumulatorEngine(polars_config)
            state_data = engine.build_state()

            # Write results to DuckDB for downstream dbt models
            engine.write_to_database(state_data)

            # Optionally validate against dbt baseline
            if state_config.get('validate_results', False):
                validation_results = engine.validate_against_dbt(state_data)
                if not validation_results.get('passed', False):
                    errors = validation_results.get('errors', [])
                    logger.warning(f"E076 validation failed: {errors}")
                    if self.verbose:
                        print(f"   ⚠️ E076 validation issues: {len(errors)} discrepancies")

            execution_time = time.time() - start_time

            if self.verbose:
                stats = engine.stats
                print(f"   ✅ E076 Polars state accumulation complete in {execution_time:.2f}s")
                print(f"      Employees: {stats.get('employees_processed', 0):,}")
                print(f"      Events: {stats.get('events_processed', 0):,}")
                print(f"      Breakdown: enrollment={stats.get('enrollment_state_time', 0):.2f}s, "
                      f"deferral={stats.get('deferral_state_time', 0):.2f}s, "
                      f"contributions={stats.get('contributions_time', 0):.2f}s, "
                      f"snapshot={stats.get('snapshot_time', 0):.2f}s")

            # Now run any remaining dbt models that Polars didn't replace
            # (e.g., fct_yearly_events consolidation, reporting models)
            self._run_polars_post_processing_models(stage, year)

            return True

        except Exception as e:
            execution_time = time.time() - start_time
            error_msg = str(e)

            # Log the error
            logger.error(f"E076 Polars state accumulation failed: {error_msg}")

            if self.verbose:
                print(f"   ❌ E076 Polars state accumulation failed after {execution_time:.2f}s")
                print(f"      Error: {error_msg}")

            # Check if fallback is enabled
            if state_config.get('fallback_on_error', True):
                if self.verbose:
                    print(f"   🔄 Falling back to dbt-based state accumulation")
                return False
            else:
                # Re-raise if fallback is disabled
                raise PipelineStageError(
                    f"E076 Polars state accumulation failed (fallback disabled): {error_msg}"
                )

    def _run_polars_post_processing_models(
        self,
        stage: StageDefinition,
        year: int
    ) -> None:
        """Run dbt models that must run after Polars state accumulation.

        E096 FIX: When using Polars state accumulation, Polars replaces:
        - int_enrollment_state_accumulator
        - int_deferral_rate_state_accumulator_v2
        - int_employee_contributions

        All other STATE_ACCUMULATION models must still run via dbt:
        - fct_yearly_events: Event consolidation and validation
        - int_employee_state_by_year: Employee state tracking
        - int_workforce_snapshot_optimized: Optimized proration snapshot
        - int_deferral_escalation_state_accumulator: Escalation state
        - int_employer_core_contributions: Employer core contributions
        - int_employee_match_calculations: Match calculations
        - fct_employer_match_events: Match event generation
        - fct_workforce_snapshot: Final snapshot (reads from Polars output)

        Args:
            stage: Stage definition with all models
            year: Simulation year
        """
        # Models that Polars replaces (should NOT run via dbt)
        polars_replaced_models = {
            "int_enrollment_state_accumulator",
            "int_deferral_rate_state_accumulator_v2",
            "int_employee_contributions",
        }

        # All models in the stage that weren't replaced by Polars
        models_to_run = [
            model for model in stage.models
            if model not in polars_replaced_models
        ]

        if not models_to_run:
            return

        if self.verbose:
            print(f"   📋 Running {len(models_to_run)} post-processing dbt models")

        for model in models_to_run:
            if self.verbose:
                print(f"      Running: {model}")

            # Special handling for fct_workforce_snapshot
            if model == "fct_workforce_snapshot":
                try:
                    def _clear(conn):
                        conn.execute(
                            "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?",
                            [year],
                        )
                        return True

                    self.db_manager.execute_with_retry(_clear)
                except Exception:
                    pass  # Non-fatal

            res = self.dbt_runner.execute_command(
                ["run", "--select", model],
                simulation_year=year,
                dbt_vars=self._dbt_vars,
                stream_output=False,  # Quieter output for post-processing
            )

            if not res.success:
                raise PipelineStageError(
                    f"E076 post-processing model {model} failed with code {res.return_code}"
                )
