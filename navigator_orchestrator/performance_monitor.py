"""
Performance Monitoring System for PlanWise Navigator

Provides comprehensive performance tracking with timing, memory usage,
and resource utilization monitoring for production observability.
"""

import time
import psutil
import threading
from contextlib import contextmanager
from datetime import datetime
from typing import Dict, Any, Optional, Generator
from dataclasses import dataclass, field

from .logger import ProductionLogger


@dataclass
class PerformanceMetrics:
    """Container for performance metrics"""
    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    duration_seconds: Optional[float] = None
    start_memory_mb: Optional[float] = None
    end_memory_mb: Optional[float] = None
    memory_delta_mb: Optional[float] = None
    peak_memory_mb: Optional[float] = None
    cpu_percent: Optional[float] = None
    status: str = "running"
    error_message: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for logging"""
        return {
            'operation': self.operation_name,
            'duration_seconds': round(self.duration_seconds, 3) if self.duration_seconds else None,
            'memory_delta_mb': round(self.memory_delta_mb, 2) if self.memory_delta_mb else None,
            'peak_memory_mb': round(self.peak_memory_mb, 2) if self.peak_memory_mb else None,
            'cpu_percent': round(self.cpu_percent, 1) if self.cpu_percent else None,
            'status': self.status,
            'error': self.error_message,
            **self.context
        }


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
        self._process = psutil.Process()

    @contextmanager
    def time_operation(self, operation_name: str, **context) -> Generator[PerformanceMetrics, None, None]:
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
            operation_name=operation_name,
            start_time=time.time(),
            context=context
        )

        # Get starting resource usage
        try:
            memory_info = self._process.memory_info()
            metrics.start_memory_mb = memory_info.rss / 1024 / 1024  # Convert to MB
            metrics.peak_memory_mb = metrics.start_memory_mb
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.logger.log_event('WARNING', f"Could not get memory info for {operation_name}")

        # Start CPU monitoring
        try:
            self._process.cpu_percent()  # Initialize CPU monitoring
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.logger.log_event('WARNING', f"Could not initialize CPU monitoring for {operation_name}")

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
            self.logger.exception(f"Operation {operation_name} failed",
                                operation=operation_name, **context)
            raise

        finally:
            # Stop monitoring and finalize metrics
            self._stop_monitoring()
            self._finalize_metrics(metrics)

            # Store metrics and log completion
            self.metrics[operation_name] = metrics
            self.logger.info(f"Completed operation: {operation_name}", **metrics.to_dict())

    def _start_monitoring(self, metrics: PerformanceMetrics) -> None:
        """Start background monitoring for peak resource usage"""
        if self._monitoring_active:
            return

        self._monitoring_active = True
        self._monitoring_thread = threading.Thread(
            target=self._monitor_resources,
            args=(metrics,),
            daemon=True
        )
        self._monitoring_thread.start()

    def _stop_monitoring(self) -> None:
        """Stop background monitoring"""
        self._monitoring_active = False
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=1.0)
            self._monitoring_thread = None

    def _monitor_resources(self, metrics: PerformanceMetrics) -> None:
        """Background thread to monitor peak resource usage"""
        while self._monitoring_active:
            try:
                # Monitor memory usage
                memory_info = self._process.memory_info()
                current_memory_mb = memory_info.rss / 1024 / 1024

                if metrics.peak_memory_mb is None or current_memory_mb > metrics.peak_memory_mb:
                    metrics.peak_memory_mb = current_memory_mb

                # Sleep briefly to avoid excessive monitoring overhead
                time.sleep(0.5)

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # Process may have ended or we lost access
                break
            except Exception:
                # Ignore monitoring errors to avoid disrupting main operation
                pass

    def _finalize_metrics(self, metrics: PerformanceMetrics) -> None:
        """Finalize metrics calculation"""
        metrics.end_time = time.time()
        metrics.duration_seconds = metrics.end_time - metrics.start_time

        # Get final resource usage
        try:
            memory_info = self._process.memory_info()
            metrics.end_memory_mb = memory_info.rss / 1024 / 1024

            if metrics.start_memory_mb is not None:
                metrics.memory_delta_mb = metrics.end_memory_mb - metrics.start_memory_mb

            # Get CPU usage (averaged over the operation duration)
            metrics.cpu_percent = self._process.cpu_percent()

        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.logger.log_event('WARNING', f"Could not get final resource usage for {metrics.operation_name}")

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
                'total_operations': 0,
                'successful_operations': 0,
                'failed_operations': 0,
                'total_duration_seconds': 0,
                'average_duration_seconds': 0,
                'slowest_operation': None,
                'fastest_operation': None
            }

        successful = [m for m in self.metrics.values() if m.status == "success"]
        failed = [m for m in self.metrics.values() if m.status == "failed"]

        durations = [m.duration_seconds for m in self.metrics.values() if m.duration_seconds is not None]
        total_duration = sum(durations)

        # Get slowest and fastest operations based on actual duration
        completed_metrics = [m for m in self.metrics.values() if m.duration_seconds is not None]
        slowest = max(completed_metrics, key=lambda m: m.duration_seconds, default=None) if completed_metrics else None
        fastest = min(completed_metrics, key=lambda m: m.duration_seconds, default=None) if completed_metrics else None

        return {
            'total_operations': len(self.metrics),
            'successful_operations': len(successful),
            'failed_operations': len(failed),
            'total_duration_seconds': round(total_duration, 2),
            'average_duration_seconds': round(total_duration / len(durations), 2) if durations else 0,
            'slowest_operation': {
                'name': slowest.operation_name,
                'duration': slowest.duration_seconds
            } if slowest and slowest.duration_seconds else None,
            'fastest_operation': {
                'name': fastest.operation_name,
                'duration': fastest.duration_seconds
            } if fastest and fastest.duration_seconds else None
        }

    def log_data_quality_check(self, year: int, check_name: str, result: Any,
                              threshold: Any = None) -> None:
        """
        Log data quality check with threshold validation

        Args:
            year: Simulation year
            check_name: Name of the data quality check
            result: Result of the check
            threshold: Optional threshold for validation
        """
        status = 'pass'

        if threshold is not None:
            try:
                if float(result) > float(threshold):
                    status = 'warning'
                    self.logger.log_event(
                        'WARNING',
                        f'Data quality check {check_name} exceeded threshold',
                        year=year,
                        check=check_name,
                        result=result,
                        threshold=threshold,
                        status=status
                    )
            except (ValueError, TypeError):
                # Non-numeric comparison, just log the result
                pass

        self.logger.info(
            f'Data quality check: {check_name}',
            year=year,
            check=check_name,
            result=result,
            threshold=threshold,
            status=status
        )
