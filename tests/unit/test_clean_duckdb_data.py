"""
Unit tests for S013-02: clean_duckdb_data operation

Comprehensive test suite for the data cleaning operation,
covering various data scenarios, edge cases, and error handling.
"""

import pytest
from unittest.mock import Mock, patch
from dagster import OpExecutionContext

from orchestrator.simulator_pipeline import clean_duckdb_data


class TestCleanDuckDBData:
    """Test suite for clean_duckdb_data operation."""

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
        conn.close = Mock()
        return conn

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_single_year_cleaning(
        self, mock_duckdb_connect, mock_context, mock_duckdb_connection
    ):
        """Test cleaning data for a single year."""
        years = [2025]

        # Mock database connection
        mock_duckdb_connect.return_value = mock_duckdb_connection

        # Execute
        result = clean_duckdb_data(mock_context, years)

        # Verify database operations
        expected_calls = [
            "DELETE FROM fct_yearly_events WHERE simulation_year = ?",
            "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?",
        ]

        for expected_sql in expected_calls:
            mock_duckdb_connection.execute.assert_any_call(expected_sql, [2025])

        # Verify result
        assert result["fct_yearly_events"] == 1
        assert result["fct_workforce_snapshot"] == 1

        # Verify connection cleanup
        mock_duckdb_connection.close.assert_called_once()

        # Verify logging
        mock_context.log.info.assert_any_call(
            "Cleaning existing data for years 2025"
        )

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_multiple_years_cleaning(
        self, mock_duckdb_connect, mock_context, mock_duckdb_connection
    ):
        """Test cleaning data for multiple years."""
        years = [2023, 2024, 2025]

        mock_duckdb_connect.return_value = mock_duckdb_connection

        result = clean_duckdb_data(mock_context, years)

        # Verify each year was processed
        for year in years:
            mock_duckdb_connection.execute.assert_any_call(
                "DELETE FROM fct_yearly_events WHERE simulation_year = ?", [year]
            )
            mock_duckdb_connection.execute.assert_any_call(
                "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?", [year]
            )

        # Verify results reflect multiple years
        assert result["fct_yearly_events"] == 3
        assert result["fct_workforce_snapshot"] == 3

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_empty_years_list(
        self, mock_duckdb_connect, mock_context, mock_duckdb_connection
    ):
        """Test behavior with empty years list."""
        years = []

        mock_duckdb_connect.return_value = mock_duckdb_connection

        result = clean_duckdb_data(mock_context, years)

        # Should return zero counts
        assert result["fct_yearly_events"] == 0
        assert result["fct_workforce_snapshot"] == 0

        # No delete operations should be performed
        mock_duckdb_connection.execute.assert_not_called()

        # No connection should be opened when years list is empty
        mock_duckdb_connect.assert_not_called()

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_large_year_range(
        self, mock_duckdb_connect, mock_context, mock_duckdb_connection
    ):
        """Test cleaning large year range."""
        years = list(range(2020, 2031))  # 11 years

        mock_duckdb_connect.return_value = mock_duckdb_connection

        result = clean_duckdb_data(mock_context, years)

        # Verify all years processed
        assert result["fct_yearly_events"] == 11
        assert result["fct_workforce_snapshot"] == 11

        # Verify database calls for each year
        assert mock_duckdb_connection.execute.call_count == 22  # 11 years * 2 tables

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_database_connection_failure(self, mock_duckdb_connect, mock_context):
        """Test handling of database connection failure."""
        years = [2025]

        # Mock connection failure
        mock_duckdb_connect.side_effect = Exception("Database connection failed")

        # Should raise the exception
        with pytest.raises(Exception) as exc_info:
            clean_duckdb_data(mock_context, years)

        assert "Database connection failed" in str(exc_info.value)

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_partial_cleaning_failure(
        self, mock_duckdb_connect, mock_context, mock_duckdb_connection
    ):
        """Test handling when some cleaning operations fail."""
        years = [2024, 2025]

        mock_duckdb_connect.return_value = mock_duckdb_connection

        # Mock execute to fail on second year for events table
        call_count = 0

        def mock_execute(sql, params):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # Second call (second year, events table)
                raise Exception("Delete operation failed")

        mock_duckdb_connection.execute.side_effect = mock_execute

        result = clean_duckdb_data(mock_context, years)

        # Should continue processing despite failure
        # Events: Year 1 succeeds, Year 2 fails = 1 success
        # Snapshots: Both years succeed = 2 successes
        assert result["fct_yearly_events"] == 1  # Only first year succeeded
        assert result["fct_workforce_snapshot"] == 2  # Both years succeeded

        # Should log warnings for failures
        mock_context.log.warning.assert_called()

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_duplicate_years_handling(
        self, mock_duckdb_connect, mock_context, mock_duckdb_connection
    ):
        """Test handling of duplicate years in input list."""
        years = [2025, 2024, 2025, 2024]  # Duplicates

        mock_duckdb_connect.return_value = mock_duckdb_connection

        result = clean_duckdb_data(mock_context, years)

        # Should process each year in the list (including duplicates)
        assert result["fct_yearly_events"] == 4
        assert result["fct_workforce_snapshot"] == 4

        # Should execute delete for each occurrence
        assert mock_duckdb_connection.execute.call_count == 8  # 4 years * 2 tables

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_negative_years(
        self, mock_duckdb_connect, mock_context, mock_duckdb_connection
    ):
        """Test handling of negative years."""
        years = [-1, 0, 2025]

        mock_duckdb_connect.return_value = mock_duckdb_connection

        result = clean_duckdb_data(mock_context, years)

        # Should process all years including negative ones
        assert result["fct_yearly_events"] == 3
        assert result["fct_workforce_snapshot"] == 3

        # Should execute delete for negative years too
        mock_duckdb_connection.execute.assert_any_call(
            "DELETE FROM fct_yearly_events WHERE simulation_year = ?", [-1]
        )

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_very_large_years(
        self, mock_duckdb_connect, mock_context, mock_duckdb_connection
    ):
        """Test handling of very large year values."""
        years = [999999, 2025, 1000000]

        mock_duckdb_connect.return_value = mock_duckdb_connection

        result = clean_duckdb_data(mock_context, years)

        assert result["fct_yearly_events"] == 3
        assert result["fct_workforce_snapshot"] == 3

        # Should handle large numbers correctly
        mock_duckdb_connection.execute.assert_any_call(
            "DELETE FROM fct_yearly_events WHERE simulation_year = ?", [999999]
        )

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_connection_cleanup_on_exception(
        self, mock_duckdb_connect, mock_context, mock_duckdb_connection
    ):
        """Test that database connection is cleaned up even when exceptions occur."""
        years = [2025]

        mock_duckdb_connect.return_value = mock_duckdb_connection
        mock_duckdb_connection.execute.side_effect = Exception("SQL execution failed")

        # Execute and expect exception
        result = clean_duckdb_data(mock_context, years)

        # Connection should still be closed despite the exception
        mock_duckdb_connection.close.assert_called_once()

        # Should return partial results
        assert "fct_yearly_events" in result
        assert "fct_workforce_snapshot" in result

    @pytest.mark.parametrize(
        "years,expected_events,expected_workforce",
        [
            ([2025], 1, 1),
            ([2024, 2025], 2, 2),
            ([2023, 2024, 2025], 3, 3),
            ([], 0, 0),
            ([2025, 2025], 2, 2),  # Duplicates
        ],
    )
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_various_year_configurations(
        self,
        mock_duckdb_connect,
        mock_context,
        mock_duckdb_connection,
        years,
        expected_events,
        expected_workforce,
    ):
        """Test various year list configurations."""
        mock_duckdb_connect.return_value = mock_duckdb_connection

        result = clean_duckdb_data(mock_context, years)

        assert result["fct_yearly_events"] == expected_events
        assert result["fct_workforce_snapshot"] == expected_workforce


