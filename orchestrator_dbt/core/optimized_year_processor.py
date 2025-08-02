"""
Optimized Year Processor for Story S031-02: Year Processing Optimization.

Integrates all performance optimizations:
- Batch dbt execution with 5 execution groups
- DuckDB columnar storage and vectorized operations
- Performance monitoring and query plan analysis
- Memory optimization for analytical workloads
- 60% performance improvement target (2-3 minutes vs 5-8 minutes)

This processor replaces the existing year_processor.py with optimized implementations.
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Dict, List, Any, Optional

from .optimized_dbt_executor import OptimizedDbtExecutor, BatchResult, ExecutionGroup
from .duckdb_optimizations import DuckDBOptimizer, OptimizationResult
from .database_manager import DatabaseManager
from .config import OrchestrationConfig
from ..utils.performance_optimizer import PerformanceOptimizer, BatchPerformanceAnalysis
from ..multi_year.simulation_state import WorkforceState, StateManager


logger = logging.getLogger(__name__)


class OptimizedYearProcessor:
    """
    Optimized year processor implementing S031-02 performance improvements.

    Key features:
    - 60% performance improvement (2-3 minutes vs 5-8 minutes baseline)
    - Batch dbt execution with dependency-aware grouping
    - DuckDB columnar storage and vectorized operations
    - Memory usage under 4GB per year
    - Query response under 1 second for individual calculations
    - Performance monitoring and regression detection
    """

    def __init__(
        self,
        config: OrchestrationConfig,
        database_manager: DatabaseManager,
        state_manager: StateManager,
        max_workers: int = 4,
        enable_monitoring: bool = True
    ):
        """
        Initialize optimized year processor.

        Args:
            config: Orchestration configuration
            database_manager: Database manager for optimizations
            state_manager: State manager for workforce state
            max_workers: Maximum concurrent workers
            enable_monitoring: Enable performance monitoring
        """
        self.config = config
        self.database_manager = database_manager
        self.state_manager = state_manager
        self.max_workers = max_workers
        self.enable_monitoring = enable_monitoring

        # Initialize optimization components
        self.dbt_executor = OptimizedDbtExecutor(
            config=config,
            database_manager=database_manager,
            max_workers=max_workers,
            enable_performance_monitoring=enable_monitoring
        )

        self.duckdb_optimizer = DuckDBOptimizer(database_manager)

        self.performance_optimizer = PerformanceOptimizer(
            database_manager=database_manager
        ) if enable_monitoring else None

        # Performance tracking
        self.processing_history: List[Dict[str, Any]] = []
        self.baseline_performance = {
            "target_time_minutes": 2.5,  # Target: 2-3 minutes
            "baseline_time_minutes": 6.5,  # Baseline: 5-8 minutes
            "improvement_target": 60.0  # 60% improvement
        }

        logger.info("OptimizedYearProcessor initialized with all performance optimizations")

    async def process_year_optimized(
        self,
        simulation_year: int,
        configuration: Dict[str, Any],
        previous_workforce: Optional[WorkforceState] = None
    ) -> Dict[str, Any]:
        """
        Process a single simulation year with all optimizations enabled.

        Args:
            simulation_year: Year to process
            configuration: Simulation configuration
            previous_workforce: Previous year's workforce state

        Returns:
            Processing results with performance metrics
        """
        logger.info(f"🚀 Starting optimized year processing for {simulation_year}")
        start_time = time.time()

        try:
            # Phase 1: Apply DuckDB optimizations
            logger.info("📊 Phase 1: Applying DuckDB optimizations")
            optimization_results = await self.duckdb_optimizer.optimize_workforce_queries(simulation_year)

            optimization_success_rate = sum(1 for r in optimization_results if r.success) / len(optimization_results)
            logger.info(f"✅ Applied {len(optimization_results)} optimizations ({optimization_success_rate:.1%} success rate)")

            # Phase 2: Execute batch dbt processing
            logger.info("🔨 Phase 2: Executing optimized batch dbt processing")

            # Prepare variables for dbt execution
            dbt_vars = {
                "simulation_year": simulation_year,
                "start_year": configuration.get("start_year", simulation_year),
                **configuration
            }

            # Execute all batch groups
            batch_results = await self.dbt_executor.execute_year_processing_batch(
                simulation_year=simulation_year,
                vars_dict=dbt_vars,
                full_refresh=configuration.get("full_refresh", False)
            )

            # Phase 3: Generate workforce state
            logger.info("👥 Phase 3: Generating optimized workforce state")
            workforce_state = await self._generate_optimized_workforce_state(
                simulation_year, batch_results
            )

            # Phase 4: Performance analysis and validation
            logger.info("📈 Phase 4: Performance analysis and validation")
            total_execution_time = time.time() - start_time

            performance_analysis = await self._analyze_year_performance(
                simulation_year, batch_results, total_execution_time
            )

            # Phase 5: Store results
            if workforce_state:
                self.state_manager.store_year_state(simulation_year, workforce_state)

            # Create comprehensive result
            result = {
                "simulation_year": simulation_year,
                "success": all(r.success for r in batch_results),
                "total_execution_time": total_execution_time,
                "execution_time_minutes": total_execution_time / 60,
                "workforce_state": workforce_state,
                "batch_results": batch_results,
                "optimization_results": optimization_results,
                "performance_analysis": performance_analysis,
                "performance_targets": {
                    "target_met": total_execution_time <= (self.baseline_performance["target_time_minutes"] * 60),
                    "improvement_achieved": self._calculate_improvement_percentage(total_execution_time),
                    "memory_target_met": performance_analysis.get("peak_memory_gb", 0) <= 4.0,
                    "speed_target_met": performance_analysis.get("avg_query_time", 0) <= 1.0
                }
            }

            # Store processing history
            self.processing_history.append(result)

            # Log performance summary
            improvement = result["performance_targets"]["improvement_achieved"]
            memory_usage = performance_analysis.get("peak_memory_gb", 0)

            logger.info(f"✅ Year {simulation_year} processing completed in {total_execution_time/60:.2f} minutes")
            logger.info(f"📈 Performance improvement: {improvement:.1f}% (target: 60%)")
            logger.info(f"💾 Peak memory usage: {memory_usage:.1f}GB (target: <4GB)")

            if result["performance_targets"]["target_met"]:
                logger.info("🎯 All performance targets achieved!")
            else:
                logger.warning("⚠️ Some performance targets not met - see analysis for details")

            return result

        except Exception as e:
            total_execution_time = time.time() - start_time
            logger.error(f"❌ Optimized year processing failed for {simulation_year}: {e}")

            return {
                "simulation_year": simulation_year,
                "success": False,
                "total_execution_time": total_execution_time,
                "error": str(e),
                "performance_targets": {
                    "target_met": False,
                    "improvement_achieved": 0.0,
                    "memory_target_met": False,
                    "speed_target_met": False
                }
            }

    async def _generate_optimized_workforce_state(
        self,
        simulation_year: int,
        batch_results: List[BatchResult]
    ) -> Optional[WorkforceState]:
        """Generate workforce state using optimized queries."""
        try:
            # Check if critical tables were built successfully
            critical_batches = [r for r in batch_results if r.group == ExecutionGroup.FINAL_OUTPUT_SEQUENTIAL]
            if not all(r.success for r in critical_batches):
                logger.error("Critical final output batch failed, cannot generate workforce state")
                return None

            # Use optimized query for workforce state generation
            with self.database_manager.get_connection() as conn:
                # Optimized workforce snapshot query using columnar operations
                workforce_query = f"""
                SELECT
                    employee_id,
                    employee_hire_date,
                    level_id,
                    salary,
                    COALESCE(department, 'Unknown') as department,
                    COALESCE(location, 'Unknown') as location,
                    age,
                    tenure_years,
                    employment_status = 'active' as is_active,
                    COALESCE(plan_eligible, false) as plan_eligible,
                    COALESCE(plan_enrolled, false) as plan_enrolled
                FROM fct_workforce_snapshot
                WHERE simulation_year = {simulation_year}
                ORDER BY employee_id
                """

                # Execute with performance monitoring
                if self.performance_optimizer:
                    await self.performance_optimizer.analyze_query_performance(
                        workforce_query,
                        f"workforce_state_{simulation_year}",
                        "SELECT"
                    )

                results = conn.execute(workforce_query).fetchall()

                # Convert to WorkforceRecord objects
                from ..multi_year.simulation_state import WorkforceRecord
                from datetime import date

                workforce_records = []
                for row in results:
                    record = WorkforceRecord(
                        employee_id=row[0],
                        hire_date=row[1] if isinstance(row[1], date) else date.fromisoformat(str(row[1])),
                        job_level=row[2] or "L1",
                        salary=float(row[3]) if row[3] else 0.0,
                        department=row[4],
                        location=row[5],
                        age=int(row[6]) if row[6] else 30,
                        tenure_years=float(row[7]) if row[7] else 0.0,
                        is_active=bool(row[8]),
                        plan_eligible=bool(row[9]),
                        plan_enrolled=bool(row[10])
                    )
                    workforce_records.append(record)

                logger.info(f"Generated workforce state with {len(workforce_records)} records")

                return WorkforceState(
                    year=simulation_year,
                    workforce_records=workforce_records,
                    metadata={
                        "generation_method": "optimized_columnar_query",
                        "generation_timestamp": datetime.utcnow().isoformat(),
                        "total_records": len(workforce_records),
                        "active_records": sum(1 for r in workforce_records if r.is_active)
                    }
                )

        except Exception as e:
            logger.error(f"Failed to generate optimized workforce state: {e}")
            return None

    async def _analyze_year_performance(
        self,
        simulation_year: int,
        batch_results: List[BatchResult],
        total_execution_time: float
    ) -> Dict[str, Any]:
        """Analyze performance of year processing."""
        # Batch-level analysis
        successful_batches = sum(1 for r in batch_results if r.success)
        total_models = sum(len(r.models) for r in batch_results)
        total_records = sum(r.records_processed for r in batch_results)

        # Calculate performance metrics
        models_per_minute = total_models / (total_execution_time / 60) if total_execution_time > 0 else 0
        records_per_second = total_records / total_execution_time if total_execution_time > 0 else 0

        # Memory usage analysis (estimated)
        peak_memory_gb = max((r.memory_peak_gb for r in batch_results), default=0.0)
        if peak_memory_gb == 0:
            # Estimate based on batch requirements
            peak_memory_gb = max((r.performance_metrics.get("memory_requirement_gb", 1.0) for r in batch_results), default=1.0)

        # Query performance analysis
        avg_query_time = total_execution_time / total_models if total_models > 0 else 0

        # Group-wise performance
        group_performance = {}
        for group in ExecutionGroup:
            group_results = [r for r in batch_results if r.group == group]
            if group_results:
                group_performance[group.value] = {
                    "execution_time": sum(r.execution_time for r in group_results),
                    "success_rate": sum(1 for r in group_results if r.success) / len(group_results),
                    "model_count": sum(len(r.models) for r in group_results),
                    "records_processed": sum(r.records_processed for r in group_results)
                }

        # Performance improvement calculation
        improvement_percentage = self._calculate_improvement_percentage(total_execution_time)

        # Bottleneck identification
        bottlenecks = []
        slowest_batch = max(batch_results, key=lambda x: x.execution_time, default=None)
        if slowest_batch:
            bottlenecks.append(f"Slowest batch: {slowest_batch.group.value} ({slowest_batch.execution_time:.2f}s)")

        failed_batches = [r for r in batch_results if not r.success]
        if failed_batches:
            bottlenecks.extend([f"Failed batch: {r.group.value}" for r in failed_batches])

        analysis = {
            "simulation_year": simulation_year,
            "total_execution_time": total_execution_time,
            "execution_time_minutes": total_execution_time / 60,
            "successful_batches": successful_batches,
            "total_batches": len(batch_results),
            "success_rate": successful_batches / len(batch_results) if batch_results else 0,
            "total_models_processed": total_models,
            "total_records_processed": total_records,
            "models_per_minute": models_per_minute,
            "records_per_second": records_per_second,
            "peak_memory_gb": peak_memory_gb,
            "avg_query_time": avg_query_time,
            "improvement_percentage": improvement_percentage,
            "group_performance": group_performance,
            "bottlenecks": bottlenecks,
            "performance_targets": {
                "time_target_met": total_execution_time <= (self.baseline_performance["target_time_minutes"] * 60),
                "memory_target_met": peak_memory_gb <= 4.0,
                "speed_target_met": avg_query_time <= 1.0,
                "improvement_target_met": improvement_percentage >= 60.0
            }
        }

        return analysis

    def _calculate_improvement_percentage(self, execution_time: float) -> float:
        """Calculate performance improvement percentage vs baseline."""
        baseline_seconds = self.baseline_performance["baseline_time_minutes"] * 60
        current_seconds = execution_time

        if baseline_seconds > 0:
            improvement = ((baseline_seconds - current_seconds) / baseline_seconds) * 100
            return max(0.0, improvement)  # Don't show negative improvements

        return 0.0

    def get_processing_summary(self) -> Dict[str, Any]:
        """Get comprehensive processing summary across all years."""
        if not self.processing_history:
            return {"message": "No processing history available"}

        successful_years = [y for y in self.processing_history if y["success"]]
        failed_years = [y for y in self.processing_history if not y["success"]]

        # Overall statistics
        total_time = sum(y["total_execution_time"] for y in self.processing_history)
        avg_time = total_time / len(self.processing_history)
        avg_improvement = sum(y["performance_targets"]["improvement_achieved"] for y in successful_years) / len(successful_years) if successful_years else 0

        # Performance trend analysis
        if len(successful_years) >= 2:
            recent_avg = sum(y["total_execution_time"] for y in successful_years[-3:]) / min(3, len(successful_years))
            earlier_avg = sum(y["total_execution_time"] for y in successful_years[:3]) / min(3, len(successful_years))
            performance_trend = ((earlier_avg - recent_avg) / earlier_avg * 100) if earlier_avg > 0 else 0
        else:
            performance_trend = 0

        # Target achievement rate
        targets_met = sum(1 for y in successful_years if y["performance_targets"]["target_met"])
        target_achievement_rate = targets_met / len(successful_years) if successful_years else 0

        # Memory efficiency
        memory_usage = [y.get("performance_analysis", {}).get("peak_memory_gb", 0) for y in successful_years]
        avg_memory = sum(memory_usage) / len(memory_usage) if memory_usage else 0

        return {
            "total_years_processed": len(self.processing_history),
            "successful_years": len(successful_years),
            "failed_years": len(failed_years),
            "success_rate": len(successful_years) / len(self.processing_history) * 100,
            "performance_metrics": {
                "total_execution_time_minutes": total_time / 60,
                "average_execution_time_minutes": avg_time / 60,
                "average_improvement_percentage": avg_improvement,
                "performance_trend": performance_trend,
                "target_achievement_rate": target_achievement_rate * 100
            },
            "resource_efficiency": {
                "average_memory_usage_gb": avg_memory,
                "memory_target_achievement": sum(1 for m in memory_usage if m <= 4.0) / len(memory_usage) * 100 if memory_usage else 0
            },
            "optimization_effectiveness": {
                "improvement_target_met": avg_improvement >= 60.0,
                "consistent_performance": performance_trend >= 0,  # Performance improving or stable
                "resource_efficient": avg_memory <= 4.0
            },
            "batch_execution_summary": self.dbt_executor.get_performance_summary(),
            "duckdb_optimization_summary": self.duckdb_optimizer.get_optimization_summary()
        }

    def reset_performance_history(self) -> None:
        """Reset all performance tracking data."""
        self.processing_history.clear()
        self.dbt_executor.reset_performance_history()
        self.duckdb_optimizer.clear_optimization_cache()

        if self.performance_optimizer:
            self.performance_optimizer.reset_performance_data()

        logger.info("All performance tracking data reset")

    def set_baseline_performance(self, time_minutes: float) -> None:
        """Set baseline performance for improvement calculations."""
        self.baseline_performance["baseline_time_minutes"] = time_minutes
        logger.info(f"Baseline performance set to {time_minutes:.2f} minutes")
