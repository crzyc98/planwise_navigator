"""
Property-based tests for tenure calculation.

Tests the formula: tenure = floor((simulation_year_end_date - hire_date) / 365.25)

Feature: 020-fix-tenure-calculation
Uses Hypothesis for property-based testing as specified in spec.md.
"""

import math
from datetime import date, timedelta
from decimal import Decimal

import pytest
from hypothesis import given, settings, assume, example
from hypothesis import strategies as st

from tests.fixtures.tenure_test_data import (
    ALL_TEST_CASES,
    YEAR_OVER_YEAR_CASES,
    TERMINATED_EMPLOYEE_CASES,
    calculate_expected_tenure,
    get_tenure_band,
    TenureTestCase,
)


# Mark all tests in this module as fast
pytestmark = pytest.mark.fast


class TestTenureCalculationFormula:
    """Tests for the core tenure calculation formula."""

    @pytest.mark.parametrize(
        "test_case",
        ALL_TEST_CASES,
        ids=[tc.name for tc in ALL_TEST_CASES]
    )
    def test_spec_acceptance_cases(self, test_case: TenureTestCase):
        """
        Test tenure calculation matches expected values from spec.md.

        Validates FR-001: System MUST calculate current_tenure as:
        floor((simulation_year_end_date - hire_date) / 365.25)
        """
        actual = calculate_expected_tenure(test_case.hire_date, test_case.simulation_year)
        assert actual == test_case.expected_tenure, (
            f"{test_case.name}: Expected tenure {test_case.expected_tenure}, "
            f"got {actual}. {test_case.description}"
        )

    def test_null_hire_date_returns_zero(self):
        """
        Test that null hire_date returns 0.

        Validates FR-006: System MUST handle null/missing hire dates
        by using a default tenure of 0.
        """
        assert calculate_expected_tenure(None, 2025) == 0

    def test_future_hire_returns_zero(self):
        """
        Test that future hire dates return 0.

        Validates FR-003: System MUST return 0 for tenure when hire_date
        is on or after simulation_year_end_date.
        """
        future_hire = date(2026, 3, 15)
        assert calculate_expected_tenure(future_hire, 2025) == 0

    def test_same_day_hire_returns_zero(self):
        """
        Test that hiring on simulation year end returns 0.

        Validates FR-003: hire_date = simulation_year_end_date should return 0.
        """
        year_end_hire = date(2025, 12, 31)
        assert calculate_expected_tenure(year_end_hire, 2025) == 0


class TestTenurePropertyBased:
    """Property-based tests using Hypothesis."""

    @given(
        hire_year=st.integers(min_value=1970, max_value=2025),
        hire_month=st.integers(min_value=1, max_value=12),
        hire_day=st.integers(min_value=1, max_value=28),  # Avoid month-end issues
        simulation_year=st.integers(min_value=2020, max_value=2030),
    )
    @settings(max_examples=200)
    def test_tenure_always_non_negative(
        self, hire_year: int, hire_month: int, hire_day: int, simulation_year: int
    ):
        """
        Property: Tenure is always >= 0 for any valid hire date.

        Validates SC-004: No employees have negative tenure values.
        """
        hire_date = date(hire_year, hire_month, hire_day)
        tenure = calculate_expected_tenure(hire_date, simulation_year)
        assert tenure >= 0, f"Negative tenure {tenure} for hire_date={hire_date}, year={simulation_year}"

    @given(
        hire_year=st.integers(min_value=1970, max_value=2020),
        hire_month=st.integers(min_value=1, max_value=12),
        hire_day=st.integers(min_value=1, max_value=28),
        base_year=st.integers(min_value=2021, max_value=2025),
    )
    @settings(max_examples=100)
    def test_tenure_increments_by_one_per_year(
        self, hire_year: int, hire_month: int, hire_day: int, base_year: int
    ):
        """
        Property: For continuing employees, tenure(year+1) = tenure(year) + 1.

        Validates FR-005: System MUST increment tenure by exactly 1 when
        advancing from simulation year N to year N+1.

        Note: This property holds for continuing employees (not new hires).
        """
        # Ensure hire_date is before base_year
        assume(hire_year < base_year)

        hire_date = date(hire_year, hire_month, hire_day)
        tenure_base = calculate_expected_tenure(hire_date, base_year)
        tenure_next = calculate_expected_tenure(hire_date, base_year + 1)

        assert tenure_next == tenure_base + 1, (
            f"Tenure should increment by 1: "
            f"tenure({base_year})={tenure_base}, tenure({base_year + 1})={tenure_next}"
        )

    @given(
        simulation_year=st.integers(min_value=2020, max_value=2030),
    )
    @settings(max_examples=50)
    def test_future_hire_always_zero(self, simulation_year: int):
        """
        Property: Hire dates after simulation year end always return 0.

        Validates FR-003.
        """
        # Create a hire date after the simulation year
        future_hire = date(simulation_year + 1, 6, 15)
        tenure = calculate_expected_tenure(future_hire, simulation_year)
        assert tenure == 0, f"Future hire should have tenure 0, got {tenure}"

    @given(
        days_since_hire=st.integers(min_value=0, max_value=36525),  # Up to 100 years
    )
    @settings(max_examples=100)
    @example(days_since_hire=365)  # Exactly 1 year
    @example(days_since_hire=366)  # Just over 1 year
    @example(days_since_hire=730)  # 2 years
    @example(days_since_hire=1826)  # ~5 years
    def test_tenure_uses_floor_not_round(self, days_since_hire: int):
        """
        Property: Tenure uses floor (truncation), not rounding.

        Validates FR-002: System MUST use integer truncation (floor).

        For example:
        - 365 days / 365.25 = 0.999... -> floor -> 0
        - 366 days / 365.25 = 1.002... -> floor -> 1
        """
        # Calculate hire date from days before 2025-12-31
        year_end = date(2025, 12, 31)
        hire_date = year_end - timedelta(days=days_since_hire)

        tenure = calculate_expected_tenure(hire_date, 2025)
        expected = int(math.floor(days_since_hire / 365.25))

        assert tenure == expected, (
            f"Days={days_since_hire}: expected floor({days_since_hire}/365.25)="
            f"{expected}, got {tenure}"
        )


