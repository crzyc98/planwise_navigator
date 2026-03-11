"""Coverage tests for planalign_cli.commands.simulate module.

Covers helper functions, LiveProgressTracker, and summary display logic.
"""

from __future__ import annotations

import io
import sys
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from planalign_cli.commands.simulate import (
    LiveProgressTracker,
    _apply_growth_override,
    _check_system_health,
    _parse_growth_rate,
    _resolve_start_year,
    _show_dry_run_preview,
    _show_enhanced_simulation_summary,
    _show_simulation_summary,
)


# =============================================================================
# _parse_growth_rate
# =============================================================================


@pytest.mark.fast
class TestParseGrowthRate:
    def test_percentage_format(self):
        assert _parse_growth_rate("3.5%") == pytest.approx(0.035)

    def test_decimal_format(self):
        assert _parse_growth_rate("0.035") == pytest.approx(0.035)

    def test_whitespace_stripped(self):
        assert _parse_growth_rate("  5%  ") == pytest.approx(0.05)

    def test_integer_percentage(self):
        assert _parse_growth_rate("10%") == pytest.approx(0.1)

    def test_plain_integer(self):
        assert _parse_growth_rate("3") == pytest.approx(3.0)


# =============================================================================
# _apply_growth_override
# =============================================================================


@pytest.mark.fast
class TestApplyGrowthOverride:
    def test_no_growth_returns_early(self, capsys):
        _apply_growth_override(None, verbose=True)
        assert capsys.readouterr().out == ""

    @patch("planalign_cli.commands.simulate.console")
    def test_verbose_logs_rate(self, mock_console):
        _apply_growth_override("3.5%", verbose=True)
        mock_console.print.assert_called_once()
        call_args = mock_console.print.call_args[0][0]
        assert "0.035" in call_args

    @patch("planalign_cli.commands.simulate.console")
    def test_not_verbose_no_log(self, mock_console):
        _apply_growth_override("3.5%", verbose=False)
        mock_console.print.assert_not_called()


# =============================================================================
# _check_system_health
# =============================================================================


@pytest.mark.fast
class TestCheckSystemHealth:
    def test_healthy_no_exit(self):
        wrapper = MagicMock()
        wrapper.check_system_health.return_value = {"healthy": True, "issues": []}
        # Should not raise
        _check_system_health(wrapper)

    def test_unhealthy_raises_exit(self):
        wrapper = MagicMock()
        wrapper.check_system_health.return_value = {
            "healthy": False,
            "issues": ["Database missing", "Config invalid"],
        }
        from click.exceptions import Exit

        with pytest.raises(Exit):
            _check_system_health(wrapper)


# =============================================================================
# _resolve_start_year
# =============================================================================


@pytest.mark.fast
class TestResolveStartYear:
    def test_force_restart_returns_start_year(self):
        wrapper = MagicMock()
        result = _resolve_start_year(
            wrapper, Path("config.yaml"), 2025, 2027, resume=False, force_restart=True
        )
        assert result == 2025

    def test_no_resume_returns_start_year(self):
        wrapper = MagicMock()
        result = _resolve_start_year(
            wrapper, Path("config.yaml"), 2025, 2027, resume=False, force_restart=False
        )
        assert result == 2025

    def test_resume_no_checkpoint_returns_start_year(self):
        wrapper = MagicMock()
        wrapper.recovery_orchestrator.calculate_config_hash.return_value = "hash123"
        wrapper.recovery_orchestrator.resume_simulation.return_value = None
        result = _resolve_start_year(
            wrapper, Path("config.yaml"), 2025, 2027, resume=True, force_restart=False
        )
        assert result == 2025

    def test_resume_with_checkpoint_returns_resume_year(self):
        wrapper = MagicMock()
        wrapper.recovery_orchestrator.calculate_config_hash.return_value = "hash123"
        wrapper.recovery_orchestrator.resume_simulation.return_value = 2026
        result = _resolve_start_year(
            wrapper, Path("config.yaml"), 2025, 2027, resume=True, force_restart=False
        )
        assert result == 2026

    def test_resume_past_end_returns_none(self):
        wrapper = MagicMock()
        wrapper.recovery_orchestrator.calculate_config_hash.return_value = "hash123"
        wrapper.recovery_orchestrator.resume_simulation.return_value = 2028
        result = _resolve_start_year(
            wrapper, Path("config.yaml"), 2025, 2027, resume=True, force_restart=False
        )
        assert result is None


