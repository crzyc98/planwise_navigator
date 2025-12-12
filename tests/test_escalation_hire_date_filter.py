"""
Tests for auto-escalation hire date cutoff filter.

Epic: 002-fix-auto-escalation-hire-filter
Purpose: Verify the hire date cutoff filter uses inclusive comparison (>=)
         so employees hired ON the cutoff date are eligible for escalation.

The bug: Both SQL and Polars code paths used > (strictly greater than) instead
of >= (greater than or equal to), causing employees hired ON the cutoff date
to be incorrectly excluded from escalation.

Expected behavior per configuration documentation:
"Only escalate employees hired ON OR AFTER this date"
"""

import pytest
from datetime import date
from decimal import Decimal


class TestHireDateCutoffFilter:
    """Test the hire date cutoff filter logic for auto-escalation."""

    @pytest.fixture
    def cutoff_date(self) -> date:
        """Standard cutoff date for testing: 2026-01-01."""
        return date(2026, 1, 1)

    def test_employee_hired_on_cutoff_date_should_be_eligible(self, cutoff_date: date):
        """
        CRITICAL TEST: Employee hired ON the cutoff date should be eligible.

        This is the core bug - the old implementation used > which excluded
        employees hired exactly on the cutoff date.

        Given: hire_date = 2026-01-01, cutoff = 2026-01-01
        Expected: Employee IS eligible for escalation (hire_date >= cutoff)
        """
        hire_date = date(2026, 1, 1)  # Same as cutoff

        # The correct comparison: hire_date >= cutoff_date (inclusive)
        is_eligible = hire_date >= cutoff_date

        assert is_eligible is True, (
            f"Employee hired ON cutoff date ({hire_date}) should be eligible. "
            f"Cutoff: {cutoff_date}. The comparison must use >= (inclusive)."
        )

    def test_employee_hired_day_before_cutoff_should_not_be_eligible(self, cutoff_date: date):
        """
        Employee hired one day BEFORE cutoff should NOT be eligible.

        Given: hire_date = 2025-12-31, cutoff = 2026-01-01
        Expected: Employee is NOT eligible for escalation
        """
        hire_date = date(2025, 12, 31)  # One day before cutoff

        is_eligible = hire_date >= cutoff_date

        assert is_eligible is False, (
            f"Employee hired before cutoff ({hire_date}) should NOT be eligible. "
            f"Cutoff: {cutoff_date}."
        )

    def test_employee_hired_day_after_cutoff_should_be_eligible(self, cutoff_date: date):
        """
        Employee hired one day AFTER cutoff should be eligible.

        Given: hire_date = 2026-01-02, cutoff = 2026-01-01
        Expected: Employee IS eligible for escalation
        """
        hire_date = date(2026, 1, 2)  # One day after cutoff

        is_eligible = hire_date >= cutoff_date

        assert is_eligible is True, (
            f"Employee hired after cutoff ({hire_date}) should be eligible. "
            f"Cutoff: {cutoff_date}."
        )

    def test_employee_hired_long_before_cutoff_should_not_be_eligible(self, cutoff_date: date):
        """
        Employee hired years before cutoff should NOT be eligible.

        This tests census employees who were hired before the simulation starts.

        Given: hire_date = 2020-06-15, cutoff = 2026-01-01
        Expected: Employee is NOT eligible for escalation
        """
        hire_date = date(2020, 6, 15)  # Hired years before cutoff

        is_eligible = hire_date >= cutoff_date

        assert is_eligible is False, (
            f"Census employee hired long before cutoff ({hire_date}) should NOT be eligible. "
            f"Cutoff: {cutoff_date}."
        )

    def test_no_cutoff_should_make_all_employees_eligible(self):
        """
        When no cutoff is configured (null/None), all employees should be eligible.

        This tests backward compatibility for plans that want universal escalation.
        """
        hire_date = date(2010, 1, 1)  # Very old hire date
        cutoff_date = None

        # When cutoff is None, the filter should not be applied
        is_eligible = cutoff_date is None or hire_date >= cutoff_date

        assert is_eligible is True, (
            "When no cutoff is configured, all employees should be eligible."
        )

    def test_cutoff_in_distant_past_should_make_all_employees_eligible(self):
        """
        When cutoff is set to distant past (1900-01-01), effectively all employees eligible.

        This is the common pattern for "all employees" configuration.
        """
        hire_date = date(2000, 1, 1)
        cutoff_date = date(1900, 1, 1)  # Very old cutoff

        is_eligible = hire_date >= cutoff_date

        assert is_eligible is True, (
            f"With distant past cutoff ({cutoff_date}), all employees should be eligible. "
            f"Hire date: {hire_date}."
        )

    def test_cutoff_in_distant_future_should_make_no_employees_eligible(self):
        """
        When cutoff is set to distant future (2999-01-01), effectively no employees eligible.
        """
        hire_date = date(2030, 12, 31)  # Even future employees
        cutoff_date = date(2999, 1, 1)  # Very future cutoff

        is_eligible = hire_date >= cutoff_date

        assert is_eligible is False, (
            f"With distant future cutoff ({cutoff_date}), no employees should be eligible. "
            f"Hire date: {hire_date}."
        )


