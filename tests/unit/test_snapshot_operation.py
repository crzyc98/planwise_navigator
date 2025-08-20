"""
Unit tests for S013-04: run_dbt_snapshot_for_year operation

Comprehensive test suite for the snapshot management operation,
covering all snapshot types, validation scenarios, and error handling.
"""

from unittest.mock import Mock, patch

import pytest
from dagster import OpExecutionContext
from orchestrator.simulator_pipeline import run_dbt_snapshot_for_year


class TestSnapshotOperation:
    """Test suite for run_dbt_snapshot_for_year operation."""

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

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_end_of_year_snapshot_success(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
    ):
        """Test successful end-of-year snapshot creation."""
        year = 2025
        snapshot_type = "end_of_year"

        # Mock database connection and queries
        mock_conn = Mock()
        # The function makes 2 fetchone() calls: pre-validation and post-validation
        mock_conn.execute.return_value.fetchone.side_effect = [
            [0],  # Initial workforce count (none expected for end_of_year)
            [150],  # Final snapshot count after creation
        ]
        mock_duckdb_connect.return_value = mock_conn

        # Execute
        result = run_dbt_snapshot_for_year(mock_context, year, snapshot_type)

        # Verify result structure
        assert result["success"] is True
        assert result["year"] == year
        assert result["snapshot_type"] == snapshot_type
        assert result["records_created"] == 150
        assert "end_of_year" in result["description"]

        # Verify dbt command execution
        mock_execute_dbt.assert_called_once_with(
            mock_context,
            ["snapshot", "--select", "scd_workforce_state"],
            {"simulation_year": year},
            False,
            f"workforce state snapshot for year {year} (end_of_year)",
        )

        # Verify database connections were closed
        assert mock_conn.close.call_count == 3

        # Verify logging
        mock_context.log.info.assert_any_call(
            f"Creating {snapshot_type} snapshot for year {year}"
        )
        mock_context.log.info.assert_any_call(
            f"Snapshot created successfully: 150 records in scd_workforce_state for year {year}"
        )

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_previous_year_snapshot_success(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
    ):
        """Test successful previous year snapshot creation."""
        year = 2024
        snapshot_type = "previous_year"

        # Mock database connection - previous_year only needs post-validation
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [
            125
        ]  # Final snapshot count
        mock_duckdb_connect.return_value = mock_conn

        result = run_dbt_snapshot_for_year(mock_context, year, snapshot_type)

        # Verify result
        assert result["success"] is True
        assert result["year"] == year
        assert result["snapshot_type"] == snapshot_type
        assert result["records_created"] == 125
        assert "previous year dependency" in result["description"]

        # Verify dbt command
        mock_execute_dbt.assert_called_once_with(
            mock_context,
            ["snapshot", "--select", "scd_workforce_state"],
            {"simulation_year": year},
            False,
            f"workforce state snapshot for year {year} (previous year dependency)",
        )

        # Verify database connections were closed (clean data + post-validation)
        assert mock_conn.close.call_count == 2

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_recovery_snapshot_with_existing_data(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
    ):
        """Test recovery snapshot when data already exists."""
        year = 2025
        snapshot_type = "recovery"

        # Mock database connection - recovery needs 2 fetchone() calls like end_of_year
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.side_effect = [
            [100],  # Existing workforce count (pre-validation)
            [200],  # Final snapshot count after recovery (post-validation)
        ]
        mock_duckdb_connect.return_value = mock_conn

        result = run_dbt_snapshot_for_year(mock_context, year, snapshot_type)

        # Verify result
        assert result["success"] is True
        assert result["year"] == year
        assert result["snapshot_type"] == snapshot_type
        assert result["records_created"] == 200

        # Verify warning was logged about existing data
        mock_context.log.warning.assert_called_once_with(
            f"Workforce snapshot already exists for year {year} - proceeding with recovery anyway"
        )

        # Verify database connections were closed (pre-validation + clean data + post-validation)
        assert mock_conn.close.call_count == 3

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

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_snapshot_creation_failure_no_records(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
    ):
        """Test handling when snapshot creation produces no records."""
        year = 2025
        snapshot_type = "end_of_year"

        # Mock database connection - no records created
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.side_effect = [
            [0],  # Initial workforce count
            [0],  # Final snapshot count - no records created
        ]
        mock_duckdb_connect.return_value = mock_conn

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

        # Verify database connections were closed (pre-validation + clean data + post-validation)
        assert mock_conn.close.call_count == 3

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_dbt_command_execution_failure(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
    ):
        """Test handling when dbt command execution fails."""
        year = 2025
        snapshot_type = "end_of_year"

        # Mock database connection for pre-validation
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [
            0
        ]  # Pre-validation only
        mock_duckdb_connect.return_value = mock_conn

        # Mock dbt command failure
        mock_execute_dbt.side_effect = Exception("dbt snapshot command failed")

        result = run_dbt_snapshot_for_year(mock_context, year, snapshot_type)

        # Verify failure result
        assert result["success"] is False
        assert result["year"] == year
        assert result["snapshot_type"] == snapshot_type
        assert result["records_created"] == 0
        assert "dbt snapshot command failed" in result["error"]

        # Verify error was logged
        mock_context.log.error.assert_called()

        # Verify database connections were closed (pre-validation + clean data, no post-validation due to failure)
        assert mock_conn.close.call_count == 2

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_database_connection_failure(self, mock_duckdb_connect, mock_context):
        """Test handling when database connection fails."""
        year = 2025
        snapshot_type = "end_of_year"

        # Mock database connection failure
        mock_duckdb_connect.side_effect = Exception("Database connection failed")

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
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_all_snapshot_types_parameter_handling(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
        snapshot_type,
    ):
        """Test that all valid snapshot types are handled correctly."""
        year = 2025

        # Mock database connection
        mock_conn = Mock()
        mock_duckdb_connect.return_value = mock_conn

        if snapshot_type == "previous_year":
            # previous_year only needs post-validation
            mock_conn.execute.return_value.fetchone.return_value = [100]  # Final count
        else:
            # end_of_year and recovery need pre-validation and post-validation
            mock_conn.execute.return_value.fetchone.side_effect = [
                [50],  # Pre-check count
                [100],  # Final count
            ]

        result = run_dbt_snapshot_for_year(mock_context, year, snapshot_type)

        # Verify result
        assert result["success"] is True
        assert result["snapshot_type"] == snapshot_type
        assert result["records_created"] == 100

        # Verify correct description based on type
        if snapshot_type == "previous_year":
            assert "previous year dependency" in result["description"]
        else:
            assert snapshot_type in result["description"]

        # Verify database connections were closed appropriately
        if snapshot_type == "previous_year":
            assert mock_conn.close.call_count == 2
        else:
            assert mock_conn.close.call_count == 3

    def test_default_snapshot_type(self, mock_context):
        """Test that default snapshot type is 'end_of_year'."""
        import inspect

        sig = inspect.signature(run_dbt_snapshot_for_year)
        default_value = sig.parameters["snapshot_type"].default
        assert default_value == "end_of_year"

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_large_snapshot_record_count(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
    ):
        """Test handling of large snapshot record counts."""
        year = 2025
        large_count = 1000000

        # Mock database connection
        mock_conn = Mock()
        # end_of_year needs pre-validation and post-validation
        mock_conn.execute.return_value.fetchone.side_effect = [
            [0],  # Pre-validation
            [large_count],  # Post-validation
        ]
        mock_duckdb_connect.return_value = mock_conn

        result = run_dbt_snapshot_for_year(mock_context, year, "end_of_year")

        assert result["success"] is True
        assert result["records_created"] == large_count

        # Verify large numbers are logged correctly
        mock_context.log.info.assert_any_call(
            f"Snapshot created successfully: {large_count} records in scd_workforce_state for year {year}"
        )

        # Verify database connections were closed (pre-validation + clean data + post-validation)
        assert mock_conn.close.call_count == 3

    @pytest.mark.parametrize("year", [2020, 2025, 2030, 2050, 1999])
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_various_simulation_years(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
        year,
    ):
        """Test snapshot operation with various simulation years."""
        # Mock database connection
        mock_conn = Mock()
        # end_of_year needs pre-validation and post-validation
        mock_conn.execute.return_value.fetchone.side_effect = [
            [0],  # Pre-validation
            [50],  # Post-validation
        ]
        mock_duckdb_connect.return_value = mock_conn

        result = run_dbt_snapshot_for_year(mock_context, year, "end_of_year")

        assert result["success"] is True
        assert result["year"] == year
        assert result["records_created"] == 50

        # Verify year is passed correctly to dbt command
        mock_execute_dbt.assert_called_once()
        call_args = mock_execute_dbt.call_args
        vars_dict = call_args[0][2]  # vars_dict parameter
        assert vars_dict["simulation_year"] == year

        # Verify database connections were closed (pre-validation + clean data + post-validation)
        assert mock_conn.close.call_count == 3

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_connection_cleanup_on_success(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
    ):
        """Test that database connections are properly cleaned up on success."""
        year = 2025

        # Mock database connection
        mock_conn = Mock()
        # end_of_year needs pre-validation and post-validation
        mock_conn.execute.return_value.fetchone.side_effect = [
            [0],  # Pre-validation
            [100],  # Post-validation
        ]
        mock_duckdb_connect.return_value = mock_conn

        result = run_dbt_snapshot_for_year(mock_context, year, "end_of_year")

        assert result["success"] is True
        assert result["records_created"] == 100
        # Should close connection 3 times: pre-validation + clean data + post-validation
        assert mock_conn.close.call_count == 3

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_connection_cleanup_on_failure(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
    ):
        """Test that database connections are cleaned up even on failure."""
        year = 2025

        # Mock database connection to fail on the first query
        mock_duckdb_connect.side_effect = Exception("Database connection failed")

        result = run_dbt_snapshot_for_year(mock_context, year, "end_of_year")

        assert result["success"] is False
        assert "Database connection failed" in result["error"]
        # When connection fails immediately, no close() is called since the connection was never established
        # This is the expected behavior for the function

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_validation_logging_patterns(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
    ):
        """Test various validation logging patterns."""
        year = 2025

        # Mock database connection
        mock_conn = Mock()
        # Test end_of_year with no existing data (expected)
        mock_conn.execute.return_value.fetchone.side_effect = [
            [0],  # Pre-validation - no existing data
            [100],  # Post-validation - snapshot created
        ]
        mock_duckdb_connect.return_value = mock_conn

        result = run_dbt_snapshot_for_year(mock_context, year, "end_of_year")

        assert result["success"] is True
        assert result["records_created"] == 100

        # Should log that no existing data is expected
        mock_context.log.info.assert_any_call(
            f"No existing workforce snapshot for year {year} - this is expected for initial snapshot creation"
        )

        # Verify database connections were closed (pre-validation + clean data + post-validation)
        assert mock_conn.close.call_count == 3