# =============================================================================
# _show_dry_run_preview
# =============================================================================


@pytest.mark.fast
class TestShowDryRunPreview:
    @patch("planalign_cli.commands.simulate.console")
    def test_preview_with_threads(self, mock_console):
        wrapper = MagicMock()
        wrapper.config_path = Path("config.yaml")
        wrapper.db_path = Path("dbt/simulation.duckdb")
        _show_dry_run_preview(wrapper, 2025, 2026, threads=4)
        # Should print Panel calls for configuration and execution plan
        assert mock_console.print.call_count >= 3

    @patch("planalign_cli.commands.simulate.console")
    def test_preview_without_threads(self, mock_console):
        wrapper = MagicMock()
        wrapper.config_path = Path("config.yaml")
        wrapper.db_path = Path("dbt/simulation.duckdb")
        _show_dry_run_preview(wrapper, 2025, 2025, threads=None)
        assert mock_console.print.call_count >= 3


# =============================================================================
# LiveProgressTracker
# =============================================================================


@pytest.mark.fast
class TestLiveProgressTracker:
    def _make_tracker(self, **kwargs):
        defaults = {"total_years": 3, "start_year": 2025, "end_year": 2027, "verbose": False}
        defaults.update(kwargs)
        return LiveProgressTracker(**defaults)

    def test_update_year_first_call(self):
        tracker = self._make_tracker()
        tracker.update_year(2025)
        assert tracker.current_year == 2025
        assert tracker.years_completed == 0

    def test_update_year_transition_increments(self):
        tracker = self._make_tracker()
        tracker.update_year(2025)
        tracker.update_year(2026)
        assert tracker.years_completed == 1
        assert tracker.current_year == 2026

    def test_update_year_same_year_no_increment(self):
        tracker = self._make_tracker()
        tracker.update_year(2025)
        tracker.update_year(2025)
        assert tracker.years_completed == 0

    def test_update_stage_first_call(self):
        tracker = self._make_tracker()
        tracker.update_stage("initialization")
        assert tracker.current_stage == "initialization"

    def test_update_stage_records_duration_of_previous(self):
        tracker = self._make_tracker()
        tracker.update_year(2025)
        tracker.update_stage("initialization")
        # Simulate time passing
        tracker.stage_start_time = datetime.now() - timedelta(seconds=5)
        tracker.update_stage("foundation")
        assert "2025_initialization" in tracker.stage_durations

    def test_update_events(self):
        tracker = self._make_tracker()
        tracker.update_year(2025)
        tracker.update_events(5000)
        assert tracker.year_events[2025] == 5000
        assert tracker.total_events == 5000

    def test_update_events_no_current_year(self):
        tracker = self._make_tracker()
        tracker.update_events(5000)
        assert tracker.total_events == 0

    def test_stage_completed(self):
        tracker = self._make_tracker()
        tracker.update_year(2025)
        tracker.stage_completed("initialization", 3.5)
        assert tracker.stage_durations["2025_initialization"] == 3.5

    def test_stage_completed_no_current_year(self):
        tracker = self._make_tracker()
        tracker.stage_completed("initialization", 3.5)
        assert len(tracker.stage_durations) == 0

    def test_year_validation(self):
        tracker = self._make_tracker()
        tracker.update_year(2025)
        # Should not raise even without progress bars
        tracker.year_validation(2025)

    def test_year_validation_wrong_year(self):
        tracker = self._make_tracker()
        tracker.update_year(2025)
        tracker.year_validation(2026)
        # No error, just skipped

    def test_on_dbt_line_verbose_signal(self):
        tracker = self._make_tracker(verbose=True)
        # Without _live, should fall back to print
        with patch("builtins.print") as mock_print:
            tracker.on_dbt_line("ERROR: compilation failed")
            mock_print.assert_called_once_with("ERROR: compilation failed")

    def test_on_dbt_line_not_verbose(self):
        tracker = self._make_tracker(verbose=False)
        with patch("builtins.print") as mock_print:
            tracker.on_dbt_line("ERROR: compilation failed")
            mock_print.assert_not_called()

    def test_on_dbt_line_noise_filtered(self):
        tracker = self._make_tracker(verbose=True)
        with patch("builtins.print") as mock_print:
            tracker.on_dbt_line("select employee_id from census")
            mock_print.assert_not_called()

    def test_on_dbt_line_with_live(self):
        tracker = self._make_tracker(verbose=True)
        mock_live = MagicMock()
        tracker._live = mock_live
        tracker.on_dbt_line("ERROR: something bad")
        mock_live.console.print.assert_called_once_with("ERROR: something bad", highlight=False)

    def test_build_status_table_basic(self):
        tracker = self._make_tracker()
        table = tracker._build_status_table()
        assert table.title == "📊 Live Simulation Metrics"

    def test_build_status_table_with_data(self):
        tracker = self._make_tracker()
        tracker.update_year(2025)
        tracker.update_stage("event_generation")
        tracker.update_events(5000)
        tracker.stage_completed("initialization", 2.5)
        table = tracker._build_status_table()
        assert table.row_count > 0

    def test_build_status_table_stage_not_in_order(self):
        tracker = self._make_tracker()
        tracker.update_year(2025)
        tracker.update_stage("unknown_stage")
        table = tracker._build_status_table()
        assert table.row_count > 0

    def test_add_estimated_remaining_no_data(self):
        from rich.table import Table

        tracker = self._make_tracker()
        table = Table()
        table.add_column("Metric")
        table.add_column("Value")
        tracker._add_estimated_remaining(table)
        assert table.row_count == 0

    def test_add_estimated_remaining_with_data(self):
        from rich.table import Table

        tracker = self._make_tracker()
        tracker.years_completed = 1
        tracker.stage_durations = {"2025_init": 10.0, "2025_foundation": 20.0}
        table = Table()
        table.add_column("Metric")
        table.add_column("Value")
        tracker._add_estimated_remaining(table)
        assert table.row_count == 1

    def test_add_estimated_remaining_over_60s(self):
        from rich.table import Table

        tracker = self._make_tracker()
        tracker.years_completed = 1
        tracker.stage_durations = {"2025_init": 60.0, "2025_foundation": 60.0}
        table = Table()
        table.add_column("Metric")
        table.add_column("Value")
        tracker._add_estimated_remaining(table)
        assert table.row_count == 1

    def test_add_estimated_remaining_all_complete(self):
        from rich.table import Table

        tracker = self._make_tracker()
        tracker.years_completed = 3  # All done
        tracker.stage_durations = {"2025_init": 10.0}
        table = Table()
        table.add_column("Metric")
        table.add_column("Value")
        tracker._add_estimated_remaining(table)
        assert table.row_count == 0

    def test_get_status_table(self):
        tracker = self._make_tracker()
        tracker.update_year(2025)
        tracker.update_stage("initialization")
        tracker.update_events(3000)
        table = tracker.get_status_table()
        assert table.row_count > 0

    def test_get_status_table_no_events(self):
        tracker = self._make_tracker()
        table = tracker.get_status_table()
        # Should still have years_completed row
        assert table.row_count >= 1

    def test_update_year_with_progress(self):
        """update_year with progress bars set updates the task."""
        tracker = self._make_tracker()
        tracker.progress = MagicMock()
        tracker.year_task = 0
        tracker.update_year(2025)
        tracker.progress.update.assert_called_once()

    def test_update_stage_with_progress(self):
        """update_stage with progress bars set updates the task."""
        tracker = self._make_tracker()
        tracker.progress = MagicMock()
        tracker.stage_task = 1
        tracker.update_stage("foundation")
        tracker.progress.update.assert_called_once()

    def test_year_validation_with_progress(self):
        """year_validation with progress bars updates completed count."""
        tracker = self._make_tracker()
        tracker.progress = MagicMock()
        tracker.year_task = 0
        tracker.update_year(2025)
        tracker.year_validation(2025)
        # Should have called update for the year_task
        assert tracker.progress.update.call_count >= 1


