#!/usr/bin/env python3
"""
Advanced Memory Management & Optimization for Navigator Orchestrator

Story S067-03: Implementation of intelligent memory management during multi-threaded execution
to keep the system stable under varying load conditions.

Features:
- Memory usage monitoring per thread with configurable limits
- Real-time memory and CPU tracking during execution
- Memory pressure detection with automatic throttling mechanisms
- Adaptive thread scaling based on available system resources
- Resource contention detection and mitigation strategies
- Performance benchmarking framework for thread count optimization
- Graceful degradation when memory limits are approached
"""

from __future__ import annotations

import gc
import os
import threading
import time
from collections import deque
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable, Dict, List, Optional, Tuple
from contextlib import contextmanager
import warnings

import psutil

from .logger import ProductionLogger


@dataclass
class MemoryUsageSnapshot:
    """Snapshot of memory usage at a point in time."""
    timestamp: float
    rss_mb: float
    vms_mb: float
    percent: float
    available_mb: float
    thread_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CPUUsageSnapshot:
    """Snapshot of CPU usage at a point in time."""
    timestamp: float
    percent: float
    load_avg: Tuple[float, float, float]
    core_count: int
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourcePressure:
    """Current resource pressure status."""
    memory_pressure: str  # "none", "moderate", "high", "critical"
    cpu_pressure: str     # "none", "moderate", "high", "critical"
    memory_usage_mb: float
    memory_percent: float
    cpu_percent: float
    recommended_action: str
    thread_count_adjustment: int = 0


@dataclass
class BenchmarkResult:
    """Result from performance benchmark."""
    thread_count: int
    execution_time: float
    memory_usage_mb: float
    cpu_utilization: float
    speedup: float
    efficiency: float
    success: bool
    error_message: Optional[str] = None


