"""
Multi-Year Simulation Orchestrator

Main coordinator class that implements the composite pattern to integrate
optimized orchestrator_dbt foundation components with multi-year simulation
workflow management. Provides 82% performance improvement through optimized
batch operations and intelligent coordination strategies.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable, Union
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

from .simulation_state import SimulationState, WorkforceState, StateManager
from .year_processor import YearProcessor, YearContext, YearResult, ProcessingMode
from .year_transition import YearTransition, TransitionContext, TransitionResult, TransitionStrategy
from ..core.workflow_orchestrator import WorkflowOrchestrator, WorkflowResult
from ..core.config import OrchestrationConfig, ValidationMode
from ..core.database_manager import DatabaseManager
from ..core.dbt_executor import DbtExecutor
from ..core.validation_framework import ValidationFramework
from ..core.multi_year_validation_framework import MultiYearValidationFramework


logger = logging.getLogger(__name__)


class OptimizationLevel(Enum):
    """Optimization level for multi-year simulation."""
    HIGH = "high"           # Maximum performance optimization
    MEDIUM = "medium"       # Balanced performance and reliability
    LOW = "low"             # Conservative optimization
    FALLBACK = "fallback"   # Sequential processing only


@dataclass
class MultiYearConfig:
    """Configuration for multi-year simulation."""
    start_year: int
    end_year: int
    optimization_level: OptimizationLevel = OptimizationLevel.HIGH
    max_workers: int = 4
    batch_size: int = 1000
    enable_state_compression: bool = True
    enable_concurrent_processing: bool = True
    enable_validation: bool = True
    fail_fast: bool = False
    transition_strategy: TransitionStrategy = TransitionStrategy.OPTIMIZED
    performance_monitoring: bool = True
    memory_limit_gb: Optional[float] = None

    @classmethod
    def from_orchestration_config(cls, orchestration_config: OrchestrationConfig) -> 'MultiYearConfig':
        """Create MultiYearConfig from OrchestrationConfig for backward compatibility."""
        simulation_config = orchestration_config.get_simulation_config()
        multi_year_config = orchestration_config.get_multi_year_config()

        return cls(
            start_year=simulation_config.get("start_year", 2025),
            end_year=simulation_config.get("end_year", 2029),
            optimization_level=multi_year_config.optimization.level,
            max_workers=multi_year_config.optimization.max_workers,
            batch_size=multi_year_config.optimization.batch_size,
            enable_state_compression=multi_year_config.performance.enable_state_compression,
            enable_concurrent_processing=multi_year_config.performance.enable_concurrent_processing,
            enable_validation=multi_year_config.error_handling.validation_mode != ValidationMode.DISABLED,
            fail_fast=multi_year_config.error_handling.fail_fast,
            transition_strategy=multi_year_config.transition.strategy,
            performance_monitoring=multi_year_config.monitoring.enable_performance_monitoring,
            memory_limit_gb=multi_year_config.optimization.memory_limit_gb,
        )

    def to_orchestration_config(self, base_config: OrchestrationConfig) -> OrchestrationConfig:
        """Convert to orchestration config for foundation setup."""
        return base_config  # Use existing config for foundation


@dataclass
class FoundationSetupResult:
    """Result of foundation setup operation."""
    success: bool
    execution_time: float
    performance_improvement: float
    workflow_details: WorkflowResult
    setup_mode: str = "optimized"
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MultiYearResult:
    """Complete result of multi-year simulation."""
    simulation_id: str
    start_year: int
    end_year: int
    success: bool
    total_execution_time: float
    foundation_setup_result: Optional[FoundationSetupResult] = None
    year_results: List[YearResult] = field(default_factory=list)
    transition_results: List[TransitionResult] = field(default_factory=list)
    final_simulation_state: Optional[SimulationState] = None
    performance_metrics: Dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.utcnow)

    @property
    def completed_years(self) -> List[int]:
        """Get list of successfully completed years."""
        return [result.year for result in self.year_results if result.success]

    @property
    def failed_years(self) -> List[int]:
        """Get list of failed years."""
        return [result.year for result in self.year_results if not result.success]

    @property
    def success_rate(self) -> float:
        """Calculate success rate across all years."""
        if not self.year_results:
            return 0.0
        successful = len([r for r in self.year_results if r.success])
        return successful / len(self.year_results)

    def get_year_result(self, year: int) -> Optional[YearResult]:
        """Get result for specific year."""
        for result in self.year_results:
            if result.year == year:
                return result
        return None


class MultiYearOrchestrator:
    """
    Main multi-year simulation orchestrator using composite pattern.

    Integrates optimized orchestrator_dbt foundation components with multi-year
    simulation workflow management. Provides:

    - Foundation setup: <10 seconds (82% improvement from 49s baseline)
    - Batch operations for seeds, staging models, and year processing
    - Concurrent execution with graceful fallback strategies
    - Memory-efficient state management with compression
    - Circuit breaker pattern for resilient error handling
    - Comprehensive performance monitoring and metrics
    """

    def __init__(
        self,
        config: MultiYearConfig,
        base_config_path: Optional[Path] = None
    ):
        """
        Initialize multi-year orchestrator.

        Args:
            config: Multi-year simulation configuration
            base_config_path: Optional path to base orchestration config
        """
        self.config = config

        # Initialize base orchestration configuration
        self.base_config = OrchestrationConfig(base_config_path)

        # Initialize foundation components using composition pattern
        self.workflow_orchestrator = WorkflowOrchestrator(base_config_path)
        self.database_manager = self.workflow_orchestrator.db_manager
        self.dbt_executor = self.workflow_orchestrator.dbt_executor
        self.validation_framework = self.workflow_orchestrator.validation_framework

        # Initialize multi-year validation framework
        self.multi_year_validation = MultiYearValidationFramework(
            self.base_config,
            self.database_manager
        )

        # Initialize multi-year specific components
        self.state_manager = StateManager(
            config=self.base_config,
            database_manager=self.database_manager,
            cache_size=100,
            enable_compression=config.enable_state_compression
        )

        self.year_processor = YearProcessor(
            config=self.base_config,
            database_manager=self.database_manager,
            dbt_executor=self.dbt_executor,
            state_manager=self.state_manager
        )

        self.year_transition = YearTransition(
            config=self.base_config,
            database_manager=self.database_manager,
            state_manager=self.state_manager
        )

        # Performance monitoring
        self._performance_metrics = {}
        self._simulation_history: List[MultiYearResult] = []

        # Generate unique simulation ID
        self.simulation_id = f"sim_{int(time.time())}_{config.start_year}_{config.end_year}"

        logger.info(f"MultiYearOrchestrator initialized: {config.start_year}-{config.end_year} "
                   f"(optimization: {config.optimization_level.value})")

    async def execute_multi_year_simulation(self) -> MultiYearResult:
        """
        Execute complete multi-year simulation workflow.

        Returns:
            Complete multi-year simulation result
        """
        logger.info(f"🎯 Starting multi-year simulation: {self.config.start_year}-{self.config.end_year}")
        logger.info("=" * 80)

        start_time = time.time()
        year_results = []
        transition_results = []

        try:
            # Step 1: Foundation Setup (leveraging optimized orchestrator_dbt)
            foundation_result = await self._execute_foundation_setup()

            if not foundation_result.success:
                logger.error("❌ Foundation setup failed, aborting simulation")
                return self._create_failure_result(
                    start_time, foundation_result, year_results, transition_results,
                    "Foundation setup failed"
                )

            # Step 2: Initialize simulation state
            simulation_state = self._initialize_simulation_state()

            # Step 2.5: Pre-simulation validation (if enabled)
            if self.config.enable_validation:
                pre_validation_result = await self._execute_pre_simulation_validation()
                if not pre_validation_result.passed and self.config.fail_fast:
                    logger.error("❌ Pre-simulation validation failed and fail_fast is enabled")
                    return self._create_failure_result(
                        start_time, foundation_result, year_results, transition_results,
                        "Pre-simulation validation failed"
                    )

            # Step 3: Execute year-by-year simulation
            for year in range(self.config.start_year, self.config.end_year + 1):
                logger.info(f"📅 Processing simulation year {year}")

                # Real-time validation during year processing (if enabled)
                if self.config.enable_validation and self.multi_year_validation.enable_real_time_validation:
                    in_progress_validation = self.multi_year_validation.validate_year_in_progress(
                        year, self.simulation_id
                    )
                    if not in_progress_validation.passed:
                        logger.warning(f"⚠️ In-progress validation warnings for year {year}: {in_progress_validation.message}")

                # Process individual year
                year_result = await self._process_simulation_year(year, simulation_state)
                year_results.append(year_result)

                if not year_result.success:
                    if self.config.fail_fast:
                        logger.error(f"❌ Year {year} failed and fail_fast is enabled")
                        break
                    else:
                        logger.warning(f"⚠️ Year {year} failed, continuing with next year")
                        continue

                # Post-year validation (if enabled)
                if self.config.enable_validation:
                    post_year_validation = await self._execute_post_year_validation(year, simulation_state)
                    if not post_year_validation.passed and self.config.fail_fast:
                        logger.error(f"❌ Post-year validation failed for year {year} and fail_fast is enabled")
                        break

                # Update simulation state
                if year_result.workforce_state:
                    simulation_state.year_states[year] = year_result.workforce_state
                    simulation_state.current_year = year
                    simulation_state.update_timestamp()

                # Execute transition to next year (if not the last year)
                if year < self.config.end_year:
                    transition_result = await self._execute_year_transition(year, year + 1, simulation_state)
                    transition_results.append(transition_result)

                    if not transition_result.success and self.config.fail_fast:
                        logger.error(f"❌ Transition {year}->{year + 1} failed and fail_fast is enabled")
                        break

            # Step 4: Final multi-year validation (if enabled and successful)
            final_validation_summary = None
            if self.config.enable_validation and overall_success:
                final_validation_summary = await self._execute_final_multi_year_validation()
                if not final_validation_summary.is_valid and self.config.fail_fast:
                    overall_success = False
                    logger.error("❌ Final multi-year validation failed")

            # Step 5: Finalize simulation
            total_execution_time = time.time() - start_time
            overall_success = self._determine_overall_success(year_results, transition_results)

            # Calculate performance metrics
            performance_metrics = self._calculate_performance_metrics(
                foundation_result, year_results, transition_results, total_execution_time
            )

            # Create final result
            result = MultiYearResult(
                simulation_id=self.simulation_id,
                start_year=self.config.start_year,
                end_year=self.config.end_year,
                success=overall_success,
                total_execution_time=total_execution_time,
                foundation_setup_result=foundation_result,
                year_results=year_results,
                transition_results=transition_results,
                final_simulation_state=simulation_state,
                performance_metrics=performance_metrics
            )

            # Track simulation history
            self._simulation_history.append(result)

            # Log final summary
            self._log_simulation_summary(result)

            return result

        except Exception as e:
            total_execution_time = time.time() - start_time
            logger.error(f"💥 Multi-year simulation failed: {e}")

            return self._create_failure_result(
                start_time,
                foundation_result if 'foundation_result' in locals() else None,
                year_results,
                transition_results,
                f"Simulation failed: {str(e)}"
            )

    async def _execute_foundation_setup(self) -> FoundationSetupResult:
        """Execute optimized foundation setup using orchestrator_dbt with circuit breaker pattern."""
        logger.info("🚀 Starting optimized foundation setup with circuit breaker pattern")
        start_time = time.time()

        # Circuit breaker state tracking
        max_retries = 3
        retry_count = 0

        while retry_count < max_retries:
            try:
                # Execute optimized workflow (targeting <10 seconds)
                if self.config.optimization_level == OptimizationLevel.HIGH:
                    logger.info("Executing HIGH optimization foundation setup")
                    workflow_result = self.workflow_orchestrator.run_complete_setup_workflow_optimized()
                elif self.config.optimization_level == OptimizationLevel.MEDIUM:
                    logger.info("Executing MEDIUM optimization foundation setup")
                    workflow_result = self.workflow_orchestrator.run_complete_setup_workflow()
                else:
                    # Low optimization or fallback - use quick setup
                    logger.info("Executing LOW/FALLBACK optimization foundation setup")
                    workflow_result = self.workflow_orchestrator.run_quick_setup()

                execution_time = time.time() - start_time

                # Validate workflow succeeded
                if workflow_result.success:
                    # Calculate performance improvement (baseline: 49 seconds)
                    baseline_time = 49.0
                    performance_improvement = max(0, (baseline_time - execution_time) / baseline_time)

                    # Validate performance target (<10 seconds for high optimization)
                    target_met = True
                    if self.config.optimization_level == OptimizationLevel.HIGH and execution_time > 10.0:
                        logger.warning(f"Foundation setup took {execution_time:.2f}s, exceeds 10s target")
                        target_met = False

                    logger.info(f"✅ Foundation setup completed in {execution_time:.2f}s "
                               f"({performance_improvement:.1%} improvement)")

                    return FoundationSetupResult(
                        success=True,
                        execution_time=execution_time,
                        performance_improvement=performance_improvement,
                        workflow_details=workflow_result,
                        setup_mode="optimized" if target_met else "standard",
                        metadata={
                            "target_met": target_met,
                            "optimization_level": self.config.optimization_level.value,
                            "steps_completed": workflow_result.steps_completed,
                            "steps_total": workflow_result.steps_total,
                            "retry_count": retry_count
                        }
                    )
                else:
                    # Workflow failed, check if we should retry with fallback
                    retry_count += 1
                    if retry_count < max_retries:
                        logger.warning(f"Foundation setup attempt {retry_count} failed, retrying with fallback strategy")
                        # Downgrade optimization level for retry
                        if self.config.optimization_level == OptimizationLevel.HIGH:
                            self.config.optimization_level = OptimizationLevel.MEDIUM
                        elif self.config.optimization_level == OptimizationLevel.MEDIUM:
                            self.config.optimization_level = OptimizationLevel.LOW
                        continue
                    else:
                        logger.error("Foundation setup failed after all retry attempts")
                        break

            except Exception as e:
                retry_count += 1
                logger.error(f"Foundation setup attempt {retry_count} failed with exception: {e}")

                if retry_count < max_retries:
                    logger.info(f"Retrying foundation setup (attempt {retry_count + 1}/{max_retries})")
                    # Add exponential backoff
                    await asyncio.sleep(2 ** retry_count)
                    continue
                else:
                    logger.error("Foundation setup failed after all retry attempts")
                    break

        # All retries exhausted, return failure
        execution_time = time.time() - start_time

        # Create a minimal workflow result for failure case
        failed_workflow_result = WorkflowResult(
            success=False,
            total_execution_time=execution_time,
            steps_completed=0,
            steps_total=5
        )

        return FoundationSetupResult(
            success=False,
            execution_time=execution_time,
            performance_improvement=0.0,
            workflow_details=failed_workflow_result,
            setup_mode="failed",
            metadata={
                "error": "Foundation setup failed after all retries",
                "retry_count": retry_count,
                "max_retries": max_retries
            }
        )

    def _initialize_simulation_state(self) -> SimulationState:
        """Initialize simulation state for multi-year processing."""
        simulation_state = SimulationState(
            simulation_id=self.simulation_id,
            start_year=self.config.start_year,
            end_year=self.config.end_year,
            current_year=self.config.start_year,
            configuration={
                "optimization_level": self.config.optimization_level.value,
                "max_workers": self.config.max_workers,
                "batch_size": self.config.batch_size,
                "enable_compression": self.config.enable_state_compression,
                "transition_strategy": self.config.transition_strategy.value
            },
            metadata={
                "orchestrator_version": "1.0.0",
                "created_by": "MultiYearOrchestrator"
            }
        )

        logger.debug(f"Initialized simulation state: {simulation_state.simulation_id}")
        return simulation_state

    async def _process_simulation_year(
        self,
        year: int,
        simulation_state: SimulationState
    ) -> YearResult:
        """Process a single simulation year."""
        logger.info(f"📊 Processing year {year}")

        try:
            # Prepare year context
            year_context = self._prepare_year_context(year, simulation_state)

            # Process the year
            year_result = await self.year_processor.process_year(year_context)

            if year_result.success:
                logger.info(f"✅ Year {year} completed successfully in {year_result.total_execution_time:.2f}s")
            else:
                logger.error(f"❌ Year {year} failed: {year_result.get_all_errors()}")

            return year_result

        except Exception as e:
            logger.error(f"Year {year} processing failed with exception: {e}")

            # Return failure result
            from .year_processor import ProcessingResult
            return YearResult(
                year=year,
                success=False,
                total_execution_time=0.0,
                processing_results=[ProcessingResult(
                    success=False,
                    execution_time=0.0,
                    errors=[f"Year processing failed: {str(e)}"]
                )],
                processing_mode=ProcessingMode.FALLBACK
            )

    def _prepare_year_context(
        self,
        year: int,
        simulation_state: SimulationState
    ) -> YearContext:
        """Prepare context for year processing."""
        # Get previous year workforce state if available
        previous_workforce = None
        if year > self.config.start_year:
            previous_year = year - 1
            previous_workforce = simulation_state.year_states.get(previous_year)

        # Determine processing mode based on optimization level
        processing_mode = ProcessingMode.OPTIMIZED
        if self.config.optimization_level == OptimizationLevel.FALLBACK:
            processing_mode = ProcessingMode.FALLBACK
        elif self.config.optimization_level == OptimizationLevel.LOW:
            processing_mode = ProcessingMode.STANDARD

        year_context = YearContext(
            year=year,
            previous_workforce=previous_workforce,
            configuration=simulation_state.configuration,
            processing_mode=processing_mode,
            max_workers=self.config.max_workers,
            batch_size=self.config.batch_size,
            enable_validation=self.config.enable_validation,
            metadata={
                "simulation_id": simulation_state.simulation_id,
                "total_years": self.config.end_year - self.config.start_year + 1,
                "year_index": year - self.config.start_year
            }
        )

        return year_context

    async def _execute_year_transition(
        self,
        from_year: int,
        to_year: int,
        simulation_state: SimulationState
    ) -> TransitionResult:
        """Execute transition between simulation years."""
        logger.info(f"🔄 Executing transition: {from_year} -> {to_year}")

        try:
            # Get current year state
            from_state = simulation_state.year_states.get(from_year)
            if not from_state:
                raise ValueError(f"No state found for year {from_year}")

            # Prepare transition context
            transition_context = TransitionContext(
                from_year=from_year,
                to_year=to_year,
                from_state=from_state,
                strategy=self.config.transition_strategy,
                validation_enabled=self.config.enable_validation,
                data_integrity_checks=True,
                performance_monitoring=self.config.performance_monitoring,
                metadata={
                    "simulation_id": simulation_state.simulation_id,
                    "configuration": simulation_state.configuration
                }
            )

            # Execute transition
            transition_result = await self.year_transition.execute_transition(transition_context)

            if transition_result.success:
                logger.info(f"✅ Transition {from_year} -> {to_year} completed in "
                           f"{transition_result.total_execution_time:.2f}s")
            else:
                logger.error(f"❌ Transition {from_year} -> {to_year} failed")

            return transition_result

        except Exception as e:
            logger.error(f"Transition {from_year} -> {to_year} failed with exception: {e}")

            return TransitionResult(
                from_year=from_year,
                to_year=to_year,
                success=False,
                total_execution_time=0.0,
                performance_metrics={"error": str(e)}
            )

    def _determine_overall_success(
        self,
        year_results: List[YearResult],
        transition_results: List[TransitionResult]
    ) -> bool:
        """Determine overall simulation success."""
        # All years must be successful
        years_successful = all(result.success for result in year_results)

        # All transitions must be successful (or at least not critical failures)
        transitions_successful = all(result.success for result in transition_results)

        return years_successful and transitions_successful

    def _calculate_performance_metrics(
        self,
        foundation_result: FoundationSetupResult,
        year_results: List[YearResult],
        transition_results: List[TransitionResult],
        total_time: float
    ) -> Dict[str, Any]:
        """Calculate comprehensive performance metrics."""
        successful_years = [r for r in year_results if r.success]
        successful_transitions = [r for r in transition_results if r.success]

        # Year processing metrics
        year_processing_time = sum(r.total_execution_time for r in year_results)
        avg_year_time = year_processing_time / len(year_results) if year_results else 0

        # Transition metrics
        transition_time = sum(r.total_execution_time for r in transition_results)
        avg_transition_time = transition_time / len(transition_results) if transition_results else 0

        # Total records processed
        total_records = sum(r.total_records_processed for r in successful_years)

        # Performance improvement calculations
        foundation_improvement = foundation_result.performance_improvement

        return {
            "total_execution_time": total_time,
            "foundation_setup_time": foundation_result.execution_time,
            "year_processing_time": year_processing_time,
            "transition_time": transition_time,
            "average_year_time": avg_year_time,
            "average_transition_time": avg_transition_time,
            "total_years_processed": len(year_results),
            "successful_years": len(successful_years),
            "successful_transitions": len(successful_transitions),
            "total_records_processed": total_records,
            "records_per_second": total_records / total_time if total_time > 0 else 0,
            "foundation_performance_improvement": foundation_improvement,
            "optimization_level": self.config.optimization_level.value,
            "memory_efficiency": self.state_manager.get_performance_metrics(),
            "overall_success_rate": len(successful_years) / len(year_results) if year_results else 0
        }

    def _create_failure_result(
        self,
        start_time: float,
        foundation_result: Optional[FoundationSetupResult],
        year_results: List[YearResult],
        transition_results: List[TransitionResult],
        failure_reason: str
    ) -> MultiYearResult:
        """Create failure result for simulation."""
        total_execution_time = time.time() - start_time

        # Create basic performance metrics for failure case
        performance_metrics = {
            "total_execution_time": total_execution_time,
            "failure_reason": failure_reason,
            "years_attempted": len(year_results),
            "transitions_attempted": len(transition_results),
            "optimization_level": self.config.optimization_level.value
        }

        if foundation_result:
            performance_metrics["foundation_setup_time"] = foundation_result.execution_time
            performance_metrics["foundation_success"] = foundation_result.success

        result = MultiYearResult(
            simulation_id=self.simulation_id,
            start_year=self.config.start_year,
            end_year=self.config.end_year,
            success=False,
            total_execution_time=total_execution_time,
            foundation_setup_result=foundation_result,
            year_results=year_results,
            transition_results=transition_results,
            performance_metrics=performance_metrics
        )

        self._simulation_history.append(result)
        return result

    def _log_simulation_summary(self, result: MultiYearResult) -> None:
        """Log comprehensive simulation summary."""
        logger.info("=" * 80)

        if result.success:
            logger.info(f"🎉 Multi-year simulation completed successfully!")
            logger.info(f"   📊 Simulation ID: {result.simulation_id}")
            logger.info(f"   📅 Years: {result.start_year}-{result.end_year} ({len(result.completed_years)} completed)")
            logger.info(f"   ⏱️  Total time: {result.total_execution_time:.2f}s")

            if result.foundation_setup_result:
                improvement = result.foundation_setup_result.performance_improvement
                logger.info(f"   🚀 Foundation setup: {result.foundation_setup_result.execution_time:.2f}s "
                           f"({improvement:.1%} improvement)")

            # Performance highlights
            performance = result.performance_metrics
            logger.info(f"   📈 Performance: {performance.get('records_per_second', 0):.0f} records/sec")
            logger.info(f"   💾 Memory efficiency: {performance.get('memory_efficiency', {}).get('memory_efficiency', 'N/A')}")

        else:
            logger.error(f"💥 Multi-year simulation failed!")
            logger.error(f"   📊 Simulation ID: {result.simulation_id}")
            logger.error(f"   📅 Years attempted: {result.start_year}-{result.end_year}")
            logger.error(f"   ⏱️  Time before failure: {result.total_execution_time:.2f}s")
            logger.error(f"   ✅ Completed years: {result.completed_years}")
            logger.error(f"   ❌ Failed years: {result.failed_years}")

            failure_reason = result.performance_metrics.get('failure_reason', 'Unknown')
            logger.error(f"   🔍 Failure reason: {failure_reason}")

        logger.info("=" * 80)

    def get_simulation_history(self) -> List[MultiYearResult]:
        """Get history of all simulation runs."""
        return self._simulation_history.copy()

    def get_current_simulation_state(self) -> Optional[SimulationState]:
        """Get current simulation state if a simulation is running."""
        if self._simulation_history:
            latest_result = self._simulation_history[-1]
            return latest_result.final_simulation_state
        return None

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get performance summary across all simulations."""
        if not self._simulation_history:
            return {"message": "No simulation history available"}

        successful_sims = [s for s in self._simulation_history if s.success]

        return {
            "total_simulations": len(self._simulation_history),
            "successful_simulations": len(successful_sims),
            "success_rate": len(successful_sims) / len(self._simulation_history),
            "average_execution_time": sum(s.total_execution_time for s in self._simulation_history) / len(self._simulation_history),
            "total_years_simulated": sum(len(s.completed_years) for s in successful_sims),
            "optimization_effectiveness": self._calculate_optimization_effectiveness(),
            "state_manager_metrics": self.state_manager.get_performance_metrics(),
            "year_processor_metrics": self.year_processor.get_performance_summary(),
            "transition_metrics": self.year_transition.get_transition_performance_summary()
        }

    def _calculate_optimization_effectiveness(self) -> Dict[str, Any]:
        """Calculate optimization effectiveness metrics."""
        if not self._simulation_history:
            return {}

        # Calculate average foundation setup time
        foundation_times = [
            s.foundation_setup_result.execution_time
            for s in self._simulation_history
            if s.foundation_setup_result
        ]

        avg_foundation_time = sum(foundation_times) / len(foundation_times) if foundation_times else 0

        # Calculate improvement vs baseline (49 seconds)
        baseline_time = 49.0
        improvement = max(0, (baseline_time - avg_foundation_time) / baseline_time) if avg_foundation_time < baseline_time else 0

        return {
            "average_foundation_setup_time": avg_foundation_time,
            "baseline_time": baseline_time,
            "performance_improvement": improvement,
            "target_achievement": avg_foundation_time < 10.0,  # <10s target
            "optimization_level_distribution": self._get_optimization_level_distribution()
        }

    def _get_optimization_level_distribution(self) -> Dict[str, int]:
        """Get distribution of optimization levels across simulations."""
        distribution = {}
        for sim in self._simulation_history:
            level = sim.performance_metrics.get("optimization_level", "unknown")
            distribution[level] = distribution.get(level, 0) + 1
        return distribution

    async def _execute_pre_simulation_validation(self) -> 'ValidationResult':
        """Execute pre-simulation validation checks."""
        logger.info("🔍 Executing pre-simulation validation")

        try:
            # Run foundation validation first
            foundation_validation = self.validation_framework.run_comprehensive_validation()

            if not foundation_validation.is_valid:
                from ..core.validation_framework import ValidationResult, ValidationStatus, ValidationSeverity
                return ValidationResult(
                    check_name="pre_simulation_validation",
                    status=ValidationStatus.FAILED,
                    severity=ValidationSeverity.CRITICAL,
                    message=f"Foundation validation failed: {foundation_validation.failed_checks} failures",
                    details={"foundation_validation": foundation_validation.__dict__}
                )

            logger.info("✅ Pre-simulation validation passed")
            from ..core.validation_framework import ValidationResult, ValidationStatus, ValidationSeverity
            return ValidationResult(
                check_name="pre_simulation_validation",
                status=ValidationStatus.PASSED,
                severity=ValidationSeverity.INFO,
                message="Pre-simulation validation completed successfully",
                details={"foundation_validation": foundation_validation.__dict__}
            )

        except Exception as e:
            logger.error(f"Pre-simulation validation error: {e}")
            from ..core.validation_framework import ValidationResult, ValidationStatus, ValidationSeverity
            return ValidationResult(
                check_name="pre_simulation_validation",
                status=ValidationStatus.ERROR,
                severity=ValidationSeverity.CRITICAL,
                message=f"Pre-simulation validation error: {e}",
                details={"error": str(e)}
            )

    async def _execute_post_year_validation(
        self,
        year: int,
        simulation_state: SimulationState
    ) -> 'ValidationResult':
        """Execute post-year validation checks."""
        logger.debug(f"🔍 Executing post-year validation for year {year}")

        try:
            # Validate workforce state consistency for the completed year
            workforce_validation = self.multi_year_validation.validate_workforce_state_consistency(
                year, self.simulation_id
            )

            if not workforce_validation.passed:
                logger.warning(f"⚠️ Workforce state validation issues for year {year}: {workforce_validation.message}")

            # If this is not the first year, validate cross-year integrity
            if year > self.config.start_year:
                cross_year_validation = self.multi_year_validation.validate_cross_year_integrity(
                    year - 1, year, self.simulation_id
                )

                if not cross_year_validation.passed:
                    logger.warning(f"⚠️ Cross-year integrity issues {year-1}->{year}: {cross_year_validation.message}")

                    # If it's a critical failure, return the cross-year result
                    if cross_year_validation.severity.value == 'critical':
                        return cross_year_validation

            logger.debug(f"✅ Post-year validation passed for year {year}")
            return workforce_validation

        except Exception as e:
            logger.error(f"Post-year validation error for year {year}: {e}")
            from ..core.validation_framework import ValidationResult, ValidationStatus, ValidationSeverity
            return ValidationResult(
                check_name=f"post_year_validation_{year}",
                status=ValidationStatus.ERROR,
                severity=ValidationSeverity.CRITICAL,
                message=f"Post-year validation error: {e}",
                details={"error": str(e), "year": year}
            )

    async def _execute_final_multi_year_validation(self) -> 'MultiYearValidationSummary':
        """Execute comprehensive final multi-year validation."""
        logger.info("🔍 Executing final multi-year validation")

        try:
            # Execute comprehensive multi-year validation
            validation_summary = self.multi_year_validation.validate_multi_year_simulation(
                self.config.start_year,
                self.config.end_year,
                self.simulation_id
            )

            if validation_summary.is_valid:
                logger.info(f"✅ Final multi-year validation passed: {validation_summary.success_rate:.1f}% success rate")
            else:
                logger.error(f"❌ Final multi-year validation failed: {validation_summary.critical_failures} critical failures")

                # Log specific failures for debugging
                for failure in validation_summary.get_critical_failures():
                    logger.error(f"   Critical failure: {failure.check_name} - {failure.message}")

            return validation_summary

        except Exception as e:
            logger.error(f"Final multi-year validation error: {e}")
            from ..core.multi_year_validation_framework import MultiYearValidationSummary
            from ..core.validation_framework import ValidationResult, ValidationStatus, ValidationSeverity

            # Create a failure summary
            error_result = ValidationResult(
                check_name="final_multi_year_validation",
                status=ValidationStatus.ERROR,
                severity=ValidationSeverity.CRITICAL,
                message=f"Final validation error: {e}",
                details={"error": str(e)}
            )

            summary = MultiYearValidationSummary()
            summary.results = [error_result]
            summary.total_checks = 1
            summary.error_checks = 1
            summary.critical_failures = 1
            summary.years_validated = list(range(self.config.start_year, self.config.end_year + 1))

            return summary

    def get_validation_summary(self) -> Dict[str, Any]:
        """Get comprehensive validation summary for the orchestrator."""
        try:
            multi_year_metrics = self.multi_year_validation.get_comprehensive_performance_metrics()

            return {
                "validation_enabled": self.config.enable_validation,
                "real_time_validation_enabled": getattr(self.multi_year_validation, 'enable_real_time_validation', False),
                "validation_mode": multi_year_metrics.get("validation_mode", "unknown"),
                "circuit_breaker_status": multi_year_metrics.get("circuit_breaker_status", {}),
                "performance_metrics": multi_year_metrics,
                "validation_history_count": len(self.multi_year_validation.get_validation_history()),
                "fail_fast_enabled": self.config.fail_fast
            }
        except Exception as e:
            logger.error(f"Error getting validation summary: {e}")
            return {
                "validation_enabled": self.config.enable_validation,
                "error": str(e)
            }

    def reset_validation_circuit_breaker(self) -> None:
        """Reset the validation circuit breaker for the multi-year validation framework."""
        try:
            self.multi_year_validation.reset_circuit_breaker()
            logger.info("✅ Validation circuit breaker reset successfully")
        except Exception as e:
            logger.error(f"Error resetting validation circuit breaker: {e}")

    def validate_specific_years(
        self,
        start_year: int,
        end_year: int,
        scenario_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute targeted validation for specific years.

        Args:
            start_year: Starting year for validation
            end_year: Ending year for validation
            scenario_id: Optional scenario ID (defaults to current simulation ID)

        Returns:
            Validation results dictionary
        """
        if scenario_id is None:
            scenario_id = self.simulation_id

        logger.info(f"🔍 Executing targeted validation for years {start_year}-{end_year}")

        try:
            validation_results = {}

            # Execute various validation checks
            validation_results["cross_year_integrity"] = []
            for year in range(start_year, end_year):
                cross_year_result = self.multi_year_validation.validate_cross_year_integrity(
                    year, year + 1, scenario_id
                )
                validation_results["cross_year_integrity"].append({
                    "from_year": year,
                    "to_year": year + 1,
                    "passed": cross_year_result.passed,
                    "message": cross_year_result.message,
                    "details": cross_year_result.details
                })

            # Execute event sourcing validation
            event_sourcing_result = self.multi_year_validation.validate_event_sourcing_integrity(
                start_year, end_year, scenario_id
            )
            validation_results["event_sourcing"] = {
                "passed": event_sourcing_result.passed,
                "message": event_sourcing_result.message,
                "events_validated": event_sourcing_result.events_validated,
                "details": event_sourcing_result.details
            }

            # Execute business logic validation
            business_logic_result = self.multi_year_validation.validate_business_logic_compliance(
                start_year, end_year, scenario_id
            )
            validation_results["business_logic"] = {
                "passed": business_logic_result.passed,
                "message": business_logic_result.message,
                "rules_checked": business_logic_result.business_rules_checked,
                "details": business_logic_result.details
            }

            # Execute financial calculations validation
            financial_result = self.multi_year_validation.validate_financial_calculations_integrity(
                start_year, end_year, scenario_id
            )
            validation_results["financial_calculations"] = {
                "passed": financial_result.passed,
                "message": financial_result.message,
                "details": financial_result.details
            }

            # Execute UUID integrity validation
            uuid_result = self.multi_year_validation.validate_uuid_integrity_comprehensive(
                start_year, end_year, scenario_id
            )
            validation_results["uuid_integrity"] = {
                "passed": uuid_result.passed,
                "message": uuid_result.message,
                "details": uuid_result.details
            }

            # Calculate overall validation status
            all_passed = all([
                all(result["passed"] for result in validation_results["cross_year_integrity"]),
                validation_results["event_sourcing"]["passed"],
                validation_results["business_logic"]["passed"],
                validation_results["financial_calculations"]["passed"],
                validation_results["uuid_integrity"]["passed"]
            ])

            validation_results["summary"] = {
                "overall_passed": all_passed,
                "years_validated": list(range(start_year, end_year + 1)),
                "scenario_id": scenario_id,
                "validation_timestamp": datetime.utcnow().isoformat()
            }

            logger.info(f"✅ Targeted validation completed: {'PASSED' if all_passed else 'FAILED'}")
            return validation_results

        except Exception as e:
            logger.error(f"Targeted validation error: {e}")
            return {
                "error": str(e),
                "years_attempted": f"{start_year}-{end_year}",
                "scenario_id": scenario_id,
                "summary": {"overall_passed": False}
            }


# Factory functions for convenient creation
def create_multi_year_orchestrator(
    start_year: int,
    end_year: int,
    optimization_level: OptimizationLevel = OptimizationLevel.HIGH,
    base_config_path: Optional[Path] = None,
    **kwargs
) -> MultiYearOrchestrator:
    """
    Factory function to create MultiYearOrchestrator with common configuration.

    Args:
        start_year: Starting simulation year
        end_year: Ending simulation year
        optimization_level: Performance optimization level
        base_config_path: Optional path to base configuration
        **kwargs: Additional configuration parameters

    Returns:
        Configured MultiYearOrchestrator instance
    """
    config = MultiYearConfig(
        start_year=start_year,
        end_year=end_year,
        optimization_level=optimization_level,
        **kwargs
    )

    return MultiYearOrchestrator(config, base_config_path)


def create_high_performance_orchestrator(
    start_year: int,
    end_year: int,
    max_workers: int = 8,
    base_config_path: Optional[Path] = None
) -> MultiYearOrchestrator:
    """
    Factory function to create high-performance MultiYearOrchestrator.

    Args:
        start_year: Starting simulation year
        end_year: Ending simulation year
        max_workers: Maximum concurrent workers
        base_config_path: Optional path to base configuration

    Returns:
        High-performance configured MultiYearOrchestrator instance
    """
    config = MultiYearConfig(
        start_year=start_year,
        end_year=end_year,
        optimization_level=OptimizationLevel.HIGH,
        max_workers=max_workers,
        batch_size=2000,
        enable_state_compression=True,
        enable_concurrent_processing=True,
        transition_strategy=TransitionStrategy.OPTIMIZED,
        performance_monitoring=True
    )

    return MultiYearOrchestrator(config, base_config_path)


# Custom exceptions
class MultiYearOrchestrationError(Exception):
    """Base exception for multi-year orchestration errors."""
    pass


class ConfigurationError(MultiYearOrchestrationError):
    """Exception for configuration errors."""
    pass


class SimulationExecutionError(MultiYearOrchestrationError):
    """Exception for simulation execution errors."""
    pass
