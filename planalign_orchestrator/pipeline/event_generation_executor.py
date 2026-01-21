#!/usr/bin/env python3
"""
Event Generation Executor Module

Responsible for executing event generation using SQL-based dbt models.
Supports performance monitoring and comprehensive error handling.

This module extracts event generation logic from PipelineOrchestrator to support
modular pipeline architecture (Story S072-02 Part 1).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List

import logging

from ..config import SimulationConfig
from ..dbt_runner import DbtResult, DbtRunner
from ..utils import DatabaseConnectionManager
from .workflow import StageDefinition, WorkflowStage

logger = logging.getLogger(__name__)


def normalize_path_for_duckdb(path: Path, base_dir: Path = None) -> str:
    """
    Normalize a path for DuckDB compatibility across all platforms.

    DuckDB requires forward slashes in paths on all platforms, including Windows.
    This function ensures paths are converted to POSIX format and made relative
    to the dbt/ directory where dbt commands execute.

    Args:
        path: The path to normalize (can be absolute or relative)
        base_dir: Optional base directory for relative path calculation.
                  Defaults to current working directory.

    Returns:
        A POSIX-formatted path string relative to the dbt/ directory,
        suitable for use in DuckDB's read_parquet() function.

    Examples:
        >>> normalize_path_for_duckdb(Path("data/parquet/events"))
        '../data/parquet/events'

        >>> normalize_path_for_duckdb(Path("C:\\Users\\data\\parquet"))  # Windows
        '../data/parquet'  # Converted to forward slashes

    Note:
        This function ensures DuckDB's read_parquet() works correctly on all platforms.
    """
    if base_dir is None:
        base_dir = Path.cwd()

    # Convert to Path object if string
    if isinstance(path, str):
        path = Path(path)

    # Handle absolute paths - convert to relative from base_dir
    if path.is_absolute():
        try:
            # Try to make it relative to base_dir
            relative_path = path.relative_to(base_dir)
            # Prefix with ../ since dbt runs from dbt/ directory
            result = f"../{relative_path.as_posix()}"
            logger.debug(f"Path normalization: absolute {path} -> {result}")
            return result
        except ValueError:
            # Path is not relative to base_dir, use as_posix() directly
            result = path.as_posix()
            logger.debug(f"Path normalization: absolute (external) {path} -> {result}")
            return result

    # Handle paths already relative from dbt/ directory (start with ../)
    path_str = str(path)
    if path_str.startswith("../") or path_str.startswith("..\\"):
        result = path.as_posix()
        logger.debug(f"Path normalization: already relative {path} -> {result}")
        return result

    # Handle relative paths from project root - prefix with ../
    result = f"../{path.as_posix()}"
    logger.debug(f"Path normalization: relative {path} -> {result}")
    return result


class PipelineStageError(RuntimeError):
    """Exception raised when a pipeline stage fails execution.

    This exception is raised when event generation, validation, or other
    pipeline stages encounter unrecoverable errors.
    """
    pass


class EventGenerationExecutor:
    """Executes event generation using SQL-based dbt models.

    This class handles the execution of event generation for multi-year simulations
    using SQL-based dbt models. It provides performance monitoring and comprehensive
    error handling.

    Key Features:
        - SQL-based event generation via dbt models
        - Sharded event generation for large datasets
        - Performance monitoring and reporting
        - Year-specific model selection

    Attributes:
        config: Simulation configuration with event generation settings
        dbt_runner: DbtRunner instance for executing dbt commands
        db_manager: Database connection manager for querying event counts
        dbt_vars: Dictionary of dbt variables for command execution
        event_shards: Number of shards for parallel event generation
        verbose: Whether to print detailed execution information

    Example:
        >>> executor = EventGenerationExecutor(
        ...     config=config,
        ...     dbt_runner=dbt_runner,
        ...     db_manager=db_manager,
        ...     dbt_vars=to_dbt_vars(config),
        ...     event_shards=1,
        ...     verbose=True
        ... )
        >>> result = executor.execute_hybrid_event_generation([2025, 2026, 2027])
        >>> print(f"Generated {result['total_events']} events in {result['execution_time']:.1f}s")
    """

    def __init__(
        self,
        config: SimulationConfig,
        dbt_runner: DbtRunner,
        db_manager: DatabaseConnectionManager,
        dbt_vars: Dict[str, Any],
        event_shards: int,
        verbose: bool = False,
    ):
        """Initialize event generation executor.

        Args:
            config: Simulation configuration with event generation settings
            dbt_runner: DbtRunner instance for executing dbt commands
            db_manager: Database connection manager for event count queries
            dbt_vars: Dictionary of dbt variables for command execution
            event_shards: Number of shards for parallel event generation (>=1)
            verbose: Whether to print detailed execution information

        Raises:
            ValueError: If event_shards < 1
        """
        if event_shards < 1:
            raise ValueError(f"event_shards must be >= 1, got {event_shards}")

        self.config = config
        self.dbt_runner = dbt_runner
        self.db_manager = db_manager
        self.dbt_vars = dbt_vars
        self.event_shards = event_shards
        self.verbose = verbose

    def execute_hybrid_event_generation(
        self, years: List[int]
    ) -> Dict[str, Any]:
        """Execute event generation using SQL-based dbt models.

        Args:
            years: List of simulation years to generate events for

        Returns:
            Dictionary with execution results:
                - mode: 'sql'
                - success: Whether all years completed successfully
                - execution_time: Total execution time in seconds
                - total_events: Total number of events generated
                - successful_years: List of years completed successfully

        Raises:
            PipelineStageError: If event generation fails

        Example:
            >>> result = executor.execute_hybrid_event_generation([2025, 2026, 2027])
            >>> print(f"Generated {result['total_events']} events in {result['execution_time']:.1f}s")
        """
        start_time = time.time()

        if self.verbose:
            print(f"🔄 Executing event generation in SQL mode for years {years}")

        return self._execute_sql_event_generation(years, start_time)

    def _execute_sql_event_generation(
        self, years: List[int], start_time: float
    ) -> Dict[str, Any]:
        """Execute event generation using SQL-based dbt models.

        This uses the dbt event generation models with optional
        threading and sharding optimizations.

        Args:
            years: List of simulation years to generate events for
            start_time: Timestamp when event generation started

        Returns:
            Dictionary with SQL execution results:
                - mode: 'sql'
                - success: Whether all years completed successfully
                - execution_time: Total execution time in seconds
                - total_events: Total number of events generated across all years
                - successful_years: List of years that completed successfully

        Raises:
            PipelineStageError: If event generation fails for any year

        Notes:
            - Uses tag:EVENT_GENERATION for model selection
            - Excludes STATE_ACCUMULATION models incorrectly tagged EVENT_GENERATION
            - Queries database to count events per year for statistics
            - Supports sharded execution for large datasets
        """

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
                        dbt_vars=self.dbt_vars,
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
                raise PipelineStageError(f"SQL event generation failed for year {year}: {e}")

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
        }

    def _execute_sharded_event_generation(self, year: int) -> List[DbtResult]:
        """Execute event generation with sharding for large datasets (E068C).

        Sharding splits event generation across multiple parallel executions,
        each processing a subset of employees. This reduces memory pressure
        and enables parallel processing for large workforce simulations.

        Args:
            year: Simulation year to generate events for

        Returns:
            List of DbtResult objects, one per shard plus union writer

        Raises:
            PipelineStageError: If any shard or union writer fails

        Notes:
            - Executes event_shards parallel dbt runs with shard_id variables
            - Final union writer combines all shards into fct_yearly_events
            - All shards must succeed before union writer executes

        Example:
            >>> results = executor._execute_sharded_event_generation(2025)
            >>> print(f"Generated events across {len(results)-1} shards")
        """
        results = []

        if self.verbose:
            print(f"   🔀 Executing event generation with {self.event_shards} shards")

        # Execute sharded event generation in parallel
        for shard_id in range(self.event_shards):
            shard_vars = self.dbt_vars.copy()
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
            dbt_vars=self.dbt_vars,
            stream_output=True
        )
        results.append(union_result)

        if not union_result.success:
            raise PipelineStageError(
                f"Event union writer failed with code {union_result.return_code}"
            )

        return results

    def _get_event_generation_models(self, year: int) -> List[str]:
        """Get the list of event generation models for a specific year.

        This matches the existing workflow definition logic and ensures
        proper model ordering for deterministic execution. Year 1 includes
        synthetic baseline enrollment events from census data.

        Args:
            year: Simulation year to get models for

        Returns:
            List of dbt model names in execution order

        Notes:
            - Year 1 (start_year) includes int_synthetic_baseline_enrollment_events
            - Subsequent years skip baseline enrollment (uses accumulator state)
            - Model order is critical for deterministic random number generation
            - Models are executed sequentially to maintain RNG state

        Example:
            >>> models = executor._get_event_generation_models(2025)
            >>> print(f"Year 2025 uses {len(models)} event generation models")
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
