"""
Unit tests for Multi-Year Simulation with Enhanced Data Persistence

Updated test suite for multi-year simulation functions, focusing on the new
data persistence behavior and enhanced validation functionality.
"""

import unittest.mock
from unittest.mock import MagicMock, Mock, patch

import pytest
from orchestrator_mvp.core.multi_year_orchestrator import \
    MultiYearSimulationOrchestrator
from orchestrator_mvp.core.multi_year_simulation import (
    get_previous_year_workforce_count, validate_multi_year_data_integrity,
    validate_year_transition)


class TestEnhancedYearTransitionValidation:
    """Test suite for enhanced year transition validation."""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock database connection."""
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = (
            1000,
            950,
            50,  # total, active, terminated employees
            42.5,
            5.2,  # avg age, tenure
            75000,  # avg compensation
            45000,
            120000,  # min, max compensation
            3,  # distinct levels
        )
        mock_conn.close.return_value = None
        return mock_conn

    @patch("orchestrator_mvp.core.multi_year_simulation.get_connection")
    def test_enhanced_validation_success(self, mock_get_conn, mock_connection):
        """Test enhanced year transition validation with comprehensive data."""
        mock_get_conn.return_value = mock_connection

        # Mock all required query results
        mock_connection.execute.return_value.fetchone.side_effect = [
            # Snapshot query result
            (1000, 950, 50, 42.5, 5.2, 75000, 45000, 120000, 3),
            # Events query result
            (
                500,
                100,
                80,
                50,
                200,
                480,
            ),  # total, hire, term, promo, raise, valid events
            # Consistency check result
            (
                100,
                80,
                20,
                25,
                5,
            ),  # hires, terms, expected_change, actual_change, variance
        ]

        # Execute
        result = validate_year_transition(2025, 2026)

        # Verify
        assert result is True
        assert mock_get_conn.called
        assert (
            mock_connection.execute.call_count >= 3
        )  # snapshot, events, consistency queries
        mock_connection.close.assert_called_once()

    @patch("orchestrator_mvp.core.multi_year_simulation.get_connection")
    def test_enhanced_validation_failure_missing_data(
        self, mock_get_conn, mock_connection
    ):
        """Test validation failure when previous year data is missing."""
        mock_get_conn.return_value = mock_connection

        # Mock missing data - empty result
        mock_connection.execute.return_value.fetchone.return_value = None

        # Execute
        result = validate_year_transition(2025, 2026)

        # Verify
        assert result is False
        mock_connection.close.assert_called_once()

    @patch("orchestrator_mvp.core.multi_year_simulation.get_connection")
    def test_enhanced_validation_data_quality_issues(
        self, mock_get_conn, mock_connection
    ):
        """Test validation with data quality concerns but still passing."""
        mock_get_conn.return_value = mock_connection

        # Mock low quality data that still passes minimum thresholds
        mock_connection.execute.return_value.fetchone.side_effect = [
            # Snapshot with low employee count but > 0
            (25, 20, 5, 35.0, 3.0, 55000, 35000, 85000, 2),
            # Events exist
            (50, 5, 8, 2, 15, 45),
            # Consistency within acceptable range
            (5, 8, -3, -2, 1),  # Small variance
        ]

        # Execute
        result = validate_year_transition(2025, 2026)

        # Verify - should still pass with warnings
        assert result is True


class TestEnhancedWorkforceCountRetrieval:
    """Test suite for enhanced workforce count retrieval with better error handling."""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock database connection."""
        mock_conn = Mock()
        mock_conn.close.return_value = None
        return mock_conn

    @patch("orchestrator_mvp.core.multi_year_simulation.get_connection")
    @patch("orchestrator_mvp.core.multi_year_simulation.get_baseline_workforce_count")
    def test_successful_previous_year_retrieval(
        self, mock_baseline, mock_get_conn, mock_connection
    ):
        """Test successful retrieval of previous year workforce count."""
        mock_get_conn.return_value = mock_connection

        # Mock successful query result with comprehensive data
        mock_connection.execute.return_value.fetchone.return_value = (
            950,  # active_count
            42.5,  # avg_age
            75000,  # avg_compensation
            3,  # distinct_levels
            "2025-12-31 23:59:59",  # snapshot_date
        )

        # Execute
        result = get_previous_year_workforce_count(2026)

        # Verify
        assert result == 950
        mock_connection.execute.assert_called_once()
        mock_connection.close.assert_called_once()
        mock_baseline.assert_not_called()  # Should not fallback

    @patch("orchestrator_mvp.core.multi_year_simulation.get_connection")
    @patch("orchestrator_mvp.core.multi_year_simulation.get_baseline_workforce_count")
    def test_fallback_to_baseline_missing_data(
        self, mock_baseline, mock_get_conn, mock_connection
    ):
        """Test fallback to baseline when previous year data is missing."""
        mock_get_conn.return_value = mock_connection
        mock_baseline.return_value = 1000

        # Mock missing data scenario
        mock_connection.execute.return_value.fetchone.return_value = None

        # Execute
        result = get_previous_year_workforce_count(2026)

        # Verify
        assert result == 1000
        mock_baseline.assert_called_once()
        mock_connection.close.assert_called_once()

    @patch("orchestrator_mvp.core.multi_year_simulation.get_connection")
    @patch("orchestrator_mvp.core.multi_year_simulation.get_baseline_workforce_count")
    def test_fallback_to_baseline_zero_count(
        self, mock_baseline, mock_get_conn, mock_connection
    ):
        """Test fallback when previous year has zero employees."""
        mock_get_conn.return_value = mock_connection
        mock_baseline.return_value = 1000

        # Mock zero count scenario
        mock_connection.execute.return_value.fetchone.return_value = (
            0,
            0,
            0,
            0,
            None,  # All zeros/nulls
        )

        # Execute
        result = get_previous_year_workforce_count(2026)

        # Verify fallback occurred
        assert result == 1000
        mock_baseline.assert_called_once()

    @patch("orchestrator_mvp.core.multi_year_simulation.get_connection")
    @patch("orchestrator_mvp.core.multi_year_simulation.get_baseline_workforce_count")
    def test_data_quality_warnings(self, mock_baseline, mock_get_conn, mock_connection):
        """Test data quality validation and warnings."""
        mock_get_conn.return_value = mock_connection

        # Mock data with quality issues but still valid
        mock_connection.execute.return_value.fetchone.return_value = (
            5,  # very low active_count (triggers warning)
            15.0,  # suspicious avg_age (triggers warning)
            25000,  # suspicious avg_compensation (triggers warning)
            1,  # too few distinct_levels (triggers warning)
            "2025-12-31 23:59:59",
        )

        # Execute - should succeed but with warnings
        result = get_previous_year_workforce_count(2026)

        # Verify still returns the count despite warnings
        assert result == 5
        mock_baseline.assert_not_called()  # Should not fallback

    @patch("orchestrator_mvp.core.multi_year_simulation.get_connection")
    @patch("orchestrator_mvp.core.multi_year_simulation.get_baseline_workforce_count")
    def test_exception_handling(self, mock_baseline, mock_get_conn, mock_connection):
        """Test exception handling with fallback to baseline."""
        mock_get_conn.return_value = mock_connection
        mock_baseline.return_value = 1000

        # Mock database exception
        mock_connection.execute.side_effect = Exception("Database connection lost")

        # Execute
        result = get_previous_year_workforce_count(2026)

        # Verify fallback occurred
        assert result == 1000
        mock_baseline.assert_called_once()
        mock_connection.close.assert_called_once()

    @patch("orchestrator_mvp.core.multi_year_simulation.get_connection")
    @patch("orchestrator_mvp.core.multi_year_simulation.get_baseline_workforce_count")
    def test_critical_failure_both_sources(
        self, mock_baseline, mock_get_conn, mock_connection
    ):
        """Test critical failure when both previous year and baseline fail."""
        mock_get_conn.return_value = mock_connection
        mock_baseline.side_effect = Exception("Baseline data also unavailable")

        # Mock database exception for previous year
        mock_connection.execute.side_effect = Exception("Database connection lost")

        # Execute and expect ValueError
        with pytest.raises(
            ValueError, match="Critical error: Cannot retrieve workforce data"
        ):
            get_previous_year_workforce_count(2026)


