"""
Unit tests for YearDependencyValidator.

Tests validation logic, error conditions, and edge cases.
These tests use mock database connections to run fast (<1s).
"""

from __future__ import annotations

from typing import Dict
from unittest.mock import MagicMock, patch

import pytest

from planalign_orchestrator.exceptions import YearDependencyError
from planalign_orchestrator.state_accumulator.registry import StateAccumulatorRegistry
from planalign_orchestrator.state_accumulator.contract import StateAccumulatorContract


class MockDatabaseConnectionManager:
    """Mock database connection manager for testing."""

    def __init__(self, table_counts: Dict[str, Dict[int, int]] = None):
        """Initialize with table counts by year.

        Args:
            table_counts: Dict mapping table_name -> {year: count}
                         e.g., {"int_enrollment": {2025: 100, 2026: 0}}
        """
        self.table_counts = table_counts or {}

    def execute_with_retry(self, func):
        """Execute function with mock connection."""
        mock_conn = MagicMock()

        def mock_execute(query, params):
            # Extract table name and year from query
            # Query format: "SELECT COUNT(*) FROM {table} WHERE {col} = ?"
            table_name = query.split("FROM")[1].split("WHERE")[0].strip()
            year = params[0]

            count = self.table_counts.get(table_name, {}).get(year, 0)
            mock_result = MagicMock()
            mock_result.fetchone.return_value = [count]
            return mock_result

        mock_conn.execute = mock_execute
        return func(mock_conn)


@pytest.fixture
def clean_registry():
    """Provide a clean registry state for testing."""
    StateAccumulatorRegistry.clear()
    yield StateAccumulatorRegistry
    StateAccumulatorRegistry.clear()


@pytest.fixture
def sample_contracts(clean_registry):
    """Register sample contracts for testing."""
    enrollment = StateAccumulatorContract(
        model_name="int_enrollment_state_accumulator",
        table_name="int_enrollment_state_accumulator",
        start_year_source="int_baseline_workforce",
    )
    deferral = StateAccumulatorContract(
        model_name="int_deferral_rate_state_accumulator",
        table_name="int_deferral_rate_state_accumulator",
        start_year_source="int_employee_compensation_by_year",
    )
    clean_registry.register(enrollment)
    clean_registry.register(deferral)
    return clean_registry


class TestYearDependencyValidatorBasic:
    """Basic tests for YearDependencyValidator."""

    def test_start_year_has_no_prior_dependency(self, sample_contracts):
        """Test that start year (2025) has no prior dependency requirement."""
        from planalign_orchestrator.state_accumulator.validator import (
            YearDependencyValidator,
        )

        # Empty database - no data for any year
        db_manager = MockDatabaseConnectionManager({})
        validator = YearDependencyValidator(db_manager, start_year=2025)

        # Should NOT raise - start year has no dependency
        validator.validate_year_dependencies(year=2025)

    def test_year_after_start_requires_prior_year_data(self, sample_contracts):
        """Test that year 2026 requires 2025 data to exist."""
        from planalign_orchestrator.state_accumulator.validator import (
            YearDependencyValidator,
        )

        # No data for 2025
        db_manager = MockDatabaseConnectionManager({})
        validator = YearDependencyValidator(db_manager, start_year=2025)

        # Should raise - 2026 requires 2025 data
        with pytest.raises(YearDependencyError) as exc_info:
            validator.validate_year_dependencies(year=2026)

        error = exc_info.value
        assert error.year == 2026
        assert len(error.missing_tables) == 2  # Both accumulators missing

    def test_validation_passes_when_prior_year_exists(self, sample_contracts):
        """Test validation passes when prior year data exists."""
        from planalign_orchestrator.state_accumulator.validator import (
            YearDependencyValidator,
        )

        # Data exists for 2025
        db_manager = MockDatabaseConnectionManager({
            "int_enrollment_state_accumulator": {2025: 100},
            "int_deferral_rate_state_accumulator": {2025: 100},
        })
        validator = YearDependencyValidator(db_manager, start_year=2025)

        # Should NOT raise - 2025 data exists
        validator.validate_year_dependencies(year=2026)

    def test_validation_fails_when_one_table_missing(self, sample_contracts):
        """Test validation fails if ANY accumulator is missing prior year data."""
        from planalign_orchestrator.state_accumulator.validator import (
            YearDependencyValidator,
        )

        # Only enrollment has 2025 data, deferral does not
        db_manager = MockDatabaseConnectionManager({
            "int_enrollment_state_accumulator": {2025: 100},
            "int_deferral_rate_state_accumulator": {2025: 0},
        })
        validator = YearDependencyValidator(db_manager, start_year=2025)

        with pytest.raises(YearDependencyError) as exc_info:
            validator.validate_year_dependencies(year=2026)

        error = exc_info.value
        assert "int_deferral_rate_state_accumulator" in error.missing_tables
        assert "int_enrollment_state_accumulator" not in error.missing_tables


