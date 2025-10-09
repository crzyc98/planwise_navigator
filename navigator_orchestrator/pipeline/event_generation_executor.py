#!/usr/bin/env python3
"""
Event Generation Executor Module

Responsible for executing event generation using either SQL-based dbt models or
Polars-based bulk event factory. Supports hybrid pipeline integration with
automatic fallback and performance monitoring.

This module extracts event generation logic from PipelineOrchestrator to support
modular pipeline architecture (Story S072-02 Part 1).
"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any, Dict, List

from ..config import SimulationConfig
from ..dbt_runner import DbtResult, DbtRunner
from ..utils import DatabaseConnectionManager
from .workflow import StageDefinition, WorkflowStage


class PipelineStageError(RuntimeError):
    """Exception raised when a pipeline stage fails execution.

    This exception is raised when event generation, validation, or other
    pipeline stages encounter unrecoverable errors.
    """
    pass


class EventGenerationExecutor:
    """Executes event generation using SQL or Polars modes.

    This class handles the execution of event generation for multi-year simulations,
    supporting both traditional SQL-based dbt models and high-performance Polars-based
    bulk event factories. It provides automatic fallback, performance monitoring, and
    comprehensive error handling.

    Key Features:
        - Hybrid SQL/Polars event generation
        - Automatic fallback on Polars errors
        - Sharded event generation for large datasets
        - Performance monitoring and reporting
        - Year-specific model selection

    Performance Targets:
        - Polars mode: ≤60s for 5k employees × 5 years
        - SQL mode: Baseline performance with threading optimization

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
        """Execute event generation using either SQL or Polars mode based on configuration.

        This method implements the hybrid pipeline integration that supports both
        SQL-based (traditional dbt models) and Polars-based (bulk factory) event generation.
        It automatically selects the appropriate mode based on configuration and provides
        automatic fallback to SQL mode if Polars generation fails.

        Args:
            years: List of simulation years to generate events for

        Returns:
            Dictionary with execution results:
                - mode: 'sql' or 'polars'
                - success: Whether all years completed successfully
                - execution_time: Total execution time in seconds
                - total_events: Total number of events generated
                - performance_target_met: Whether performance target was met (Polars only)
                - fallback_used: Whether fallback to SQL mode was triggered
                - output_path: Path to Polars output (Polars only)
                - successful_years: List of years completed successfully (SQL only)

        Raises:
            PipelineStageError: If event generation fails and fallback is disabled
            ImportError: If Polars mode is requested but polars is not installed

        Example:
            >>> result = executor.execute_hybrid_event_generation([2025, 2026, 2027])
            >>> if result['mode'] == 'polars':
            ...     print(f"Polars mode: {result['total_events']} events in {result['execution_time']:.1f}s")
            ...     print(f"Target met: {result['performance_target_met']}")
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
        """Execute event generation using Polars bulk event factory.

        This provides high-performance vectorized event generation using Polars
        with target performance of ≤60s for 5k employees × 5 years. The Polars
        mode uses lazy evaluation, streaming, and parallel I/O for optimal performance.

        Args:
            years: List of simulation years to generate events for
            start_time: Timestamp when event generation started
            fallback: Whether this is a fallback execution after error

        Returns:
            Dictionary with Polars execution results:
                - mode: 'polars'
                - success: Always True if no exception raised
                - execution_time: Total execution time in seconds
                - total_events: Total number of events generated
                - output_path: Path to Parquet output directory
                - performance_target_met: Whether ≤60s target was met
                - fallback_used: Whether this is a fallback execution

        Raises:
            ImportError: If polars or polars_event_factory is not available
            PipelineStageError: If Polars event generation fails

        Notes:
            - Updates dbt_vars with polars_events_path for downstream models
            - Configures POLARS_MAX_THREADS environment variable
            - Collects performance statistics for monitoring
        """
        try:
            from ..polars_event_factory import PolarsEventGenerator, EventFactoryConfig
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
        self.dbt_vars.update({
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
        """Execute event generation using traditional SQL-based dbt models.

        This uses the existing dbt event generation models with optional
        threading and sharding optimizations. SQL mode provides baseline
        performance and serves as a fallback when Polars mode is unavailable
        or fails.

        Args:
            years: List of simulation years to generate events for
            start_time: Timestamp when event generation started
            fallback: Whether this is a fallback execution after Polars failure

        Returns:
            Dictionary with SQL execution results:
                - mode: 'sql'
                - success: Whether all years completed successfully
                - execution_time: Total execution time in seconds
                - total_events: Total number of events generated across all years
                - successful_years: List of years that completed successfully
                - fallback_used: Whether this is a fallback execution

        Raises:
            PipelineStageError: If event generation fails for any year

        Notes:
            - Uses tag:EVENT_GENERATION for model selection
            - Excludes STATE_ACCUMULATION models incorrectly tagged EVENT_GENERATION
            - Queries database to count events per year for statistics
            - Supports sharded execution for large datasets
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