class TestMultiYearDataIntegrityValidation:
    """Test suite for multi-year data integrity validation."""

    @pytest.fixture
    def mock_connection(self):
        """Create a mock database connection."""
        mock_conn = Mock()
        mock_conn.close.return_value = None
        return mock_conn

    @patch("orchestrator_mvp.core.multi_year_simulation.get_connection")
    def test_successful_integrity_validation(self, mock_get_conn, mock_connection):
        """Test successful multi-year data integrity validation."""
        mock_get_conn.return_value = mock_connection

        # Mock baseline availability
        mock_connection.execute.return_value.fetchone.side_effect = [
            (1000,),  # baseline_count > 0
        ]

        # Mock existing years query
        mock_connection.execute.return_value.fetchall.return_value = [
            (2025, 950),
            (2026, 980),  # (year, employee_count)
        ]

        # Execute
        result = validate_multi_year_data_integrity(2025, 2027)

        # Verify
        assert result["baseline_available"] is True
        assert len(result["existing_years"]) == 2
        assert result["data_gaps"] == [2027]
        assert result["can_proceed"] is True
        mock_connection.close.assert_called_once()

    @patch("orchestrator_mvp.core.multi_year_simulation.get_connection")
    def test_missing_baseline_validation(self, mock_get_conn, mock_connection):
        """Test validation when baseline is missing."""
        mock_get_conn.return_value = mock_connection

        # Mock missing baseline
        mock_connection.execute.return_value.fetchone.return_value = (
            0,
        )  # No baseline data
        mock_connection.execute.return_value.fetchall.return_value = (
            []
        )  # No existing years

        # Execute
        result = validate_multi_year_data_integrity(2025, 2027)

        # Verify
        assert result["baseline_available"] is False
        assert result["can_proceed"] is False
        assert "Generate baseline workforce data" in result["recommendations"][0]

    @patch("orchestrator_mvp.core.multi_year_simulation.get_connection")
    def test_partial_data_validation(self, mock_get_conn, mock_connection):
        """Test validation with partial multi-year data."""
        mock_get_conn.return_value = mock_connection

        # Mock baseline exists
        mock_connection.execute.return_value.fetchone.return_value = (1000,)

        # Mock partial existing years
        mock_connection.execute.return_value.fetchall.return_value = [
            (2025, 950)  # Only 2025 exists
        ]

        # Execute
        result = validate_multi_year_data_integrity(2025, 2027)

        # Verify
        assert result["baseline_available"] is True
        assert len(result["existing_years"]) == 1
        assert result["existing_years"][0]["year"] == 2025
        assert result["data_gaps"] == [2026, 2027]
        assert result["can_proceed"] is True  # Can proceed with baseline

    @patch("orchestrator_mvp.core.multi_year_simulation.get_connection")
    def test_database_connection_failure(self, mock_get_conn, mock_connection):
        """Test handling of database connection failures."""
        mock_get_conn.return_value = mock_connection
        mock_connection.execute.side_effect = Exception("Connection failed")

        # Execute
        result = validate_multi_year_data_integrity(2025, 2027)

        # Verify
        assert result["baseline_available"] is False
        assert result["can_proceed"] is False
        assert "Resolve database connectivity issues" in result["recommendations"]
        mock_connection.close.assert_called_once()


