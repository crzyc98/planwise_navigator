"""
Tests for _ProgressMonitor class and module-level regex patterns
in planalign_cli/integration/orchestrator_wrapper.py.
"""

from __future__ import annotations

import io

import pytest
from unittest.mock import MagicMock, call

from planalign_cli.integration.orchestrator_wrapper import (
    _MAX_LINE_LENGTH,
    _YEAR_PATTERN,
    _STAGE_PATTERN,
    _EVENT_PATTERN,
    _COMPLETED_STAGE_PATTERN,
    _FOUNDATION_VALIDATION_PATTERN,
    _ProgressMonitor,
)


# ---------------------------------------------------------------------------
# Regex pattern tests
# ---------------------------------------------------------------------------


@pytest.mark.fast
class TestYearPattern:
    """Tests for _YEAR_PATTERN regex."""

    def test_matches_year_line(self):
        match = _YEAR_PATTERN.search("\U0001f504 Starting simulation year 2025")
        assert match is not None
        assert match.group(1) == "2025"

    def test_matches_year_with_surrounding_text(self):
        match = _YEAR_PATTERN.search("INFO \U0001f504 Starting simulation year 2027 ...")
        assert match is not None
        assert match.group(1) == "2027"

    def test_no_match_without_emoji(self):
        assert _YEAR_PATTERN.search("Starting simulation year 2025") is None

    def test_no_match_on_unrelated_line(self):
        assert _YEAR_PATTERN.search("Running dbt build") is None


@pytest.mark.fast
class TestStagePattern:
    """Tests for _STAGE_PATTERN regex."""

    def test_matches_stage_line(self):
        match = _STAGE_PATTERN.search("\U0001f4cb Starting initialization")
        assert match is not None
        assert match.group(1) == "initialization"

    def test_matches_event_generation(self):
        match = _STAGE_PATTERN.search("\U0001f4cb Starting event_generation")
        assert match is not None
        assert match.group(1) == "event_generation"

    def test_no_match_without_emoji(self):
        assert _STAGE_PATTERN.search("Starting initialization") is None

    def test_no_match_on_unrelated_line(self):
        assert _STAGE_PATTERN.search("dbt run complete") is None


@pytest.mark.fast
class TestEventPattern:
    """Tests for _EVENT_PATTERN regex."""

    def test_matches_simple_count(self):
        match = _EVENT_PATTERN.search("\U0001f4ca Generated 500 events")
        assert match is not None
        assert match.group(1) == "500"

    def test_matches_comma_separated_count(self):
        match = _EVENT_PATTERN.search("\U0001f4ca Generated 1,234 events")
        assert match is not None
        assert match.group(1) == "1,234"

    def test_matches_large_comma_count(self):
        match = _EVENT_PATTERN.search("\U0001f4ca Generated 1,234,567 events")
        assert match is not None
        assert match.group(1) == "1,234,567"

    def test_no_match_without_emoji(self):
        assert _EVENT_PATTERN.search("Generated 500 events") is None

    def test_no_match_on_unrelated_line(self):
        assert _EVENT_PATTERN.search("Processing events...") is None


@pytest.mark.fast
class TestCompletedStagePattern:
    """Tests for _COMPLETED_STAGE_PATTERN regex."""

    def test_matches_completed_line(self):
        match = _COMPLETED_STAGE_PATTERN.search("\u2705 Completed initialization in 5.20s")
        assert match is not None
        assert match.group(1) == "initialization"
        assert match.group(2) == "5.20"

    def test_matches_long_duration(self):
        match = _COMPLETED_STAGE_PATTERN.search("\u2705 Completed event_generation in 123.45s")
        assert match is not None
        assert match.group(1) == "event_generation"
        assert match.group(2) == "123.45"

    def test_no_match_without_emoji(self):
        assert _COMPLETED_STAGE_PATTERN.search("Completed initialization in 5.20s") is None

    def test_no_match_on_unrelated_line(self):
        assert _COMPLETED_STAGE_PATTERN.search("step finished") is None


