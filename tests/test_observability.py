"""
Comprehensive tests for the observability framework

Tests structured logging, performance monitoring, run summaries,
and integrated observability management.
"""

import json
import shutil
import tempfile
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from navigator_orchestrator.logger import (JSONFormatter, ProductionLogger,
                                           get_logger)
from navigator_orchestrator.observability import (ObservabilityManager,
                                                  create_observability_manager,
                                                  observability_session)
from navigator_orchestrator.performance_monitor import (PerformanceMetrics,
                                                        PerformanceMonitor)
from navigator_orchestrator.run_summary import (RunIssue, RunMetadata,
                                                RunSummaryGenerator)


class TestProductionLogger:
    """Test the structured JSON logging system"""

    def setup_method(self):
        """Setup test environment"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.original_cwd = Path.cwd()
        # Change to test directory to avoid polluting real logs
        import os

        os.chdir(self.test_dir)

    def teardown_method(self):
        """Cleanup test environment"""
        import os

        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_logger_creation(self):
        """Test logger creation with auto-generated run ID"""
        logger = ProductionLogger()
        assert logger.run_id is not None
        assert len(logger.run_id) > 0
        assert "-" in logger.run_id  # Should contain timestamp-uuid format

    def test_custom_run_id(self):
        """Test logger creation with custom run ID"""
        custom_id = "test-run-12345"
        logger = ProductionLogger(run_id=custom_id)
        assert logger.get_run_id() == custom_id

    def test_log_levels(self):
        """Test different log levels"""
        logger = ProductionLogger(run_id="test-levels")

        logger.debug("Debug message", key="debug")
        logger.info("Info message", key="info")
        logger.warning("Warning message", key="warning")
        logger.error("Error message", key="error")
        logger.critical("Critical message", key="critical")

        # Verify log file was created
        log_file = Path("logs/navigator.log")
        assert log_file.exists()

        # Read and verify log entries
        with open(log_file) as f:
            log_lines = f.readlines()

        assert len(log_lines) >= 4  # Should have at least INFO and above

        # Verify JSON structure
        for line in log_lines:
            log_data = json.loads(line.strip())
            assert "timestamp" in log_data
            assert "run_id" in log_data
            assert log_data["run_id"] == "test-levels"
            assert "level" in log_data
            assert "message" in log_data

    def test_structured_logging(self):
        """Test structured logging with custom fields"""
        logger = ProductionLogger(run_id="test-structured")

        logger.info(
            "Test message", year=2025, operation="test_op", duration=1.5, success=True
        )

        log_file = Path("logs/navigator.log")
        with open(log_file) as f:
            log_data = json.loads(f.read().strip())

        assert log_data["year"] == 2025
        assert log_data["operation"] == "test_op"
        assert log_data["duration"] == 1.5
        assert log_data["success"] is True

    def test_exception_logging(self):
        """Test exception logging with traceback"""
        logger = ProductionLogger(run_id="test-exception")

        try:
            raise ValueError("Test exception")
        except ValueError:
            logger.exception("Test exception occurred", context="test")

        log_file = Path("logs/navigator.log")
        with open(log_file) as f:
            log_data = json.loads(f.read().strip())

        assert "exception" in log_data
        assert log_data["exception"]["type"] == "ValueError"
        assert "Test exception" in log_data["exception"]["message"]
        assert "traceback" in log_data["exception"]

    def test_factory_function(self):
        """Test logger factory function"""
        logger = get_logger(run_id="factory-test", log_level="DEBUG")
        assert logger.get_run_id() == "factory-test"
        assert logger.log_level == 10  # DEBUG level


class TestPerformanceMonitor:
    """Test the performance monitoring system"""

    def setup_method(self):
        """Setup test environment"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.original_cwd = Path.cwd()
        import os

        os.chdir(self.test_dir)

        self.logger = ProductionLogger(run_id="perf-test")
        self.monitor = PerformanceMonitor(self.logger)

    def teardown_method(self):
        """Cleanup test environment"""
        import os

        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_operation_timing(self):
        """Test basic operation timing"""
        with self.monitor.time_operation("test_operation", year=2025) as metrics:
            time.sleep(0.1)  # Simulate work
            assert metrics.operation_name == "test_operation"
            assert metrics.status == "running"

        assert metrics.status == "success"
        assert metrics.duration_seconds is not None
        assert metrics.duration_seconds >= 0.1
        assert metrics.start_memory_mb is not None
        assert metrics.end_memory_mb is not None

    def test_failed_operation(self):
        """Test operation timing with failure"""
        with pytest.raises(ValueError):
            with self.monitor.time_operation("failing_operation") as metrics:
                raise ValueError("Test failure")

        assert metrics.status == "failed"
        assert metrics.error_message == "Test failure"
        assert metrics.duration_seconds is not None

    def test_metrics_collection(self):
        """Test metrics collection and retrieval"""
        with self.monitor.time_operation("op1"):
            time.sleep(0.05)

        with self.monitor.time_operation("op2"):
            time.sleep(0.1)

        metrics = self.monitor.get_metrics()
        assert "op1" in metrics
        assert "op2" in metrics

        op1_metrics = self.monitor.get_metrics("op1")
        assert op1_metrics["operation"] == "op1"
        assert op1_metrics["status"] == "success"

    def test_performance_summary(self):
        """Test performance summary generation"""
        with self.monitor.time_operation("fast_op"):
            time.sleep(0.05)

        with self.monitor.time_operation("slow_op"):
            time.sleep(0.15)

        summary = self.monitor.get_summary()
        assert summary["total_operations"] == 2
        assert summary["successful_operations"] == 2
        assert summary["failed_operations"] == 0
        assert summary["slowest_operation"]["name"] == "slow_op"
        assert summary["fastest_operation"]["name"] == "fast_op"

    def test_data_quality_logging(self):
        """Test data quality check logging"""
        self.monitor.log_data_quality_check(2025, "row_count", 1000, 1200)
        self.monitor.log_data_quality_check(
            2025, "error_rate", 0.05, 0.01
        )  # Should trigger warning

        # Verify logs were created (basic check)
        log_file = Path("logs/navigator.log")
        assert log_file.exists()


