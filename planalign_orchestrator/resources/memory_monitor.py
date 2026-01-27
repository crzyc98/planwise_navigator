"""
Memory usage monitoring with per-thread tracking and pressure detection.

Features:
- Real-time memory monitoring with configurable intervals
- Per-thread memory attribution (best effort)
- Memory pressure detection with multiple threshold levels
- Historical memory usage tracking for trend analysis
- Memory leak detection capabilities
"""

from __future__ import annotations

import gc
import threading
import time
from collections import deque
from contextlib import contextmanager
from typing import Any, Dict, Optional

import psutil

from .data_models import MemoryUsageSnapshot, ResourcePressure


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
        thresholds: Optional[Dict[str, float]] = None,
    ):
        self.monitoring_interval = monitoring_interval
        self.history_size = history_size

        # Default thresholds in MB
        self.thresholds = thresholds or {
            "moderate_mb": 2000.0,
            "high_mb": 3000.0,
            "critical_mb": 3500.0,
            "gc_trigger_mb": 2500.0,
            "fallback_trigger_mb": 3200.0,
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
                target=self._monitor_loop, daemon=True, name="MemoryMonitor"
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

    def _capture_memory_snapshot(
        self, thread_id: Optional[str] = None
    ) -> MemoryUsageSnapshot:
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
                thread_id=thread_id or threading.current_thread().name,
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
                thread_id=thread_id,
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
            thread_count_adjustment=thread_adjustment,
        )

    def get_memory_trends(self, window_minutes: int = 5) -> Dict[str, Any]:
        """Analyze memory usage trends over a time window."""
        cutoff_time = time.time() - (window_minutes * 60)

        with self._lock:
            recent_snapshots = [
                s for s in self.memory_history if s.timestamp >= cutoff_time
            ]

        if len(recent_snapshots) < 2:
            return {
                "trend": "insufficient_data",
                "growth_rate_mb_per_minute": 0.0,
                "peak_usage_mb": 0.0,
                "average_usage_mb": 0.0,
            }

        # Calculate trends
        start_usage = recent_snapshots[0].rss_mb
        end_usage = recent_snapshots[-1].rss_mb
        time_span = recent_snapshots[-1].timestamp - recent_snapshots[0].timestamp

        growth_rate = (
            (end_usage - start_usage) / (time_span / 60) if time_span > 0 else 0.0
        )
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
            "sample_count": len(recent_snapshots),
        }

    def detect_memory_leaks(
        self, threshold_mb: float = 800.0, window_minutes: int = 15
    ) -> bool:
        """Detect potential memory leaks based on sustained growth."""
        trends = self.get_memory_trends(window_minutes)

        # Memory leak indicators:
        # 1. Sustained growth over time window
        # 2. Growth rate exceeding threshold
        # 3. No recent decreases in memory usage

        if trends["trend"] == "insufficient_data":
            return False

        is_leak = (
            trends["trend"] in ["increasing", "rapidly_increasing"]
            and trends["growth_rate_mb_per_minute"] > threshold_mb / window_minutes
            and trends["peak_usage_mb"] > self.thresholds["high_mb"]
        )

        return is_leak

    def _trigger_garbage_collection(self) -> None:
        """Trigger garbage collection to free memory."""
        try:
            gc.collect()
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
                print(
                    f"Operation {operation_name}: {memory_delta:+.1f}MB memory change in {duration:.1f}s"
                )
