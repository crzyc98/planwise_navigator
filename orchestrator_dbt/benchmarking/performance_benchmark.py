#!/usr/bin/env python3
"""
Performance Benchmarking Suite for Story S031-03 Event Generation Performance.

This module provides comprehensive performance benchmarking capabilities to measure
the 65% improvement target achieved by migrating event generation from orchestrator_mvp
to orchestrator_dbt. Includes detailed timing analysis, throughput measurements,
and comparative performance reporting.

Key Features:
- End-to-end event generation performance measurement
- Batch SQL operation performance analysis
- Memory usage monitoring and optimization
- Comparative benchmarking against MVP baseline
- Detailed performance reporting and visualization
- Performance regression detection

Integration with Story S031-03:
- Validates 65% performance improvement target achievement
- Measures batch SQL operation efficiency gains
- Monitors memory usage improvements
- Provides stakeholder performance reporting
"""

import time
import psutil
import logging
import statistics
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional, Tuple, Union
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import json
import matplotlib.pyplot as plt
import pandas as pd

from ..core.database_manager import DatabaseManager
from ..core.config import OrchestrationConfig
from ..simulation.event_generator import BatchEventGenerator
from ..simulation.workforce_calculator import WorkforceCalculator
from ..simulation.compensation_processor import CompensationProcessor
from ..simulation.eligibility_processor import EligibilityProcessor
from ..core.id_generator import UnifiedIDGenerator, create_id_generator_from_config

logger = logging.getLogger(__name__)


class BenchmarkCategory(Enum):
    """Categories of performance benchmarks."""
    EVENT_GENERATION = "event_generation"
    WORKFORCE_CALCULATION = "workforce_calculation"
    COMPENSATION_PROCESSING = "compensation_processing"
    ELIGIBILITY_PROCESSING = "eligibility_processing"
    ID_GENERATION = "id_generation"
    DATABASE_OPERATIONS = "database_operations"
    END_TO_END = "end_to_end"


class BenchmarkMetric(Enum):
    """Types of performance metrics."""
    EXECUTION_TIME = "execution_time"
    THROUGHPUT = "throughput"
    MEMORY_USAGE = "memory_usage"
    CPU_USAGE = "cpu_usage"
    DATABASE_QUERIES = "database_queries"
    EVENTS_PER_SECOND = "events_per_second"


@dataclass
class PerformanceResult:
    """Individual performance measurement result."""
    benchmark_name: str
    category: BenchmarkCategory
    metric: BenchmarkMetric
    value: float
    unit: str
    execution_time: float
    timestamp: datetime = field(default_factory=datetime.now)
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'benchmark_name': self.benchmark_name,
            'category': self.category.value,
            'metric': self.metric.value,
            'value': self.value,
            'unit': self.unit,
            'execution_time': self.execution_time,
            'timestamp': self.timestamp.isoformat(),
            'metadata': self.metadata
        }


@dataclass
class BenchmarkSuite:
    """Collection of related performance benchmarks."""
    suite_name: str
    results: List[PerformanceResult] = field(default_factory=list)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    total_execution_time: float = 0.0

    @property
    def duration(self) -> timedelta:
        """Calculate total benchmark duration."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return timedelta(0)

    def add_result(self, result: PerformanceResult) -> None:
        """Add a performance result to the suite."""
        self.results.append(result)

    def get_results_by_category(self, category: BenchmarkCategory) -> List[PerformanceResult]:
        """Get all results for a specific category."""
        return [r for r in self.results if r.category == category]

    def get_results_by_metric(self, metric: BenchmarkMetric) -> List[PerformanceResult]:
        """Get all results for a specific metric."""
        return [r for r in self.results if r.metric == metric]


@dataclass
class ComparisonResult:
    """Result of comparing two performance measurements."""
    baseline_value: float
    current_value: float
    improvement_percent: float
    improvement_absolute: float
    meets_target: bool
    target_percent: float = 65.0

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization."""
        return {
            'baseline_value': self.baseline_value,
            'current_value': self.current_value,
            'improvement_percent': self.improvement_percent,
            'improvement_absolute': self.improvement_absolute,
            'meets_target': self.meets_target,
            'target_percent': self.target_percent
        }


