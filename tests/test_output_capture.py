"""
Tests for output capture mechanism and TTY detection.
"""

from __future__ import annotations

import io
import sys
from unittest.mock import MagicMock, patch

import pytest
from rich.console import Console

from planalign_cli.ui.output_capture import (
    OutputCapture,
    PlainTextProgressFallback,
    is_tty,
)


class TestOutputCapture:
    """Test OutputCapture routes lines through Console.print()."""

    def test_capture_line_calls_console_print(self):
        mock_console = MagicMock(spec=Console)
        capture = OutputCapture(mock_console)
        capture.capture_line("test output line")
        mock_console.print.assert_called_once_with("test output line", highlight=False)

    def test_capture_line_ignores_empty_lines(self):
        mock_console = MagicMock(spec=Console)
        capture = OutputCapture(mock_console)
        capture.capture_line("")
        mock_console.print.assert_not_called()

    def test_capture_line_ignores_whitespace_only(self):
        mock_console = MagicMock(spec=Console)
        capture = OutputCapture(mock_console)
        capture.capture_line("   ")
        mock_console.print.assert_not_called()

    def test_capture_line_renders_during_live_context(self):
        """Test that capture_line works with a real Console writing to StringIO."""
        output = io.StringIO()
        real_console = Console(file=output, force_terminal=True)
        capture = OutputCapture(real_console)
        capture.capture_line("dbt model output")
        rendered = output.getvalue()
        assert "dbt model output" in rendered


class TestPlainTextProgressFallback:
    """Test PlainTextProgressFallback emits plain text."""

    def _make_fallback(self, verbose=False):
        return PlainTextProgressFallback(3, 2025, 2027, verbose=verbose)

    def test_update_year_prints(self, capsys):
        fb = self._make_fallback()
        fb.update_year(2025)
        captured = capsys.readouterr()
        assert "Starting year 2025" in captured.out

    def test_update_stage_prints(self, capsys):
        fb = self._make_fallback()
        fb.update_stage("event_generation")
        captured = capsys.readouterr()
        assert "Event Generation" in captured.out

    def test_stage_completed_prints(self, capsys):
        fb = self._make_fallback()
        fb.stage_completed("initialization", 3.5)
        captured = capsys.readouterr()
        assert "Completed Initialization in 3.5s" in captured.out

    def test_update_events_prints(self, capsys):
        fb = self._make_fallback()
        fb.update_events(5000)
        captured = capsys.readouterr()
        assert "5,000" in captured.out

    def test_year_validation_prints(self, capsys):
        fb = self._make_fallback()
        fb.year_validation(2025)
        captured = capsys.readouterr()
        assert "Year 2025 validation complete" in captured.out

    def test_on_dbt_line_verbose(self, capsys):
        fb = self._make_fallback(verbose=True)
        fb.on_dbt_line("model compiled")
        captured = capsys.readouterr()
        assert "[dbt] model compiled" in captured.out

    def test_on_dbt_line_not_verbose(self, capsys):
        fb = self._make_fallback(verbose=False)
        fb.on_dbt_line("model compiled")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_years_completed_tracks(self):
        fb = self._make_fallback()
        fb.update_year(2025)
        fb.update_year(2026)
        assert fb.years_completed == 1


class TestIsTty:
    """Test TTY detection."""

    def test_returns_false_when_not_tty(self):
        with patch.object(sys, 'stdout', new=io.StringIO()):
            assert is_tty() is False

    @patch("sys.stdout")
    @patch("os.name", "posix")
    def test_returns_true_on_posix_tty(self, mock_stdout):
        mock_stdout.isatty.return_value = True
        assert is_tty() is True

    @patch("sys.stdout")
    @patch("os.name", "nt")
    def test_returns_true_on_windows_with_wt_session(self, mock_stdout):
        mock_stdout.isatty.return_value = True
        with patch.dict("os.environ", {"WT_SESSION": "some-guid"}, clear=False):
            assert is_tty() is True

    @patch("os.name", "nt")
    def test_falls_back_to_rich_on_windows_without_term(self):
        with patch.object(sys.stdout, 'isatty', return_value=True):
            with patch.dict("os.environ", {}, clear=True):
                with patch("planalign_cli.ui.output_capture.Console") as mock_console_cls:
                    mock_console_cls.return_value.is_terminal = False
                    result = is_tty()
                    assert result is False
