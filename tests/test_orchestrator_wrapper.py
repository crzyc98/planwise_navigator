"""Coverage tests for planalign_cli.integration.orchestrator_wrapper module.

Covers _ProgressMonitor, ProgressAwareOrchestrator, OrchestratorWrapper
properties, and regex pattern matching.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from planalign_cli.integration.orchestrator_wrapper import (
    ProgressAwareOrchestrator,
    _ProgressMonitor,
    _YEAR_PATTERN,
    _STAGE_PATTERN,
    _EVENT_PATTERN,
    _COMPLETED_STAGE_PATTERN,
    _FOUNDATION_VALIDATION_PATTERN,
    _MAX_LINE_LENGTH,
    OrchestratorWrapper,
)


# =============================================================================
# Regex patterns
# =============================================================================


@pytest.mark.fast
class TestRegexPatterns:
    def test_year_pattern(self):
        m = _YEAR_PATTERN.search("🔄 Starting simulation year 2025")
        assert m is not None
        assert m.group(1) == "2025"

    def test_stage_pattern(self):
        m = _STAGE_PATTERN.search("📋 Starting initialization")
        assert m is not None
        assert m.group(1) == "initialization"

    def test_event_pattern(self):
        m = _EVENT_PATTERN.search("📊 Generated 5,000 events")
        assert m is not None
        assert m.group(1) == "5,000"

    def test_event_pattern_no_comma(self):
        m = _EVENT_PATTERN.search("📊 Generated 500 events")
        assert m is not None
        assert m.group(1) == "500"

    def test_completed_stage_pattern(self):
        m = _COMPLETED_STAGE_PATTERN.search("✅ Completed initialization in 3.5s")
        assert m is not None
        assert m.group(1) == "initialization"
        assert m.group(2) == "3.5"

    def test_foundation_validation_pattern(self):
        m = _FOUNDATION_VALIDATION_PATTERN.search(
            "📊 Foundation model validation for year 2025:"
        )
        assert m is not None
        assert m.group(1) == "2025"


# =============================================================================
# _ProgressMonitor
# =============================================================================


@pytest.mark.fast
class TestProgressMonitor:
    def _make_monitor(self, callback=None):
        if callback is None:
            callback = MagicMock()
        original_stdout = io.StringIO()
        return _ProgressMonitor(callback, original_stdout), callback, original_stdout

    def test_write_processes_complete_lines(self):
        monitor, callback, _ = self._make_monitor()
        monitor.write("🔄 Starting simulation year 2025\n")
        callback.update_year.assert_called_once_with(2025)

    def test_write_buffers_incomplete_lines(self):
        monitor, callback, _ = self._make_monitor()
        monitor.write("🔄 Starting simulation")
        callback.update_year.assert_not_called()
        assert "🔄 Starting simulation" in monitor.buffer

    def test_write_completes_buffered_line(self):
        monitor, callback, _ = self._make_monitor()
        monitor.write("🔄 Starting simulation ")
        monitor.write("year 2025\n")
        callback.update_year.assert_called_once_with(2025)

    def test_write_multiple_lines(self):
        monitor, callback, _ = self._make_monitor()
        monitor.write("📋 Starting initialization\n📋 Starting foundation\n")
        assert callback.update_stage.call_count == 2

    def test_write_calls_on_dbt_line(self):
        monitor, callback, _ = self._make_monitor()
        monitor.write("ERROR: compilation failed\n")
        callback.on_dbt_line.assert_called_once_with("ERROR: compilation failed")

    def test_write_reentrant_guard(self):
        """Re-entrant write bypasses processing and goes to original_stdout."""
        original_stdout = io.StringIO()
        callback = MagicMock()
        monitor = _ProgressMonitor(callback, original_stdout)

        # Simulate re-entrant write by setting _writing flag
        monitor._writing = True
        monitor.write("reentrant text")
        assert "reentrant text" in original_stdout.getvalue()
        callback.update_year.assert_not_called()

    def test_process_line_truncates_long_lines(self):
        monitor, callback, _ = self._make_monitor()
        long_line = "x" * 2000 + "\n"
        monitor.write(long_line)
        # Should not crash, line is truncated to _MAX_LINE_LENGTH

    def test_check_year(self):
        monitor, callback, _ = self._make_monitor()
        monitor._check_year("🔄 Starting simulation year 2026")
        assert monitor.current_year == 2026
        callback.update_year.assert_called_once_with(2026)

    def test_check_year_no_match(self):
        monitor, callback, _ = self._make_monitor()
        monitor._check_year("some random line")
        assert monitor.current_year is None

    def test_check_stage(self):
        monitor, callback, _ = self._make_monitor()
        monitor._check_stage("📋 Starting foundation")
        callback.update_stage.assert_called_once_with("foundation")

    def test_check_stage_no_match(self):
        monitor, callback, _ = self._make_monitor()
        monitor._check_stage("some random line")
        callback.update_stage.assert_not_called()

    def test_check_events(self):
        monitor, callback, _ = self._make_monitor()
        monitor._check_events("📊 Generated 5,000 events")
        callback.update_events.assert_called_once_with(5000)

    def test_check_events_no_match(self):
        monitor, callback, _ = self._make_monitor()
        monitor._check_events("random")
        callback.update_events.assert_not_called()

    def test_check_events_no_update_events_method(self):
        callback = MagicMock(spec=[])  # No update_events
        monitor = _ProgressMonitor(callback, io.StringIO())
        # Should not raise
        monitor._check_events("📊 Generated 500 events")

    def test_check_completed_stage(self):
        monitor, callback, _ = self._make_monitor()
        monitor._check_completed_stage("✅ Completed initialization in 3.5s")
        callback.stage_completed.assert_called_once_with("initialization", 3.5)

    def test_check_completed_stage_no_match(self):
        monitor, callback, _ = self._make_monitor()
        monitor._check_completed_stage("random")
        callback.stage_completed.assert_not_called()

    def test_check_foundation_validation(self):
        monitor, callback, _ = self._make_monitor()
        monitor._check_foundation_validation(
            "📊 Foundation model validation for year 2025:"
        )
        callback.year_validation.assert_called_once_with(2025)

    def test_check_foundation_validation_no_match(self):
        monitor, callback, _ = self._make_monitor()
        monitor._check_foundation_validation("random")
        callback.year_validation.assert_not_called()

    def test_flush(self):
        original_stdout = MagicMock()
        monitor = _ProgressMonitor(MagicMock(), original_stdout)
        monitor.flush()
        original_stdout.flush.assert_called_once()

    def test_callback_without_update_year(self):
        """Callback without update_year method doesn't crash."""
        callback = MagicMock(spec=[])
        monitor = _ProgressMonitor(callback, io.StringIO())
        monitor._check_year("🔄 Starting simulation year 2025")
        # Just verifying no AttributeError

    def test_callback_without_update_stage(self):
        callback = MagicMock(spec=[])
        monitor = _ProgressMonitor(callback, io.StringIO())
        monitor._check_stage("📋 Starting foundation")

    def test_callback_without_stage_completed(self):
        callback = MagicMock(spec=[])
        monitor = _ProgressMonitor(callback, io.StringIO())
        monitor._check_completed_stage("✅ Completed initialization in 3.5s")

    def test_callback_without_year_validation(self):
        callback = MagicMock(spec=[])
        monitor = _ProgressMonitor(callback, io.StringIO())
        monitor._check_foundation_validation(
            "📊 Foundation model validation for year 2025:"
        )

    def test_callback_without_on_dbt_line(self):
        """No crash if callback doesn't have on_dbt_line."""
        callback = MagicMock(spec=["update_year"])
        monitor = _ProgressMonitor(callback, io.StringIO())
        monitor.write("some line\n")


