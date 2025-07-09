"""
Unit tests for uncovered functions in simulator_pipeline.py to boost coverage.

These tests target high-impact functions that are currently uncovered,
providing minimal but meaningful coverage to reach the 95% target.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from dagster import OpExecutionContext, AssetExecutionContext

from orchestrator.simulator_pipeline import (
    clean_orphaned_data_outside_range,
    run_dbt_event_models_for_year,
    baseline_workforce_validated,
    validate_year_results,
)


class TestCleanOrphanedDataOutsideRange:
    """Tests for clean_orphaned_data_outside_range function."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock Dagster execution context."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        context.log.info = Mock()
        context.log.error = Mock()
        return context

    def test_empty_simulation_range(self, mock_context):
        """Test handling of empty simulation range."""
        result = clean_orphaned_data_outside_range(mock_context, [])

        assert result == {"fct_yearly_events": 0, "fct_workforce_snapshot": 0}
        mock_context.log.info.assert_called_with("No simulation range specified - no orphaned data cleanup")

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_successful_orphaned_data_cleanup(self, mock_duckdb_connect, mock_context):
        """Test successful cleanup of orphaned data."""
        # Mock database connection
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.side_effect = [
            [50],  # fct_yearly_events count
            [30],  # fct_workforce_snapshot count
        ]
        mock_duckdb_connect.return_value = mock_conn

        result = clean_orphaned_data_outside_range(mock_context, [2025, 2026, 2027])

        assert result == {"fct_yearly_events": 50, "fct_workforce_snapshot": 30}
        # Check that the initial log message was called (among others)
        mock_context.log.info.assert_any_call("Cleaning orphaned data outside simulation range 2025-2027")
        mock_conn.close.assert_called()

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_single_year_range(self, mock_duckdb_connect, mock_context):
        """Test cleanup with single year range."""
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.side_effect = [[10], [5]]
        mock_duckdb_connect.return_value = mock_conn

        result = clean_orphaned_data_outside_range(mock_context, [2025])

        assert result == {"fct_yearly_events": 10, "fct_workforce_snapshot": 5}
        mock_context.log.info.assert_any_call("Cleaning orphaned data outside simulation range 2025")


class TestRunDbtEventModelsForYear:
    """Tests for run_dbt_event_models_for_year function."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock Dagster execution context."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        context.log.info = Mock()
        return context

    @pytest.fixture
    def sample_config(self):
        """Sample configuration for testing."""
        return {
            "random_seed": 42,
            "target_growth_rate": 0.03,
            "total_termination_rate": 0.12,
            "new_hire_termination_rate": 0.25,
            "full_refresh": False,
        }

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline._log_hiring_calculation_debug")
    def test_successful_event_models_execution(self, mock_log_hiring, mock_execute_dbt, mock_context, sample_config):
        """Test successful execution of event models."""
        # Mock hiring debug info
        mock_log_hiring.return_value = {"debug_info": "test"}

        # Mock execute_dbt_command to succeed
        mock_execute_dbt.return_value = None

        result = run_dbt_event_models_for_year(mock_context, 2025, sample_config)

        assert result["year"] == 2025
        assert len(result["models_executed"]) == 5
        assert "int_termination_events" in result["models_executed"]
        assert "int_hiring_events" in result["models_executed"]
        assert result["hiring_debug"] == {"debug_info": "test"}

        # Verify all models were executed
        assert mock_execute_dbt.call_count == 5


class TestBaselineWorkforceValidated:
    """Tests for baseline_workforce_validated function."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock Dagster asset execution context."""
        context = Mock(spec=AssetExecutionContext)
        context.log = Mock()
        context.log.info = Mock()
        context.log.error = Mock()
        return context

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_successful_baseline_validation(self, mock_duckdb_connect, mock_context):
        """Test successful baseline workforce validation."""
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [1500]  # Baseline workforce count
        mock_duckdb_connect.return_value = mock_conn

        result = baseline_workforce_validated(mock_context)

        assert result is True
        mock_context.log.info.assert_called()
        mock_conn.close.assert_called()

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_baseline_validation_failure(self, mock_duckdb_connect, mock_context):
        """Test baseline validation failure with no workforce data."""
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [0]  # No baseline workforce
        mock_duckdb_connect.return_value = mock_conn

        result = baseline_workforce_validated(mock_context)

        assert result is False
        mock_context.log.error.assert_called()


class TestValidateYearResults:
    """Tests for validate_year_results function."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock Dagster execution context."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        context.log.info = Mock()
        context.log.warning = Mock()
        return context

    @patch("orchestrator.simulator_pipeline.assert_year_complete")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_successful_year_validation(self, mock_duckdb_connect, mock_assert_year_complete, mock_context):
        """Test successful year results validation."""
        # Mock assert_year_complete to succeed
        mock_assert_year_complete.return_value = None

        mock_conn = Mock()
        # Mock all validation queries to return valid data
        mock_conn.execute.return_value.fetchone.side_effect = [
            [1500],  # Workforce snapshot count
            [200],   # Yearly events count
            [1600],  # Final workforce count
            [100],   # Hire events
            [80],    # Termination events
        ]
        mock_duckdb_connect.return_value = mock_conn

        config = {"target_growth_rate": 0.03}
        result = validate_year_results(mock_context, 2025, config)

        assert result["year"] == 2025
        assert result["validation_passed"] is True
        mock_conn.close.assert_called()

    @patch("orchestrator.simulator_pipeline.assert_year_complete")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_year_validation_failure(self, mock_duckdb_connect, mock_assert_year_complete, mock_context):
        """Test year validation failure with assertion error."""
        # Mock assert_year_complete to raise an exception
        mock_assert_year_complete.side_effect = AssertionError("Year validation failed")

        config = {"target_growth_rate": 0.03}
        result = validate_year_results(mock_context, 2025, config)

        assert result["year"] == 2025
        assert result["validation_passed"] is False
        mock_context.log.warning.assert_called()