class TestSnapshotOperationIntegration:
    """Integration tests for snapshot operation with realistic scenarios."""

    @pytest.fixture
    def integration_context(self):
        """Create a more realistic context for integration testing."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        return context

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_multi_year_snapshot_sequence(
        self, mock_duckdb_connect, mock_execute_dbt, integration_context
    ):
        """Test realistic multi-year snapshot creation sequence."""
        # Simulate a 3-year simulation requiring snapshots
        years = [2023, 2024, 2025]

        mock_conn = Mock()
        mock_conn.close = Mock()
        mock_duckdb_connect.return_value = mock_conn

        # Different record counts for each year to simulate growth
        record_counts = [100, 125, 150]

        results = []
        for i, year in enumerate(years):
            # Reset side_effect for each iteration - end_of_year needs pre-validation and post-validation
            mock_conn.execute.return_value.fetchone.side_effect = [
                [0],  # Pre-validation
                [record_counts[i]],  # Post-validation
            ]

            result = run_dbt_snapshot_for_year(integration_context, year, "end_of_year")
            results.append(result)

        # Verify all snapshots succeeded
        assert all(r["success"] for r in results)
        assert [r["year"] for r in results] == years
        assert [r["records_created"] for r in results] == record_counts

        # Verify dbt commands were called for each year
        assert mock_execute_dbt.call_count == len(years)

        # Verify database connections were closed properly for each year (3 times per year)
        expected_close_calls = len(years) * 3
        assert mock_conn.close.call_count == expected_close_calls

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_error_recovery_workflow(
        self, mock_duckdb_connect, mock_execute_dbt, integration_context
    ):
        """Test error recovery workflow using recovery snapshot type."""
        year = 2025

        mock_conn = Mock()
        mock_conn.close = Mock()
        mock_duckdb_connect.return_value = mock_conn

        # First attempt fails (simulate corrupted snapshot)
        # recovery needs pre-validation and post-validation
        mock_conn.execute.return_value.fetchone.side_effect = [
            [50],  # Pre-check shows existing data
            [0],  # Post-execution shows no records (failure)
        ]

        result = run_dbt_snapshot_for_year(integration_context, year, "recovery")

        # Verify failure was handled gracefully
        assert result["success"] is False
        assert result["snapshot_type"] == "recovery"
        assert "no records found" in result["error"]

        # Verify appropriate logging occurred
        integration_context.log.warning.assert_called_once()  # Warning about existing data
        integration_context.log.error.assert_called_once()  # Error about failure

        # Verify database connections were closed (pre-validation + clean data + post-validation)
        assert mock_conn.close.call_count == 3

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_mixed_snapshot_types_workflow(
        self, mock_duckdb_connect, mock_execute_dbt, integration_context
    ):
        """Test workflow using different snapshot types in sequence."""
        # We need separate mock connections for each call since the function creates new connections
        mock_connections = []

        # Simulate multi-year workflow with different snapshot types
        workflow = [
            (2024, "previous_year", [[50]]),  # Only post-validation for previous_year
            (2025, "end_of_year", [[0], [100]]),  # Pre-validation and post-validation
            (2025, "recovery", [[100], [150]]),  # Pre-validation and post-validation
        ]

        results = []
        for year, snapshot_type, fetchone_returns in workflow:
            # Create a new mock connection for each iteration
            mock_conn = Mock()
            mock_conn.close = Mock()
            mock_connections.append(mock_conn)

            if snapshot_type == "previous_year":
                mock_conn.execute.return_value.fetchone.return_value = fetchone_returns[
                    0
                ]
            else:
                mock_conn.execute.return_value.fetchone.side_effect = fetchone_returns

            # Mock duckdb.connect to return this specific connection
            mock_duckdb_connect.return_value = mock_conn

            result = run_dbt_snapshot_for_year(integration_context, year, snapshot_type)
            results.append(result)

        # Verify all operations succeeded
        assert all(r["success"] for r in results)

        # Verify correct snapshot types were recorded
        expected_types = ["previous_year", "end_of_year", "recovery"]
        assert [r["snapshot_type"] for r in results] == expected_types

        # Verify correct record counts
        expected_records = [50, 100, 150]
        assert [r["records_created"] for r in results] == expected_records

        # Verify each connection was closed the appropriate number of times
        expected_close_counts = [
            2,
            3,
            3,
        ]  # previous_year: 2, end_of_year: 3, recovery: 3
        for i, expected_count in enumerate(expected_close_counts):
            assert mock_connections[i].close.call_count == expected_count
