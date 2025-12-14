"""
Unit tests for YearDependencyError formatting.

Tests error message generation and attributes.
These tests should run fast (<1s).
"""

from __future__ import annotations

import pytest

from planalign_orchestrator.exceptions import YearDependencyError


class TestYearDependencyErrorCreation:
    """Tests for YearDependencyError instantiation."""

    def test_error_attributes(self):
        """Test that error has correct attributes."""
        error = YearDependencyError(
            year=2027,
            missing_tables={"int_enrollment_state_accumulator": 0},
            start_year=2025,
        )

        assert error.year == 2027
        assert error.missing_tables == {"int_enrollment_state_accumulator": 0}
        assert error.start_year == 2025

    def test_error_is_exception(self):
        """Test that YearDependencyError is an Exception."""
        error = YearDependencyError(
            year=2027,
            missing_tables={},
            start_year=2025,
        )

        assert isinstance(error, Exception)
        with pytest.raises(YearDependencyError):
            raise error


class TestYearDependencyErrorMessage:
    """Tests for error message formatting."""

    def test_message_contains_year(self):
        """Test that error message contains the failed year."""
        error = YearDependencyError(
            year=2027,
            missing_tables={"int_enrollment_state_accumulator": 0},
            start_year=2025,
        )

        assert "2027" in error.message
        assert "2026" in error.message  # Prior year

    def test_message_contains_missing_tables(self):
        """Test that error message lists missing tables."""
        error = YearDependencyError(
            year=2026,
            missing_tables={
                "int_enrollment_state_accumulator": 0,
                "int_deferral_rate_state_accumulator": 0,
            },
            start_year=2025,
        )

        assert "int_enrollment_state_accumulator" in error.message
        assert "int_deferral_rate_state_accumulator" in error.message

    def test_message_contains_sequence_hint(self):
        """Test that error message contains year sequence hint."""
        error = YearDependencyError(
            year=2027,
            missing_tables={"int_enrollment_state_accumulator": 0},
            start_year=2025,
        )

        # Should suggest running 2025 -> 2026 -> 2027
        assert "2025" in error.message
        assert "2026" in error.message
        assert "2027" in error.message
        assert "Resolution" in error.message

    def test_message_contains_prior_year_info(self):
        """Test that error message mentions prior year."""
        error = YearDependencyError(
            year=2027,
            missing_tables={"int_enrollment_state_accumulator": 0},
            start_year=2025,
        )

        # Should mention that year 2027 depends on 2026
        assert "depends on year 2026" in error.message

    def test_message_format_with_single_table(self):
        """Test message format with single missing table."""
        error = YearDependencyError(
            year=2026,
            missing_tables={"int_test_accumulator": 0},
            start_year=2025,
        )

        assert "int_test_accumulator" in error.message
        assert "0 rows for year 2025" in error.message

    def test_message_format_with_multiple_tables(self):
        """Test message format with multiple missing tables."""
        error = YearDependencyError(
            year=2026,
            missing_tables={
                "int_table_a": 0,
                "int_table_b": 0,
                "int_table_c": 0,
            },
            start_year=2025,
        )

        # All tables should be listed
        assert "int_table_a" in error.message
        assert "int_table_b" in error.message
        assert "int_table_c" in error.message


class TestYearDependencyErrorResolutionHints:
    """Tests for resolution hints."""

    def test_has_resolution_hints(self):
        """Test that error has resolution hints."""
        error = YearDependencyError(
            year=2027,
            missing_tables={"int_test": 0},
            start_year=2025,
        )

        assert len(error.resolution_hints) > 0

    def test_resolution_hint_has_title(self):
        """Test that resolution hint has a title."""
        error = YearDependencyError(
            year=2027,
            missing_tables={"int_test": 0},
            start_year=2025,
        )

        hint = error.resolution_hints[0]
        assert hint.title
        assert len(hint.title) > 0

    def test_resolution_hint_has_steps(self):
        """Test that resolution hint has actionable steps."""
        error = YearDependencyError(
            year=2027,
            missing_tables={"int_test": 0},
            start_year=2025,
        )

        hint = error.resolution_hints[0]
        assert len(hint.steps) > 0


class TestYearDependencyErrorSequenceCalculation:
    """Tests for year sequence calculation in error messages."""

    def test_short_sequence(self):
        """Test sequence for short year range."""
        error = YearDependencyError(
            year=2026,
            missing_tables={"int_test": 0},
            start_year=2025,
        )

        # Should contain "2025 -> 2026"
        assert "2025" in error.message
        assert "2026" in error.message

    def test_long_sequence(self):
        """Test sequence for longer year range."""
        error = YearDependencyError(
            year=2029,
            missing_tables={"int_test": 0},
            start_year=2025,
        )

        # Should contain full sequence
        assert "2025" in error.message
        assert "2029" in error.message

    def test_sequence_uses_arrow_separator(self):
        """Test that sequence uses arrow separator."""
        error = YearDependencyError(
            year=2027,
            missing_tables={"int_test": 0},
            start_year=2025,
        )

        # Should use -> separator
        assert "->" in error.message