# =============================================================================
# _show_simulation_summary / _show_enhanced_simulation_summary
# =============================================================================


@pytest.mark.fast
class TestShowSimulationSummary:
    @patch("planalign_cli.commands.simulate.console")
    def test_basic_summary(self, mock_console):
        summary = MagicMock(spec=[])
        _show_simulation_summary(summary, 2025, 2027, verbose=False)
        assert mock_console.print.call_count >= 1

    @patch("planalign_cli.commands.simulate.console")
    def test_summary_with_total_events(self, mock_console):
        summary = MagicMock()
        summary.total_events = 15000
        del summary.summary
        del summary.performance_metrics
        del summary.growth_analysis
        _show_simulation_summary(summary, 2025, 2027, verbose=False)
        assert mock_console.print.call_count >= 1

    @patch("planalign_cli.commands.simulate.console")
    def test_summary_with_nested_total_events(self, mock_console):
        summary = MagicMock()
        del summary.total_events
        summary.summary.total_events = 10000
        del summary.performance_metrics
        del summary.growth_analysis
        _show_simulation_summary(summary, 2025, 2027, verbose=False)
        assert mock_console.print.call_count >= 1

    @patch("planalign_cli.commands.simulate.console")
    def test_summary_verbose_with_growth(self, mock_console):
        summary = MagicMock()
        summary.total_events = 5000
        summary.growth_analysis = "+200 employees"
        summary.performance_metrics = {"total_duration": "120s", "peak_memory": "256MB"}
        _show_simulation_summary(summary, 2025, 2026, verbose=True)
        # Verbose mode prints additional details
        assert mock_console.print.call_count >= 3

    @patch("planalign_cli.commands.simulate.console")
    def test_enhanced_summary_basic(self, mock_console):
        summary = MagicMock(spec=[])
        _show_enhanced_simulation_summary(summary, 2025, 2027, verbose=False)
        assert mock_console.print.call_count >= 1

    @patch("planalign_cli.commands.simulate.console")
    def test_enhanced_summary_high_events(self, mock_console):
        summary = MagicMock()
        summary.total_events = 20000
        del summary.performance_metrics
        del summary.growth_analysis
        _show_enhanced_simulation_summary(summary, 2025, 2027, verbose=False)
        assert mock_console.print.call_count >= 1

    @patch("planalign_cli.commands.simulate.console")
    def test_enhanced_summary_low_events(self, mock_console):
        summary = MagicMock()
        summary.total_events = 500
        del summary.performance_metrics
        del summary.growth_analysis
        _show_enhanced_simulation_summary(summary, 2025, 2027, verbose=False)
        assert mock_console.print.call_count >= 1

    @patch("planalign_cli.commands.simulate.console")
    def test_enhanced_summary_with_metrics(self, mock_console):
        summary = MagicMock()
        summary.total_events = 10000
        summary.performance_metrics = {"total_duration": "90s"}
        summary.growth_analysis = "+150 employees"
        _show_enhanced_simulation_summary(summary, 2025, 2027, verbose=False)
        assert mock_console.print.call_count >= 1
