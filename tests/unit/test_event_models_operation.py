"""
Unit tests for S013-03: _run_dbt_event_models_for_year_internal function

Comprehensive test suite for the event processing modularization,
covering Epic 11.5 sequence validation, hiring calculations, and debug logging.
"""

import pytest
from unittest.mock import Mock, patch
from dagster import OpExecutionContext

from orchestrator.simulator_pipeline import _run_dbt_event_models_for_year_internal


class TestEventModelsOperation:
    """Test suite for _run_dbt_event_models_for_year_internal function."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock Dagster execution context."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        context.log.info = Mock()
        context.log.error = Mock()
        return context

    @pytest.fixture
    def sample_config(self):
        """Create a sample configuration dictionary."""
        return {
            "random_seed": 42,
            "target_growth_rate": 0.03,
            "total_termination_rate": 0.12,
            "new_hire_termination_rate": 0.25,
            "full_refresh": False,
        }

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
    def test_epic_11_5_sequence_execution(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
        sample_config,
    ):
        """Test that Epic 11.5 event model sequence is executed correctly."""
        year = 2025

        # Mock database connection for debug logging
        mock_duckdb_connect.return_value = mock_duckdb_connection
        mock_duckdb_connection.fetchone.return_value = [1000]  # Mock hire count

        # Execute and verify the function runs without errors
        _run_dbt_event_models_for_year_internal(mock_context, year, sample_config)

        # Verify Epic 11.5 sequence models are executed in correct order
        expected_models = [
            "int_termination_events",
            "int_promotion_events",
            "int_merit_events",
            "int_hiring_events",
            "int_new_hire_termination_events",
        ]

        # Check that execute_dbt_command was called for each model
        assert mock_execute_dbt.call_count == len(expected_models)

        # Verify models were called in correct sequence
        for i, expected_model in enumerate(expected_models):
            call_args = mock_execute_dbt.call_args_list[i]
            command = call_args[0][1]  # Second argument is the command list
            assert command == ["run", "--select", expected_model]

            # Verify vars dict contains simulation_year
            vars_dict = call_args[0][2]  # Third argument is vars_dict
            assert vars_dict["simulation_year"] == year

            # Verify full_refresh parameter
            full_refresh = call_args[0][3]  # Fourth argument is full_refresh
            assert full_refresh == sample_config["full_refresh"]

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_hiring_calculation_debug_logging(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
        sample_config,
    ):
        """Test hiring calculation debug logging functionality."""
        year = 2025
        expected_workforce_count = 150

        # Mock database connection for debug query
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [expected_workforce_count]
        mock_duckdb_connect.return_value = mock_conn

        # Execute and verify debug query was executed
        result = _run_dbt_event_models_for_year_internal(mock_context, year, sample_config)
        expected_debug_query = "SELECT COUNT(*) FROM int_baseline_workforce WHERE employment_status = 'active'"
        mock_conn.execute.assert_called_with(expected_debug_query)

        # Verify debug logging
        mock_context.log.info.assert_any_call("🔍 HIRING CALCULATION DEBUG:")
        mock_context.log.info.assert_any_call(
            f"  📊 Starting workforce: {expected_workforce_count} active employees"
        )

        # Verify workforce count is included in result
        assert result["hiring_debug"]["workforce_count"] == expected_workforce_count

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_configuration_parameter_passing(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
        sample_config,
    ):
        """Test that configuration parameters are correctly passed to dbt models."""
        year = 2025
        mock_duckdb_connect.return_value = mock_duckdb_connection
        mock_duckdb_connection.fetchone.return_value = [75]

        # Execute and verify configuration parameters
        _run_dbt_event_models_for_year_internal(mock_context, year, sample_config)

        # Verify each execute_dbt_command call received correct configuration
        for call_args in mock_execute_dbt.call_args_list:
            vars_dict = call_args[0][2]  # vars_dict argument

            # Check required configuration parameters
            assert vars_dict["simulation_year"] == year
            assert vars_dict["random_seed"] == sample_config["random_seed"]
            assert (
                vars_dict["target_growth_rate"] == sample_config["target_growth_rate"]
            )
            assert (
                vars_dict["total_termination_rate"]
                == sample_config["total_termination_rate"]
            )
            assert (
                vars_dict["new_hire_termination_rate"]
                == sample_config["new_hire_termination_rate"]
            )

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_return_structure_validation(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
        sample_config,
    ):
        """Test that return structure contains all required elements."""
        year = 2025
        workforce_count = 200

        # Mock database connection for debug query
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [workforce_count]
        mock_duckdb_connect.return_value = mock_conn

        result = _run_dbt_event_models_for_year_internal(mock_context, year, sample_config)

        # Verify return structure
        assert "year" in result
        assert "models_executed" in result
        assert "hiring_debug" in result

        assert result["year"] == year
        assert len(result["models_executed"]) == 5  # All Epic 11.5 models

        # Verify hiring debug structure
        hiring_debug = result["hiring_debug"]
        assert "workforce_count" in hiring_debug
        assert "experienced_terms" in hiring_debug
        assert "growth_amount" in hiring_debug
        assert "total_hires_needed" in hiring_debug
        assert "expected_new_hire_terms" in hiring_debug
        assert "net_hiring_impact" in hiring_debug
        assert hiring_debug["workforce_count"] == workforce_count

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_model_execution_failure_handling(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
        sample_config,
    ):
        """Test error handling when a model execution fails."""
        year = 2025
        mock_duckdb_connect.return_value = mock_duckdb_connection

        # Mock execute_dbt_command to fail on the third model (int_merit_events)
        def mock_execute_side_effect(*args):
            if "int_merit_events" in args[1]:
                raise Exception("Merit events model failed")

        mock_execute_dbt.side_effect = mock_execute_side_effect

        # Should raise the exception
        with pytest.raises(Exception) as exc_info:
            _run_dbt_event_models_for_year_internal(mock_context, year, sample_config)

        assert "Merit events model failed" in str(exc_info.value)

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_database_connection_failure_in_debug(
        self, mock_duckdb_connect, mock_execute_dbt, mock_context, sample_config
    ):
        """Test handling of database connection failure during debug logging."""
        year = 2025

        # Mock database connection failure
        mock_duckdb_connect.side_effect = Exception("Database connection failed")

        # Should raise the exception
        with pytest.raises(Exception) as exc_info:
            _run_dbt_event_models_for_year_internal(mock_context, year, sample_config)

        assert "Database connection failed" in str(exc_info.value)

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_zero_hiring_events_scenario(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
        sample_config,
    ):
        """Test scenario where no hiring events are generated."""
        year = 2025

        # Mock zero hiring events - Mock database connection for debug query
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [0]
        mock_duckdb_connect.return_value = mock_conn

        result = _run_dbt_event_models_for_year_internal(mock_context, year, sample_config)

        # Verify debug logging handles zero case
        mock_context.log.info.assert_any_call(
            f"  📊 Starting workforce: 0 active employees"
        )

        # Verify result structure
        assert result["hiring_debug"]["workforce_count"] == 0

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_large_hiring_events_scenario(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
        sample_config,
    ):
        """Test scenario with large number of hiring events."""
        year = 2025
        large_workforce_count = 10000

        # Mock database connection for debug query
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [large_workforce_count]
        mock_duckdb_connect.return_value = mock_conn

        result = _run_dbt_event_models_for_year_internal(mock_context, year, sample_config)

        # Verify large numbers are handled correctly
        assert result["hiring_debug"]["workforce_count"] == large_workforce_count
        mock_context.log.info.assert_any_call(
            f"  📊 Starting workforce: {large_workforce_count} active employees"
        )

    @pytest.mark.parametrize("year", [2020, 2025, 2030, 2050])
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_various_simulation_years(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
        sample_config,
        year,
    ):
        """Test operation with various simulation years."""
        # Mock database connection for debug query
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [100]
        mock_duckdb_connect.return_value = mock_conn

        result = _run_dbt_event_models_for_year_internal(mock_context, year, sample_config)

        # Verify year is correctly passed through
        assert result["year"] == year
        assert result["hiring_debug"]["year"] == year

        # Verify each dbt command received correct year
        for call_args in mock_execute_dbt.call_args_list:
            vars_dict = call_args[0][2]
            assert vars_dict["simulation_year"] == year

    @pytest.mark.parametrize(
        "config_key,config_value",
        [
            ("random_seed", 123),
            ("target_growth_rate", 0.05),
            ("total_termination_rate", 0.15),
            ("new_hire_termination_rate", 0.30),
            ("full_refresh", True),
        ],
    )
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_configuration_parameter_variations(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        mock_context,
        mock_duckdb_connection,
        sample_config,
        config_key,
        config_value,
    ):
        """Test various configuration parameter values."""
        year = 2025
        mock_duckdb_connect.return_value = mock_duckdb_connection
        mock_duckdb_connection.fetchone.return_value = [50]

        # Update config with test value
        test_config = sample_config.copy()
        test_config[config_key] = config_value

        # Execute with configuration and verify it was passed correctly
        _run_dbt_event_models_for_year_internal(mock_context, year, test_config)

        # For full_refresh, check the execute_dbt_command call parameter instead of vars_dict
        if config_key == "full_refresh":
            for call_args in mock_execute_dbt.call_args_list:
                full_refresh_param = call_args[0][3]  # 4th parameter is full_refresh
                assert full_refresh_param == config_value
        else:
            for call_args in mock_execute_dbt.call_args_list:
                vars_dict = call_args[0][2]
                assert vars_dict[config_key] == config_value


class TestEventModelsOperationIntegration:
    """Integration tests for event models operation with realistic scenarios."""

    @pytest.fixture
    def integration_context(self):
        """Create a more realistic context for integration testing."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        return context

    @pytest.fixture
    def realistic_config(self):
        """Create a realistic simulation configuration."""
        return {
            "random_seed": 42,
            "target_growth_rate": 0.03,
            "total_termination_rate": 0.12,
            "new_hire_termination_rate": 0.25,
            "full_refresh": False,
            "start_year": 2023,
            "end_year": 2027,
        }

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_realistic_multi_year_workflow(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        integration_context,
        realistic_config,
    ):
        """Test realistic multi-year event processing workflow."""
        years = [2023, 2024, 2025]
        workforce_counts = [120, 135, 150]  # Increasing hiring over years

        mock_conn = Mock()
        mock_conn.close = Mock()
        mock_duckdb_connect.return_value = mock_conn

        results = []
        for i, year in enumerate(years):
            # Mock different hire counts for each year
            mock_conn.execute.return_value.fetchone.return_value = [workforce_counts[i]]

            result = _run_dbt_event_models_for_year_internal(
                integration_context, year, realistic_config
            )
            results.append(result)

        # Verify all years processed correctly
        for i, result in enumerate(results):
            assert result["year"] == years[i]
            assert result["hiring_debug"]["workforce_count"] == workforce_counts[i]
            assert len(result["models_executed"]) == 5

        # Verify total dbt command executions (5 models * 3 years)
        assert mock_execute_dbt.call_count == 15

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_sequential_execution_order_validation(
        self,
        mock_duckdb_connect,
        mock_execute_dbt,
        integration_context,
        realistic_config,
    ):
        """Test that Epic 11.5 sequence is maintained across multiple executions."""
        year = 2025

        mock_conn = Mock()
        mock_conn.close = Mock()
        mock_duckdb_connect.return_value = mock_conn
        mock_conn.execute.return_value.fetchone.return_value = [100]

        # Execute multiple times
        for _ in range(3):
            _run_dbt_event_models_for_year_internal(integration_context, year, realistic_config)

        # Verify sequence order is maintained in all executions
        expected_sequence = [
            "int_termination_events",
            "int_promotion_events",
            "int_merit_events",
            "int_hiring_events",
            "int_new_hire_termination_events",
        ]

        # Check every 5 calls (one complete sequence)
        for execution in range(3):
            start_idx = execution * 5
            for i, expected_model in enumerate(expected_sequence):
                call_idx = start_idx + i
                call_args = mock_execute_dbt.call_args_list[call_idx]
                command = call_args[0][1]
                assert command == ["run", "--select", expected_model]
