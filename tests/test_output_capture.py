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
    _is_signal_line,
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
        fb.on_dbt_line("12 of 30 OK created")
        captured = capsys.readouterr()
        assert "[dbt] 12 of 30 OK created" in captured.out

    def test_on_dbt_line_not_verbose(self, capsys):
        fb = self._make_fallback(verbose=False)
        fb.on_dbt_line("12 of 30 OK created")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_years_completed_tracks(self):
        fb = self._make_fallback()
        fb.update_year(2025)
        fb.update_year(2026)
        assert fb.years_completed == 1


@pytest.mark.fast
class TestIsSignalLine:
    """Tests for _is_signal_line regex-based filtering."""

    # --- Signal lines that SHOULD be detected ---

    @pytest.mark.parametrize("line", [
        "ERROR: compilation error",
        "  error in model int_foo",
        "WARNING: unused config",
        "warn: deprecated feature",
        "3 of 5 OK created fct_yearly_events",
        "Running with dbt=1.8.8",
        "Finished running 12 table models",
        "Done.",
        "OK created int_baseline_workforce",
        "FAIL 1 stg_census",
        "PASS 42 not_null_employee_id",
    ])
    def test_signal_lines_detected(self, line: str):
        assert _is_signal_line(line) is True

    @pytest.mark.parametrize("line", [
        "ERROR: something",
        "error: something",
        "Error: something",
    ])
    def test_signal_case_insensitive(self, line: str):
        assert _is_signal_line(line) is True

    # --- Noise lines that SHOULD be filtered ---

    @pytest.mark.parametrize("line", [
        "select employee_id, hire_date",
        "  SELECT count(*) FROM employees",
        "from stg_census",
        "  FROM int_baseline_workforce",
        "where simulation_year = 2025",
        "  WHERE employee_id IS NOT NULL",
        "with base AS (",
        "  WITH cte AS (",
        "join int_termination_events",
        "  JOIN stg_census ON ...",
        "group by employee_id",
        "order by hire_date",
        "---",
        "------",
        "=====",
        "=========",
        "[debug] some message",
        "  [debug] another message",
        "Concurrency: 1 thread",
        "registered in project",
    ])
    def test_noise_lines_filtered(self, line: str):
        assert _is_signal_line(line) is False

    # --- The -‐{2,} change: two dashes now match noise ---

    def test_two_dashes_matched_as_noise(self):
        """Two dashes should be filtered as noise after -‐{2,} change."""
        assert _is_signal_line("--") is False

    def test_three_dashes_matched_as_noise(self):
        assert _is_signal_line("---") is False

    def test_single_dash_not_noise(self):
        """A single dash is not noise (doesn't match -{2,}) and not a signal either."""
        assert _is_signal_line("-") is False

    # --- Edge cases ---

    def test_empty_string(self):
        assert _is_signal_line("") is False

    def test_whitespace_only(self):
        assert _is_signal_line("   ") is False

    def test_tab_only(self):
        assert _is_signal_line("\t") is False

    def test_newline_only(self):
        assert _is_signal_line("\n") is False

    def test_plain_text_no_signal(self):
        """A line with no signal keywords is not a signal."""
        assert _is_signal_line("loading seeds") is False

    def test_noise_keyword_with_signal_not_filtered(self):
        """A line starting with a noise keyword but also having a signal
        should still be filtered because noise check runs first."""
        assert _is_signal_line("select error count") is False

    # --- Non-capturing group verification ---
    # These verify that the regex doesn't create unwanted capture groups
    # that could cause match.group() issues in downstream code.

    def test_signal_search_returns_match_without_groups(self):
        """Non-capturing groups should not produce numbered groups."""
        from planalign_cli.ui.output_capture import _SIGNAL_PATTERNS
        m = _SIGNAL_PATTERNS.search("3 of 5 OK")
        assert m is not None
        assert m.groups() == ()

    def test_noise_match_returns_match_without_groups(self):
        """Non-capturing groups should not produce numbered groups."""
        from planalign_cli.ui.output_capture import _NOISE_PATTERNS
        m = _NOISE_PATTERNS.match("select foo")
        assert m is not None
        assert m.groups() == ()


@pytest.mark.fast
class TestPlainTextProgressFallbackDbtLine:
    """Tests for on_dbt_line signal filtering integration."""

    def _make_fallback(self, verbose: bool = True):
        return PlainTextProgressFallback(3, 2025, 2027, verbose=verbose)

    def test_on_dbt_line_prints_signal(self, capsys):
        fb = self._make_fallback(verbose=True)
        fb.on_dbt_line("ERROR: compilation failed")
        captured = capsys.readouterr()
        assert "[dbt] ERROR: compilation failed" in captured.out

    def test_on_dbt_line_filters_noise(self, capsys):
        fb = self._make_fallback(verbose=True)
        fb.on_dbt_line("select employee_id from census")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_on_dbt_line_filters_dashes(self, capsys):
        fb = self._make_fallback(verbose=True)
        fb.on_dbt_line("--")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_on_dbt_line_filters_empty(self, capsys):
        fb = self._make_fallback(verbose=True)
        fb.on_dbt_line("")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_on_dbt_line_not_verbose_skips_signal(self, capsys):
        fb = self._make_fallback(verbose=False)
        fb.on_dbt_line("ERROR: something bad")
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_on_dbt_line_progress_pattern(self, capsys):
        fb = self._make_fallback(verbose=True)
        fb.on_dbt_line("12 of 30 OK created int_foo")
        captured = capsys.readouterr()
        assert "[dbt] 12 of 30 OK created int_foo" in captured.out


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

    @patch("sys.stdout")
    @patch("os.name", "nt")
    def test_returns_true_on_windows_with_term_env(self, mock_stdout):
        """Windows with TERM env var set returns True without Rich fallback."""
        mock_stdout.isatty.return_value = True
        with patch.dict("os.environ", {"TERM": "xterm-256color", "WT_SESSION": ""}, clear=False):
            assert is_tty() is True

    @patch("os.name", "nt")
    def test_rich_console_exception_returns_false(self):
        """Windows Rich Console detection failure returns False."""
        with patch.object(sys.stdout, 'isatty', return_value=True):
            with patch.dict("os.environ", {}, clear=True):
                with patch("planalign_cli.ui.output_capture.Console", side_effect=Exception("boom")):
                    assert is_tty() is False

    def test_update_year_same_year_no_increment(self, capsys):
        """Calling update_year with same year doesn't increment counter."""
        fb = PlainTextProgressFallback(3, 2025, 2027)
        fb.update_year(2025)
        fb.update_year(2025)
        assert fb.years_completed == 0

    def test_update_year_multiple_transitions(self, capsys):
        """Multiple year transitions track completed count correctly."""
        fb = PlainTextProgressFallback(3, 2025, 2027)
        fb.update_year(2025)
        fb.update_year(2026)
        fb.update_year(2027)
        assert fb.years_completed == 2
        captured = capsys.readouterr()
        assert "2/3 completed" in captured.out
