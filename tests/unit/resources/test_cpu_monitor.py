"""
Tests for the CPUMonitor class.

Tests CPU monitoring functionality including snapshots,
pressure detection, and trend analysis.
"""

import pytest
import time
from unittest.mock import MagicMock, patch

from planalign_orchestrator.resources import (
    CPUMonitor,
    CPUUsageSnapshot,
)


@pytest.fixture
def cpu_monitor():
    """Create a CPUMonitor instance for testing."""
    return CPUMonitor(monitoring_interval=0.1, history_size=10)


class TestCPUUsageSnapshot:
    """Tests for CPUUsageSnapshot dataclass."""

    @pytest.mark.fast
    def test_snapshot_creation(self):
        """Test creating a CPUUsageSnapshot."""
        snapshot = CPUUsageSnapshot(
            timestamp=time.time(),
            percent=50.0,
            load_avg=(1.0, 0.8, 0.5),
            core_count=8,
        )
        assert snapshot.percent == 50.0
        assert snapshot.load_avg == (1.0, 0.8, 0.5)
        assert snapshot.core_count == 8

    @pytest.mark.fast
    def test_snapshot_with_context(self):
        """Test snapshot with additional context."""
        snapshot = CPUUsageSnapshot(
            timestamp=time.time(),
            percent=50.0,
            load_avg=(1.0, 0.8, 0.5),
            core_count=8,
            context={"operation": "test"},
        )
        assert snapshot.context["operation"] == "test"


class TestCPUMonitor:
    """Tests for CPUMonitor class."""

    @pytest.mark.fast
    def test_initialization(self, cpu_monitor):
        """Test monitor initializes correctly."""
        assert cpu_monitor.monitoring_interval == 0.1
        assert cpu_monitor.history_size == 10
        assert cpu_monitor._monitoring_active is False
        assert cpu_monitor.core_count is not None

    @pytest.mark.fast
    def test_default_thresholds(self, cpu_monitor):
        """Test default thresholds are set."""
        assert "moderate_percent" in cpu_monitor.thresholds
        assert "high_percent" in cpu_monitor.thresholds
        assert "critical_percent" in cpu_monitor.thresholds
        assert cpu_monitor.thresholds["moderate_percent"] == 70.0

    @pytest.mark.fast
    @patch("psutil.cpu_percent")
    @patch("os.getloadavg")
    def test_capture_cpu_snapshot(self, mock_loadavg, mock_cpu, cpu_monitor):
        """Test capturing a CPU snapshot."""
        mock_cpu.return_value = 45.0
        mock_loadavg.return_value = (1.0, 0.8, 0.5)

        snapshot = cpu_monitor._capture_cpu_snapshot()

        assert snapshot.percent == 45.0
        assert snapshot.load_avg == (1.0, 0.8, 0.5)

    @pytest.mark.fast
    def test_get_current_pressure_none(self, cpu_monitor):
        """Test pressure detection when CPU is low."""
        with patch.object(
            cpu_monitor,
            "_capture_cpu_snapshot",
            return_value=CPUUsageSnapshot(
                timestamp=time.time(),
                percent=30.0,  # Below moderate threshold
                load_avg=(0.5, 0.4, 0.3),
                core_count=8,
            ),
        ):
            pressure = cpu_monitor.get_current_pressure()
            assert pressure == "none"

    @pytest.mark.fast
    def test_get_current_pressure_moderate(self, cpu_monitor):
        """Test pressure detection at moderate level."""
        with patch.object(
            cpu_monitor,
            "_capture_cpu_snapshot",
            return_value=CPUUsageSnapshot(
                timestamp=time.time(),
                percent=75.0,  # Above moderate, below high
                load_avg=(2.0, 1.5, 1.0),
                core_count=8,
            ),
        ):
            pressure = cpu_monitor.get_current_pressure()
            assert pressure == "moderate"

    @pytest.mark.fast
    def test_get_current_pressure_high(self, cpu_monitor):
        """Test pressure detection at high level."""
        with patch.object(
            cpu_monitor,
            "_capture_cpu_snapshot",
            return_value=CPUUsageSnapshot(
                timestamp=time.time(),
                percent=90.0,  # Above high, below critical
                load_avg=(4.0, 3.5, 3.0),
                core_count=8,
            ),
        ):
            pressure = cpu_monitor.get_current_pressure()
            assert pressure == "high"

    @pytest.mark.fast
    def test_get_current_pressure_critical(self, cpu_monitor):
        """Test pressure detection at critical level."""
        with patch.object(
            cpu_monitor,
            "_capture_cpu_snapshot",
            return_value=CPUUsageSnapshot(
                timestamp=time.time(),
                percent=98.0,  # Above critical
                load_avg=(8.0, 7.0, 6.0),
                core_count=8,
            ),
        ):
            pressure = cpu_monitor.get_current_pressure()
            assert pressure == "critical"

    @pytest.mark.fast
    def test_get_cpu_trends_insufficient_data(self, cpu_monitor):
        """Test trends when insufficient data."""
        trends = cpu_monitor.get_cpu_trends()
        assert trends["trend"] == "insufficient_data"

    @pytest.mark.fast
    def test_get_optimal_thread_count_low_cpu(self, cpu_monitor):
        """Test optimal thread count estimation with low CPU."""
        with patch.object(
            cpu_monitor,
            "_capture_cpu_snapshot",
            return_value=CPUUsageSnapshot(
                timestamp=time.time(),
                percent=20.0,  # Low CPU usage
                load_avg=(0.5, 0.4, 0.3),
                core_count=8,
            ),
        ):
            estimate = cpu_monitor.get_optimal_thread_count_estimate()
            # Low CPU = can handle more threads
            assert estimate >= 4

    @pytest.mark.fast
    def test_get_optimal_thread_count_high_cpu(self, cpu_monitor):
        """Test optimal thread count estimation with high CPU."""
        with patch.object(
            cpu_monitor,
            "_capture_cpu_snapshot",
            return_value=CPUUsageSnapshot(
                timestamp=time.time(),
                percent=90.0,  # High CPU usage
                load_avg=(4.0, 3.5, 3.0),
                core_count=8,
            ),
        ):
            estimate = cpu_monitor.get_optimal_thread_count_estimate()
            # High CPU = conservative thread count
            assert estimate == 1


class TestBackwardCompatibility:
    """Tests to verify backward compatibility of imports."""

    @pytest.mark.fast
    def test_import_from_old_path(self):
        """Test that old import path still works."""
        from planalign_orchestrator.resource_manager import CPUMonitor
        from planalign_orchestrator.resource_manager import CPUUsageSnapshot

        assert CPUMonitor is not None
        assert CPUUsageSnapshot is not None

    @pytest.mark.fast
    def test_import_from_new_path(self):
        """Test that new import path works."""
        from planalign_orchestrator.resources import CPUMonitor
        from planalign_orchestrator.resources import CPUUsageSnapshot

        assert CPUMonitor is not None
        assert CPUUsageSnapshot is not None

    @pytest.mark.fast
    def test_same_class_from_both_paths(self):
        """Test that both paths return the same class."""
        from planalign_orchestrator.resource_manager import CPUMonitor as CM_Old
        from planalign_orchestrator.resources import CPUMonitor as CM_New

        assert CM_Old is CM_New