@pytest.mark.fast
class TestFoundationValidationPattern:
    """Tests for _FOUNDATION_VALIDATION_PATTERN regex."""

    def test_matches_validation_line(self):
        match = _FOUNDATION_VALIDATION_PATTERN.search(
            "\U0001f4ca Foundation model validation for year 2025:"
        )
        assert match is not None
        assert match.group(1) == "2025"

    def test_no_match_without_emoji(self):
        assert _FOUNDATION_VALIDATION_PATTERN.search(
            "Foundation model validation for year 2025:"
        ) is None

    def test_no_match_on_unrelated_line(self):
        assert _FOUNDATION_VALIDATION_PATTERN.search("validation passed") is None


# ---------------------------------------------------------------------------
# _ProgressMonitor tests
# ---------------------------------------------------------------------------


def _make_monitor(callback=None, stdout=None):
    """Create a _ProgressMonitor with sensible defaults for testing."""
    if callback is None:
        callback = MagicMock()
    if stdout is None:
        stdout = MagicMock()
    return _ProgressMonitor(callback, stdout), callback, stdout


@pytest.mark.fast
class TestProgressMonitorWrite:
    """Tests for _ProgressMonitor.write() buffering and line splitting."""

    def test_buffers_incomplete_line(self):
        monitor, cb, _ = _make_monitor()
        monitor.write("partial text")
        assert monitor.buffer == "partial text"
        # No complete line, so no callback dispatching
        cb.update_year.assert_not_called()

    def test_processes_complete_line(self):
        monitor, cb, _ = _make_monitor()
        monitor.write("\U0001f504 Starting simulation year 2025\n")
        cb.update_year.assert_called_once_with(2025)

    def test_processes_multiple_lines_in_one_write(self):
        monitor, cb, _ = _make_monitor()
        monitor.write(
            "\U0001f4cb Starting initialization\n"
            "\U0001f4cb Starting foundation\n"
        )
        assert cb.update_stage.call_count == 2
        cb.update_stage.assert_any_call("initialization")
        cb.update_stage.assert_any_call("foundation")

    def test_buffers_across_writes(self):
        monitor, cb, _ = _make_monitor()
        monitor.write("\U0001f504 Starting simulation")
        cb.update_year.assert_not_called()
        monitor.write(" year 2026\n")
        cb.update_year.assert_called_once_with(2026)

    def test_calls_on_dbt_line_when_present(self):
        cb = MagicMock()
        monitor, _, _ = _make_monitor(callback=cb)
        monitor.write("some dbt output\n")
        cb.on_dbt_line.assert_called_once_with("some dbt output")

    def test_skips_on_dbt_line_when_absent(self):
        cb = MagicMock(spec=[])  # no attributes
        monitor, _, _ = _make_monitor(callback=cb)
        # Should not raise even though callback lacks on_dbt_line
        monitor.write("some output\n")

    def test_flushes_original_stdout_on_write(self):
        monitor, _, stdout = _make_monitor()
        monitor.write("text\n")
        stdout.flush.assert_called()


@pytest.mark.fast
class TestProgressMonitorProcessLine:
    """Tests for _process_line dispatching to individual check methods."""

    def test_year_detection(self):
        monitor, cb, _ = _make_monitor()
        monitor._process_line("\U0001f504 Starting simulation year 2025")
        cb.update_year.assert_called_once_with(2025)
        assert monitor.current_year == 2025

    def test_stage_detection(self):
        monitor, cb, _ = _make_monitor()
        monitor._process_line("\U0001f4cb Starting event_generation")
        cb.update_stage.assert_called_once_with("event_generation")

    def test_event_count_detection_simple(self):
        monitor, cb, _ = _make_monitor()
        monitor._process_line("\U0001f4ca Generated 42 events")
        cb.update_events.assert_called_once_with(42)

    def test_event_count_detection_comma_separated(self):
        monitor, cb, _ = _make_monitor()
        monitor._process_line("\U0001f4ca Generated 1,500 events")
        cb.update_events.assert_called_once_with(1500)

    def test_completed_stage_detection(self):
        monitor, cb, _ = _make_monitor()
        monitor._process_line("\u2705 Completed initialization in 3.50s")
        cb.stage_completed.assert_called_once_with("initialization", 3.5)

    def test_foundation_validation_detection(self):
        monitor, cb, _ = _make_monitor()
        monitor._process_line(
            "\U0001f4ca Foundation model validation for year 2026:"
        )
        cb.year_validation.assert_called_once_with(2026)

    def test_unrelated_line_triggers_no_callbacks(self):
        monitor, cb, _ = _make_monitor()
        monitor._process_line("dbt run complete, no errors found")
        cb.update_year.assert_not_called()
        cb.update_stage.assert_not_called()
        cb.update_events.assert_not_called()
        cb.stage_completed.assert_not_called()
        cb.year_validation.assert_not_called()


