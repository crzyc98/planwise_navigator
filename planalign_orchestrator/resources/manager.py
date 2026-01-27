"""
Comprehensive resource management facade.

Integrates memory monitoring, CPU monitoring, adaptive thread scaling,
and performance optimization into a unified interface.

Features:
- Integrated memory and CPU monitoring
- Adaptive thread count optimization
- Resource pressure detection and mitigation
- Performance benchmarking capabilities
- Graceful degradation under load
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, List, Optional, Tuple, TYPE_CHECKING

from .data_models import ResourcePressure
from .memory_monitor import MemoryMonitor
from .cpu_monitor import CPUMonitor
from .adaptive_scaling import AdaptiveThreadAdjuster
from .benchmarker import PerformanceBenchmarker

if TYPE_CHECKING:
    from ..logger import ProductionLogger


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
        logger: Optional["ProductionLogger"] = None,
    ):
        self.logger = logger
        self.config = config or {}

        # Initialize monitors
        memory_config = self.config.get("memory", {})
        cpu_config = self.config.get("cpu", {})

        self.memory_monitor = MemoryMonitor(
            monitoring_interval=memory_config.get("monitoring_interval", 1.0),
            history_size=memory_config.get("history_size", 100),
            thresholds=memory_config.get("thresholds"),
        )

        self.cpu_monitor = CPUMonitor(
            monitoring_interval=cpu_config.get("monitoring_interval", 1.0),
            history_size=cpu_config.get("history_size", 100),
            thresholds=cpu_config.get("thresholds"),
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
        context: Optional[Dict[str, Any]] = None,
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
                "leak_detected": self.memory_monitor.detect_memory_leaks(),
            },
            "cpu": {
                "pressure": cpu_pressure,
                "current_percent": self.cpu_monitor._capture_cpu_snapshot().percent,
                "trends": cpu_trends,
                "optimal_thread_estimate": self.cpu_monitor.get_optimal_thread_count_estimate(),
            },
            "recommendations": {
                "action": memory_pressure.recommended_action,
                "thread_adjustment": memory_pressure.thread_count_adjustment,
            },
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
            memory_pressure.memory_pressure != "critical"
            and cpu_pressure != "critical"
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
            "cleanup_effective": memory_freed > 10,  # More than 10MB freed
        }

        if self.logger:
            self.logger.info("Resource cleanup executed", **cleanup_result)

        return cleanup_result

    @contextmanager
    def monitor_execution(self, operation_name: str, expected_thread_count: int = 1):
        """Context manager for monitoring resource usage during execution."""
        context = {
            "operation": operation_name,
            "expected_threads": expected_thread_count,
        }

        start_time = time.time()
        initial_status = self.get_resource_status()
        # Ensure variables are always defined for logging in finally
        success = False
        error: Optional[str] = None

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
                self.thread_adjuster.record_performance(
                    expected_thread_count, execution_time
                )

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
                        memory_delta_mb=final_status["memory"]["usage_mb"]
                        - initial_status["memory"]["usage_mb"],
                    )