class TestCleanDuckDBDataIntegration:
    """Integration tests for clean_duckdb_data with realistic scenarios."""

    @pytest.fixture
    def integration_context(self):
        """Create a more realistic context for integration testing."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        return context

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_realistic_multi_year_simulation_cleanup(
        self, mock_duckdb_connect, integration_context
    ):
        """Test realistic multi-year simulation data cleanup."""
        # Simulate cleaning for a 5-year simulation
        years = list(range(2021, 2026))

        mock_conn = Mock()
        mock_conn.close = Mock()
        mock_duckdb_connect.return_value = mock_conn

        result = clean_duckdb_data(integration_context, years)

        # Verify comprehensive cleaning
        assert result["fct_yearly_events"] == 5
        assert result["fct_workforce_snapshot"] == 5

        # Verify all years were processed
        for year in years:
            mock_conn.execute.assert_any_call(
                "DELETE FROM fct_yearly_events WHERE simulation_year = ?", [year]
            )
            mock_conn.execute.assert_any_call(
                "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?", [year]
            )

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_incremental_cleaning_workflow(
        self, mock_duckdb_connect, integration_context
    ):
        """Test incremental cleaning workflow for extending simulations."""
        mock_conn = Mock()
        mock_conn.close = Mock()
        mock_duckdb_connect.return_value = mock_conn

        # First clean years 2023-2025
        result1 = clean_duckdb_data(integration_context, [2023, 2024, 2025])
        assert result1["fct_yearly_events"] == 3

        # Then extend to include 2026-2027
        result2 = clean_duckdb_data(integration_context, [2026, 2027])
        assert result2["fct_yearly_events"] == 2

        # Verify total database operations
        expected_total_calls = 10  # (3 + 2) years * 2 tables
        assert mock_conn.execute.call_count == expected_total_calls