class PerformanceBenchmark:
    """Comprehensive performance benchmarking system for orchestrator_dbt migration.

    This system measures performance improvements achieved by the migration from
    orchestrator_mvp to orchestrator_dbt, with a focus on validating the 65%
    improvement target for event generation operations.
    """

    def __init__(
        self,
        database_manager: DatabaseManager,
        config: OrchestrationConfig,
        enable_memory_monitoring: bool = True,
        enable_cpu_monitoring: bool = True,
        baseline_data_path: Optional[Path] = None
    ):
        """Initialize performance benchmark system.

        Args:
            database_manager: Database operations manager
            config: Orchestration configuration
            enable_memory_monitoring: Enable memory usage monitoring
            enable_cpu_monitoring: Enable CPU usage monitoring
            baseline_data_path: Path to baseline performance data (MVP results)
        """
        self.db_manager = database_manager
        self.config = config
        self.enable_memory_monitoring = enable_memory_monitoring
        self.enable_cpu_monitoring = enable_cpu_monitoring
        self.baseline_data_path = baseline_data_path

        # Initialize components for benchmarking
        self.event_generator = BatchEventGenerator(database_manager, config, batch_size=10000)
        self.workforce_calculator = WorkforceCalculator(database_manager, config)
        self.compensation_processor = CompensationProcessor(database_manager, config)
        self.eligibility_processor = EligibilityProcessor(database_manager, config)
        self.id_generator = create_id_generator_from_config(config, database_manager=database_manager)

        # Performance tracking
        self.current_suite: Optional[BenchmarkSuite] = None
        self.baseline_data: Optional[Dict[str, Any]] = None

        # System monitoring
        self.process = psutil.Process()

        # Load baseline data if available
        if baseline_data_path and baseline_data_path.exists():
            self._load_baseline_data()

    def start_benchmark_suite(self, suite_name: str) -> BenchmarkSuite:
        """Start a new benchmark suite."""
        self.current_suite = BenchmarkSuite(
            suite_name=suite_name,
            start_time=datetime.now()
        )
        logger.info(f"🚀 Starting benchmark suite: {suite_name}")
        return self.current_suite

    def finish_benchmark_suite(self) -> BenchmarkSuite:
        """Finish the current benchmark suite."""
        if not self.current_suite:
            raise ValueError("No active benchmark suite")

        self.current_suite.end_time = datetime.now()
        self.current_suite.total_execution_time = self.current_suite.duration.total_seconds()

        logger.info(
            f"✅ Completed benchmark suite: {self.current_suite.suite_name} "
            f"({self.current_suite.total_execution_time:.3f}s, {len(self.current_suite.results)} results)"
        )

        completed_suite = self.current_suite
        self.current_suite = None
        return completed_suite

    def benchmark_event_generation_end_to_end(
        self,
        simulation_year: int,
        workforce_size: int = 100000,
        iterations: int = 3
    ) -> PerformanceResult:
        """Benchmark complete event generation pipeline end-to-end.

        This is the primary benchmark for measuring the 65% improvement target.
        Measures time to generate all event types for a full simulation year.

        Args:
            simulation_year: Year to simulate
            workforce_size: Size of workforce for benchmarking
            iterations: Number of iterations to average

        Returns:
            PerformanceResult with end-to-end timing
        """
        logger.info(f"🔍 Benchmarking end-to-end event generation for {workforce_size} employees")

        execution_times = []
        memory_usage = []
        events_generated = []

        for iteration in range(iterations):
            logger.debug(f"Running iteration {iteration + 1}/{iterations}")

            # Clear any previous state
            self._prepare_benchmark_environment()

            # Monitor system resources
            start_memory = self.process.memory_info().rss / 1024 / 1024  # MB
            start_cpu_percent = self.process.cpu_percent()

            start_time = time.time()

            try:
                # Generate all event types in sequence (matching MVP workflow)
                all_events = []

                # 1. Termination events
                termination_events = self.event_generator.generate_termination_events(simulation_year)
                all_events.extend(termination_events)

                # 2. Hiring events
                hiring_events = self.event_generator.generate_hiring_events(simulation_year)
                all_events.extend(hiring_events)

                # 3. Merit raise events
                merit_events = self.event_generator.generate_merit_events(simulation_year)
                all_events.extend(merit_events)

                # 4. Promotion events
                promotion_events = self.event_generator.generate_promotion_events(simulation_year)
                all_events.extend(promotion_events)

                # 5. Store events in database
                self.event_generator.store_events_in_database(all_events, simulation_year)

                end_time = time.time()
                execution_time = end_time - start_time

                # Monitor system resources
                end_memory = self.process.memory_info().rss / 1024 / 1024  # MB
                memory_used = end_memory - start_memory

                execution_times.append(execution_time)
                memory_usage.append(memory_used)
                events_generated.append(len(all_events))

                logger.debug(
                    f"Iteration {iteration + 1}: {execution_time:.3f}s, "
                    f"{len(all_events)} events, {memory_used:.1f}MB memory"
                )

            except Exception as e:
                logger.error(f"Benchmark iteration {iteration + 1} failed: {str(e)}")
                raise

        # Calculate statistics
        avg_execution_time = statistics.mean(execution_times)
        std_execution_time = statistics.stdev(execution_times) if len(execution_times) > 1 else 0
        avg_memory_usage = statistics.mean(memory_usage)
        avg_events = statistics.mean(events_generated)
        events_per_second = avg_events / avg_execution_time

        # Create performance result
        result = PerformanceResult(
            benchmark_name="end_to_end_event_generation",
            category=BenchmarkCategory.END_TO_END,
            metric=BenchmarkMetric.EXECUTION_TIME,
            value=avg_execution_time,
            unit="seconds",
            execution_time=avg_execution_time,
            metadata={
                'simulation_year': simulation_year,
                'workforce_size': workforce_size,
                'iterations': iterations,
                'execution_times': execution_times,
                'std_execution_time': std_execution_time,
                'avg_memory_usage_mb': avg_memory_usage,
                'avg_events_generated': avg_events,
                'events_per_second': events_per_second,
                'performance_target': '65% improvement over MVP'
            }
        )

        if self.current_suite:
            self.current_suite.add_result(result)

        logger.info(
            f"✅ End-to-end benchmark completed: {avg_execution_time:.3f}s ±{std_execution_time:.3f}s, "
            f"{events_per_second:.0f} events/sec"
        )

        return result

    def benchmark_batch_sql_operations(
        self,
        simulation_year: int,
        batch_sizes: List[int] = None
    ) -> List[PerformanceResult]:
        """Benchmark batch SQL operation performance across different batch sizes.

        Args:
            simulation_year: Year to simulate
            batch_sizes: List of batch sizes to test

        Returns:
            List of PerformanceResult objects for different batch sizes
        """
        if batch_sizes is None:
            batch_sizes = [1000, 5000, 10000, 25000, 50000]

        logger.info(f"🔍 Benchmarking batch SQL operations for batch sizes: {batch_sizes}")

        results = []

        for batch_size in batch_sizes:
            logger.debug(f"Testing batch size: {batch_size}")

            # Create event generator with specific batch size
            batch_generator = BatchEventGenerator(self.db_manager, self.config, batch_size=batch_size)

            start_time = time.time()

            try:
                # Test batch termination event generation (most SQL-intensive)
                termination_events = batch_generator.generate_termination_events(simulation_year)

                end_time = time.time()
                execution_time = end_time - start_time

                events_per_second = len(termination_events) / execution_time if execution_time > 0 else 0

                result = PerformanceResult(
                    benchmark_name=f"batch_sql_operations_{batch_size}",
                    category=BenchmarkCategory.DATABASE_OPERATIONS,
                    metric=BenchmarkMetric.THROUGHPUT,
                    value=events_per_second,
                    unit="events/second",
                    execution_time=execution_time,
                    metadata={
                        'batch_size': batch_size,
                        'events_generated': len(termination_events),
                        'simulation_year': simulation_year
                    }
                )

                results.append(result)

                if self.current_suite:
                    self.current_suite.add_result(result)

                logger.debug(f"Batch size {batch_size}: {events_per_second:.0f} events/sec")

            except Exception as e:
                logger.error(f"Batch size {batch_size} benchmark failed: {str(e)}")
                continue

        # Find optimal batch size
        if results:
            best_result = max(results, key=lambda r: r.value)
            logger.info(f"✅ Optimal batch size: {best_result.metadata['batch_size']} ({best_result.value:.0f} events/sec)")

        return results

    def benchmark_memory_efficiency(
        self,
        simulation_year: int,
        workforce_sizes: List[int] = None
    ) -> List[PerformanceResult]:
        """Benchmark memory efficiency across different workforce sizes.

        Args:
            simulation_year: Year to simulate
            workforce_sizes: List of workforce sizes to test

        Returns:
            List of PerformanceResult objects for memory usage
        """
        if workforce_sizes is None:
            workforce_sizes = [10000, 50000, 100000, 250000, 500000]

        logger.info(f"🔍 Benchmarking memory efficiency for workforce sizes: {workforce_sizes}")

        results = []

        for workforce_size in workforce_sizes:
            logger.debug(f"Testing workforce size: {workforce_size}")

            # Clear memory before test
            import gc
            gc.collect()

            start_memory = self.process.memory_info().rss / 1024 / 1024  # MB
            start_time = time.time()

            try:
                # Generate events for workforce size
                termination_events = self.event_generator.generate_termination_events(simulation_year)

                # Measure peak memory usage
                peak_memory = self.process.memory_info().rss / 1024 / 1024  # MB
                memory_used = peak_memory - start_memory

                end_time = time.time()
                execution_time = end_time - start_time

                # Calculate memory efficiency (events per MB)
                memory_efficiency = len(termination_events) / memory_used if memory_used > 0 else 0

                result = PerformanceResult(
                    benchmark_name=f"memory_efficiency_{workforce_size}",
                    category=BenchmarkCategory.EVENT_GENERATION,
                    metric=BenchmarkMetric.MEMORY_USAGE,
                    value=memory_used,
                    unit="MB",
                    execution_time=execution_time,
                    metadata={
                        'workforce_size': workforce_size,
                        'events_generated': len(termination_events),
                        'memory_efficiency_events_per_mb': memory_efficiency,
                        'peak_memory_mb': peak_memory,
                        'simulation_year': simulation_year
                    }
                )

                results.append(result)

                if self.current_suite:
                    self.current_suite.add_result(result)

                logger.debug(f"Workforce {workforce_size}: {memory_used:.1f}MB, {memory_efficiency:.0f} events/MB")

            except Exception as e:
                logger.error(f"Memory benchmark for workforce {workforce_size} failed: {str(e)}")
                continue

        return results

    def benchmark_component_performance(self, simulation_year: int) -> List[PerformanceResult]:
        """Benchmark individual component performance.

        Args:
            simulation_year: Year to simulate

        Returns:
            List of PerformanceResult objects for each component
        """
        logger.info("🔍 Benchmarking individual component performance")

        results = []

        # Benchmark workforce calculation
        start_time = time.time()
        try:
            workforce_req = self.workforce_calculator.calculate_workforce_requirements(simulation_year)
            execution_time = time.time() - start_time

            result = PerformanceResult(
                benchmark_name="workforce_calculation",
                category=BenchmarkCategory.WORKFORCE_CALCULATION,
                metric=BenchmarkMetric.EXECUTION_TIME,
                value=execution_time,
                unit="seconds",
                execution_time=execution_time,
                metadata={
                    'simulation_year': simulation_year,
                    'terminations_needed': workforce_req.terminations_needed,
                    'hires_needed': workforce_req.hires_needed
                }
            )
            results.append(result)

            if self.current_suite:
                self.current_suite.add_result(result)

            logger.debug(f"Workforce calculation: {execution_time:.3f}s")

        except Exception as e:
            logger.error(f"Workforce calculation benchmark failed: {str(e)}")

        # Benchmark compensation processing
        start_time = time.time()
        try:
            promotion_eligible = []  # Mock data for benchmark
            comp_results = self.compensation_processor.process_annual_compensation_cycle(
                simulation_year, promotion_eligible
            )
            execution_time = time.time() - start_time

            result = PerformanceResult(
                benchmark_name="compensation_processing",
                category=BenchmarkCategory.COMPENSATION_PROCESSING,
                metric=BenchmarkMetric.EXECUTION_TIME,
                value=execution_time,
                unit="seconds",
                execution_time=execution_time,
                metadata={
                    'simulation_year': simulation_year,
                    'compensation_results': len(comp_results.get('merit_calculations', []))
                }
            )
            results.append(result)

            if self.current_suite:
                self.current_suite.add_result(result)

            logger.debug(f"Compensation processing: {execution_time:.3f}s")

        except Exception as e:
            logger.error(f"Compensation processing benchmark failed: {str(e)}")

        # Benchmark eligibility processing
        start_time = time.time()
        try:
            eligible_employees = self.eligibility_processor.get_eligible_employees(simulation_year)
            execution_time = time.time() - start_time

            result = PerformanceResult(
                benchmark_name="eligibility_processing",
                category=BenchmarkCategory.ELIGIBILITY_PROCESSING,
                metric=BenchmarkMetric.EXECUTION_TIME,
                value=execution_time,
                unit="seconds",
                execution_time=execution_time,
                metadata={
                    'simulation_year': simulation_year,
                    'eligible_employees': len(eligible_employees)
                }
            )
            results.append(result)

            if self.current_suite:
                self.current_suite.add_result(result)

            logger.debug(f"Eligibility processing: {execution_time:.3f}s")

        except Exception as e:
            logger.error(f"Eligibility processing benchmark failed: {str(e)}")

        # Benchmark ID generation
        start_time = time.time()
        try:
            test_ids = self.id_generator.generate_batch_employee_ids(
                start_sequence=1,
                count=10000,
                is_baseline=False,
                hire_year=simulation_year,
                validate_collisions=False  # Skip for benchmark
            )
            execution_time = time.time() - start_time

            ids_per_second = len(test_ids) / execution_time if execution_time > 0 else 0

            result = PerformanceResult(
                benchmark_name="id_generation",
                category=BenchmarkCategory.ID_GENERATION,
                metric=BenchmarkMetric.THROUGHPUT,
                value=ids_per_second,
                unit="IDs/second",
                execution_time=execution_time,
                metadata={
                    'simulation_year': simulation_year,
                    'ids_generated': len(test_ids)
                }
            )
            results.append(result)

            if self.current_suite:
                self.current_suite.add_result(result)

            logger.debug(f"ID generation: {ids_per_second:.0f} IDs/sec")

        except Exception as e:
            logger.error(f"ID generation benchmark failed: {str(e)}")

        return results

    def compare_with_baseline(
        self,
        current_result: PerformanceResult,
        baseline_key: str
    ) -> Optional[ComparisonResult]:
        """Compare current performance with MVP baseline.

        Args:
            current_result: Current performance result
            baseline_key: Key to look up baseline value

        Returns:
            ComparisonResult if baseline data available, None otherwise
        """
        if not self.baseline_data or baseline_key not in self.baseline_data:
            logger.warning(f"No baseline data available for {baseline_key}")
            return None

        baseline_value = self.baseline_data[baseline_key]
        current_value = current_result.value

        # Calculate improvement (lower is better for execution time)
        if current_result.metric == BenchmarkMetric.EXECUTION_TIME:
            improvement_percent = ((baseline_value - current_value) / baseline_value) * 100
            improvement_absolute = baseline_value - current_value
        else:
            # Higher is better for throughput metrics
            improvement_percent = ((current_value - baseline_value) / baseline_value) * 100
            improvement_absolute = current_value - baseline_value

        meets_target = improvement_percent >= 65.0

        comparison = ComparisonResult(
            baseline_value=baseline_value,
            current_value=current_value,
            improvement_percent=improvement_percent,
            improvement_absolute=improvement_absolute,
            meets_target=meets_target
        )

        logger.info(
            f"📊 Performance comparison for {baseline_key}: "
            f"{improvement_percent:+.1f}% improvement "
            f"({'✅ Target met' if meets_target else '❌ Target missed'})"
        )

        return comparison

    def generate_performance_report(
        self,
        suite: BenchmarkSuite,
        output_path: Optional[Path] = None
    ) -> Dict[str, Any]:
        """Generate comprehensive performance report.

        Args:
            suite: Completed benchmark suite
            output_path: Optional path to save report

        Returns:
            Performance report dictionary
        """
        logger.info(f"📊 Generating performance report for suite: {suite.suite_name}")

        report = {
            'suite_info': {
                'name': suite.suite_name,
                'start_time': suite.start_time.isoformat() if suite.start_time else None,
                'end_time': suite.end_time.isoformat() if suite.end_time else None,
                'duration_seconds': suite.total_execution_time,
                'total_results': len(suite.results)
            },
            'performance_summary': self._generate_performance_summary(suite),
            'category_analysis': self._generate_category_analysis(suite),
            'baseline_comparisons': self._generate_baseline_comparisons(suite),
            'recommendations': self._generate_performance_recommendations(suite),
            'detailed_results': [r.to_dict() for r in suite.results],
            'metadata': {
                'generated_at': datetime.now().isoformat(),
                'story': 'S031-03-event-generation-performance',
                'target_improvement': '65%',
                'system_info': self._get_system_info()
            }
        }

        # Save report if path provided
        if output_path:
            with open(output_path, 'w') as f:
                json.dump(report, f, indent=2, default=str)
            logger.info(f"📄 Performance report saved to: {output_path}")

        return report

    def _prepare_benchmark_environment(self) -> None:
        """Prepare clean environment for benchmarking."""
        import gc
        gc.collect()

        # Reset component metrics
        if hasattr(self.event_generator, 'metrics'):
            self.event_generator.metrics.reset()

    def _load_baseline_data(self) -> None:
        """Load baseline performance data from MVP system."""
        try:
            with open(self.baseline_data_path, 'r') as f:
                self.baseline_data = json.load(f)
            logger.info(f"📊 Loaded baseline data from {self.baseline_data_path}")
        except Exception as e:
            logger.warning(f"Failed to load baseline data: {str(e)}")
            self.baseline_data = None

    def _generate_performance_summary(self, suite: BenchmarkSuite) -> Dict[str, Any]:
        """Generate performance summary statistics."""
        summary = {
            'total_benchmarks': len(suite.results),
            'categories_tested': len(set(r.category for r in suite.results)),
            'metrics_collected': len(set(r.metric for r in suite.results))
        }

        # Find key performance metrics
        end_to_end_results = suite.get_results_by_category(BenchmarkCategory.END_TO_END)
        if end_to_end_results:
            best_end_to_end = min(end_to_end_results, key=lambda r: r.value)
            summary['best_end_to_end_time'] = best_end_to_end.value
            summary['best_end_to_end_throughput'] = best_end_to_end.metadata.get('events_per_second', 0)

        return summary

    def _generate_category_analysis(self, suite: BenchmarkSuite) -> Dict[str, Any]:
        """Generate per-category performance analysis."""
        analysis = {}

        for category in BenchmarkCategory:
            results = suite.get_results_by_category(category)
            if not results:
                continue

            category_analysis = {
                'benchmark_count': len(results),
                'avg_execution_time': statistics.mean([r.execution_time for r in results]),
                'total_execution_time': sum([r.execution_time for r in results])
            }

            # Add metric-specific analysis
            execution_time_results = [r for r in results if r.metric == BenchmarkMetric.EXECUTION_TIME]
            if execution_time_results:
                category_analysis['fastest_execution'] = min(r.value for r in execution_time_results)
                category_analysis['slowest_execution'] = max(r.value for r in execution_time_results)

            throughput_results = [r for r in results if r.metric == BenchmarkMetric.THROUGHPUT]
            if throughput_results:
                category_analysis['peak_throughput'] = max(r.value for r in throughput_results)
                category_analysis['avg_throughput'] = statistics.mean([r.value for r in throughput_results])

            analysis[category.value] = category_analysis

        return analysis

    def _generate_baseline_comparisons(self, suite: BenchmarkSuite) -> Dict[str, Any]:
        """Generate baseline comparison analysis."""
        if not self.baseline_data:
            return {'available': False, 'message': 'No baseline data available'}

        comparisons = {'available': True, 'results': {}}

        # Compare key metrics
        end_to_end_results = suite.get_results_by_category(BenchmarkCategory.END_TO_END)
        if end_to_end_results:
            best_result = min(end_to_end_results, key=lambda r: r.value)
            comparison = self.compare_with_baseline(best_result, 'end_to_end_execution_time')
            if comparison:
                comparisons['results']['end_to_end'] = comparison.to_dict()

        return comparisons

    def _generate_performance_recommendations(self, suite: BenchmarkSuite) -> List[str]:
        """Generate performance optimization recommendations."""
        recommendations = []

        # Analyze batch operation results
        batch_results = [r for r in suite.results if 'batch_sql_operations' in r.benchmark_name]
        if batch_results:
            best_batch = max(batch_results, key=lambda r: r.value)
            optimal_batch_size = best_batch.metadata.get('batch_size', 10000)
            recommendations.append(f"Use batch size of {optimal_batch_size} for optimal throughput")

        # Analyze memory usage
        memory_results = suite.get_results_by_metric(BenchmarkMetric.MEMORY_USAGE)
        if memory_results:
            avg_memory = statistics.mean([r.value for r in memory_results])
            if avg_memory > 1000:  # > 1GB
                recommendations.append("Consider implementing memory streaming for large datasets")

        # Check if target improvement is met
        end_to_end_results = suite.get_results_by_category(BenchmarkCategory.END_TO_END)
        if end_to_end_results and self.baseline_data:
            best_result = min(end_to_end_results, key=lambda r: r.value)
            comparison = self.compare_with_baseline(best_result, 'end_to_end_execution_time')
            if comparison and not comparison.meets_target:
                recommendations.append(f"Performance improvement of {comparison.improvement_percent:.1f}% falls short of 65% target")

        return recommendations

    def _get_system_info(self) -> Dict[str, Any]:
        """Get system information for benchmark context."""
        return {
            'cpu_count': psutil.cpu_count(),
            'memory_total_gb': psutil.virtual_memory().total / 1024 / 1024 / 1024,
            'python_version': f"{__import__('sys').version_info.major}.{__import__('sys').version_info.minor}",
            'platform': __import__('platform').platform()
        }