class MemoryMonitor:
    """
    Memory usage monitoring with per-thread tracking and pressure detection.

    Features:
    - Real-time memory monitoring with configurable intervals
    - Per-thread memory attribution (best effort)
    - Memory pressure detection with multiple threshold levels
    - Historical memory usage tracking for trend analysis
    - Memory leak detection capabilities
    """

    def __init__(
        self,
        monitoring_interval: float = 1.0,
        history_size: int = 100,
        thresholds: Optional[Dict[str, float]] = None
    ):
        self.monitoring_interval = monitoring_interval
        self.history_size = history_size

        # Default thresholds in MB
        self.thresholds = thresholds or {
            "moderate_mb": 2000.0,
            "high_mb": 3000.0,
            "critical_mb": 3500.0,
            "gc_trigger_mb": 2500.0,
            "fallback_trigger_mb": 3200.0
        }

        # Memory history and tracking
        self.memory_history: deque[MemoryUsageSnapshot] = deque(maxlen=history_size)
        self.thread_memory: Dict[str, deque[MemoryUsageSnapshot]] = {}

        # Monitoring state
        self._monitoring_active = False
        self._monitoring_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        # Process handle for monitoring
        self._process = psutil.Process()

    def start_monitoring(self) -> None:
        """Start background memory monitoring."""
        with self._lock:
            if self._monitoring_active:
                return

            self._monitoring_active = True
            self._monitoring_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="MemoryMonitor"
            )
            self._monitoring_thread.start()

    def stop_monitoring(self) -> None:
        """Stop background memory monitoring."""
        with self._lock:
            self._monitoring_active = False
            if self._monitoring_thread and self._monitoring_thread.is_alive():
                self._monitoring_thread.join(timeout=2.0)
            self._monitoring_thread = None

    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._monitoring_active:
            try:
                snapshot = self._capture_memory_snapshot()

                with self._lock:
                    self.memory_history.append(snapshot)

                    # Check for pressure and trigger GC if needed
                    if snapshot.rss_mb > self.thresholds["gc_trigger_mb"]:
                        self._trigger_garbage_collection()

                time.sleep(self.monitoring_interval)

            except Exception:
                # Silently continue monitoring on errors
                time.sleep(self.monitoring_interval)

    def _capture_memory_snapshot(self, thread_id: Optional[str] = None) -> MemoryUsageSnapshot:
        """Capture current memory usage snapshot."""
        try:
            memory_info = self._process.memory_info()
            virtual_memory = psutil.virtual_memory()

            snapshot = MemoryUsageSnapshot(
                timestamp=time.time(),
                rss_mb=memory_info.rss / 1024 / 1024,
                vms_mb=memory_info.vms / 1024 / 1024,
                percent=virtual_memory.percent,
                available_mb=virtual_memory.available / 1024 / 1024,
                thread_id=thread_id or threading.current_thread().name
            )

            return snapshot

        except Exception:
            # Return minimal snapshot on error
            return MemoryUsageSnapshot(
                timestamp=time.time(),
                rss_mb=0.0,
                vms_mb=0.0,
                percent=0.0,
                available_mb=0.0,
                thread_id=thread_id
            )

    def track_thread_memory(self, thread_id: str) -> None:
        """Start tracking memory usage for a specific thread."""
        snapshot = self._capture_memory_snapshot(thread_id)

        with self._lock:
            if thread_id not in self.thread_memory:
                self.thread_memory[thread_id] = deque(maxlen=self.history_size)
            self.thread_memory[thread_id].append(snapshot)

    def get_current_pressure(self) -> ResourcePressure:
        """Get current memory pressure assessment."""
        snapshot = self._capture_memory_snapshot()

        # Determine pressure level
        memory_mb = snapshot.rss_mb

        if memory_mb > self.thresholds["critical_mb"]:
            pressure_level = "critical"
            recommended_action = "immediate_fallback"
        elif memory_mb > self.thresholds["high_mb"]:
            pressure_level = "high"
            recommended_action = "reduce_threads"
        elif memory_mb > self.thresholds["moderate_mb"]:
            pressure_level = "moderate"
            recommended_action = "monitor_closely"
        else:
            pressure_level = "none"
            recommended_action = "continue_normal"

        # Calculate thread count adjustment recommendation
        thread_adjustment = 0
        if pressure_level == "critical":
            thread_adjustment = -3
        elif pressure_level == "high":
            thread_adjustment = -2
        elif pressure_level == "moderate":
            thread_adjustment = -1

        return ResourcePressure(
            memory_pressure=pressure_level,
            cpu_pressure="none",  # CPU monitor will update this
            memory_usage_mb=memory_mb,
            memory_percent=snapshot.percent,
            cpu_percent=0.0,
            recommended_action=recommended_action,
            thread_count_adjustment=thread_adjustment
        )

    def get_memory_trends(self, window_minutes: int = 5) -> Dict[str, Any]:
        """Analyze memory usage trends over a time window."""
        cutoff_time = time.time() - (window_minutes * 60)

        with self._lock:
            recent_snapshots = [
                s for s in self.memory_history
                if s.timestamp >= cutoff_time
            ]

        if len(recent_snapshots) < 2:
            return {
                "trend": "insufficient_data",
                "growth_rate_mb_per_minute": 0.0,
                "peak_usage_mb": 0.0,
                "average_usage_mb": 0.0
            }

        # Calculate trends
        start_usage = recent_snapshots[0].rss_mb
        end_usage = recent_snapshots[-1].rss_mb
        time_span = recent_snapshots[-1].timestamp - recent_snapshots[0].timestamp

        growth_rate = (end_usage - start_usage) / (time_span / 60) if time_span > 0 else 0.0
        peak_usage = max(s.rss_mb for s in recent_snapshots)
        avg_usage = sum(s.rss_mb for s in recent_snapshots) / len(recent_snapshots)

        # Determine trend
        if growth_rate > 100:  # More than 100MB/minute growth
            trend = "rapidly_increasing"
        elif growth_rate > 20:  # More than 20MB/minute growth
            trend = "increasing"
        elif growth_rate < -20:
            trend = "decreasing"
        else:
            trend = "stable"

        return {
            "trend": trend,
            "growth_rate_mb_per_minute": growth_rate,
            "peak_usage_mb": peak_usage,
            "average_usage_mb": avg_usage,
            "sample_count": len(recent_snapshots)
        }

    def detect_memory_leaks(self, threshold_mb: float = 800.0, window_minutes: int = 15) -> bool:
        """Detect potential memory leaks based on sustained growth."""
        trends = self.get_memory_trends(window_minutes)

        # Memory leak indicators:
        # 1. Sustained growth over time window
        # 2. Growth rate exceeding threshold
        # 3. No recent decreases in memory usage

        if trends["trend"] == "insufficient_data":
            return False

        is_leak = (
            trends["trend"] in ["increasing", "rapidly_increasing"] and
            trends["growth_rate_mb_per_minute"] > threshold_mb / window_minutes and
            trends["peak_usage_mb"] > self.thresholds["high_mb"]
        )

        return is_leak

    def _trigger_garbage_collection(self) -> None:
        """Trigger garbage collection to free memory."""
        try:
            collected = gc.collect()
            # Force collection of all generations
            for generation in range(3):
                gc.collect(generation)
        except Exception:
            pass  # Silently continue if GC fails

    @contextmanager
    def monitor_operation(self, operation_name: str):
        """Context manager to monitor memory usage during an operation."""
        start_snapshot = self._capture_memory_snapshot()
        start_time = time.time()

        try:
            yield
        finally:
            end_snapshot = self._capture_memory_snapshot()
            end_time = time.time()

            # Calculate memory delta for the operation
            memory_delta = end_snapshot.rss_mb - start_snapshot.rss_mb
            duration = end_time - start_time

            # Log significant memory usage
            if abs(memory_delta) > 50:  # More than 50MB change
                print(f"Operation {operation_name}: {memory_delta:+.1f}MB memory change in {duration:.1f}s")