class TestYearDependencyValidatorMultiYear:
    """Tests for multi-year scenarios."""

    def test_year_2027_requires_2026_data(self, sample_contracts):
        """Test that year 2027 requires 2026 data (not 2025)."""
        from planalign_orchestrator.state_accumulator.validator import (
            YearDependencyValidator,
        )

        # Data for 2025 but not 2026
        db_manager = MockDatabaseConnectionManager({
            "int_enrollment_state_accumulator": {2025: 100, 2026: 0},
            "int_deferral_rate_state_accumulator": {2025: 100, 2026: 0},
        })
        validator = YearDependencyValidator(db_manager, start_year=2025)

        # 2026 should pass (2025 data exists)
        validator.validate_year_dependencies(year=2026)

        # 2027 should fail (2026 data missing)
        with pytest.raises(YearDependencyError) as exc_info:
            validator.validate_year_dependencies(year=2027)

        assert exc_info.value.year == 2027

    def test_chain_of_years_validates_correctly(self, sample_contracts):
        """Test validation works for a chain of years."""
        from planalign_orchestrator.state_accumulator.validator import (
            YearDependencyValidator,
        )

        # Full chain of data
        db_manager = MockDatabaseConnectionManager({
            "int_enrollment_state_accumulator": {2025: 100, 2026: 100, 2027: 100},
            "int_deferral_rate_state_accumulator": {2025: 100, 2026: 100, 2027: 100},
        })
        validator = YearDependencyValidator(db_manager, start_year=2025)

        # All should pass
        validator.validate_year_dependencies(year=2025)
        validator.validate_year_dependencies(year=2026)
        validator.validate_year_dependencies(year=2027)
        validator.validate_year_dependencies(year=2028)  # 2027 data exists


class TestYearDependencyValidatorGetMissing:
    """Tests for get_missing_years helper method."""

    def test_get_missing_years_returns_empty_when_all_present(self, sample_contracts):
        """Test get_missing_years returns empty dict when all data present."""
        from planalign_orchestrator.state_accumulator.validator import (
            YearDependencyValidator,
        )

        db_manager = MockDatabaseConnectionManager({
            "int_enrollment_state_accumulator": {2025: 100},
            "int_deferral_rate_state_accumulator": {2025: 100},
        })
        validator = YearDependencyValidator(db_manager, start_year=2025)

        missing = validator.get_missing_years(year=2026)
        assert missing == {}

    def test_get_missing_years_returns_missing_tables(self, sample_contracts):
        """Test get_missing_years returns dict of missing tables."""
        from planalign_orchestrator.state_accumulator.validator import (
            YearDependencyValidator,
        )

        db_manager = MockDatabaseConnectionManager({})
        validator = YearDependencyValidator(db_manager, start_year=2025)

        missing = validator.get_missing_years(year=2026)

        assert len(missing) == 2
        assert "int_enrollment_state_accumulator" in missing
        assert "int_deferral_rate_state_accumulator" in missing


class TestYearDependencyValidatorCheckpoint:
    """Tests for checkpoint dependency validation (US3)."""

    def test_validate_checkpoint_dependencies_full_chain(self, sample_contracts):
        """Test checkpoint validation for a full dependency chain."""
        from planalign_orchestrator.state_accumulator.validator import (
            YearDependencyValidator,
        )

        db_manager = MockDatabaseConnectionManager({
            "int_enrollment_state_accumulator": {2025: 100, 2026: 100},
            "int_deferral_rate_state_accumulator": {2025: 100, 2026: 100},
        })
        validator = YearDependencyValidator(db_manager, start_year=2025)

        # Checkpoint at 2027 requires 2025 and 2026 data
        validator.validate_checkpoint_dependencies(checkpoint_year=2027)

    def test_validate_checkpoint_dependencies_broken_chain(self, sample_contracts):
        """Test checkpoint validation fails for broken chain."""
        from planalign_orchestrator.state_accumulator.validator import (
            YearDependencyValidator,
        )

        # 2025 exists but 2026 is missing
        db_manager = MockDatabaseConnectionManager({
            "int_enrollment_state_accumulator": {2025: 100, 2026: 0},
            "int_deferral_rate_state_accumulator": {2025: 100, 2026: 0},
        })
        validator = YearDependencyValidator(db_manager, start_year=2025)

        # Checkpoint at 2028 should fail - 2026 data missing (year 2027 check fails)
        with pytest.raises(YearDependencyError):
            validator.validate_checkpoint_dependencies(checkpoint_year=2028)


class TestYearDependencyValidatorEdgeCases:
    """Edge case tests."""

    def test_empty_registry_validation_passes(self, clean_registry):
        """Test validation passes when no accumulators are registered."""
        from planalign_orchestrator.state_accumulator.validator import (
            YearDependencyValidator,
        )

        db_manager = MockDatabaseConnectionManager({})
        validator = YearDependencyValidator(db_manager, start_year=2025)

        # No accumulators registered, so nothing to validate
        validator.validate_year_dependencies(year=2026)

    def test_different_start_years(self, sample_contracts):
        """Test validation with different start year configurations."""
        from planalign_orchestrator.state_accumulator.validator import (
            YearDependencyValidator,
        )

        db_manager = MockDatabaseConnectionManager({
            "int_enrollment_state_accumulator": {2023: 100},
            "int_deferral_rate_state_accumulator": {2023: 100},
        })

        # Start year 2023
        validator = YearDependencyValidator(db_manager, start_year=2023)
        validator.validate_year_dependencies(year=2023)  # Start year - OK
        validator.validate_year_dependencies(year=2024)  # 2023 data exists - OK
