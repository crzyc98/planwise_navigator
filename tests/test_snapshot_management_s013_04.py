"""
Test suite for S013-04: Snapshot Management Operation

Tests the run_dbt_snapshot_for_year operation for centralized snapshot management
across different simulation contexts with comprehensive validation and error handling.
"""

from unittest.mock import Mock, patch

import pytest
from dagster import OpExecutionContext
from orchestrator.simulator_pipeline import run_dbt_snapshot_for_year


class TestSnapshotManagementOperation:
    """Test suite for the run_dbt_snapshot_for_year operation."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock Dagster execution context."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        context.log.info = Mock()
        context.log.warning = Mock()
        context.log.error = Mock()
        return context

    @pytest.fixture
    def mock_duckdb_connection(self):
        """Create a mock DuckDB connection."""
        conn = Mock()
        conn.execute = Mock()
        conn.fetchone = Mock()
        conn.close = Mock()
        return conn

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    def test_end_of_year_snapshot_success(
        self,
        mock_execute_dbt,
        mock_duckdb_connect,
        mock_context,
        mock_duckdb_connection,
    ):
        """Test successful end-of-year snapshot creation."""
        # Setup
        year = 2025
        snapshot_type = "end_of_year"

        # Mock database connection and queries
        mock_duckdb_connect.return_value = mock_duckdb_connection
        mock_duckdb_connection.execute.return_value.fetchone.side_effect = [
            [0],  # Initial workforce count (none expected for end_of_year)
            [150],  # Final snapshot count after creation
        ]

        # Execute
        result = run_dbt_snapshot_for_year(mock_context, year, snapshot_type)

        # Verify
        assert result["success"] is True
        assert result["year"] == year
        assert result["snapshot_type"] == snapshot_type
        assert result["records_created"] == 150
        assert "end_of_year" in result["description"]

        # Verify dbt command was called correctly
        mock_execute_dbt.assert_called_once_with(
            mock_context,
            ["snapshot", "--select", "scd_workforce_state"],
            {"simulation_year": year},
            False,
            f"workforce state snapshot for year {year} (end_of_year)",
        )

        # Verify database connections were closed
        assert (
            mock_duckdb_connection.close.call_count == 3
        )  # Pre-validation, cleanup, and post-validation

        # Verify logging
        mock_context.log.info.assert_any_call(
            f"Creating {snapshot_type} snapshot for year {year}"
        )
        mock_context.log.info.assert_any_call(
            f"Snapshot created successfully: 150 records in scd_workforce_state for year {year}"
        )

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    def test_previous_year_snapshot_success(
        self,
        mock_execute_dbt,
        mock_duckdb_connect,
        mock_context,
        mock_duckdb_connection,
    ):
        """Test successful previous year snapshot creation."""
        # Setup
        year = 2024
        snapshot_type = "previous_year"

        # Mock database connection - no pre-validation for previous_year
        mock_duckdb_connect.return_value = mock_duckdb_connection
        mock_duckdb_connection.execute.return_value.fetchone.return_value = [125]

        # Execute
        result = run_dbt_snapshot_for_year(mock_context, year, snapshot_type)

        # Verify
        assert result["success"] is True
        assert result["year"] == year
        assert result["snapshot_type"] == snapshot_type
        assert result["records_created"] == 125
        assert "previous year dependency" in result["description"]

        # Verify dbt command was called correctly for previous year
        mock_execute_dbt.assert_called_once_with(
            mock_context,
            ["snapshot", "--select", "scd_workforce_state"],
            {"simulation_year": year},
            False,
            f"workforce state snapshot for year {year} (previous year dependency)",
        )

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    def test_recovery_snapshot_with_existing_data(
        self,
        mock_execute_dbt,
        mock_duckdb_connect,
        mock_context,
        mock_duckdb_connection,
    ):
        """Test recovery snapshot when data already exists."""
        # Setup
        year = 2025
        snapshot_type = "recovery"

        # Mock database connection - existing data found
        mock_duckdb_connect.return_value = mock_duckdb_connection
        mock_duckdb_connection.execute.return_value.fetchone.side_effect = [
            [100],  # Existing workforce count
            [200],  # Final snapshot count after recovery
        ]

        # Execute
        result = run_dbt_snapshot_for_year(mock_context, year, snapshot_type)

        # Verify
        assert result["success"] is True
        assert result["year"] == year
        assert result["snapshot_type"] == snapshot_type
        assert result["records_created"] == 200

        # Verify warning was logged about existing data
        mock_context.log.warning.assert_called_once_with(
            f"Workforce snapshot already exists for year {year} - proceeding with recovery anyway"
        )

    def test_invalid_snapshot_type(self, mock_context):
        """Test error handling for invalid snapshot type."""
        year = 2025
        invalid_type = "invalid_type"

        # Execute and verify exception
        with pytest.raises(ValueError) as exc_info:
            run_dbt_snapshot_for_year(mock_context, year, invalid_type)

        assert "Invalid snapshot_type 'invalid_type'" in str(exc_info.value)
        assert "Must be one of: ['end_of_year', 'previous_year', 'recovery']" in str(
            exc_info.value
        )

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    def test_snapshot_creation_failure_no_records(
        self,
        mock_execute_dbt,
        mock_duckdb_connect,
        mock_context,
        mock_duckdb_connection,
    ):
        """Test handling when snapshot creation produces no records."""
        # Setup
        year = 2025
        snapshot_type = "end_of_year"

        # Mock database connection - no records created
        mock_duckdb_connect.return_value = mock_duckdb_connection
        mock_duckdb_connection.execute.return_value.fetchone.side_effect = [
            [0],  # Initial workforce count
            [0],  # Final snapshot count - no records created
        ]

        # Execute
        result = run_dbt_snapshot_for_year(mock_context, year, snapshot_type)

        # Verify failure result
        assert result["success"] is False
        assert result["year"] == year
        assert result["snapshot_type"] == snapshot_type
        assert result["records_created"] == 0
        assert "FAILED" in result["description"]
        assert "error" in result
        assert "no records found in scd_workforce_state" in result["error"]

        # Verify error was logged
        mock_context.log.error.assert_called()

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    def test_dbt_command_execution_failure(
        self,
        mock_execute_dbt,
        mock_duckdb_connect,
        mock_context,
        mock_duckdb_connection,
    ):
        """Test handling when dbt command execution fails."""
        # Setup
        year = 2025
        snapshot_type = "end_of_year"

        # Mock database connection for pre-validation
        mock_duckdb_connect.return_value = mock_duckdb_connection
        mock_duckdb_connection.execute.return_value.fetchone.return_value = [0]

        # Mock dbt command failure
        mock_execute_dbt.side_effect = Exception("dbt snapshot command failed")

        # Execute
        result = run_dbt_snapshot_for_year(mock_context, year, snapshot_type)

        # Verify failure result
        assert result["success"] is False
        assert result["year"] == year
        assert result["snapshot_type"] == snapshot_type
        assert result["records_created"] == 0
        assert "dbt snapshot command failed" in result["error"]

        # Verify error was logged
        mock_context.log.error.assert_called()

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_database_connection_failure(self, mock_duckdb_connect, mock_context):
        """Test handling when database connection fails."""
        # Setup
        year = 2025
        snapshot_type = "end_of_year"

        # Mock database connection failure
        mock_duckdb_connect.side_effect = Exception("Database connection failed")

        # Execute
        result = run_dbt_snapshot_for_year(mock_context, year, snapshot_type)

        # Verify failure result
        assert result["success"] is False
        assert result["year"] == year
        assert result["snapshot_type"] == snapshot_type
        assert result["records_created"] == 0
        assert "Database connection failed" in result["error"]

    @pytest.mark.parametrize(
        "snapshot_type", ["end_of_year", "previous_year", "recovery"]
    )
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    def test_all_snapshot_types_parameter_handling(
        self,
        mock_execute_dbt,
        mock_duckdb_connect,
        mock_context,
        mock_duckdb_connection,
        snapshot_type,
    ):
        """Test that all valid snapshot types are handled correctly."""
        year = 2025

        # Mock database connection
        mock_duckdb_connect.return_value = mock_duckdb_connection
        mock_duckdb_connection.execute.return_value.fetchone.side_effect = [
            [50],  # Pre-check count (if applicable)
            [100],  # Final count
        ]

        # Execute
        result = run_dbt_snapshot_for_year(mock_context, year, snapshot_type)

        # Verify
        assert result["success"] is True
        assert result["snapshot_type"] == snapshot_type

        # Verify correct description based on type
        if snapshot_type == "previous_year":
            assert "previous year dependency" in result["description"]
        else:
            assert snapshot_type in result["description"]

    def test_default_snapshot_type(self, mock_context):
        """Test that default snapshot type is 'end_of_year'."""
        # This test verifies the function signature - default parameter should be 'end_of_year'
        import inspect

        sig = inspect.signature(run_dbt_snapshot_for_year)
        default_value = sig.parameters["snapshot_type"].default
        assert default_value == "end_of_year"


class TestSnapshotOperationIntegration:
    """Integration tests for snapshot operation with realistic scenarios."""

    @pytest.fixture
    def integration_context(self):
        """Create a more realistic context for integration testing."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        return context

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    def test_multi_year_snapshot_sequence(
        self, mock_execute_dbt, mock_duckdb_connect, integration_context
    ):
        """Test realistic multi-year snapshot creation sequence."""
        # Simulate a 3-year simulation requiring snapshots
        years = [2023, 2024, 2025]

        # Mock database responses for each year
        mock_conn = Mock()
        mock_conn.close = Mock()
        mock_duckdb_connect.return_value = mock_conn

        # Different record counts for each year to simulate growth
        record_counts = [100, 125, 150]

        results = []
        for i, year in enumerate(years):
            # Reset side_effect for each iteration (3 connections: pre-validation, cleanup, post-validation)
            mock_conn.execute.return_value.fetchone.side_effect = [
                [record_counts[i]],  # Pre-validation: workforce count
                [record_counts[i]],  # Post-validation: final snapshot count
            ]

            result = run_dbt_snapshot_for_year(integration_context, year, "end_of_year")
            results.append(result)

        # Verify all snapshots succeeded
        assert all(r["success"] for r in results)
        assert [r["year"] for r in results] == years
        assert [r["records_created"] for r in results] == record_counts

        # Verify dbt commands were called for each year
        assert mock_execute_dbt.call_count == len(years)

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    def test_error_recovery_workflow(
        self, mock_execute_dbt, mock_duckdb_connect, integration_context
    ):
        """Test error recovery workflow using recovery snapshot type."""
        year = 2025

        # Mock database connection
        mock_conn = Mock()
        mock_conn.close = Mock()
        mock_duckdb_connect.return_value = mock_conn

        # First attempt fails (simulate corrupted snapshot)
        mock_conn.execute.return_value.fetchone.side_effect = [
            [50],  # Pre-check shows existing data
            [0],  # Post-execution shows no records (failure)
        ]

        # Execute recovery snapshot
        result = run_dbt_snapshot_for_year(integration_context, year, "recovery")

        # Verify failure was handled gracefully
        assert result["success"] is False
        assert result["snapshot_type"] == "recovery"
        assert "no records found" in result["error"]

        # Verify appropriate logging occurred
        integration_context.log.warning.assert_called_once()  # Warning about existing data
        integration_context.log.error.assert_called_once()  # Error about failure