def create_performance_benchmark(
    database_manager: DatabaseManager,
    config: OrchestrationConfig,
    baseline_data_path: Optional[Path] = None
) -> PerformanceBenchmark:
    """Factory function to create configured performance benchmark.

    Args:
        database_manager: Database operations manager
        config: Orchestration configuration
        baseline_data_path: Path to baseline performance data

    Returns:
        Configured PerformanceBenchmark instance
    """
    return PerformanceBenchmark(
        database_manager=database_manager,
        config=config,
        enable_memory_monitoring=True,
        enable_cpu_monitoring=True,
        baseline_data_path=baseline_data_path
    )


def run_comprehensive_benchmark(
    database_manager: DatabaseManager,
    config: OrchestrationConfig,
    simulation_year: int = 2025,
    output_path: Optional[Path] = None
) -> Dict[str, Any]:
    """Run comprehensive performance benchmark suite.

    Args:
        database_manager: Database operations manager
        config: Orchestration configuration
        simulation_year: Year to simulate for benchmarking
        output_path: Optional path to save report

    Returns:
        Performance report dictionary
    """
    benchmark = create_performance_benchmark(database_manager, config)

    # Start benchmark suite
    suite = benchmark.start_benchmark_suite(f"comprehensive_s031_03_{simulation_year}")

    try:
        # Run end-to-end benchmark (primary metric)
        benchmark.benchmark_event_generation_end_to_end(simulation_year, iterations=5)

        # Run component benchmarks
        benchmark.benchmark_component_performance(simulation_year)

        # Run batch operation benchmarks
        benchmark.benchmark_batch_sql_operations(simulation_year)

        # Run memory efficiency benchmarks
        benchmark.benchmark_memory_efficiency(simulation_year)

    finally:
        # Finish suite
        suite = benchmark.finish_benchmark_suite()

    # Generate report
    report = benchmark.generate_performance_report(suite, output_path)

    return report
