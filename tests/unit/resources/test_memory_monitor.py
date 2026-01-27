"""
Tests for the MemoryMonitor class.

Tests memory monitoring functionality including snapshots,
pressure detection, and trend analysis.
"""

import pytest
import time
from unittest.mock import MagicMock, patch

from planalign_orchestrator.resources import (
    MemoryMonitor,
    MemoryUsageSnapshot,
    ResourcePressure,
)


@pytest.fixture
def memory_monitor():
    """Create a MemoryMonitor instance for testing."""
    return MemoryMonitor(monitoring_interval=0.1, history_size=10)


class TestMemoryUsageSnapshot:
    """Tests for MemoryUsageSnapshot dataclass."""

    @pytest.mark.fast
    def test_snapshot_creation(self):
        """Test creating a MemoryUsageSnapshot."""
        snapshot = MemoryUsageSnapshot(
            timestamp=time.time(),
            rss_mb=100.0,
            vms_mb=200.0,
            percent=25.0,
            available_mb=3000.0,
            thread_id="main",
        )
        assert snapshot.rss_mb == 100.0
        assert snapshot.vms_mb == 200.0
        assert snapshot.percent == 25.0

    @pytest.mark.fast
    def test_snapshot_with_context(self):
        """Test snapshot with additional context."""
        snapshot = MemoryUsageSnapshot(
            timestamp=time.time(),
            rss_mb=100.0,
            vms_mb=200.0,
            percent=25.0,
            available_mb=3000.0,
            context={"operation": "test"},
        )
        assert snapshot.context["operation"] == "test"


class TestMemoryMonitor:
    """Tests for MemoryMonitor class."""

    @pytest.mark.fast
    def test_initialization(self, memory_monitor):
        """Test monitor initializes correctly."""
        assert memory_monitor.monitoring_interval == 0.1
        assert memory_monitor.history_size == 10
        assert memory_monitor._monitoring_active is False

    @pytest.mark.fast
    def test_default_thresholds(self, memory_monitor):
        """Test default thresholds are set."""
        assert "moderate_mb" in memory_monitor.thresholds
        assert "high_mb" in memory_monitor.thresholds
        assert "critical_mb" in memory_monitor.thresholds

    @pytest.mark.fast
    @patch("psutil.Process")
    @patch("psutil.virtual_memory")
    def test_capture_memory_snapshot(self, mock_vm, mock_process, memory_monitor):
        """Test capturing a memory snapshot."""
        mock_process.return_value.memory_info.return_value.rss = 100 * 1024 * 1024
        mock_process.return_value.memory_info.return_value.vms = 200 * 1024 * 1024
        mock_vm.return_value.percent = 25.0
        mock_vm.return_value.available = 3000 * 1024 * 1024

        memory_monitor._process = mock_process.return_value

        snapshot = memory_monitor._capture_memory_snapshot()

        assert snapshot.rss_mb == pytest.approx(100.0, rel=0.1)
        assert snapshot.vms_mb == pytest.approx(200.0, rel=0.1)

    @pytest.mark.fast
    def test_get_current_pressure_none(self, memory_monitor):
        """Test pressure detection when memory is low."""
        with patch.object(
            memory_monitor,
            "_capture_memory_snapshot",
            return_value=MemoryUsageSnapshot(
                timestamp=time.time(),
                rss_mb=500.0,  # Below moderate threshold
                vms_mb=800.0,
                percent=10.0,
                available_mb=4000.0,
            ),
        ):
            pressure = memory_monitor.get_current_pressure()
            assert pressure.memory_pressure == "none"
            assert pressure.recommended_action == "continue_normal"

    @pytest.mark.fast
    def test_get_current_pressure_moderate(self, memory_monitor):
        """Test pressure detection at moderate level."""
        with patch.object(
            memory_monitor,
            "_capture_memory_snapshot",
            return_value=MemoryUsageSnapshot(
                timestamp=time.time(),
                rss_mb=2500.0,  # Above moderate, below high
                vms_mb=3000.0,
                percent=50.0,
                available_mb=2000.0,
            ),
        ):
            pressure = memory_monitor.get_current_pressure()
            assert pressure.memory_pressure == "moderate"
            assert pressure.thread_count_adjustment == -1

    @pytest.mark.fast
    def test_get_current_pressure_critical(self, memory_monitor):
        """Test pressure detection at critical level."""
        with patch.object(
            memory_monitor,
            "_capture_memory_snapshot",
            return_value=MemoryUsageSnapshot(
                timestamp=time.time(),
                rss_mb=4000.0,  # Above critical
                vms_mb=5000.0,
                percent=90.0,
                available_mb=500.0,
            ),
        ):
            pressure = memory_monitor.get_current_pressure()
            assert pressure.memory_pressure == "critical"
            assert pressure.recommended_action == "immediate_fallback"
            assert pressure.thread_count_adjustment == -3

    @pytest.mark.fast
    def test_get_memory_trends_insufficient_data(self, memory_monitor):
        """Test trends when insufficient data."""
        trends = memory_monitor.get_memory_trends()
        assert trends["trend"] == "insufficient_data"

    @pytest.mark.fast
    def test_detect_memory_leaks_no_data(self, memory_monitor):
        """Test leak detection with no data."""
        is_leak = memory_monitor.detect_memory_leaks()
        assert is_leak is False

    @pytest.mark.fast
    def test_track_thread_memory(self, memory_monitor):
        """Test tracking memory for specific thread."""
        with patch.object(
            memory_monitor,
            "_capture_memory_snapshot",
            return_value=MemoryUsageSnapshot(
                timestamp=time.time(),
                rss_mb=100.0,
                vms_mb=200.0,
                percent=25.0,
                available_mb=3000.0,
                thread_id="worker-1",
            ),
        ):
            memory_monitor.track_thread_memory("worker-1")
            assert "worker-1" in memory_monitor.thread_memory
            assert len(memory_monitor.thread_memory["worker-1"]) == 1


class TestBackwardCompatibility:
    """Tests to verify backward compatibility of imports."""

    @pytest.mark.fast
    def test_import_from_old_path(self):
        """Test that old import path still works."""
        from planalign_orchestrator.resource_manager import MemoryMonitor
        from planalign_orchestrator.resource_manager import MemoryUsageSnapshot

        assert MemoryMonitor is not None
        assert MemoryUsageSnapshot is not None

    @pytest.mark.fast
    def test_import_from_new_path(self):
        """Test that new import path works."""
        from planalign_orchestrator.resources import MemoryMonitor
        from planalign_orchestrator.resources import MemoryUsageSnapshot

        assert MemoryMonitor is not None
        assert MemoryUsageSnapshot is not None

    @pytest.mark.fast
    def test_same_class_from_both_paths(self):
        """Test that both paths return the same class."""
        from planalign_orchestrator.resource_manager import MemoryMonitor as MM_Old
        from planalign_orchestrator.resources import MemoryMonitor as MM_New

        assert MM_Old is MM_New