class CPUMonitor:
    """
    Real-time CPU utilization tracking and analysis.

    Features:
    - Real-time CPU monitoring with configurable intervals
    - Load average tracking for system health assessment
    - CPU pressure detection with threshold-based alerts
    - Per-core utilization tracking when available
    - Integration with thread scaling decisions
    """

    def __init__(
        self,
        monitoring_interval: float = 1.0,
        history_size: int = 100,
        thresholds: Optional[Dict[str, float]] = None
    ):
        self.monitoring_interval = monitoring_interval
        self.history_size = history_size

        # Default CPU thresholds
        self.thresholds = thresholds or {
            "moderate_percent": 70.0,
            "high_percent": 85.0,
            "critical_percent": 95.0
        }

        # CPU history tracking
        self.cpu_history: deque[CPUUsageSnapshot] = deque(maxlen=history_size)

        # Monitoring state
        self._monitoring_active = False
        self._monitoring_thread: Optional[threading.Thread] = None
        self._lock = threading.RLock()

        # System information
        self.core_count = psutil.cpu_count()
        self.logical_cpu_count = psutil.cpu_count(logical=True)

    def start_monitoring(self) -> None:
        """Start background CPU monitoring."""
        with self._lock:
            if self._monitoring_active:
                return

            # Initialize CPU monitoring
            psutil.cpu_percent(interval=None)

            self._monitoring_active = True
            self._monitoring_thread = threading.Thread(
                target=self._monitor_loop,
                daemon=True,
                name="CPUMonitor"
            )
            self._monitoring_thread.start()

    def stop_monitoring(self) -> None:
        """Stop background CPU monitoring."""
        with self._lock:
            self._monitoring_active = False
            if self._monitoring_thread and self._monitoring_thread.is_alive():
                self._monitoring_thread.join(timeout=2.0)
            self._monitoring_thread = None

    def _monitor_loop(self) -> None:
        """Background monitoring loop."""
        while self._monitoring_active:
            try:
                snapshot = self._capture_cpu_snapshot()

                with self._lock:
                    self.cpu_history.append(snapshot)

                time.sleep(self.monitoring_interval)

            except Exception:
                # Silently continue monitoring on errors
                time.sleep(self.monitoring_interval)

    def _capture_cpu_snapshot(self) -> CPUUsageSnapshot:
        """Capture current CPU usage snapshot."""
        try:
            cpu_percent = psutil.cpu_percent(interval=None)
            load_avg = os.getloadavg() if hasattr(os, 'getloadavg') else (0.0, 0.0, 0.0)

            snapshot = CPUUsageSnapshot(
                timestamp=time.time(),
                percent=cpu_percent,
                load_avg=load_avg,
                core_count=self.core_count
            )

            return snapshot

        except Exception:
            # Return minimal snapshot on error
            return CPUUsageSnapshot(
                timestamp=time.time(),
                percent=0.0,
                load_avg=(0.0, 0.0, 0.0),
                core_count=self.core_count
            )

    def get_current_pressure(self) -> str:
        """Get current CPU pressure level."""
        snapshot = self._capture_cpu_snapshot()
        cpu_percent = snapshot.percent

        if cpu_percent > self.thresholds["critical_percent"]:
            return "critical"
        elif cpu_percent > self.thresholds["high_percent"]:
            return "high"
        elif cpu_percent > self.thresholds["moderate_percent"]:
            return "moderate"
        else:
            return "none"

    def get_cpu_trends(self, window_minutes: int = 5) -> Dict[str, Any]:
        """Analyze CPU usage trends over a time window."""
        cutoff_time = time.time() - (window_minutes * 60)

        with self._lock:
            recent_snapshots = [
                s for s in self.cpu_history
                if s.timestamp >= cutoff_time
            ]

        if len(recent_snapshots) < 2:
            return {
                "trend": "insufficient_data",
                "average_cpu": 0.0,
                "peak_cpu": 0.0,
                "load_average_1m": 0.0
            }

        avg_cpu = sum(s.percent for s in recent_snapshots) / len(recent_snapshots)
        peak_cpu = max(s.percent for s in recent_snapshots)
        latest_load = recent_snapshots[-1].load_avg[0] if recent_snapshots else 0.0

        return {
            "trend": "analyzed",
            "average_cpu": avg_cpu,
            "peak_cpu": peak_cpu,
            "load_average_1m": latest_load,
            "sample_count": len(recent_snapshots)
        }

    def get_optimal_thread_count_estimate(self) -> int:
        """Estimate optimal thread count based on current CPU utilization."""
        current_cpu = self._capture_cpu_snapshot().percent

        # Conservative thread count estimation
        if current_cpu < 30:
            # Low utilization - can likely handle more threads
            return min(self.logical_cpu_count, 8)
        elif current_cpu < 60:
            # Moderate utilization - use physical cores
            return min(self.core_count, 4)
        elif current_cpu < 80:
            # High utilization - be conservative
            return max(1, min(self.core_count // 2, 2))
        else:
            # Very high utilization - single thread only
            return 1


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
        memory_monitor: MemoryMonitor,
        cpu_monitor: CPUMonitor,
        logger: Optional[ProductionLogger] = None
    ):
        self.memory_monitor = memory_monitor
        self.cpu_monitor = cpu_monitor
        self.logger = logger

        # Adjustment history for learning
        self.adjustment_history: List[Dict[str, Any]] = []
        self.performance_history: Dict[int, List[float]] = {}  # thread_count -> execution_times

        # Configuration
        self.min_threads = 1
        self.max_threads = min(16, psutil.cpu_count())
        self.adjustment_cooldown = 30.0  # seconds
        self.last_adjustment_time = 0.0

    def get_optimal_thread_count(
        self,
        current_threads: int,
        execution_context: Optional[Dict[str, Any]] = None
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
            reason = f"critical_memory_pressure_{memory_pressure.memory_usage_mb:.0f}mb"
            return new_count, reason

        if cpu_pressure == "critical":
            new_count = max(1, current_threads - 2)
            reason = "critical_cpu_pressure"
            return new_count, reason

        # Get performance-based recommendation
        perf_recommendation = self._get_performance_based_recommendation(current_threads)

        # Get resource-based recommendation
        resource_recommendation = self._get_resource_based_recommendation(
            memory_pressure, cpu_pressure
        )

        # Combine recommendations conservatively
        recommended_count = min(perf_recommendation, resource_recommendation)
        recommended_count = max(self.min_threads, min(self.max_threads, recommended_count))

        # Determine reason
        if recommended_count != current_threads:
            if recommended_count < current_threads:
                reason = "resource_pressure_reduction"
            else:
                reason = "performance_optimization_increase"

            self.last_adjustment_time = now
            self._record_adjustment(current_threads, recommended_count, reason, execution_context)
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
            self.performance_history[thread_count] = self.performance_history[thread_count][-10:]

    def _get_performance_based_recommendation(self, current_threads: int) -> int:
        """Get thread count recommendation based on historical performance."""
        if len(self.performance_history) < 2:
            return current_threads

        # Analyze performance across different thread counts
        best_thread_count = current_threads
        best_avg_time = float('inf')

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
        cpu_pressure: str
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
        context: Optional[Dict[str, Any]]
    ) -> None:
        """Record thread count adjustment for analysis."""
        adjustment_record = {
            "timestamp": time.time(),
            "old_thread_count": old_count,
            "new_thread_count": new_count,
            "reason": reason,
            "context": context or {}
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
                reason=reason
            )


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
        memory_monitor: MemoryMonitor,
        cpu_monitor: CPUMonitor,
        logger: Optional[ProductionLogger] = None
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
        max_thread_count: Optional[int] = None
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
            test_counts = [t for t in self.thread_counts_to_test if t <= max_thread_count]
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
                    speedup = baseline_time / execution_time if baseline_time and execution_time > 0 else 0.0
                    efficiency = speedup / thread_count if thread_count > 0 else 0.0

                result = BenchmarkResult(
                    thread_count=thread_count,
                    execution_time=execution_time,
                    memory_usage_mb=memory_usage,
                    cpu_utilization=avg_cpu,
                    speedup=speedup,
                    efficiency=efficiency,
                    success=True
                )

                results.append(result)

                if self.logger:
                    self.logger.info(
                        f"Benchmark result: {thread_count} threads",
                        execution_time=execution_time,
                        speedup=speedup,
                        efficiency=efficiency,
                        memory_usage_mb=memory_usage
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
                    error_message=str(e)
                )
                results.append(error_result)

                if self.logger:
                    self.logger.error(f"Benchmark failed for {thread_count} threads: {e}")

        self.benchmark_results.extend(results)
        return results

    def analyze_benchmark_results(
        self,
        results: List[BenchmarkResult]
    ) -> Dict[str, Any]:
        """Analyze benchmark results and provide recommendations."""
        successful_results = [r for r in results if r.success]

        if not successful_results:
            return {
                "optimal_thread_count": 1,
                "recommendation": "fallback_to_single_thread",
                "analysis": "all_benchmarks_failed"
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
            "recommendation": self._generate_recommendation(successful_results, optimal_thread_count),
            "results_summary": [
                {
                    "threads": r.thread_count,
                    "speedup": r.speedup,
                    "efficiency": r.efficiency,
                    "memory_mb": r.memory_usage_mb
                }
                for r in successful_results
            ]
        }

        return analysis

    def _generate_recommendation(
        self,
        results: List[BenchmarkResult],
        optimal_count: int
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


class ResourceManager:
    """
    Comprehensive resource management system with intelligent memory management,
    adaptive thread scaling, and performance optimization.

    Features:
    - Integrated memory and CPU monitoring
    - Adaptive thread count optimization
    - Resource pressure detection and mitigation
    - Performance benchmarking capabilities
    - Graceful degradation under load
    """

    def __init__(
        self,
        config: Optional[Dict[str, Any]] = None,
        logger: Optional[ProductionLogger] = None
    ):
        self.logger = logger
        self.config = config or {}

        # Initialize monitors
        memory_config = self.config.get("memory", {})
        cpu_config = self.config.get("cpu", {})

        self.memory_monitor = MemoryMonitor(
            monitoring_interval=memory_config.get("monitoring_interval", 1.0),
            history_size=memory_config.get("history_size", 100),
            thresholds=memory_config.get("thresholds")
        )

        self.cpu_monitor = CPUMonitor(
            monitoring_interval=cpu_config.get("monitoring_interval", 1.0),
            history_size=cpu_config.get("history_size", 100),
            thresholds=cpu_config.get("thresholds")
        )

        # Initialize adaptive components
        self.thread_adjuster = AdaptiveThreadAdjuster(
            self.memory_monitor, self.cpu_monitor, logger
        )

        self.benchmarker = PerformanceBenchmarker(
            self.memory_monitor, self.cpu_monitor, logger
        )

        # Resource management state
        self._monitoring_active = False
        self._resource_hooks: List[Callable[[ResourcePressure], None]] = []

    def start_monitoring(self) -> None:
        """Start all resource monitoring components."""
        if self._monitoring_active:
            return

        self.memory_monitor.start_monitoring()
        self.cpu_monitor.start_monitoring()
        self._monitoring_active = True

        if self.logger:
            self.logger.info("Resource monitoring started")

    def stop_monitoring(self) -> None:
        """Stop all resource monitoring components."""
        if not self._monitoring_active:
            return

        self.memory_monitor.stop_monitoring()
        self.cpu_monitor.stop_monitoring()
        self._monitoring_active = False

        if self.logger:
            self.logger.info("Resource monitoring stopped")

    def optimize_thread_count(
        self,
        current_threads: int,
        context: Optional[Dict[str, Any]] = None
    ) -> Tuple[int, str]:
        """
        Dynamically adjust thread count based on system resources and performance.

        Returns:
            Tuple of (optimal_thread_count, reason)
        """
        return self.thread_adjuster.get_optimal_thread_count(current_threads, context)

    def get_resource_status(self) -> Dict[str, Any]:
        """Get comprehensive resource status and recommendations."""
        memory_pressure = self.memory_monitor.get_current_pressure()
        cpu_pressure = self.cpu_monitor.get_current_pressure()
        memory_trends = self.memory_monitor.get_memory_trends()
        cpu_trends = self.cpu_monitor.get_cpu_trends()

        return {
            "timestamp": time.time(),
            "memory": {
                "pressure": memory_pressure.memory_pressure,
                "usage_mb": memory_pressure.memory_usage_mb,
                "percent": memory_pressure.memory_percent,
                "trends": memory_trends,
                "leak_detected": self.memory_monitor.detect_memory_leaks()
            },
            "cpu": {
                "pressure": cpu_pressure,
                "current_percent": self.cpu_monitor._capture_cpu_snapshot().percent,
                "trends": cpu_trends,
                "optimal_thread_estimate": self.cpu_monitor.get_optimal_thread_count_estimate()
            },
            "recommendations": {
                "action": memory_pressure.recommended_action,
                "thread_adjustment": memory_pressure.thread_count_adjustment
            }
        }

    def add_resource_hook(self, hook: Callable[[ResourcePressure], None]) -> None:
        """Add a callback hook for resource pressure changes."""
        self._resource_hooks.append(hook)

    def check_resource_health(self) -> bool:
        """Check if system resources are healthy for continued operation."""
        memory_pressure = self.memory_monitor.get_current_pressure()
        cpu_pressure = self.cpu_monitor.get_current_pressure()

        # System is unhealthy if either resource is at critical pressure
        return (
            memory_pressure.memory_pressure != "critical" and
            cpu_pressure != "critical"
        )

    def trigger_resource_cleanup(self) -> Dict[str, Any]:
        """Trigger resource cleanup and return status."""
        initial_memory = self.memory_monitor._capture_memory_snapshot().rss_mb

        # Trigger garbage collection
        self.memory_monitor._trigger_garbage_collection()

        # Wait a moment for cleanup
        time.sleep(1.0)

        final_memory = self.memory_monitor._capture_memory_snapshot().rss_mb
        memory_freed = initial_memory - final_memory

        cleanup_result = {
            "initial_memory_mb": initial_memory,
            "final_memory_mb": final_memory,
            "memory_freed_mb": memory_freed,
            "cleanup_effective": memory_freed > 10  # More than 10MB freed
        }

        if self.logger:
            self.logger.info("Resource cleanup executed", **cleanup_result)

        return cleanup_result

    @contextmanager
    def monitor_execution(self, operation_name: str, expected_thread_count: int = 1):
        """Context manager for monitoring resource usage during execution."""
        context = {
            "operation": operation_name,
            "expected_threads": expected_thread_count
        }

        start_time = time.time()
        initial_status = self.get_resource_status()

        # Record performance start
        with self.memory_monitor.monitor_operation(operation_name):
            try:
                yield self
                success = True
                error = None
            except Exception as e:
                success = False
                error = str(e)
                raise
            finally:
                end_time = time.time()
                execution_time = end_time - start_time

                # Record performance for thread optimization
                self.thread_adjuster.record_performance(expected_thread_count, execution_time)

                final_status = self.get_resource_status()

                # Log execution summary
                if self.logger:
                    self.logger.info(
                        f"Resource monitoring complete: {operation_name}",
                        execution_time=execution_time,
                        success=success,
                        error=error,
                        initial_memory_mb=initial_status["memory"]["usage_mb"],
                        final_memory_mb=final_status["memory"]["usage_mb"],
                        memory_delta_mb=final_status["memory"]["usage_mb"] - initial_status["memory"]["usage_mb"]
                    )