@pytest.mark.fast
class TestProgressMonitorCheckMethods:
    """Tests for individual _check_* methods and their hasattr guards."""

    def test_check_year_skips_when_callback_lacks_method(self):
        cb = MagicMock(spec=[])  # no attributes at all
        monitor, _, _ = _make_monitor(callback=cb)
        # Should not raise
        monitor._check_year("\U0001f504 Starting simulation year 2025")
        assert monitor.current_year == 2025  # still sets internal state

    def test_check_stage_skips_when_callback_lacks_method(self):
        cb = MagicMock(spec=[])
        monitor, _, _ = _make_monitor(callback=cb)
        monitor._check_stage("\U0001f4cb Starting initialization")
        # No error raised

    def test_check_events_skips_when_callback_lacks_method(self):
        cb = MagicMock(spec=[])
        monitor, _, _ = _make_monitor(callback=cb)
        monitor._check_events("\U0001f4ca Generated 100 events")
        # No error raised

    def test_check_completed_stage_skips_when_callback_lacks_method(self):
        cb = MagicMock(spec=[])
        monitor, _, _ = _make_monitor(callback=cb)
        monitor._check_completed_stage("\u2705 Completed initialization in 1.00s")
        # No error raised

    def test_check_foundation_validation_skips_when_callback_lacks_method(self):
        cb = MagicMock(spec=[])
        monitor, _, _ = _make_monitor(callback=cb)
        monitor._check_foundation_validation(
            "\U0001f4ca Foundation model validation for year 2025:"
        )
        # No error raised


@pytest.mark.fast
class TestProgressMonitorLineTruncation:
    """Tests for _MAX_LINE_LENGTH truncation."""

    def test_max_line_length_constant(self):
        assert _MAX_LINE_LENGTH == 1000

    def test_long_line_is_truncated_before_matching(self):
        """Lines exceeding _MAX_LINE_LENGTH are truncated in _process_line."""
        # Build a line with the year pattern buried past the limit
        padding = "x" * (_MAX_LINE_LENGTH + 10)
        line = padding + "\U0001f504 Starting simulation year 2025"
        monitor, cb, _ = _make_monitor()
        monitor._process_line(line)
        # Pattern is beyond truncation point, so no match
        cb.update_year.assert_not_called()

    def test_line_within_limit_matches_normally(self):
        line = "\U0001f504 Starting simulation year 2025"
        assert len(line) < _MAX_LINE_LENGTH
        monitor, cb, _ = _make_monitor()
        monitor._process_line(line)
        cb.update_year.assert_called_once_with(2025)


@pytest.mark.fast
class TestProgressMonitorReentrancy:
    """Tests for the _writing re-entrancy guard."""

    def test_reentrant_write_goes_to_original_stdout(self):
        """When _writing is True, write() delegates directly to original_stdout."""
        stdout = MagicMock()
        monitor, _, _ = _make_monitor(stdout=stdout)

        # Simulate re-entrancy: set _writing=True before calling write
        monitor._writing = True
        monitor.write("re-entrant text")
        stdout.write.assert_called_once_with("re-entrant text")

    def test_writing_flag_reset_after_normal_write(self):
        monitor, _, _ = _make_monitor()
        monitor.write("text\n")
        assert monitor._writing is False

    def test_writing_flag_reset_after_exception(self):
        """_writing is reset even if processing raises an exception."""
        cb = MagicMock()
        cb.update_year.side_effect = RuntimeError("boom")
        monitor, _, _ = _make_monitor(callback=cb)
        # Should not propagate the exception from _process_line?
        # Actually write() doesn't catch exceptions from _process_line,
        # so we expect the error to propagate but _writing to be reset.
        with pytest.raises(RuntimeError, match="boom"):
            monitor.write("\U0001f504 Starting simulation year 2025\n")
        assert monitor._writing is False


@pytest.mark.fast
class TestProgressMonitorFlush:
    """Tests for _ProgressMonitor.flush()."""

    def test_flush_delegates_to_original_stdout(self):
        stdout = MagicMock()
        monitor, _, _ = _make_monitor(stdout=stdout)
        monitor.flush()
        stdout.flush.assert_called_once()