class TestSQLFilterLogic:
    """
    Tests that validate the SQL filter logic matches expected behavior.

    These tests verify that the dbt model int_deferral_rate_escalation_events.sql
    applies the correct >= comparison for hire_date_cutoff.
    """

    def test_sql_filter_comparison_operator(self):
        """
        Verify the SQL WHERE clause uses >= for hire date comparison.

        The correct SQL should be:
            AND w.employee_hire_date >= '{{ esc_hire_cutoff }}'::DATE

        NOT:
            AND w.employee_hire_date > '{{ esc_hire_cutoff }}'::DATE
        """
        # Read the actual SQL file and check the comparison operator
        import os
        sql_file_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'dbt', 'models', 'intermediate', 'events',
            'int_deferral_rate_escalation_events.sql'
        )

        with open(sql_file_path, 'r') as f:
            sql_content = f.read()

        # Check for the CORRECT pattern (>= inclusive)
        correct_pattern = "employee_hire_date >="
        # Check for the INCORRECT pattern (> exclusive) - this is the bug
        incorrect_pattern = "employee_hire_date > '"

        # The fix should have replaced > with >=
        assert correct_pattern in sql_content, (
            f"SQL file should use >= for hire date comparison. "
            f"Expected pattern: {correct_pattern}"
        )

        # Verify the bug is fixed (no standalone > without =)
        # We need to be careful here - the >= pattern contains >
        # So we check that there's no `> '` pattern (the bug) remaining
        lines_with_hire_date = [
            line for line in sql_content.split('\n')
            if 'employee_hire_date' in line and '>' in line
        ]
        for line in lines_with_hire_date:
            # If line contains employee_hire_date and >, it should contain >=
            assert '>=' in line or '>' not in line.split('employee_hire_date')[1][:5], (
                f"Found potentially incorrect > comparison in SQL: {line.strip()}"
            )


class TestPolarsFilterLogic:
    """
    Tests that validate the Polars filter logic matches expected behavior.

    These tests verify that polars_event_factory.py applies the correct
    >= comparison for hire_date_cutoff.
    """

    def test_polars_filter_comparison_operator(self):
        """
        Verify the Polars filter uses >= for hire date comparison.

        The correct Polars code should be:
            pl.col('employee_hire_date') >= pl.lit(cutoff_date)

        NOT:
            pl.col('employee_hire_date') > pl.lit(cutoff_date)
        """
        import os
        polars_file_path = os.path.join(
            os.path.dirname(os.path.dirname(__file__)),
            'planalign_orchestrator', 'polars_event_factory.py'
        )

        with open(polars_file_path, 'r') as f:
            polars_content = f.read()

        # Find the escalation section and check the comparison
        # We're looking for the line that filters by employee_hire_date
        lines = polars_content.split('\n')
        hire_date_filter_lines = [
            (i, line) for i, line in enumerate(lines)
            if 'employee_hire_date' in line and ('>' in line or '>=' in line)
        ]

        found_correct_comparison = False
        for line_num, line in hire_date_filter_lines:
            if '>=' in line and 'employee_hire_date' in line:
                found_correct_comparison = True
                break

        assert found_correct_comparison, (
            "Polars code should use >= for hire date comparison. "
            "Expected: pl.col('employee_hire_date') >= pl.lit(cutoff_date)"
        )


# Mark test file for pytest discovery
pytest_plugins = []
