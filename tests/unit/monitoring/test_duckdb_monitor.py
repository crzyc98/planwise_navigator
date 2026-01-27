"""
Tests for DuckDBPerformanceMonitor class.

Tests the DuckDB-specific performance monitoring functionality
including checkpoints, statistics, and report generation.
"""

import pytest
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

from planalign_orchestrator.monitoring import (
    DuckDBPerformanceMonitor,
    PerformanceCheckpoint,
    PerformanceLevel,
    PerformanceOptimization,
)


@pytest.fixture
def temp_db_path():
    """Create a temporary database path for testing."""
    with tempfile.NamedTemporaryFile(suffix=".duckdb", delete=False) as f:
        yield Path(f.name)


@pytest.fixture
def temp_reports_dir():
    """Create a temporary reports directory for testing."""
    with tempfile.TemporaryDirectory() as d:
        yield Path(d)


@pytest.fixture
def mock_logger():
    """Create a mock logger for testing."""
    logger = MagicMock()
    return logger


@pytest.fixture
def duckdb_monitor(temp_db_path, temp_reports_dir, mock_logger):
    """Create a DuckDBPerformanceMonitor instance for testing."""
    return DuckDBPerformanceMonitor(
        database_path=temp_db_path,
        logger=mock_logger,
        reports_dir=temp_reports_dir,
    )


class TestDuckDBPerformanceMonitorInitialization:
    """Tests for DuckDBPerformanceMonitor initialization."""

    @pytest.mark.fast
    def test_initialization(self, duckdb_monitor, temp_db_path, temp_reports_dir):
        """Test monitor initializes correctly."""
        assert duckdb_monitor.database_path == temp_db_path
        assert duckdb_monitor.reports_dir == temp_reports_dir
        assert duckdb_monitor.monitoring_active is False
        assert duckdb_monitor.checkpoints == []

    @pytest.mark.fast
    def test_thresholds_set(self, duckdb_monitor):
        """Test that performance thresholds are set."""
        assert "memory_warning_gb" in duckdb_monitor.thresholds
        assert "cpu_target_percent" in duckdb_monitor.thresholds
        assert "stage_time_target_s" in duckdb_monitor.thresholds
        assert duckdb_monitor.thresholds["memory_warning_gb"] == 32.0
        assert duckdb_monitor.thresholds["cpu_target_percent"] == 80.0


class TestDuckDBPerformanceMonitorLifecycle:
    """Tests for monitor lifecycle (start/stop)."""

    @pytest.mark.fast
    @patch("psutil.virtual_memory")
    @patch("psutil.cpu_percent")
    @patch("psutil.cpu_count")
    @patch("psutil.disk_io_counters")
    @patch("psutil.Process")
    def test_start_monitoring(
        self,
        mock_process,
        mock_io,
        mock_cpu_count,
        mock_cpu_percent,
        mock_memory,
        duckdb_monitor,
    ):
        """Test starting performance monitoring."""
        mock_memory.return_value.used = 8 * (1024**3)  # 8GB
        mock_memory.return_value.percent = 25.0
        mock_memory.return_value.available = 24 * (1024**3)
        mock_memory.return_value.total = 32 * (1024**3)
        mock_cpu_percent.return_value = 50.0
        mock_cpu_count.return_value = 8
        mock_io.return_value = MagicMock(
            read_bytes=0, write_bytes=0, read_count=0, write_count=0
        )
        mock_process.return_value.threads.return_value = [MagicMock()]

        duckdb_monitor.start_monitoring()

        assert duckdb_monitor.monitoring_active is True
        assert duckdb_monitor.start_time is not None
        assert duckdb_monitor.initial_metrics is not None

    @pytest.mark.fast
    def test_stop_monitoring(self, duckdb_monitor):
        """Test stopping performance monitoring."""
        duckdb_monitor.monitoring_active = True
        duckdb_monitor.start_time = time.time()

        duckdb_monitor.stop_monitoring()

        assert duckdb_monitor.monitoring_active is False


