"""
Dynamic thread count optimization based on system resources and performance.

Features:
- Automatic thread count adjustment based on resource availability
- Performance-based optimization using historical execution data
- Graceful degradation under resource pressure
- Integration with benchmarking results for optimal scaling
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple, TYPE_CHECKING

import psutil

from .data_models import ResourcePressure

if TYPE_CHECKING:
    from ..logger import ProductionLogger
    from .memory_monitor import MemoryMonitor
    from .cpu_monitor import CPUMonitor


class AdaptiveThreadAdjuster:
    """
    Dynamic thread count optimization based on system resources and performance.

    Features:
    - Automatic thread count adjustment based on resource availability
    - Performance-based optimization using historical execution data
    - Graceful degradation under resource pressure
    - Integration with benchmarking results for optimal scaling
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

        # Adjustment history for learning
        self.adjustment_history: List[Dict[str, Any]] = []
        self.performance_history: Dict[int, List[float]] = (
            {}
        )  # thread_count -> execution_times

        # Configuration
        self.min_threads = 1
        self.max_threads = min(16, psutil.cpu_count())
        self.adjustment_cooldown = 30.0  # seconds
        self.last_adjustment_time = 0.0

    def get_optimal_thread_count(
        self,
        current_threads: int,
        execution_context: Optional[Dict[str, Any]] = None,
    ) -> Tuple[int, str]:
        """
        Determine optimal thread count based on current system state.

        Returns:
            Tuple of (recommended_thread_count, reason)
        """
        now = time.time()

        # Check cooldown period
        if now - self.last_adjustment_time < self.adjustment_cooldown:
            return current_threads, "adjustment_cooldown"

        # Get current resource pressure
        memory_pressure = self.memory_monitor.get_current_pressure()
        cpu_pressure = self.cpu_monitor.get_current_pressure()

        # Handle critical resource pressure immediately
        if memory_pressure.memory_pressure == "critical":
            new_count = max(1, current_threads - 3)
            reason = (
                f"critical_memory_pressure_{memory_pressure.memory_usage_mb:.0f}mb"
            )
            return new_count, reason

        if cpu_pressure == "critical":
            new_count = max(1, current_threads - 2)
            reason = "critical_cpu_pressure"
            return new_count, reason

        # Get performance-based recommendation
        perf_recommendation = self._get_performance_based_recommendation(
            current_threads
        )

        # Get resource-based recommendation
        resource_recommendation = self._get_resource_based_recommendation(
            memory_pressure, cpu_pressure
        )

        # Combine recommendations conservatively
        recommended_count = min(perf_recommendation, resource_recommendation)
        recommended_count = max(
            self.min_threads, min(self.max_threads, recommended_count)
        )

        # Determine reason
        if recommended_count != current_threads:
            if recommended_count < current_threads:
                reason = "resource_pressure_reduction"
            else:
                reason = "performance_optimization_increase"

            self.last_adjustment_time = now
            self._record_adjustment(
                current_threads, recommended_count, reason, execution_context
            )
        else:
            reason = "no_adjustment_needed"

        return recommended_count, reason

    def record_performance(self, thread_count: int, execution_time: float) -> None:
        """Record performance metrics for a given thread count."""
        if thread_count not in self.performance_history:
            self.performance_history[thread_count] = []

        self.performance_history[thread_count].append(execution_time)

        # Keep only recent performance data
        if len(self.performance_history[thread_count]) > 20:
            self.performance_history[thread_count] = self.performance_history[
                thread_count
            ][-10:]

    def _get_performance_based_recommendation(self, current_threads: int) -> int:
        """Get thread count recommendation based on historical performance."""
        if len(self.performance_history) < 2:
            return current_threads

        # Analyze performance across different thread counts
        best_thread_count = current_threads
        best_avg_time = float("inf")

        for thread_count, execution_times in self.performance_history.items():
            if len(execution_times) >= 3:  # Need sufficient samples
                avg_time = sum(execution_times[-5:]) / len(execution_times[-5:])
                if avg_time < best_avg_time:
                    best_avg_time = avg_time
                    best_thread_count = thread_count

        # Don't make dramatic jumps
        if abs(best_thread_count - current_threads) > 2:
            if best_thread_count > current_threads:
                return current_threads + 1
            else:
                return current_threads - 1

        return best_thread_count

    def _get_resource_based_recommendation(
        self,
        memory_pressure: ResourcePressure,
        cpu_pressure: str,
    ) -> int:
        """Get thread count recommendation based on current resource usage."""
        cpu_estimate = self.cpu_monitor.get_optimal_thread_count_estimate()

        # Start with CPU-based estimate
        recommendation = cpu_estimate

        # Adjust for memory pressure
        if memory_pressure.memory_pressure == "high":
            recommendation = max(1, recommendation - 2)
        elif memory_pressure.memory_pressure == "moderate":
            recommendation = max(1, recommendation - 1)

        # Adjust for CPU pressure
        if cpu_pressure == "high":
            recommendation = max(1, recommendation - 1)
        elif cpu_pressure == "moderate":
            recommendation = max(1, min(recommendation, 2))

        return recommendation

    def _record_adjustment(
        self,
        old_count: int,
        new_count: int,
        reason: str,
        context: Optional[Dict[str, Any]],
    ) -> None:
        """Record thread count adjustment for analysis."""
        adjustment_record = {
            "timestamp": time.time(),
            "old_thread_count": old_count,
            "new_thread_count": new_count,
            "reason": reason,
            "context": context or {},
        }

        self.adjustment_history.append(adjustment_record)

        # Keep only recent adjustments
        if len(self.adjustment_history) > 100:
            self.adjustment_history = self.adjustment_history[-50:]

        if self.logger:
            self.logger.info(
                "Thread count adjustment",
                old_threads=old_count,
                new_threads=new_count,
                reason=reason,
            )
