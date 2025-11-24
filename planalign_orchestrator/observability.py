"""
Integrated Observability Manager for PlanWise Navigator

Provides a unified interface for logging, performance monitoring, and run tracking
with enterprise-grade observability features.
"""

from contextlib import contextmanager
from typing import Any, ContextManager, Dict, Optional

from .logger import ProductionLogger, get_logger
from .performance_monitor import PerformanceMetrics, PerformanceMonitor
from .run_summary import RunSummaryGenerator


class ObservabilityManager:
    """
    Unified observability manager that integrates logging, performance monitoring,
    and run tracking for comprehensive production observability.

    Features:
    - Unified interface for all observability components
    - Automatic component integration and correlation
    - Context managers for operation tracking
    - Simplified API for common observability patterns
    """

    def __init__(self, run_id: Optional[str] = None, log_level: str = "INFO"):
        """
        Initialize observability manager

        Args:
            run_id: Unique identifier for this simulation run. Generated if not provided.
            log_level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        """
        # Initialize core components
        self.logger = get_logger(run_id=run_id, log_level=log_level)
        self.performance_monitor = PerformanceMonitor(self.logger)
        self.run_summary = RunSummaryGenerator(
            run_id=self.logger.get_run_id(),
            logger=self.logger,
            performance_monitor=self.performance_monitor,
        )

        # Store run ID for external access
        self.run_id = self.logger.get_run_id()

    def get_run_id(self) -> str:
        """Get the run ID for this observability session"""
        return self.run_id

    @contextmanager
    def track_operation(
        self, operation_name: str, **context
    ) -> ContextManager[PerformanceMetrics]:
        """
        Context manager that tracks an operation with full observability

        Args:
            operation_name: Name of the operation being tracked
            **context: Additional context to include in logs and metrics

        Yields:
            PerformanceMetrics object for the operation
        """
        with self.performance_monitor.time_operation(
            operation_name, **context
        ) as metrics:
            yield metrics

    def log_info(self, message: str, **kwargs) -> None:
        """Log info message with structured data"""
        self.logger.info(message, **kwargs)

    def log_warning(self, message: str, **kwargs) -> None:
        """Log warning message and add to run summary"""
        self.logger.warning(message, **kwargs)
        self.run_summary.add_warning(message, kwargs)

    def log_error(self, message: str, **kwargs) -> None:
        """Log error message and add to run summary"""
        self.logger.error(message, **kwargs)
        self.run_summary.add_error(message, kwargs)

    def log_exception(self, message: str, **kwargs) -> None:
        """Log exception with traceback and add to run summary"""
        self.logger.exception(message, **kwargs)
        self.run_summary.add_error(f"Exception: {message}", kwargs)

    def add_metric(self, name: str, value: Any, description: str = None) -> None:
        """Add custom metric to run summary"""
        self.run_summary.add_metric(name, value, description)

    def set_configuration(self, config: Dict[str, Any]) -> None:
        """Set run configuration for audit trail"""
        self.run_summary.set_configuration(config)

    def set_backup_path(self, backup_path: str) -> None:
        """Set backup path for audit trail"""
        self.run_summary.set_backup_path(backup_path)

    def log_data_quality_check(
        self, year: int, check_name: str, result: Any, threshold: Any = None
    ) -> None:
        """Log data quality check with threshold validation"""
        self.performance_monitor.log_data_quality_check(
            year, check_name, result, threshold
        )

    def get_performance_summary(self) -> Dict[str, Any]:
        """Get summary of performance metrics"""
        return self.performance_monitor.get_summary()

    def get_issue_summary(self) -> Dict[str, Any]:
        """Get summary of issues for quick status check"""
        return self.run_summary.get_issue_summary()

    def finalize_run(self, final_status: str = "success") -> Dict[str, Any]:
        """
        Finalize run and generate comprehensive summary

        Args:
            final_status: Final status of the run ('success', 'failed', 'partial')

        Returns:
            Complete run summary dictionary
        """
        return self.run_summary.generate_summary(final_status)

    def close(self) -> None:
        """Close observability manager and cleanup resources"""
        self.logger.close()


# Convenience functions for quick setup
def create_observability_manager(
    run_id: Optional[str] = None, log_level: str = "INFO"
) -> ObservabilityManager:
    """
    Factory function to create a configured observability manager

    Args:
        run_id: Optional run ID. Generated if not provided.
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Returns:
        Configured ObservabilityManager instance
    """
    return ObservabilityManager(run_id=run_id, log_level=log_level)


@contextmanager
def observability_session(
    run_id: Optional[str] = None, log_level: str = "INFO"
) -> ContextManager[ObservabilityManager]:
    """
    Context manager for complete observability session with automatic cleanup

    Args:
        run_id: Optional run ID. Generated if not provided.
        log_level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)

    Yields:
        ObservabilityManager instance
    """
    obs_manager = create_observability_manager(run_id=run_id, log_level=log_level)
    try:
        yield obs_manager
    finally:
        obs_manager.close()