class TestPerformanceCheckpoints:
    """Tests for checkpoint recording."""

    @pytest.mark.fast
    @patch("psutil.virtual_memory")
    @patch("psutil.cpu_percent")
    @patch("psutil.cpu_count")
    @patch("psutil.disk_io_counters")
    @patch("psutil.Process")
    def test_record_checkpoint(
        self,
        mock_process,
        mock_io,
        mock_cpu_count,
        mock_cpu_percent,
        mock_memory,
        duckdb_monitor,
    ):
        """Test recording a performance checkpoint."""
        mock_memory.return_value.used = 8 * (1024**3)
        mock_memory.return_value.percent = 25.0
        mock_memory.return_value.available = 24 * (1024**3)
        mock_memory.return_value.total = 32 * (1024**3)
        mock_cpu_percent.return_value = 50.0
        mock_cpu_count.return_value = 8
        mock_io.return_value = MagicMock(
            read_bytes=1000, write_bytes=2000, read_count=10, write_count=20
        )
        mock_process.return_value.threads.return_value = [MagicMock()]

        duckdb_monitor.start_monitoring()
        checkpoint = duckdb_monitor.record_checkpoint("test_stage")

        assert isinstance(checkpoint, PerformanceCheckpoint)
        assert checkpoint.stage_name == "test_stage"
        assert len(duckdb_monitor.checkpoints) == 1

    @pytest.mark.fast
    def test_checkpoint_to_dict(self):
        """Test converting checkpoint to dictionary."""
        checkpoint = PerformanceCheckpoint(
            stage_name="test",
            timestamp=1000.0,
            elapsed_time=10.0,
            memory_usage_gb=8.0,
            memory_percent=25.0,
            memory_available_gb=24.0,
            disk_usage_gb=100.0,
            database_size_gb=1.0,
            cpu_percent=50.0,
            cpu_count=8,
            io_read_bytes=1000,
            io_write_bytes=2000,
            io_read_count=10,
            io_write_count=20,
            thread_count=4,
        )

        result = checkpoint.to_dict()
        assert result["stage_name"] == "test"
        assert result["memory_usage_gb"] == 8.0
        assert result["cpu_percent"] == 50.0


class TestPerformanceStatistics:
    """Tests for performance statistics calculation."""

    @pytest.mark.fast
    def test_get_statistics_no_checkpoints(self, duckdb_monitor):
        """Test getting statistics with no checkpoints."""
        result = duckdb_monitor.get_performance_statistics()
        assert "error" in result

    @pytest.mark.fast
    def test_get_statistics_with_checkpoints(self, duckdb_monitor):
        """Test getting statistics with recorded checkpoints."""
        # Add mock checkpoints
        duckdb_monitor.checkpoints = [
            PerformanceCheckpoint(
                stage_name="stage1",
                timestamp=1000.0,
                elapsed_time=0.0,
                memory_usage_gb=8.0,
                memory_percent=25.0,
                memory_available_gb=24.0,
                disk_usage_gb=100.0,
                database_size_gb=1.0,
                cpu_percent=50.0,
                cpu_count=8,
                io_read_bytes=1000,
                io_write_bytes=2000,
                io_read_count=10,
                io_write_count=20,
                thread_count=4,
            ),
            PerformanceCheckpoint(
                stage_name="stage2",
                timestamp=1010.0,
                elapsed_time=10.0,
                memory_usage_gb=12.0,
                memory_percent=37.5,
                memory_available_gb=20.0,
                disk_usage_gb=100.0,
                database_size_gb=1.5,
                cpu_percent=75.0,
                cpu_count=8,
                io_read_bytes=2000,
                io_write_bytes=4000,
                io_read_count=20,
                io_write_count=40,
                thread_count=4,
            ),
        ]

        stats = duckdb_monitor.get_performance_statistics()

        assert "summary" in stats
        assert stats["summary"]["total_checkpoints"] == 2
        assert stats["summary"]["peak_memory_gb"] == 12.0
        assert stats["summary"]["avg_memory_gb"] == 10.0
        assert stats["summary"]["database_growth_gb"] == 0.5


class TestPerformanceLevel:
    """Tests for performance level assessment."""

    @pytest.mark.fast
    def test_performance_level_enum(self):
        """Test PerformanceLevel enum values."""
        assert PerformanceLevel.EXCELLENT.value == "excellent"
        assert PerformanceLevel.GOOD.value == "good"
        assert PerformanceLevel.MODERATE.value == "moderate"
        assert PerformanceLevel.POOR.value == "poor"
        assert PerformanceLevel.CRITICAL.value == "critical"

    @pytest.mark.fast
    def test_assess_overall_performance_no_checkpoints(self, duckdb_monitor):
        """Test performance assessment with no checkpoints."""
        level = duckdb_monitor._assess_overall_performance()
        assert level == PerformanceLevel.CRITICAL

    @pytest.mark.fast
    def test_assess_overall_performance_excellent(self, duckdb_monitor):
        """Test performance assessment for excellent performance."""
        # Low memory, good CPU, fast stages, low DB growth
        duckdb_monitor.checkpoints = [
            PerformanceCheckpoint(
                stage_name="stage1",
                timestamp=1000.0,
                elapsed_time=0.0,
                memory_usage_gb=5.0,
                memory_percent=15.0,
                memory_available_gb=27.0,
                disk_usage_gb=100.0,
                database_size_gb=1.0,
                cpu_percent=85.0,
                cpu_count=8,
                io_read_bytes=0,
                io_write_bytes=0,
                io_read_count=0,
                io_write_count=0,
                thread_count=4,
            ),
            PerformanceCheckpoint(
                stage_name="stage2",
                timestamp=1020.0,
                elapsed_time=20.0,
                memory_usage_gb=6.0,
                memory_percent=18.0,
                memory_available_gb=26.0,
                disk_usage_gb=100.0,
                database_size_gb=1.2,
                cpu_percent=80.0,
                cpu_count=8,
                io_read_bytes=0,
                io_write_bytes=0,
                io_read_count=0,
                io_write_count=0,
                thread_count=4,
            ),
        ]

        level = duckdb_monitor._assess_overall_performance()
        assert level in [PerformanceLevel.EXCELLENT, PerformanceLevel.GOOD]