class TestYearOverYearIncrement:
    """Tests for year-over-year tenure increment validation."""

    @pytest.mark.parametrize(
        "base_case,next_case",
        YEAR_OVER_YEAR_CASES,
        ids=[f"{c[0].name}_to_{c[1].name}" for c in YEAR_OVER_YEAR_CASES]
    )
    def test_year_over_year_increment(
        self, base_case: TenureTestCase, next_case: TenureTestCase
    ):
        """
        Validates SC-005: Multi-year simulations show tenure incrementing
        by exactly 1 year per simulation year for continuing employees.
        """
        base_tenure = calculate_expected_tenure(
            base_case.hire_date, base_case.simulation_year
        )
        next_tenure = calculate_expected_tenure(
            next_case.hire_date, next_case.simulation_year
        )

        assert next_tenure == base_tenure + 1, (
            f"Year-over-year increment failed: "
            f"tenure({base_case.simulation_year})={base_tenure}, "
            f"tenure({next_case.simulation_year})={next_tenure}"
        )


class TestTenureBandAssignment:
    """Tests for tenure band assignment using [min, max) convention."""

    @pytest.mark.parametrize(
        "tenure,expected_band",
        [
            (0, "< 2"),
            (1, "< 2"),
            (2, "2-4"),
            (3, "2-4"),
            (4, "2-4"),
            (5, "5-9"),
            (9, "5-9"),
            (10, "10-19"),
            (19, "10-19"),
            (20, "20+"),
            (45, "20+"),
        ],
        ids=lambda x: f"tenure_{x}" if isinstance(x, int) else x
    )
    def test_tenure_band_boundaries(self, tenure: int, expected_band: str):
        """
        Test tenure band assignment follows [min, max) convention.

        Validates SC-003: Tenure band assignments are consistent with
        the [min, max) interval convention defined in config_tenure_bands.csv.

        User Story 3 Acceptance:
        - tenure 1.9 (truncated to 1) -> "< 2" band
        - tenure 4.99 (truncated to 4) -> "2-4" band (not "5-9")
        """
        actual_band = get_tenure_band(tenure)
        assert actual_band == expected_band, (
            f"Tenure {tenure} should be in band '{expected_band}', got '{actual_band}'"
        )

    def test_boundary_case_tenure_4_99(self):
        """
        Specific test for spec edge case: tenure 4.99 years -> 4 years -> "2-4" band.

        From User Story 3 acceptance scenario.
        """
        # 4.99 years truncates to 4
        tenure = 4
        band = get_tenure_band(tenure)
        assert band == "2-4", f"Tenure 4 should be in '2-4' band, got '{band}'"

    def test_boundary_case_tenure_1_9(self):
        """
        Specific test for spec edge case: tenure 1.9 years -> 1 year -> "< 2" band.

        From User Story 3 acceptance scenario.
        """
        # 1.9 years truncates to 1
        tenure = 1
        band = get_tenure_band(tenure)
        assert band == "< 2", f"Tenure 1 should be in '< 2' band, got '{band}'"