class TestRunSummaryGenerator:
    """Test the run summary and reporting system"""

    def setup_method(self):
        """Setup test environment"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.original_cwd = Path.cwd()
        import os

        os.chdir(self.test_dir)

        self.logger = ProductionLogger(run_id="summary-test")
        self.performance_monitor = PerformanceMonitor(self.logger)
        self.summary = RunSummaryGenerator(
            "summary-test", self.logger, self.performance_monitor
        )

    def teardown_method(self):
        """Cleanup test environment"""
        import os

        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_issue_tracking(self):
        """Test error and warning tracking"""
        self.summary.add_error("Test error", {"context": "test"})
        self.summary.add_warning("Test warning", {"level": "minor"})

        issue_summary = self.summary.get_issue_summary()
        assert issue_summary["total_errors"] == 1
        assert issue_summary["total_warnings"] == 1
        assert issue_summary["has_issues"] is True
        assert "Test error" in issue_summary["latest_error"]["message"]

    def test_custom_metrics(self):
        """Test custom metrics tracking"""
        self.summary.add_metric("total_employees", 42331, "Total workforce size")
        self.summary.add_metric("processing_rate", 850.5, "Events per second")

        assert "total_employees" in self.summary.custom_metrics
        assert self.summary.custom_metrics["total_employees"]["value"] == 42331

    def test_configuration_tracking(self):
        """Test configuration and backup tracking"""
        config = {"start_year": 2025, "end_year": 2027, "growth_rate": 0.03}
        self.summary.set_configuration(config)

        backup_path = "/tmp/backup_20250818.sql"
        self.summary.set_backup_path(backup_path)

        assert self.summary.metadata.configuration == config
        assert self.summary.metadata.backup_path == backup_path

    def test_summary_generation(self):
        """Test complete summary generation"""
        # Add some test data
        self.summary.add_error("Test error")
        self.summary.add_metric("test_metric", 123)
        self.summary.set_configuration({"test": "config"})

        # Generate summary
        summary = self.summary.generate_summary("success")

        # Verify structure
        assert "run_metadata" in summary
        assert "execution_summary" in summary
        assert "performance_metrics" in summary
        assert "custom_metrics" in summary
        assert "issues" in summary

        # Verify content
        assert summary["run_metadata"]["run_id"] == "summary-test"
        assert summary["run_metadata"]["status"] == "success"
        assert summary["execution_summary"]["total_errors"] == 1
        assert summary["custom_metrics"]["test_metric"]["value"] == 123

        # Verify artifacts were created
        artifacts_dir = Path("artifacts/runs/summary-test")
        assert artifacts_dir.exists()
        assert (artifacts_dir / "summary.json").exists()
        assert (artifacts_dir / "errors.json").exists()

    def test_monitoring_export(self):
        """Test export format for monitoring systems"""
        export_data = self.summary.export_for_monitoring()

        required_fields = [
            "run_id",
            "status",
            "error_count",
            "warning_count",
            "start_time",
            "environment",
            "user",
        ]

        for field in required_fields:
            assert field in export_data


class TestObservabilityManager:
    """Test the integrated observability manager"""

    def setup_method(self):
        """Setup test environment"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.original_cwd = Path.cwd()
        import os

        os.chdir(self.test_dir)

    def teardown_method(self):
        """Cleanup test environment"""
        import os

        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_manager_creation(self):
        """Test observability manager creation"""
        manager = ObservabilityManager(run_id="obs-test")
        assert manager.get_run_id() == "obs-test"
        assert manager.logger is not None
        assert manager.performance_monitor is not None
        assert manager.run_summary is not None

    def test_integrated_operation_tracking(self):
        """Test integrated operation tracking"""
        manager = ObservabilityManager(run_id="tracking-test")

        with manager.track_operation("test_integration", year=2025) as metrics:
            time.sleep(0.1)
            manager.add_metric("processed_records", 1000)

        assert metrics.status == "success"
        assert metrics.duration_seconds >= 0.1

        perf_summary = manager.get_performance_summary()
        assert perf_summary["total_operations"] == 1

    def test_unified_logging(self):
        """Test unified logging interface"""
        manager = ObservabilityManager(run_id="logging-test")

        manager.log_info("Info message", key="value")
        manager.log_warning("Warning message", severity="medium")
        manager.log_error("Error message", error_code=500)

        issue_summary = manager.get_issue_summary()
        assert issue_summary["total_warnings"] == 1
        assert issue_summary["total_errors"] == 1

    def test_run_finalization(self):
        """Test run finalization and summary generation"""
        manager = ObservabilityManager(run_id="final-test")

        # Simulate some activity
        with manager.track_operation("setup"):
            time.sleep(0.05)

        manager.add_metric("final_count", 42)
        manager.set_configuration({"mode": "test"})

        # Finalize run
        summary = manager.finalize_run("success")

        assert summary["run_metadata"]["status"] == "success"
        assert summary["custom_metrics"]["final_count"]["value"] == 42

        # Verify artifacts
        artifacts_dir = Path("artifacts/runs/final-test")
        assert artifacts_dir.exists()

    def test_factory_function(self):
        """Test factory function"""
        manager = create_observability_manager(run_id="factory-test", log_level="DEBUG")
        assert manager.get_run_id() == "factory-test"

    def test_context_manager(self):
        """Test observability session context manager"""
        with observability_session(run_id="context-test") as manager:
            manager.log_info("Test message in context")
            assert manager.get_run_id() == "context-test"

        # Manager should be closed after context exit
        # (We can't easily test the close state, but this verifies no exceptions)


