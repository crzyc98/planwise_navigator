#!/usr/bin/env python3
"""
Performance benchmarking suite for PlanWise Navigator optimization levels.

Story S063-09: Large Dataset Stress Testing
- Detailed performance comparison across low/medium/high optimization levels
- Memory usage patterns and efficiency analysis
- Processing rate and throughput benchmarking
- Single-threaded performance characteristics documentation
"""

import json
import logging
import statistics
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import matplotlib.pyplot as plt
import pandas as pd
import seaborn as sns

from .stress_test_framework import (
    OPTIMIZATION_LEVELS,
    StressTestExecutor,
    StressTestResult,
    MemoryProfiler
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class BenchmarkMetrics:
    """Comprehensive performance metrics for benchmarking"""

    # Basic performance
    execution_time_seconds: float
    peak_memory_mb: float
    average_memory_mb: float
    memory_efficiency: float  # Percentage of memory limit used

    # Processing metrics
    records_processed: int
    processing_rate_records_per_sec: float
    database_size_mb: float

    # Memory stability
    memory_std_dev: float
    memory_growth_rate: float  # MB per second
    gc_triggered: bool

    # Success metrics
    success_rate: float
    years_completed: int
    memory_limit_exceeded: bool

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

@dataclass
class OptimizationLevelBenchmark:
    """Benchmark results for a specific optimization level"""

    level_name: str
    configuration: Dict[str, Any]

    # Statistical metrics across multiple runs
    mean_metrics: BenchmarkMetrics
    median_metrics: BenchmarkMetrics
    std_dev_metrics: BenchmarkMetrics

    # Individual run results
    individual_runs: List[BenchmarkMetrics]

    # Scaling characteristics
    scaling_analysis: Dict[str, Any]

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class PerformanceBenchmarker:
    """Advanced performance benchmarking for optimization levels"""

    def __init__(self, test_data_dir: Path, results_dir: Path):
        self.test_data_dir = test_data_dir
        self.results_dir = results_dir
        self.executor = StressTestExecutor(test_data_dir)

        self.results_dir.mkdir(parents=True, exist_ok=True)

    def run_optimization_level_comparison(
        self,
        dataset_sizes: List[int],
        simulation_years: List[int],
        runs_per_config: int = 3,
        timeout_minutes: int = 60
    ) -> Dict[str, OptimizationLevelBenchmark]:
        """
        Run comprehensive comparison of optimization levels

        Args:
            dataset_sizes: Employee counts to benchmark
            simulation_years: Years to simulate for each test
            runs_per_config: Number of runs per configuration for statistical accuracy
            timeout_minutes: Timeout per individual test

        Returns:
            Dictionary of optimization level benchmarks
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"OPTIMIZATION LEVEL BENCHMARK COMPARISON")
        logger.info(f"{'='*70}")
        logger.info(f"Dataset sizes: {[f'{s:,}' for s in dataset_sizes]}")
        logger.info(f"Simulation years: {simulation_years}")
        logger.info(f"Runs per configuration: {runs_per_config}")
        logger.info(f"Total benchmarks: {len(OPTIMIZATION_LEVELS) * len(dataset_sizes) * runs_per_config}")

        benchmark_results = {}

        for level_name, opt_config in OPTIMIZATION_LEVELS.items():
            logger.info(f"\n{'='*50}")
            logger.info(f"BENCHMARKING OPTIMIZATION LEVEL: {level_name.upper()}")
            logger.info(f"Memory limit: {opt_config.memory_limit_gb}GB | Batch size: {opt_config.batch_size}")
            logger.info(f"{'='*50}")

            level_benchmark = self._benchmark_optimization_level(
                level_name=level_name,
                dataset_sizes=dataset_sizes,
                simulation_years=simulation_years,
                runs_per_config=runs_per_config,
                timeout_minutes=timeout_minutes
            )

            benchmark_results[level_name] = level_benchmark

            # Save intermediate results
            self._save_level_benchmark(level_name, level_benchmark)

        # Generate comprehensive comparison
        self._generate_comparison_analysis(benchmark_results, dataset_sizes, simulation_years)

        return benchmark_results

    def _benchmark_optimization_level(
        self,
        level_name: str,
        dataset_sizes: List[int],
        simulation_years: List[int],
        runs_per_config: int,
        timeout_minutes: int
    ) -> OptimizationLevelBenchmark:
        """Benchmark a single optimization level across all dataset sizes"""

        opt_config = OPTIMIZATION_LEVELS[level_name]
        all_metrics = []
        scaling_data = {}

        for dataset_size in dataset_sizes:
            logger.info(f"\nBenchmarking {level_name} with {dataset_size:,} employees...")

            size_metrics = []

            for run_idx in range(runs_per_config):
                logger.info(f"  Run {run_idx + 1}/{runs_per_config}...")

                # Execute stress test
                result = self.executor.run_single_stress_test(
                    dataset_size=dataset_size,
                    optimization_level=level_name,
                    simulation_years=simulation_years,
                    timeout_minutes=timeout_minutes
                )

                # Convert to benchmark metrics
                metrics = self._convert_to_benchmark_metrics(result, opt_config)
                size_metrics.append(metrics)
                all_metrics.append(metrics)

                # Log individual run result
                status = "✅" if result.success else "❌"
                memory_pct = (result.peak_memory_mb / (opt_config.memory_limit_gb * 1024)) * 100
                logger.info(f"    {status} Duration: {result.test_duration:.1f}s | "
                           f"Peak memory: {result.peak_memory_mb:.1f}MB ({memory_pct:.1f}% of limit)")

            # Calculate statistics for this dataset size
            if size_metrics:
                scaling_data[dataset_size] = {
                    'mean_execution_time': statistics.mean(m.execution_time_seconds for m in size_metrics),
                    'mean_peak_memory': statistics.mean(m.peak_memory_mb for m in size_metrics),
                    'mean_processing_rate': statistics.mean(m.processing_rate_records_per_sec for m in size_metrics if m.processing_rate_records_per_sec > 0),
                    'success_rate': sum(1 for m in size_metrics if m.success_rate > 0.8) / len(size_metrics),
                    'memory_efficiency': statistics.mean(m.memory_efficiency for m in size_metrics)
                }

        # Calculate overall statistics
        if all_metrics:
            mean_metrics = self._calculate_mean_metrics(all_metrics)
            median_metrics = self._calculate_median_metrics(all_metrics)
            std_dev_metrics = self._calculate_std_dev_metrics(all_metrics)
        else:
            # Handle empty metrics case
            mean_metrics = median_metrics = std_dev_metrics = BenchmarkMetrics(
                execution_time_seconds=0, peak_memory_mb=0, average_memory_mb=0,
                memory_efficiency=0, records_processed=0, processing_rate_records_per_sec=0,
                database_size_mb=0, memory_std_dev=0, memory_growth_rate=0,
                gc_triggered=False, success_rate=0, years_completed=0, memory_limit_exceeded=False
            )

        return OptimizationLevelBenchmark(
            level_name=level_name,
            configuration=asdict(opt_config),
            mean_metrics=mean_metrics,
            median_metrics=median_metrics,
            std_dev_metrics=std_dev_metrics,
            individual_runs=all_metrics,
            scaling_analysis=scaling_data
        )

    def _convert_to_benchmark_metrics(
        self,
        result: StressTestResult,
        opt_config
    ) -> BenchmarkMetrics:
        """Convert stress test result to benchmark metrics"""

        memory_limit_mb = opt_config.memory_limit_gb * 1024
        memory_efficiency = (result.peak_memory_mb / memory_limit_mb) * 100 if memory_limit_mb > 0 else 0

        # Calculate memory stability metrics (simplified)
        memory_std_dev = result.peak_memory_mb * 0.1  # Placeholder - would need detailed memory sampling
        memory_growth_rate = result.peak_memory_mb / result.test_duration if result.test_duration > 0 else 0

        processing_rate = result.processing_rate_records_per_sec if result.processing_rate_records_per_sec > 0 else 0

        return BenchmarkMetrics(
            execution_time_seconds=result.test_duration,
            peak_memory_mb=result.peak_memory_mb,
            average_memory_mb=result.average_memory_mb,
            memory_efficiency=memory_efficiency,
            records_processed=result.records_processed,
            processing_rate_records_per_sec=processing_rate,
            database_size_mb=result.database_final_size_mb,
            memory_std_dev=memory_std_dev,
            memory_growth_rate=memory_growth_rate,
            gc_triggered=result.memory_exceeded_limit,  # Approximation
            success_rate=1.0 if result.success else 0.0,
            years_completed=len(result.completed_years),
            memory_limit_exceeded=result.memory_exceeded_limit
        )

    def _calculate_mean_metrics(self, metrics_list: List[BenchmarkMetrics]) -> BenchmarkMetrics:
        """Calculate mean values across all metrics"""
        if not metrics_list:
            return BenchmarkMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, False, 0, 0, False)

        return BenchmarkMetrics(
            execution_time_seconds=statistics.mean(m.execution_time_seconds for m in metrics_list),
            peak_memory_mb=statistics.mean(m.peak_memory_mb for m in metrics_list),
            average_memory_mb=statistics.mean(m.average_memory_mb for m in metrics_list),
            memory_efficiency=statistics.mean(m.memory_efficiency for m in metrics_list),
            records_processed=int(statistics.mean(m.records_processed for m in metrics_list)),
            processing_rate_records_per_sec=statistics.mean(m.processing_rate_records_per_sec for m in metrics_list),
            database_size_mb=statistics.mean(m.database_size_mb for m in metrics_list),
            memory_std_dev=statistics.mean(m.memory_std_dev for m in metrics_list),
            memory_growth_rate=statistics.mean(m.memory_growth_rate for m in metrics_list),
            gc_triggered=sum(1 for m in metrics_list if m.gc_triggered) / len(metrics_list) > 0.5,
            success_rate=statistics.mean(m.success_rate for m in metrics_list),
            years_completed=int(statistics.mean(m.years_completed for m in metrics_list)),
            memory_limit_exceeded=sum(1 for m in metrics_list if m.memory_limit_exceeded) / len(metrics_list) > 0.5
        )

    def _calculate_median_metrics(self, metrics_list: List[BenchmarkMetrics]) -> BenchmarkMetrics:
        """Calculate median values across all metrics"""
        if not metrics_list:
            return BenchmarkMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, False, 0, 0, False)

        return BenchmarkMetrics(
            execution_time_seconds=statistics.median(m.execution_time_seconds for m in metrics_list),
            peak_memory_mb=statistics.median(m.peak_memory_mb for m in metrics_list),
            average_memory_mb=statistics.median(m.average_memory_mb for m in metrics_list),
            memory_efficiency=statistics.median(m.memory_efficiency for m in metrics_list),
            records_processed=int(statistics.median(m.records_processed for m in metrics_list)),
            processing_rate_records_per_sec=statistics.median(m.processing_rate_records_per_sec for m in metrics_list),
            database_size_mb=statistics.median(m.database_size_mb for m in metrics_list),
            memory_std_dev=statistics.median(m.memory_std_dev for m in metrics_list),
            memory_growth_rate=statistics.median(m.memory_growth_rate for m in metrics_list),
            gc_triggered=sum(1 for m in metrics_list if m.gc_triggered) / len(metrics_list) > 0.5,
            success_rate=statistics.median(m.success_rate for m in metrics_list),
            years_completed=int(statistics.median(m.years_completed for m in metrics_list)),
            memory_limit_exceeded=sum(1 for m in metrics_list if m.memory_limit_exceeded) / len(metrics_list) > 0.5
        )

    def _calculate_std_dev_metrics(self, metrics_list: List[BenchmarkMetrics]) -> BenchmarkMetrics:
        """Calculate standard deviation across all metrics"""
        if len(metrics_list) < 2:
            return BenchmarkMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0, False, 0, 0, False)

        return BenchmarkMetrics(
            execution_time_seconds=statistics.stdev(m.execution_time_seconds for m in metrics_list),
            peak_memory_mb=statistics.stdev(m.peak_memory_mb for m in metrics_list),
            average_memory_mb=statistics.stdev(m.average_memory_mb for m in metrics_list),
            memory_efficiency=statistics.stdev(m.memory_efficiency for m in metrics_list),
            records_processed=int(statistics.stdev(m.records_processed for m in metrics_list)),
            processing_rate_records_per_sec=statistics.stdev(m.processing_rate_records_per_sec for m in metrics_list),
            database_size_mb=statistics.stdev(m.database_size_mb for m in metrics_list),
            memory_std_dev=statistics.stdev(m.memory_std_dev for m in metrics_list),
            memory_growth_rate=statistics.stdev(m.memory_growth_rate for m in metrics_list),
            gc_triggered=False,  # N/A for standard deviation
            success_rate=statistics.stdev(m.success_rate for m in metrics_list),
            years_completed=int(statistics.stdev(m.years_completed for m in metrics_list)),
            memory_limit_exceeded=False  # N/A for standard deviation
        )

    def _save_level_benchmark(self, level_name: str, benchmark: OptimizationLevelBenchmark):
        """Save individual optimization level benchmark"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"benchmark_{level_name}_optimization_{timestamp}.json"

        benchmark_path = self.results_dir / filename

        with open(benchmark_path, 'w') as f:
            json.dump(benchmark.to_dict(), f, indent=2)

        logger.info(f"Saved {level_name} benchmark: {benchmark_path}")

    def _generate_comparison_analysis(
        self,
        benchmark_results: Dict[str, OptimizationLevelBenchmark],
        dataset_sizes: List[int],
        simulation_years: List[int]
    ):
        """Generate comprehensive comparison analysis and visualizations"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create comprehensive comparison report
        comparison_report = {
            'metadata': {
                'timestamp': timestamp,
                'dataset_sizes': dataset_sizes,
                'simulation_years': simulation_years,
                'optimization_levels_tested': list(benchmark_results.keys())
            },
            'performance_comparison': {},
            'scaling_analysis': {},
            'recommendations': [],
            'detailed_benchmarks': {name: bench.to_dict() for name, bench in benchmark_results.items()}
        }

        # Performance comparison matrix
        for level_name, benchmark in benchmark_results.items():
            comparison_report['performance_comparison'][level_name] = {
                'mean_execution_time': benchmark.mean_metrics.execution_time_seconds,
                'mean_peak_memory_mb': benchmark.mean_metrics.peak_memory_mb,
                'memory_efficiency_pct': benchmark.mean_metrics.memory_efficiency,
                'mean_processing_rate': benchmark.mean_metrics.processing_rate_records_per_sec,
                'success_rate': benchmark.mean_metrics.success_rate,
                'memory_limit_gb': OPTIMIZATION_LEVELS[level_name].memory_limit_gb,
                'batch_size': OPTIMIZATION_LEVELS[level_name].batch_size
            }

        # Scaling analysis
        comparison_report['scaling_analysis'] = self._analyze_scaling_characteristics(benchmark_results)

        # Generate recommendations
        comparison_report['recommendations'] = self._generate_optimization_recommendations(benchmark_results)

        # Save comprehensive report
        report_path = self.results_dir / f"optimization_levels_comparison_{timestamp}.json"
        with open(report_path, 'w') as f:
            json.dump(comparison_report, f, indent=2)

        # Generate CSV summary
        self._generate_csv_comparison(benchmark_results, timestamp)

        # Generate visualizations
        self._generate_performance_charts(benchmark_results, timestamp)

        logger.info(f"Comprehensive comparison report: {report_path}")

    def _analyze_scaling_characteristics(
        self,
        benchmark_results: Dict[str, OptimizationLevelBenchmark]
    ) -> Dict[str, Any]:
        """Analyze scaling characteristics across optimization levels"""
        scaling_analysis = {}

        for level_name, benchmark in benchmark_results.items():
            scaling_data = benchmark.scaling_analysis

            if not scaling_data:
                continue

            dataset_sizes = sorted(scaling_data.keys())

            # Calculate scaling efficiency
            if len(dataset_sizes) >= 2:
                small_size = min(dataset_sizes)
                large_size = max(dataset_sizes)

                small_metrics = scaling_data[small_size]
                large_metrics = scaling_data[large_size]

                # Linear scaling would have processing_rate stay constant
                size_ratio = large_size / small_size
                time_ratio = large_metrics['mean_execution_time'] / small_metrics['mean_execution_time']

                scaling_efficiency = size_ratio / time_ratio  # 1.0 = perfect linear scaling

                scaling_analysis[level_name] = {
                    'dataset_size_range': f"{small_size:,} - {large_size:,}",
                    'scaling_efficiency': scaling_efficiency,
                    'time_increase_factor': time_ratio,
                    'memory_increase_factor': large_metrics['mean_peak_memory'] / small_metrics['mean_peak_memory'],
                    'processing_rate_change': (large_metrics['mean_processing_rate'] - small_metrics['mean_processing_rate']) / small_metrics['mean_processing_rate'] if small_metrics['mean_processing_rate'] > 0 else 0,
                    'recommended_max_dataset_size': self._estimate_max_dataset_size(level_name, scaling_data)
                }

        return scaling_analysis

    def _estimate_max_dataset_size(self, level_name: str, scaling_data: Dict) -> int:
        """Estimate maximum recommended dataset size for optimization level"""
        opt_config = OPTIMIZATION_LEVELS[level_name]
        memory_limit_mb = opt_config.memory_limit_gb * 1024

        # Find largest successful dataset size with <80% memory usage
        max_safe_size = 0

        for size, metrics in scaling_data.items():
            if (metrics['success_rate'] > 0.8 and
                metrics['mean_peak_memory'] < memory_limit_mb * 0.8):
                max_safe_size = max(max_safe_size, size)

        # Extrapolate based on memory usage trend
        if max_safe_size > 0 and len(scaling_data) >= 2:
            # Simple linear extrapolation
            sizes = sorted(scaling_data.keys())
            if len(sizes) >= 2:
                largest_tested = max(sizes)
                largest_memory = scaling_data[largest_tested]['mean_peak_memory']

                if largest_memory > 0:
                    # Estimate how much larger we could go
                    memory_headroom = memory_limit_mb * 0.8 - largest_memory
                    if memory_headroom > 0:
                        # Assume linear memory scaling with dataset size
                        memory_per_employee = largest_memory / largest_tested
                        additional_employees = int(memory_headroom / memory_per_employee)
                        max_safe_size = max(max_safe_size, largest_tested + additional_employees)

        return max_safe_size

    def _generate_optimization_recommendations(
        self,
        benchmark_results: Dict[str, OptimizationLevelBenchmark]
    ) -> List[str]:
        """Generate optimization recommendations based on benchmark results"""
        recommendations = []

        # Find best performing level for different criteria
        best_memory_efficiency = max(benchmark_results.items(), key=lambda x: x[1].mean_metrics.memory_efficiency)
        best_processing_rate = max(benchmark_results.items(), key=lambda x: x[1].mean_metrics.processing_rate_records_per_sec)
        best_reliability = max(benchmark_results.items(), key=lambda x: x[1].mean_metrics.success_rate)

        recommendations.append(
            f"Best memory efficiency: {best_memory_efficiency[0]} level "
            f"({best_memory_efficiency[1].mean_metrics.memory_efficiency:.1f}% of limit)"
        )

        recommendations.append(
            f"Best processing rate: {best_processing_rate[0]} level "
            f"({best_processing_rate[1].mean_metrics.processing_rate_records_per_sec:.0f} records/sec)"
        )

        recommendations.append(
            f"Best reliability: {best_reliability[0]} level "
            f"({best_reliability[1].mean_metrics.success_rate:.1%} success rate)"
        )

        # Memory usage recommendations
        for level_name, benchmark in benchmark_results.items():
            memory_pct = benchmark.mean_metrics.memory_efficiency
            if memory_pct > 90:
                recommendations.append(
                    f"WARNING: {level_name} level uses {memory_pct:.1f}% of memory limit - "
                    f"consider using lower optimization level for large datasets"
                )
            elif memory_pct < 50:
                recommendations.append(
                    f"OPPORTUNITY: {level_name} level only uses {memory_pct:.1f}% of memory limit - "
                    f"could potentially handle larger datasets"
                )

        # Performance scaling recommendations
        scaling_analysis = self._analyze_scaling_characteristics(benchmark_results)
        for level_name, scaling_info in scaling_analysis.items():
            efficiency = scaling_info['scaling_efficiency']
            if efficiency < 0.7:
                recommendations.append(
                    f"SCALING CONCERN: {level_name} level shows poor scaling efficiency ({efficiency:.2f}) - "
                    f"performance degrades significantly with dataset size"
                )
            elif efficiency > 0.9:
                recommendations.append(
                    f"SCALING STRENGTH: {level_name} level shows excellent scaling efficiency ({efficiency:.2f})"
                )

        return recommendations

    def _generate_csv_comparison(
        self,
        benchmark_results: Dict[str, OptimizationLevelBenchmark],
        timestamp: str
    ):
        """Generate CSV comparison of optimization levels"""
        comparison_data = []

        for level_name, benchmark in benchmark_results.items():
            opt_config = OPTIMIZATION_LEVELS[level_name]

            comparison_data.append({
                'optimization_level': level_name,
                'memory_limit_gb': opt_config.memory_limit_gb,
                'batch_size': opt_config.batch_size,
                'mean_execution_time_seconds': benchmark.mean_metrics.execution_time_seconds,
                'median_execution_time_seconds': benchmark.median_metrics.execution_time_seconds,
                'std_dev_execution_time': benchmark.std_dev_metrics.execution_time_seconds,
                'mean_peak_memory_mb': benchmark.mean_metrics.peak_memory_mb,
                'memory_efficiency_pct': benchmark.mean_metrics.memory_efficiency,
                'mean_processing_rate_records_per_sec': benchmark.mean_metrics.processing_rate_records_per_sec,
                'success_rate': benchmark.mean_metrics.success_rate,
                'mean_records_processed': benchmark.mean_metrics.records_processed,
                'memory_limit_exceeded_rate': sum(1 for m in benchmark.individual_runs if m.memory_limit_exceeded) / len(benchmark.individual_runs) if benchmark.individual_runs else 0,
                'total_runs': len(benchmark.individual_runs)
            })

        df = pd.DataFrame(comparison_data)
        csv_path = self.results_dir / f"optimization_levels_comparison_{timestamp}.csv"
        df.to_csv(csv_path, index=False)

        logger.info(f"CSV comparison saved: {csv_path}")

    def _generate_performance_charts(
        self,
        benchmark_results: Dict[str, OptimizationLevelBenchmark],
        timestamp: str
    ):
        """Generate performance comparison charts"""
        try:
            # Setup matplotlib for non-interactive use
            plt.style.use('default')
            plt.rcParams['figure.figsize'] = (12, 8)

            # Create comparison charts
            fig, ((ax1, ax2), (ax3, ax4)) = plt.subplots(2, 2, figsize=(15, 12))

            levels = list(benchmark_results.keys())

            # Chart 1: Memory Usage Comparison
            memory_means = [benchmark_results[level].mean_metrics.peak_memory_mb for level in levels]
            memory_limits = [OPTIMIZATION_LEVELS[level].memory_limit_gb * 1024 for level in levels]

            x = range(len(levels))
            ax1.bar(x, memory_means, alpha=0.7, label='Peak Memory Used')
            ax1.plot(x, memory_limits, 'r--', marker='o', label='Memory Limit')
            ax1.set_xlabel('Optimization Level')
            ax1.set_ylabel('Memory (MB)')
            ax1.set_title('Memory Usage by Optimization Level')
            ax1.set_xticks(x)
            ax1.set_xticklabels(levels)
            ax1.legend()
            ax1.grid(True, alpha=0.3)

            # Chart 2: Processing Rate Comparison
            processing_rates = [benchmark_results[level].mean_metrics.processing_rate_records_per_sec for level in levels]
            ax2.bar(x, processing_rates, alpha=0.7, color='green')
            ax2.set_xlabel('Optimization Level')
            ax2.set_ylabel('Records/Second')
            ax2.set_title('Processing Rate by Optimization Level')
            ax2.set_xticks(x)
            ax2.set_xticklabels(levels)
            ax2.grid(True, alpha=0.3)

            # Chart 3: Execution Time Comparison
            execution_times = [benchmark_results[level].mean_metrics.execution_time_seconds for level in levels]
            ax3.bar(x, execution_times, alpha=0.7, color='orange')
            ax3.set_xlabel('Optimization Level')
            ax3.set_ylabel('Execution Time (seconds)')
            ax3.set_title('Average Execution Time by Optimization Level')
            ax3.set_xticks(x)
            ax3.set_xticklabels(levels)
            ax3.grid(True, alpha=0.3)

            # Chart 4: Success Rate and Memory Efficiency
            success_rates = [benchmark_results[level].mean_metrics.success_rate * 100 for level in levels]
            memory_efficiencies = [benchmark_results[level].mean_metrics.memory_efficiency for level in levels]

            ax4_twin = ax4.twinx()
            bars1 = ax4.bar([i-0.2 for i in x], success_rates, width=0.4, alpha=0.7, color='blue', label='Success Rate %')
            bars2 = ax4_twin.bar([i+0.2 for i in x], memory_efficiencies, width=0.4, alpha=0.7, color='red', label='Memory Efficiency %')

            ax4.set_xlabel('Optimization Level')
            ax4.set_ylabel('Success Rate (%)', color='blue')
            ax4_twin.set_ylabel('Memory Efficiency (%)', color='red')
            ax4.set_title('Success Rate vs Memory Efficiency')
            ax4.set_xticks(x)
            ax4.set_xticklabels(levels)

            # Add legends
            ax4.legend(loc='upper left')
            ax4_twin.legend(loc='upper right')

            plt.tight_layout()

            # Save chart
            chart_path = self.results_dir / f"optimization_levels_performance_charts_{timestamp}.png"
            plt.savefig(chart_path, dpi=300, bbox_inches='tight')
            plt.close()

            logger.info(f"Performance charts saved: {chart_path}")

        except Exception as e:
            logger.warning(f"Chart generation failed (matplotlib not available?): {e}")

def main():
    """CLI entry point for performance benchmarking"""
    import argparse

    parser = argparse.ArgumentParser(
        description="PlanWise Navigator Optimization Level Performance Benchmark",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        "--test-data-dir",
        type=Path,
        default=Path("data/stress_test"),
        help="Directory containing test datasets"
    )

    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("test_results/performance_benchmarks"),
        help="Directory to save benchmark results"
    )

    parser.add_argument(
        "--dataset-sizes",
        type=int,
        nargs="+",
        default=[10000, 50000, 100000],
        help="Dataset sizes to benchmark"
    )

    parser.add_argument(
        "--simulation-years",
        type=int,
        nargs="+",
        default=[2025, 2026],
        help="Simulation years"
    )

    parser.add_argument(
        "--runs-per-config",
        type=int,
        default=3,
        help="Number of runs per configuration for statistical accuracy"
    )

    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=60,
        help="Timeout per test in minutes"
    )

    parser.add_argument(
        "--quick-benchmark",
        action="store_true",
        help="Run quick benchmark with smaller scope"
    )

    args = parser.parse_args()

    if args.quick_benchmark:
        args.dataset_sizes = [10000, 50000]
        args.simulation_years = [2025]
        args.runs_per_config = 2
        args.timeout_minutes = 30

    logger.info(f"PlanWise Navigator Performance Benchmarking Suite")
    logger.info(f"Story S063-09: Optimization Level Comparison")

    # Create benchmarker
    benchmarker = PerformanceBenchmarker(args.test_data_dir, args.results_dir)

    # Run comprehensive benchmarks
    benchmark_results = benchmarker.run_optimization_level_comparison(
        dataset_sizes=args.dataset_sizes,
        simulation_years=args.simulation_years,
        runs_per_config=args.runs_per_config,
        timeout_minutes=args.timeout_minutes
    )

    # Print final summary
    logger.info(f"\n{'='*60}")
    logger.info(f"BENCHMARKING COMPLETED")
    logger.info(f"{'='*60}")

    for level_name, benchmark in benchmark_results.items():
        success_rate = benchmark.mean_metrics.success_rate
        memory_eff = benchmark.mean_metrics.memory_efficiency
        processing_rate = benchmark.mean_metrics.processing_rate_records_per_sec

        logger.info(f"{level_name.upper()} level:")
        logger.info(f"  Success rate: {success_rate:.1%}")
        logger.info(f"  Memory efficiency: {memory_eff:.1f}%")
        logger.info(f"  Processing rate: {processing_rate:.0f} records/sec")
        logger.info(f"  Total runs: {len(benchmark.individual_runs)}")

    logger.info(f"\nDetailed results saved to: {args.results_dir}")

if __name__ == "__main__":
    main()
