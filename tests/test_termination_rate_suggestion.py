"""Tests for termination rate suggestion feature.

Tests the core fix for the bug where termination rates always returned 100%.
All tests verify that rates are realistic and not hardcoded defaults.
"""

import pytest
from datetime import date, timedelta
from decimal import Decimal

from planalign_api.services.suggestion_service import TerminationRateSuggestionService
from tests.fixtures.workforce_data import assert_valid_termination_rate

# Import fixtures to make them available to tests
pytest_plugins = ["tests.fixtures.workforce_data"]


@pytest.mark.fast
class TestTerminationRateSuggestion:
    """Test termination rate suggestion calculations."""

    @pytest.fixture
    def service(self):
        """Create service instance for testing."""
        return TerminationRateSuggestionService()

    # ===== Happy Path Tests (US1) =====

    def test_termination_rate_basic(self, service, sample_census_data):
        """Test: 95 active, 5 terminated → expect 5.26%"""
        # Arrange
        scenario_id = "test_scenario"
        plan_design_id = "standard_401k"
        year = 2025

        # Act
        result = service.suggest_termination_rate(
            sample_census_data, scenario_id, plan_design_id, year
        )

        # Assert - Core fix: NOT 100%
        assert result.suggested_rate is not None
        assert result.suggested_rate != 100.0
        assert result.error_message is None

        # Verify calculation
        expected_rate = Decimal(5) / Decimal(95) * 100
        actual_rate = Decimal(str(result.suggested_rate))
        assert abs(actual_rate - expected_rate) < Decimal("0.1")
        assert_valid_termination_rate(result.model_dump())

    def test_termination_rate_no_terminations(
        self, service, edge_case_census_data
    ):
        """Test: 100 active, 0 terminated → expect 0%"""
        # Arrange
        no_term_data = edge_case_census_data["no_terminations"]
        scenario_id = "test_no_term"
        plan_design_id = "standard_401k"
        year = 2025

        # Act
        result = service.suggest_termination_rate(
            no_term_data, scenario_id, plan_design_id, year
        )

        # Assert
        assert result.suggested_rate == Decimal("0")
        assert result.error_message is None
        assert result.confidence == "MEDIUM"  # 100 employees = MEDIUM confidence
        assert result.sample_size == 100
        assert_valid_termination_rate(result.model_dump())

    def test_termination_rate_high_turnover(self, service):
        """Test: 40 active, 20 terminated → expect 50%"""
        # Arrange
        census_data = self._create_census(active=40, terminated=20)

        # Act
        result = service.suggest_termination_rate(
            census_data, "test_high", "standard_401k", 2025
        )

        # Assert - 20/40 active = 50%
        assert result.suggested_rate == Decimal("50")
        assert result.error_message is None
        assert_valid_termination_rate(result.model_dump())

    def test_termination_rate_small_population(self, service):
        """Test: 4 active, 1 terminated → expect 25%"""
        # Arrange - Use helper to ensure correct counts
        census_data = self._create_census(active=4, terminated=1)

        # Act
        result = service.suggest_termination_rate(
            census_data, "test_small", "standard_401k", 2025
        )

        # Assert - 1/4 active = 25%
        assert result.suggested_rate == Decimal("25.00")
        assert result.confidence == "LOW"
        assert result.sample_size == 4
        assert_valid_termination_rate(result.model_dump())

    # ===== Edge Case Tests (US2) =====

    def test_termination_rate_zero_active(self, service, edge_case_census_data):
        """Test: 0 active employees → expect error message"""
        # Arrange
        zero_active = edge_case_census_data["zero_active"]

        # Act
        result = service.suggest_termination_rate(
            zero_active, "test_zero", "standard_401k", 2025
        )

        # Assert - Core fix: NOT 100%, returns error instead
        assert result.suggested_rate is None
        assert result.error_message is not None
        assert "no active employees" in result.error_message.lower()
        assert result.sample_size == 0
        assert_valid_termination_rate(result.model_dump())

    def test_termination_rate_single_employee(self, service, edge_case_census_data):
        """Test: 1 active, 0 terminated → expect 0%"""
        # Arrange
        single_emp = edge_case_census_data["single_employee"]

        # Act
        result = service.suggest_termination_rate(
            single_emp, "test_single", "standard_401k", 2025
        )

        # Assert
        assert result.suggested_rate == Decimal("0")
        assert result.error_message is None
        assert result.confidence == "LOW"
        assert result.sample_size == 1
        assert_valid_termination_rate(result.model_dump())

    def test_termination_rate_missing_termination_data(self, service):
        """Test: Census with no termination dates → expect 0%"""
        # Arrange - All active, no termination dates
        census_data = [
            {
                "employee_id": f"EMP{i:05d}",
                "employment_status": "ACTIVE",
                "hire_date": date(2020, 1, 1) + timedelta(days=i*10),
                "termination_date": None,
                "annual_salary": 50000,
                "age": 30,
                "tenure_months": 60,
            }
            for i in range(50)
        ]

        # Act
        result = service.suggest_termination_rate(
            census_data, "test_missing", "standard_401k", 2025
        )

        # Assert
        assert result.suggested_rate == Decimal("0")
        assert result.error_message is None
        assert_valid_termination_rate(result.model_dump())

    def test_termination_rate_confidence_high(self, service):
        """Test: 200 active employees → confidence HIGH"""
        # Arrange
        today = date.today()
        census_data = [
            {
                "employee_id": f"EMP{i:05d}",
                "employment_status": "ACTIVE",
                "hire_date": date(2020, 1, 1) + timedelta(days=i*2),
                "termination_date": None,
                "annual_salary": 50000,
                "age": 30,
                "tenure_months": (today - date(2020, 1, 1)).days / 30,
            }
            for i in range(200)
        ]

        # Act
        result = service.suggest_termination_rate(
            census_data, "test_conf_high", "standard_401k", 2025
        )

        # Assert
        assert result.confidence == "HIGH"
        assert result.sample_size == 200

    def test_termination_rate_confidence_medium(self, service):
        """Test: 50 active employees → confidence MEDIUM"""
        # Arrange
        today = date.today()
        census_data = [
            {
                "employee_id": f"EMP{i:05d}",
                "employment_status": "ACTIVE",
                "hire_date": date(2020, 1, 1) + timedelta(days=i*10),
                "termination_date": None,
                "annual_salary": 50000,
                "age": 30,
                "tenure_months": (today - date(2020, 1, 1)).days / 30,
            }
            for i in range(50)
        ]

        # Act
        result = service.suggest_termination_rate(
            census_data, "test_conf_med", "standard_401k", 2025
        )

        # Assert
        assert result.confidence == "MEDIUM"
        assert result.sample_size == 50

    def test_termination_rate_confidence_low(self, service):
        """Test: 5 active employees → confidence LOW"""
        # Arrange
        today = date.today()
        census_data = [
            {
                "employee_id": f"EMP{i:05d}",
                "employment_status": "ACTIVE",
                "hire_date": date(2020, 1, 1) + timedelta(days=i*100),
                "termination_date": None,
                "annual_salary": 50000,
                "age": 30,
                "tenure_months": (today - date(2020, 1, 1)).days / 30,
            }
            for i in range(5)
        ]

        # Act
        result = service.suggest_termination_rate(
            census_data, "test_conf_low", "standard_401k", 2025
        )

        # Assert
        assert result.confidence == "LOW"
        assert result.sample_size == 5

    # ===== Calculation Component Tests =====

    def test_calculate_active_employee_count(self, service, sample_census_data):
        """Test active employee counting."""
        # Act
        count = service.calculate_active_employee_count(
            sample_census_data, "test", 2025
        )

        # Assert
        assert count == 95

    def test_calculate_terminated_employee_count(self, service, sample_census_data):
        """Test terminated employee counting."""
        # Act
        count = service.calculate_terminated_employee_count(
            sample_census_data, "test", 2025
        )

        # Assert
        assert count == 5

    def test_calculate_with_audit_trail(self, service, sample_census_data):
        """Test calculation with full audit trail."""
        # Act
        suggestion, calculation = service.calculate_with_audit(
            sample_census_data, "test", "standard_401k", 2025
        )

        # Assert
        assert suggestion.suggested_rate is not None
        assert suggestion.suggested_rate != 100.0
        assert calculation.total_active_employees == 95
        assert calculation.total_terminated_employees == 5
        assert calculation.calculation_status == "SUCCESS"

    # ===== Regression Tests (Ensure bug is fixed) =====

    def test_never_returns_100_percent(self, service, sample_census_data, edge_case_census_data):
        """Regression test: System never returns 100% (the original bug)."""
        test_cases = [
            (sample_census_data, "Baseline 5% turnover"),
            (edge_case_census_data["no_terminations"], "No terminations"),
            (edge_case_census_data["single_employee"], "Single employee"),
        ]

        for census_data, description in test_cases:
            if not census_data:
                continue

            result = service.suggest_termination_rate(
                census_data, "test", "standard_401k", 2025
            )

            # Core assertion: NEVER 100%
            if result.suggested_rate is not None:
                assert result.suggested_rate != 100.0, f"BUG REGRESSION: {description}"
                assert result.suggested_rate < 100.0, f"BUG REGRESSION: {description}"

    def test_rates_vary_across_datasets(self, service):
        """Test that rates vary appropriately across different census files."""
        # Create datasets with different turnover rates
        datasets = {
            "high_turnover": self._create_census(active=50, terminated=25),  # 50%
            "medium_turnover": self._create_census(active=100, terminated=10),  # 10%
            "low_turnover": self._create_census(active=200, terminated=5),  # 2.5%
        }

        rates = {}
        for name, census in datasets.items():
            result = service.suggest_termination_rate(
                census, name, "standard_401k", 2025
            )
            rates[name] = float(result.suggested_rate)

        # Assert rates vary appropriately
        assert rates["high_turnover"] > rates["medium_turnover"]
        assert rates["medium_turnover"] > rates["low_turnover"]

    @staticmethod
    def _create_census(active: int, terminated: int) -> list:
        """Helper to create census data with specific counts."""
        today = date.today()
        census = []

        # Active employees
        for i in range(active):
            census.append({
                "employee_id": f"EMP{i:05d}",
                "employment_status": "ACTIVE",
                "hire_date": date(2020, 1, 1) + timedelta(days=i*10),
                "termination_date": None,
                "annual_salary": 50000,
                "age": 30,
                "tenure_months": (today - (date(2020, 1, 1) + timedelta(days=i*10))).days / 30,
            })

        # Terminated employees
        for i in range(terminated):
            census.append({
                "employee_id": f"EMP{active+i:05d}",
                "employment_status": "TERMINATED",
                "hire_date": date(2020, 1, 1),
                "termination_date": date(2025, 6, 15) + timedelta(days=i*10),
                "annual_salary": 50000,
                "age": 30,
                "tenure_months": 60,
            })

        return census