class TestMultiYearOrchestratorDataManagement:
    """Test suite for MultiYearSimulationOrchestrator data management modes."""

    def test_preserve_data_mode_initialization(self):
        """Test orchestrator initialization with data preservation."""
        config = {
            "target_growth_rate": 0.03,
            "workforce": {"total_termination_rate": 0.12},
        }

        orchestrator = MultiYearSimulationOrchestrator(
            2025, 2027, config, force_clear=False, preserve_data=True
        )

        assert orchestrator.force_clear is False
        assert orchestrator.preserve_data is True
        assert orchestrator.start_year == 2025
        assert orchestrator.end_year == 2027

    def test_force_clear_mode_initialization(self):
        """Test orchestrator initialization with force clear."""
        config = {
            "target_growth_rate": 0.03,
            "workforce": {"total_termination_rate": 0.12},
        }

        orchestrator = MultiYearSimulationOrchestrator(
            2025, 2027, config, force_clear=True, preserve_data=False
        )

        assert orchestrator.force_clear is True
        assert orchestrator.preserve_data is False

    @patch("orchestrator_mvp.core.multi_year_orchestrator.get_connection")
    def test_selective_year_clearing(self, mock_get_conn):
        """Test selective clearing of specific years."""
        mock_conn = Mock()
        mock_conn.execute.return_value.rowcount = 100  # Mock deleted rows
        mock_get_conn.return_value = mock_conn

        config = {
            "target_growth_rate": 0.03,
            "workforce": {"total_termination_rate": 0.12},
        }
        orchestrator = MultiYearSimulationOrchestrator(2025, 2027, config)

        # Execute selective clearing
        orchestrator.clear_specific_years([2026])

        # Verify specific year was targeted
        expected_calls = [
            unittest.mock.call(
                "DELETE FROM fct_yearly_events WHERE simulation_year = ?", [2026]
            ),
            unittest.mock.call(
                "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?", [2026]
            ),
        ]
        mock_conn.execute.assert_has_calls(expected_calls, any_order=False)
        mock_conn.close.assert_called_once()

    def test_rollback_year_functionality(self):
        """Test rollback year with selective clearing."""
        config = {
            "target_growth_rate": 0.03,
            "workforce": {"total_termination_rate": 0.12},
        }
        orchestrator = MultiYearSimulationOrchestrator(2025, 2027, config)

        # Add some mock completed years
        orchestrator.results["years_completed"] = [2025, 2026]
        orchestrator.results["step_details"] = {2025: {}, 2026: {}}

        with patch(
            "orchestrator_mvp.core.multi_year_orchestrator.get_connection"
        ) as mock_get_conn:
            mock_conn = Mock()
            mock_conn.execute.return_value.rowcount = 50
            mock_get_conn.return_value = mock_conn

            # Execute rollback
            orchestrator.rollback_year(2026)

            # Verify year was removed from tracking
            assert 2026 not in orchestrator.results["years_completed"]
            assert 2026 not in orchestrator.results["step_details"]
            assert (
                2025 in orchestrator.results["years_completed"]
            )  # Other years preserved
