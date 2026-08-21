"""
Base performance monitor for PlanAlign Engine.

Provides basic operation timing and resource monitoring through
a context manager interface integrated with structured logging.
"""

import threading
import time
from contextlib import contextmanager
from typing import Any, Dict, Generator, Optional

import psutil

from ..logger import ProductionLogger
from .data_models import PerformanceMetrics


class PerformanceMonitor:
    """
    Performance monitoring system that tracks timing, memory usage, and resource utilization.

    Features:
    - Context manager for automatic operation timing
    - Memory usage tracking with peak detection
    - CPU utilization monitoring
    - Integration with structured logging
    - Comprehensive metrics collection
    """

    def __init__(self, logger: ProductionLogger):
        """
        Initialize performance monitor

        Args:
            logger: ProductionLogger instance for recording metrics
        """
        self.logger = logger
        self.metrics: Dict[str, PerformanceMetrics] = {}
        self._monitoring_active = False
        self._monitoring_thread: Optional[threading.Thread] = None
        self._monitoring_lock = threading.Lock()
        self._active_metrics: Dict[int, PerformanceMetrics] = {}
        self._stop_event = threading.Event()
        self._idle_timeout_seconds = 0.5
        self._process = psutil.Process()

    @contextmanager
    def time_operation(
        self, operation_name: str, **context
    ) -> Generator[PerformanceMetrics, None, None]:
        """
        Context manager for timing operations with resource monitoring

        Args:
            operation_name: Name of the operation being timed
            **context: Additional context to include in metrics

        Yields:
            PerformanceMetrics object that gets updated during operation
        """
        # Initialize metrics
        metrics = PerformanceMetrics(
            operation_name=operation_name, start_time=time.time(), context=context
        )

        # Get starting resource usage
        try:
            memory_info = self._process.memory_info()
            metrics.start_memory_mb = memory_info.rss / 1024 / 1024  # Convert to MB
            metrics.peak_memory_mb = metrics.start_memory_mb
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.logger.log_event(
                "WARNING", f"Could not get memory info for {operation_name}"
            )

        # Start CPU monitoring
        try:
            self._process.cpu_percent()  # Initialize CPU monitoring
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.logger.log_event(
                "WARNING", f"Could not initialize CPU monitoring for {operation_name}"
            )

        # Log operation start
        self.logger.info(f"Starting operation: {operation_name}", **context)

        try:
            # Start background monitoring for long operations
            self._start_monitoring(metrics)

            yield metrics

            # Operation completed successfully
            metrics.status = "success"

        except Exception as e:
            # Operation failed
            metrics.status = "failed"
            metrics.error_message = str(e)
            self.logger.exception(
                f"Operation {operation_name} failed",
                operation=operation_name,
                **context,
            )
            raise

        finally:
            # Stop monitoring and finalize metrics
            self._stop_monitoring(metrics)
            self._finalize_metrics(metrics)

            # Store metrics and log completion
            self.metrics[operation_name] = metrics
            self.logger.info(
                f"Completed operation: {operation_name}", **metrics.to_dict()
            )

    def _start_monitoring(self, metrics: PerformanceMetrics) -> None:
        """Register metrics and lazily start one reusable sampler thread."""
        with self._monitoring_lock:
            self._active_metrics[id(metrics)] = metrics
            if self._monitoring_thread and self._monitoring_thread.is_alive():
                return

            self._stop_event.clear()
            self._monitoring_active = True
            self._monitoring_thread = threading.Thread(
                target=self._monitor_resources,
                daemon=True,
                name="planalign-resource-monitor",
            )
            self._monitoring_thread.start()

    def _stop_monitoring(self, metrics: PerformanceMetrics) -> None:
        """Unregister metrics without joining the shared sampler on every exit."""
        with self._monitoring_lock:
            self._active_metrics.pop(id(metrics), None)

    def _monitor_resources(self) -> None:
        """Sample all active operations until the monitor has been idle briefly."""
        idle_since: Optional[float] = None
        while not self._stop_event.is_set():
            with self._monitoring_lock:
                active_metrics = list(self._active_metrics.values())

            if active_metrics:
                idle_since = None
                self._sample_metrics(active_metrics)
            elif idle_since is None:
                idle_since = time.monotonic()
            elif time.monotonic() - idle_since >= self._idle_timeout_seconds:
                with self._monitoring_lock:
                    if self._active_metrics:
                        idle_since = None
                        continue
                    break

            self._stop_event.wait(0.5)

        with self._monitoring_lock:
            if threading.current_thread() is self._monitoring_thread:
                self._monitoring_thread = None
                self._monitoring_active = False

    def _sample_metrics(self, metrics_list: list[PerformanceMetrics]) -> None:
        """Update peak memory for the currently active operations."""
        try:
            memory_info = self._process.memory_info()
            current_memory_mb = memory_info.rss / 1024 / 1024
            for metrics in metrics_list:
                if (
                    metrics.peak_memory_mb is None
                    or current_memory_mb > metrics.peak_memory_mb
                ):
                    metrics.peak_memory_mb = current_memory_mb
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            return
        except Exception:
            # Ignore monitoring errors to avoid disrupting the main operation.
            return

    def close(self) -> None:
        """Stop the reusable sampler and release monitoring resources."""
        self._stop_event.set()
        thread = self._monitoring_thread
        if thread and thread is not threading.current_thread():
            thread.join(timeout=1.0)
        with self._monitoring_lock:
            self._active_metrics.clear()
            self._monitoring_thread = None
            self._monitoring_active = False

    def __del__(self) -> None:
        """Best-effort cleanup for monitors not owned by an observability session."""
        try:
            self.close()
        except Exception:
            pass

    def _finalize_metrics(self, metrics: PerformanceMetrics) -> None:
        """Finalize metrics calculation"""
        metrics.end_time = time.time()
        metrics.duration_seconds = metrics.end_time - metrics.start_time

        # Get final resource usage
        try:
            memory_info = self._process.memory_info()
            end_memory_mb = memory_info.rss / 1024 / 1024
            metrics.end_memory_mb = end_memory_mb

            if metrics.start_memory_mb is not None:
                metrics.memory_delta_mb = end_memory_mb - metrics.start_memory_mb

            # Get CPU usage (averaged over the operation duration)
            metrics.cpu_percent = self._process.cpu_percent()

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.logger.log_event(
                "WARNING",
                f"Could not get final resource usage for {metrics.operation_name}",
            )

    def get_metrics(self, operation_name: Optional[str] = None) -> Dict[str, Any]:
        """
        Get performance metrics

        Args:
            operation_name: Specific operation to get metrics for. If None, returns all metrics.

        Returns:
            Dictionary of performance metrics
        """
        if operation_name:
            metrics = self.metrics.get(operation_name)
            return metrics.to_dict() if metrics else {}

        return {name: metrics.to_dict() for name, metrics in self.metrics.items()}

    def get_summary(self) -> Dict[str, Any]:
        """Get summary of all performance metrics"""
        if not self.metrics:
            return {
                "total_operations": 0,
                "successful_operations": 0,
                "failed_operations": 0,
                "total_duration_seconds": 0,
                "average_duration_seconds": 0,
                "slowest_operation": None,
                "fastest_operation": None,
            }

        successful = [m for m in self.metrics.values() if m.status == "success"]
        failed = [m for m in self.metrics.values() if m.status == "failed"]

        durations = [
            m.duration_seconds
            for m in self.metrics.values()
            if m.duration_seconds is not None
        ]
        total_duration = sum(durations)

        # Get slowest and fastest operations based on actual duration
        completed_metrics = [
            m for m in self.metrics.values() if m.duration_seconds is not None
        ]
        slowest = (
            max(
                completed_metrics,
                key=lambda m: m.duration_seconds or 0.0,
                default=None,
            )
            if completed_metrics
            else None
        )
        fastest = (
            min(
                completed_metrics,
                key=lambda m: m.duration_seconds or 0.0,
                default=None,
            )
            if completed_metrics
            else None
        )

        return {
            "total_operations": len(self.metrics),
            "successful_operations": len(successful),
            "failed_operations": len(failed),
            "total_duration_seconds": round(total_duration, 2),
            "average_duration_seconds": round(total_duration / len(durations), 2)
            if durations
            else 0,
            "slowest_operation": {
                "name": slowest.operation_name,
                "duration": slowest.duration_seconds,
            }
            if slowest and slowest.duration_seconds
            else None,
            "fastest_operation": {
                "name": fastest.operation_name,
                "duration": fastest.duration_seconds,
            }
            if fastest and fastest.duration_seconds
            else None,
        }

    def log_data_quality_check(
        self, year: int, check_name: str, result: Any, threshold: Any = None
    ) -> None:
        """
        Log data quality check with threshold validation

        Args:
            year: Simulation year
            check_name: Name of the data quality check
            result: Result of the check
            threshold: Optional threshold for validation
        """
        status = "pass"

        if threshold is not None:
            try:
                if float(result) > float(threshold):
                    status = "warning"
                    self.logger.log_event(
                        "WARNING",
                        f"Data quality check {check_name} exceeded threshold",
                        year=year,
                        check=check_name,
                        result=result,
                        threshold=threshold,
                        status=status,
                    )
            except (ValueError, TypeError):
                # Non-numeric comparison, just log the result
                pass

        self.logger.info(
            f"Data quality check: {check_name}",
            year=year,
            check=check_name,
            result=result,
            threshold=threshold,
            status=status,
        )
