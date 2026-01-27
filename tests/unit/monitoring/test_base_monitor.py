"""
Tests for the base PerformanceMonitor class.

Tests the core performance monitoring functionality including
operation timing, resource tracking, and metrics collection.
"""

import pytest
import time
from unittest.mock import MagicMock, patch

from planalign_orchestrator.monitoring import PerformanceMonitor, PerformanceMetrics


@pytest.fixture
def mock_logger():
    """Create a mock logger for testing."""
    logger = MagicMock()
    logger.info = MagicMock()
    logger.log_event = MagicMock()
    logger.exception = MagicMock()
    return logger


@pytest.fixture
def performance_monitor(mock_logger):
    """Create a PerformanceMonitor instance for testing."""
    return PerformanceMonitor(logger=mock_logger)


class TestPerformanceMetrics:
    """Tests for PerformanceMetrics dataclass."""

    def test_metrics_creation(self):
        """Test creating a PerformanceMetrics instance."""
        metrics = PerformanceMetrics(
            operation_name="test_op",
            start_time=time.time(),
        )
        assert metrics.operation_name == "test_op"
        assert metrics.status == "running"
        assert metrics.end_time is None

    def test_metrics_to_dict(self):
        """Test converting metrics to dictionary."""
        metrics = PerformanceMetrics(
            operation_name="test_op",
            start_time=1000.0,
            end_time=1010.0,
            duration_seconds=10.0,
            memory_delta_mb=5.5,
            cpu_percent=50.0,
            status="success",
            context={"year": 2025},
        )
        result = metrics.to_dict()

        assert result["operation"] == "test_op"
        assert result["duration_seconds"] == 10.0
        assert result["memory_delta_mb"] == 5.5
        assert result["cpu_percent"] == 50.0
        assert result["status"] == "success"
        assert result["year"] == 2025

    def test_metrics_to_dict_with_none_values(self):
        """Test to_dict handles None values correctly."""
        metrics = PerformanceMetrics(
            operation_name="test_op",
            start_time=1000.0,
        )
        result = metrics.to_dict()

        assert result["operation"] == "test_op"
        assert result["duration_seconds"] is None
        assert result["memory_delta_mb"] is None


class TestPerformanceMonitor:
    """Tests for PerformanceMonitor class."""

    @pytest.mark.fast
    def test_monitor_initialization(self, performance_monitor, mock_logger):
        """Test monitor initializes correctly."""
        assert performance_monitor.logger is mock_logger
        assert performance_monitor.metrics == {}
        assert performance_monitor._monitoring_active is False

    @pytest.mark.fast
    @patch("psutil.Process")
    def test_time_operation_success(self, mock_process, performance_monitor):
        """Test successful operation timing."""
        mock_process_instance = MagicMock()
        mock_process_instance.memory_info.return_value.rss = 100 * 1024 * 1024  # 100MB
        mock_process_instance.cpu_percent.return_value = 50.0
        mock_process.return_value = mock_process_instance
        performance_monitor._process = mock_process_instance

        with performance_monitor.time_operation("test_operation", year=2025) as metrics:
            assert metrics.operation_name == "test_operation"
            assert metrics.status == "running"
            time.sleep(0.01)  # Small delay to ensure timing works

        # After context manager exits
        assert metrics.status == "success"
        assert metrics.duration_seconds is not None
        assert metrics.duration_seconds > 0

    @pytest.mark.fast
    @patch("psutil.Process")
    def test_time_operation_with_exception(self, mock_process, performance_monitor):
        """Test operation timing when exception occurs."""
        mock_process_instance = MagicMock()
        mock_process_instance.memory_info.return_value.rss = 100 * 1024 * 1024
        mock_process_instance.cpu_percent.return_value = 50.0
        mock_process.return_value = mock_process_instance
        performance_monitor._process = mock_process_instance

        with pytest.raises(ValueError):
            with performance_monitor.time_operation("failing_operation") as metrics:
                raise ValueError("Test error")

        assert metrics.status == "failed"
        assert metrics.error_message == "Test error"

    @pytest.mark.fast
    def test_get_metrics_empty(self, performance_monitor):
        """Test get_metrics when no operations have been timed."""
        assert performance_monitor.get_metrics() == {}
        assert performance_monitor.get_metrics("nonexistent") == {}

    @pytest.mark.fast
    def test_get_summary_empty(self, performance_monitor):
        """Test get_summary when no operations have been timed."""
        summary = performance_monitor.get_summary()
        assert summary["total_operations"] == 0
        assert summary["successful_operations"] == 0
        assert summary["failed_operations"] == 0

    @pytest.mark.fast
    @patch("psutil.Process")
    def test_get_summary_with_operations(self, mock_process, performance_monitor):
        """Test get_summary with completed operations."""
        mock_process_instance = MagicMock()
        mock_process_instance.memory_info.return_value.rss = 100 * 1024 * 1024
        mock_process_instance.cpu_percent.return_value = 50.0
        mock_process.return_value = mock_process_instance
        performance_monitor._process = mock_process_instance

        with performance_monitor.time_operation("op1"):
            time.sleep(0.01)
        with performance_monitor.time_operation("op2"):
            time.sleep(0.01)

        summary = performance_monitor.get_summary()
        assert summary["total_operations"] == 2
        assert summary["successful_operations"] == 2
        assert summary["failed_operations"] == 0
        assert summary["total_duration_seconds"] > 0

    @pytest.mark.fast
    def test_log_data_quality_check(self, performance_monitor, mock_logger):
        """Test logging data quality check."""
        performance_monitor.log_data_quality_check(
            year=2025,
            check_name="test_check",
            result=0.05,
            threshold=0.10,
        )
        mock_logger.info.assert_called()

    @pytest.mark.fast
    def test_log_data_quality_check_exceeds_threshold(
        self, performance_monitor, mock_logger
    ):
        """Test logging data quality check that exceeds threshold."""
        performance_monitor.log_data_quality_check(
            year=2025,
            check_name="test_check",
            result=0.15,  # Exceeds threshold
            threshold=0.10,
        )
        mock_logger.log_event.assert_called()


class TestBackwardCompatibility:
    """Tests to verify backward compatibility of imports."""

    @pytest.mark.fast
    def test_import_from_old_path(self):
        """Test that old import path still works."""
        from planalign_orchestrator.performance_monitor import PerformanceMonitor
        from planalign_orchestrator.performance_monitor import PerformanceMetrics

        assert PerformanceMonitor is not None
        assert PerformanceMetrics is not None

    @pytest.mark.fast
    def test_import_from_new_path(self):
        """Test that new import path works."""
        from planalign_orchestrator.monitoring import PerformanceMonitor
        from planalign_orchestrator.monitoring import PerformanceMetrics

        assert PerformanceMonitor is not None
        assert PerformanceMetrics is not None

    @pytest.mark.fast
    def test_same_class_from_both_paths(self):
        """Test that both paths return the same class."""
        from planalign_orchestrator.performance_monitor import (
            PerformanceMonitor as PM_Old,
        )
        from planalign_orchestrator.monitoring import PerformanceMonitor as PM_New

        assert PM_Old is PM_New