class TestIntegration:
    """Integration tests for the complete observability framework"""

    def setup_method(self):
        """Setup test environment"""
        self.test_dir = Path(tempfile.mkdtemp())
        self.original_cwd = Path.cwd()
        import os

        os.chdir(self.test_dir)

    def teardown_method(self):
        """Cleanup test environment"""
        import os

        os.chdir(self.original_cwd)
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_complete_simulation_workflow(self):
        """Test a complete simulation workflow with full observability"""
        with observability_session(run_id="simulation-test") as obs:
            # Set up simulation
            obs.set_configuration(
                {"start_year": 2025, "end_year": 2027, "growth_rate": 0.03}
            )

            # Simulate multi-year processing
            total_events = 0

            for year in [2025, 2026, 2027]:
                with obs.track_operation(f"process_year_{year}", year=year) as metrics:
                    # Simulate processing time
                    time.sleep(0.05)

                    # Simulate some events
                    year_events = 1000 + year
                    total_events += year_events

                    obs.add_metric(f"events_year_{year}", year_events)
                    obs.log_data_quality_check(year, "event_count", year_events, 2000)

            # Add final metrics
            obs.add_metric("total_events_processed", total_events)

            # Simulate a warning
            obs.log_warning("High memory usage detected", memory_mb=512)

            # Finalize run
            summary = obs.finalize_run("success")

        # Verify complete workflow
        assert summary["run_metadata"]["status"] == "success"
        assert summary["execution_summary"]["total_warnings"] == 1
        assert summary["execution_summary"]["total_errors"] == 0
        assert summary["performance_metrics"]["total_operations"] == 3
        assert (
            summary["custom_metrics"]["total_events_processed"]["value"] == total_events
        )

        # Verify all artifacts were created
        artifacts_dir = Path("artifacts/runs/simulation-test")
        assert artifacts_dir.exists()
        assert (artifacts_dir / "summary.json").exists()
        assert (artifacts_dir / "warnings.json").exists()
        assert (artifacts_dir / "performance.json").exists()

        # Verify log file structure
        log_file = Path("logs/navigator.log")
        assert log_file.exists()

        with open(log_file) as f:
            log_lines = f.readlines()

        # Should have multiple structured log entries
        assert len(log_lines) > 5

        # Verify all entries are valid JSON with run correlation
        for line in log_lines:
            log_data = json.loads(line.strip())
            assert log_data["run_id"] == "simulation-test"
            assert "timestamp" in log_data
            assert "level" in log_data


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