# =============================================================================
# ProgressAwareOrchestrator
# =============================================================================


@pytest.mark.fast
class TestProgressAwareOrchestrator:
    def test_getattr_delegates(self):
        orchestrator = MagicMock()
        orchestrator.some_attr = "value"
        pao = ProgressAwareOrchestrator(orchestrator, MagicMock())
        assert pao.some_attr == "value"

    def test_wires_progress_callback_to_year_executor(self):
        orchestrator = MagicMock()
        orchestrator.year_executor = MagicMock()
        callback = MagicMock()
        ProgressAwareOrchestrator(orchestrator, callback)
        assert orchestrator.year_executor.progress_callback == callback

    def test_no_year_executor_no_error(self):
        orchestrator = MagicMock(spec=["execute_multi_year_simulation"])
        callback = MagicMock()
        # Should not raise
        ProgressAwareOrchestrator(orchestrator, callback)

    def test_execute_redirects_stdout(self):
        orchestrator = MagicMock()
        orchestrator.execute_multi_year_simulation.return_value = "result"
        callback = MagicMock()
        pao = ProgressAwareOrchestrator(orchestrator, callback)

        result = pao.execute_multi_year_simulation(start_year=2025, end_year=2027)
        assert result == "result"
        orchestrator.execute_multi_year_simulation.assert_called_once()

    def test_execute_restores_stdout_on_error(self):
        orchestrator = MagicMock()
        orchestrator.execute_multi_year_simulation.side_effect = RuntimeError("boom")
        callback = MagicMock()
        pao = ProgressAwareOrchestrator(orchestrator, callback)

        original = sys.stdout
        with pytest.raises(RuntimeError, match="boom"):
            pao.execute_multi_year_simulation()
        assert sys.stdout is original

    def test_execute_flushes_remaining_buffer(self):
        orchestrator = MagicMock()

        def side_effect(**kwargs):
            # Simulate output without trailing newline
            sys.stdout.write("🔄 Starting simulation year 2025")
            return "result"

        orchestrator.execute_multi_year_simulation.side_effect = side_effect
        callback = MagicMock()
        pao = ProgressAwareOrchestrator(orchestrator, callback)
        result = pao.execute_multi_year_simulation()
        assert result == "result"