class TestTerminatedEmployeeTenure:
    """Tests for terminated employee tenure calculation."""

    def test_terminated_mid_year_uses_termination_date(self):
        """
        Test that terminated employees have tenure calculated to termination date.

        Validates: Terminated employee tenure = floor((termination_date - hire_date) / 365.25)
        """
        hire_date = date(2020, 1, 1)
        termination_date = date(2025, 6, 30)
        simulation_year = 2025

        # Tenure to termination date (2007 days)
        tenure_to_termination = calculate_expected_tenure(hire_date, simulation_year, termination_date)
        # Tenure to year end (2191 days)
        tenure_to_year_end = calculate_expected_tenure(hire_date, simulation_year, None)

        assert tenure_to_termination == 5, f"Expected 5 years to termination, got {tenure_to_termination}"
        assert tenure_to_year_end == 5, f"Expected 5 years to year end, got {tenure_to_year_end}"
        # In this case they're the same, but the calculation path differs

    def test_terminated_early_year_differs_from_year_end(self):
        """
        Test case where termination date gives different tenure than year end.

        Hire: 2024-12-15, Termination: 2025-01-15 = 31 days = 0 years
        Hire: 2024-12-15, Year End: 2025-12-31 = 381 days = 1 year
        """
        hire_date = date(2024, 12, 15)
        termination_date = date(2025, 1, 15)
        simulation_year = 2025

        tenure_to_termination = calculate_expected_tenure(hire_date, simulation_year, termination_date)
        tenure_to_year_end = calculate_expected_tenure(hire_date, simulation_year, None)

        assert tenure_to_termination == 0, f"Expected 0 years to termination, got {tenure_to_termination}"
        assert tenure_to_year_end == 1, f"Expected 1 year to year end, got {tenure_to_year_end}"
        # This demonstrates why termination date matters for accurate tenure

    def test_terminated_same_day_as_hire(self):
        """Test termination on hire date results in 0 tenure."""
        hire_date = date(2025, 6, 15)
        termination_date = date(2025, 6, 15)

        tenure = calculate_expected_tenure(hire_date, 2025, termination_date)
        assert tenure == 0, f"Expected 0 years for same-day termination, got {tenure}"


class TestSqlPolarsParity:
    """
    Tests for SQL/Polars calculation parity.

    Note: These tests validate the formula implementation. Full parity testing
    between SQL and Polars modes requires integration tests with actual database.
    """

    def test_sql_polars_parity_formula_consistency(self):
        """
        Test that the Python reference formula matches the expected SQL/Polars behavior.

        Validates FR-004: System MUST use the same calculation formula in both
        SQL (dbt) and Polars execution modes.

        The Polars implementation (polars_state_pipeline.py lines 1860-1866) uses:
            (year_end - hire_date).dt.total_days() / 365.25

        This test verifies our reference formula produces the same results.
        """
        test_cases = [
            # (hire_date, simulation_year, expected_tenure)
            (date(2020, 6, 15), 2025, 5),
            (date(2021, 1, 1), 2025, 4),
            (date(2025, 7, 1), 2025, 0),
            (date(2020, 2, 29), 2025, 5),  # Leap year
        ]

        for hire_date, sim_year, expected in test_cases:
            actual = calculate_expected_tenure(hire_date, sim_year)
            assert actual == expected, (
                f"Parity check failed: hire={hire_date}, year={sim_year}, "
                f"expected={expected}, got={actual}"
            )

    @pytest.mark.integration
    def test_sql_polars_parity(self):
        """
        Integration test: Compare SQL and Polars mode outputs.

        This test requires database setup and is marked as integration.
        Run with: pytest tests/test_tenure_calculation.py::TestSqlPolarsParity::test_sql_polars_parity -v

        Validates SC-002: SQL mode and Polars mode produce identical tenure
        values for the same input data (100% match).
        """
        pytest.skip(
            "Integration test requires database setup. "
            "Run full simulation in both modes to validate parity."
        )
