"""
Real-time CPU utilization tracking and analysis.

Features:
- Real-time CPU monitoring with configurable intervals
- Load average tracking for system health assessment
- CPU pressure detection with threshold-based alerts
- Per-core utilization tracking when available
- Integration with thread scaling decisions
"""

from __future__ import annotations

import os
import threading
import time
from collections import deque
from typing import Any, Dict, Optional

import psutil

from .data_models import CPUUsageSnapshot


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
        thresholds: Optional[Dict[str, float]] = None,
    ):
        self.monitoring_interval = monitoring_interval
        self.history_size = history_size

        # Default CPU thresholds
        self.thresholds = thresholds or {
            "moderate_percent": 70.0,
            "high_percent": 85.0,
            "critical_percent": 95.0,
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
                target=self._monitor_loop, daemon=True, name="CPUMonitor"
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
            load_avg = (
                os.getloadavg() if hasattr(os, "getloadavg") else (0.0, 0.0, 0.0)
            )

            snapshot = CPUUsageSnapshot(
                timestamp=time.time(),
                percent=cpu_percent,
                load_avg=load_avg,
                core_count=self.core_count,
            )

            return snapshot

        except Exception:
            # Return minimal snapshot on error
            return CPUUsageSnapshot(
                timestamp=time.time(),
                percent=0.0,
                load_avg=(0.0, 0.0, 0.0),
                core_count=self.core_count,
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
                s for s in self.cpu_history if s.timestamp >= cutoff_time
            ]

        if len(recent_snapshots) < 2:
            return {
                "trend": "insufficient_data",
                "average_cpu": 0.0,
                "peak_cpu": 0.0,
                "load_average_1m": 0.0,
            }

        avg_cpu = sum(s.percent for s in recent_snapshots) / len(recent_snapshots)
        peak_cpu = max(s.percent for s in recent_snapshots)
        latest_load = recent_snapshots[-1].load_avg[0] if recent_snapshots else 0.0

        return {
            "trend": "analyzed",
            "average_cpu": avg_cpu,
            "peak_cpu": peak_cpu,
            "load_average_1m": latest_load,
            "sample_count": len(recent_snapshots),
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