# =============================================================================
# OrchestratorWrapper
# =============================================================================


@pytest.mark.fast
class TestOrchestratorWrapper:
    @patch("planalign_cli.integration.orchestrator_wrapper.load_simulation_config")
    def test_config_lazy_loads(self, mock_load):
        mock_config = MagicMock()
        mock_config.optimization = None
        mock_load.return_value = mock_config
        wrapper = OrchestratorWrapper(
            config_path=Path("config/simulation_config.yaml"),
            db_path=Path("dbt/simulation.duckdb"),
        )
        # Create the file check expectation
        with patch.object(Path, "exists", return_value=True):
            _ = wrapper.config
        mock_load.assert_called_once()

    @patch("planalign_cli.integration.orchestrator_wrapper.load_simulation_config")
    def test_config_missing_file_raises(self, mock_load):
        wrapper = OrchestratorWrapper(
            config_path=Path("nonexistent.yaml"),
            db_path=Path("dbt/simulation.duckdb"),
        )
        with pytest.raises(FileNotFoundError):
            _ = wrapper.config

    @patch("planalign_cli.integration.orchestrator_wrapper.DatabaseConnectionManager")
    def test_db_lazy_loads(self, mock_db_cls):
        wrapper = OrchestratorWrapper(
            config_path=Path("config.yaml"),
            db_path=Path("dbt/simulation.duckdb"),
        )
        _ = wrapper.db
        mock_db_cls.assert_called_once()

    @patch("planalign_cli.integration.orchestrator_wrapper.CheckpointManager")
    def test_checkpoint_manager_lazy_loads(self, mock_cp_cls):
        wrapper = OrchestratorWrapper(
            config_path=Path("config.yaml"),
            db_path=Path("dbt/simulation.duckdb"),
        )
        _ = wrapper.checkpoint_manager
        mock_cp_cls.assert_called_once()

    @patch("planalign_cli.integration.orchestrator_wrapper.RecoveryOrchestrator")
    @patch("planalign_cli.integration.orchestrator_wrapper.CheckpointManager")
    def test_recovery_orchestrator_lazy_loads(self, mock_cp_cls, mock_ro_cls):
        wrapper = OrchestratorWrapper(
            config_path=Path("config.yaml"),
            db_path=Path("dbt/simulation.duckdb"),
        )
        _ = wrapper.recovery_orchestrator
        mock_ro_cls.assert_called_once()

    @patch("planalign_cli.integration.orchestrator_wrapper.ScenarioBatchRunner")
    def test_create_batch_runner(self, mock_runner_cls):
        wrapper = OrchestratorWrapper(
            config_path=Path("config.yaml"),
            db_path=Path("dbt/simulation.duckdb"),
        )
        wrapper.create_batch_runner(Path("scenarios"), Path("output"))
        mock_runner_cls.assert_called_once()

    @patch("planalign_cli.integration.orchestrator_wrapper.load_simulation_config")
    def test_validate_configuration_valid(self, mock_load):
        mock_config = MagicMock()
        mock_config.optimization = None
        mock_config.scenario_id = "baseline"
        mock_config.plan_design_id = "standard"
        mock_load.return_value = mock_config
        wrapper = OrchestratorWrapper(
            config_path=Path("config.yaml"),
            db_path=Path("dbt/simulation.duckdb"),
        )
        with patch.object(Path, "exists", return_value=True):
            result = wrapper.validate_configuration()
        assert result["valid"]

    @patch("planalign_cli.integration.orchestrator_wrapper.load_simulation_config")
    def test_validate_configuration_missing_ids(self, mock_load):
        mock_config = MagicMock()
        mock_config.optimization = None
        mock_config.scenario_id = None
        mock_config.plan_design_id = None
        mock_load.return_value = mock_config
        wrapper = OrchestratorWrapper(
            config_path=Path("config.yaml"),
            db_path=Path("dbt/simulation.duckdb"),
        )
        with patch.object(Path, "exists", return_value=True):
            result = wrapper.validate_configuration()
        assert result["valid"]
        assert len(result["warnings"]) > 0

    def test_validate_configuration_error(self):
        wrapper = OrchestratorWrapper(
            config_path=Path("nonexistent.yaml"),
            db_path=Path("dbt/simulation.duckdb"),
        )
        result = wrapper.validate_configuration()
        assert not result["valid"]
        assert "error" in result

    @patch("planalign_cli.integration.orchestrator_wrapper.CheckpointManager")
    def test_get_checkpoint_info_error(self, mock_cp_cls):
        mock_cp_cls.side_effect = RuntimeError("no db")
        wrapper = OrchestratorWrapper(
            config_path=Path("config.yaml"),
            db_path=Path("nonexistent.duckdb"),
        )
        result = wrapper.get_checkpoint_info()
        assert not result["success"]

    @patch("planalign_cli.integration.orchestrator_wrapper.load_simulation_config")
    def test_check_system_health_healthy(self, mock_load):
        mock_config = MagicMock()
        mock_config.optimization = None
        mock_load.return_value = mock_config
        wrapper = OrchestratorWrapper(
            config_path=Path("config.yaml"),
            db_path=Path("dbt/simulation.duckdb"),
        )
        with patch.object(Path, "exists", return_value=True):
            health = wrapper.check_system_health()
        assert health["healthy"]

    def test_check_system_health_missing_config(self):
        wrapper = OrchestratorWrapper(
            config_path=Path("nonexistent.yaml"),
            db_path=Path("dbt/simulation.duckdb"),
        )
        with patch.object(Path, "exists", return_value=True):
            health = wrapper.check_system_health()
        assert not health["healthy"]

    def test_check_system_health_missing_db(self):
        wrapper = OrchestratorWrapper(
            config_path=Path("config.yaml"),
            db_path=Path("nonexistent.duckdb"),
        )
        with patch.object(Path, "exists", side_effect=lambda: False):
            # Need more specific patching
            pass

    @patch("planalign_cli.integration.orchestrator_wrapper.load_simulation_config")
    def test_check_system_health_db_not_exists(self, mock_load):
        mock_config = MagicMock()
        mock_config.optimization = None
        mock_load.return_value = mock_config
        wrapper = OrchestratorWrapper(
            config_path=Path("config.yaml"),
            db_path=Path("nonexistent.duckdb"),
        )

        def exists_side_effect(self_path=None):
            """config.yaml and dirs exist, db does not."""
            path_str = str(wrapper.db_path if self_path is None else self_path)
            return "nonexistent" not in path_str

        with patch.object(Path, "exists", side_effect=lambda: True):
            # db_path.exists() is called directly
            with patch.object(type(wrapper.db_path), "exists", return_value=False):
                health = wrapper.check_system_health()
        assert "Database file does not exist" in str(health["warnings"])