class TestReportGeneration:
    """Tests for report generation."""

    @pytest.mark.fast
    def test_generate_report_no_checkpoints(self, duckdb_monitor):
        """Test report generation with no checkpoints."""
        report = duckdb_monitor.generate_report()
        assert "No performance data available" in report

    @pytest.mark.fast
    def test_generate_report_with_checkpoints(self, duckdb_monitor):
        """Test report generation with checkpoints."""
        duckdb_monitor.checkpoints = [
            PerformanceCheckpoint(
                stage_name="INITIALIZATION",
                timestamp=1000.0,
                elapsed_time=0.0,
                memory_usage_gb=8.0,
                memory_percent=25.0,
                memory_available_gb=24.0,
                disk_usage_gb=100.0,
                database_size_gb=1.0,
                cpu_percent=50.0,
                cpu_count=8,
                io_read_bytes=1000,
                io_write_bytes=2000,
                io_read_count=10,
                io_write_count=20,
                thread_count=4,
            ),
        ]

        report = duckdb_monitor.generate_report()

        assert "DuckDB Performance Analysis Report" in report
        assert "EXECUTIVE SUMMARY" in report
        assert "STAGE BREAKDOWN" in report


class TestOptimizationRecommendations:
    """Tests for optimization recommendations."""

    @pytest.mark.fast
    def test_performance_optimization_dataclass(self):
        """Test PerformanceOptimization dataclass."""
        opt = PerformanceOptimization(
            category="Memory",
            severity="warning",
            description="High memory usage",
            recommendation="Reduce batch size",
            potential_improvement="20% improvement",
            priority=2,
        )

        assert opt.category == "Memory"
        assert opt.priority == 2

    @pytest.mark.fast
    def test_recommendations_high_memory(self, duckdb_monitor):
        """Test recommendations for high memory usage."""
        duckdb_monitor.checkpoints = [
            PerformanceCheckpoint(
                stage_name="stage1",
                timestamp=1000.0,
                elapsed_time=0.0,
                memory_usage_gb=50.0,  # High memory
                memory_percent=75.0,
                memory_available_gb=16.0,
                disk_usage_gb=100.0,
                database_size_gb=1.0,
                cpu_percent=50.0,
                cpu_count=8,
                io_read_bytes=0,
                io_write_bytes=0,
                io_read_count=0,
                io_write_count=0,
                thread_count=4,
            ),
        ]

        recommendations = duckdb_monitor._generate_optimization_recommendations()
        assert len(recommendations) > 0
        # Should have a memory-related recommendation
        memory_recs = [r for r in recommendations if "Memory" in r.category]
        assert len(memory_recs) > 0


class TestDataExport:
    """Tests for performance data export."""

    @pytest.mark.fast
    def test_export_performance_data(self, duckdb_monitor, temp_reports_dir):
        """Test exporting performance data to JSON."""
        duckdb_monitor.checkpoints = [
            PerformanceCheckpoint(
                stage_name="stage1",
                timestamp=1000.0,
                elapsed_time=0.0,
                memory_usage_gb=8.0,
                memory_percent=25.0,
                memory_available_gb=24.0,
                disk_usage_gb=100.0,
                database_size_gb=1.0,
                cpu_percent=50.0,
                cpu_count=8,
                io_read_bytes=0,
                io_write_bytes=0,
                io_read_count=0,
                io_write_count=0,
                thread_count=4,
            ),
        ]
        duckdb_monitor.start_time = 1000.0
        duckdb_monitor.initial_metrics = {"memory_gb": 8.0}

        export_path = duckdb_monitor.export_performance_data("test_export.json")

        assert export_path.exists()
        assert export_path.name == "test_export.json"


class TestBackwardCompatibility:
    """Tests to verify backward compatibility of imports."""

    @pytest.mark.fast
    def test_import_duckdb_monitor_from_old_path(self):
        """Test that old import path still works for DuckDBPerformanceMonitor."""
        from planalign_orchestrator.performance_monitor import DuckDBPerformanceMonitor

        assert DuckDBPerformanceMonitor is not None

    @pytest.mark.fast
    def test_import_duckdb_monitor_from_new_path(self):
        """Test that new import path works for DuckDBPerformanceMonitor."""
        from planalign_orchestrator.monitoring import DuckDBPerformanceMonitor

        assert DuckDBPerformanceMonitor is not None

    @pytest.mark.fast
    def test_same_duckdb_monitor_from_both_paths(self):
        """Test that both paths return the same DuckDBPerformanceMonitor class."""
        from planalign_orchestrator.performance_monitor import (
            DuckDBPerformanceMonitor as DM_Old,
        )
        from planalign_orchestrator.monitoring import (
            DuckDBPerformanceMonitor as DM_New,
        )

        assert DM_Old is DM_New
