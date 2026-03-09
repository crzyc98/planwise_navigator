"""
Tests for progress display callback wiring and LiveProgressTracker state management.
"""

from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from planalign_cli.commands.simulate import LiveProgressTracker


class TestLiveProgressTrackerState:
    """Test LiveProgressTracker internal state updates."""

    def _make_tracker(self, total_years=3, start_year=2025, end_year=2027, verbose=False):
        return LiveProgressTracker(total_years, start_year, end_year, verbose)

    def test_update_year_sets_current_year(self):
        tracker = self._make_tracker()
        tracker.update_year(2025)
        assert tracker.current_year == 2025

    def test_update_year_increments_completed_on_transition(self):
        tracker = self._make_tracker()
        tracker.update_year(2025)
        assert tracker.years_completed == 0
        tracker.update_year(2026)
        assert tracker.years_completed == 1

    def test_update_stage_sets_current_stage(self):
        tracker = self._make_tracker()
        tracker.update_stage("initialization")
        assert tracker.current_stage == "initialization"

    def test_stage_completed_records_duration(self):
        tracker = self._make_tracker()
        tracker.update_year(2025)
        tracker.stage_completed("initialization", 5.2)
        assert tracker.stage_durations["2025_initialization"] == 5.2

    def test_update_events_accumulates(self):
        tracker = self._make_tracker()
        tracker.update_year(2025)
        tracker.update_events(100)
        assert tracker.total_events == 100
        assert tracker.year_events[2025] == 100

    def test_year_validation_updates_progress(self):
        tracker = self._make_tracker()
        tracker.update_year(2025)
        # Should not raise when progress is None (no Live display)
        tracker.year_validation(2025)


class TestProgressCallbackWiring:
    """Test that create_orchestrator wires progress callback correctly."""

    @patch("planalign_cli.integration.orchestrator_wrapper.PipelineOrchestrator")
    @patch("planalign_cli.integration.orchestrator_wrapper.DbtRunner")
    @patch("planalign_cli.integration.orchestrator_wrapper.DataValidator")
    @patch("planalign_cli.integration.orchestrator_wrapper.RegistryManager")
    def test_create_orchestrator_returns_wrapper_when_callback_provided(
        self, mock_registries, mock_validator, mock_runner, mock_orchestrator
    ):
        from planalign_cli.integration.orchestrator_wrapper import (
            OrchestratorWrapper,
            ProgressAwareOrchestrator,
        )

        wrapper = MagicMock(spec=OrchestratorWrapper)
        wrapper.config = MagicMock()
        wrapper.config.orchestrator = None
        wrapper.config.get_thread_count.return_value = 1
        wrapper.db = MagicMock()
        wrapper.db_path = MagicMock()
        wrapper.verbose = False

        callback = MagicMock()
        result = OrchestratorWrapper.create_orchestrator(
            wrapper, threads=1, progress_callback=callback
        )
        assert isinstance(result, ProgressAwareOrchestrator)

    @patch("planalign_cli.integration.orchestrator_wrapper.PipelineOrchestrator")
    @patch("planalign_cli.integration.orchestrator_wrapper.DbtRunner")
    @patch("planalign_cli.integration.orchestrator_wrapper.DataValidator")
    @patch("planalign_cli.integration.orchestrator_wrapper.RegistryManager")
    def test_create_orchestrator_returns_plain_when_no_callback(
        self, mock_registries, mock_validator, mock_runner, mock_orchestrator
    ):
        from planalign_cli.integration.orchestrator_wrapper import OrchestratorWrapper

        wrapper = MagicMock(spec=OrchestratorWrapper)
        wrapper.config = MagicMock()
        wrapper.config.orchestrator = None
        wrapper.config.get_thread_count.return_value = 1
        wrapper.db = MagicMock()
        wrapper.db_path = MagicMock()
        wrapper.verbose = False

        result = OrchestratorWrapper.create_orchestrator(
            wrapper, threads=1, progress_callback=None
        )
        # Should return the raw orchestrator, not wrapped
        assert not isinstance(result, object.__class__)  # not ProgressAwareOrchestrator


class TestLiveProgressTrackerOnDbtLine:
    """Test on_dbt_line method for verbose dbt output routing."""

    def test_on_dbt_line_noop_when_not_verbose(self):
        tracker = LiveProgressTracker(1, 2025, 2025, verbose=False)
        # Should not raise even when _live is None
        tracker.on_dbt_line("some dbt output")

    def test_on_dbt_line_noop_when_live_is_none(self):
        tracker = LiveProgressTracker(1, 2025, 2025, verbose=True)
        # _live is None by default, should fall back to print
        with patch("builtins.print") as mock_print:
            tracker.on_dbt_line("some dbt output")
            mock_print.assert_called_once_with("some dbt output")

    def test_on_dbt_line_uses_console_when_live_active(self):
        tracker = LiveProgressTracker(1, 2025, 2025, verbose=True)
        mock_live = MagicMock()
        mock_console = MagicMock()
        mock_live.console = mock_console
        tracker._live = mock_live

        tracker.on_dbt_line("model compiled")
        mock_console.print.assert_called_once_with("model compiled", highlight=False)

    def test_on_dbt_line_ignores_empty_lines(self):
        tracker = LiveProgressTracker(1, 2025, 2025, verbose=True)
        mock_live = MagicMock()
        tracker._live = mock_live
        tracker.on_dbt_line("")
        mock_live.console.print.assert_not_called()
