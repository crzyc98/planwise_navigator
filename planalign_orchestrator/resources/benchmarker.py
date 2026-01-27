"""
Performance benchmarking framework for optimal thread count detection.

Features:
- Systematic benchmarking of different thread counts
- Speedup and efficiency analysis
- Resource utilization correlation with performance
- Optimal configuration recommendations
"""

from __future__ import annotations

import time
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

from .data_models import BenchmarkResult

if TYPE_CHECKING:
    from ..logger import ProductionLogger
    from .memory_monitor import MemoryMonitor
    from .cpu_monitor import CPUMonitor


class PerformanceBenchmarker:
    """
    Performance benchmarking framework for optimal thread count detection.

    Features:
    - Systematic benchmarking of different thread counts
    - Speedup and efficiency analysis
    - Resource utilization correlation with performance
    - Optimal configuration recommendations
    """

    def __init__(
        self,
        memory_monitor: "MemoryMonitor",
        cpu_monitor: "CPUMonitor",
        logger: Optional["ProductionLogger"] = None,
    ):
        self.memory_monitor = memory_monitor
        self.cpu_monitor = cpu_monitor
        self.logger = logger

        # Benchmark configuration
        self.thread_counts_to_test = [1, 2, 4, 6, 8]
        self.benchmark_results: List[BenchmarkResult] = []

    def run_benchmark_suite(
        self,
        benchmark_function: Callable[[int], float],
        baseline_thread_count: int = 1,
        max_thread_count: Optional[int] = None,
    ) -> List[BenchmarkResult]:
        """
        Run comprehensive benchmark suite across different thread counts.

        Args:
            benchmark_function: Function that takes thread_count and returns execution_time
            baseline_thread_count: Thread count to use as baseline for speedup calculation
            max_thread_count: Maximum thread count to test

        Returns:
            List of benchmark results
        """
        if max_thread_count:
            test_counts = [
                t for t in self.thread_counts_to_test if t <= max_thread_count
            ]
        else:
            test_counts = self.thread_counts_to_test.copy()

        if baseline_thread_count not in test_counts:
            test_counts.insert(0, baseline_thread_count)

        results = []
        baseline_time = None

        for thread_count in sorted(test_counts):
            if self.logger:
                self.logger.info(f"Running benchmark with {thread_count} threads")

            try:
                # Capture initial resource state
                initial_memory = self.memory_monitor._capture_memory_snapshot()
                initial_cpu = self.cpu_monitor._capture_cpu_snapshot()

                # Run benchmark
                start_time = time.time()
                execution_time = benchmark_function(thread_count)
                end_time = time.time()

                # Capture final resource state
                final_memory = self.memory_monitor._capture_memory_snapshot()
                final_cpu = self.cpu_monitor._capture_cpu_snapshot()

                # Calculate resource usage
                memory_usage = final_memory.rss_mb - initial_memory.rss_mb
                avg_cpu = (initial_cpu.percent + final_cpu.percent) / 2

                # Calculate speedup and efficiency
                if thread_count == baseline_thread_count:
                    baseline_time = execution_time
                    speedup = 1.0
                    efficiency = 1.0
                else:
                    speedup = (
                        baseline_time / execution_time
                        if baseline_time and execution_time > 0
                        else 0.0
                    )
                    efficiency = speedup / thread_count if thread_count > 0 else 0.0

                result = BenchmarkResult(
                    thread_count=thread_count,
                    execution_time=execution_time,
                    memory_usage_mb=memory_usage,
                    cpu_utilization=avg_cpu,
                    speedup=speedup,
                    efficiency=efficiency,
                    success=True,
                )

                results.append(result)

                if self.logger:
                    self.logger.info(
                        f"Benchmark result: {thread_count} threads",
                        execution_time=execution_time,
                        speedup=speedup,
                        efficiency=efficiency,
                        memory_usage_mb=memory_usage,
                    )

            except Exception as e:
                error_result = BenchmarkResult(
                    thread_count=thread_count,
                    execution_time=0.0,
                    memory_usage_mb=0.0,
                    cpu_utilization=0.0,
                    speedup=0.0,
                    efficiency=0.0,
                    success=False,
                    error_message=str(e),
                )
                results.append(error_result)

                if self.logger:
                    self.logger.error(
                        f"Benchmark failed for {thread_count} threads: {e}"
                    )

        self.benchmark_results.extend(results)
        return results

    def analyze_benchmark_results(
        self,
        results: List[BenchmarkResult],
    ) -> Dict[str, Any]:
        """Analyze benchmark results and provide recommendations."""
        successful_results = [r for r in results if r.success]

        if not successful_results:
            return {
                "optimal_thread_count": 1,
                "recommendation": "fallback_to_single_thread",
                "analysis": "all_benchmarks_failed",
            }

        # Find optimal thread count based on efficiency
        best_efficiency = max(successful_results, key=lambda r: r.efficiency)
        best_speedup = max(successful_results, key=lambda r: r.speedup)

        # Conservative recommendation prioritizing efficiency
        optimal_thread_count = best_efficiency.thread_count

        # Analysis summary
        analysis = {
            "optimal_thread_count": optimal_thread_count,
            "best_efficiency_threads": best_efficiency.thread_count,
            "best_speedup_threads": best_speedup.thread_count,
            "max_speedup": best_speedup.speedup,
            "max_efficiency": best_efficiency.efficiency,
            "recommendation": self._generate_recommendation(
                successful_results, optimal_thread_count
            ),
            "results_summary": [
                {
                    "threads": r.thread_count,
                    "speedup": r.speedup,
                    "efficiency": r.efficiency,
                    "memory_mb": r.memory_usage_mb,
                }
                for r in successful_results
            ],
        }

        return analysis

    def _generate_recommendation(
        self,
        results: List[BenchmarkResult],
        optimal_count: int,
    ) -> str:
        """Generate human-readable recommendation based on benchmark results."""
        if optimal_count == 1:
            return "single_thread_optimal"
        elif optimal_count <= 2:
            return "low_parallelism_recommended"
        elif optimal_count <= 4:
            return "moderate_parallelism_recommended"
        else:
            return "high_parallelism_beneficial"
