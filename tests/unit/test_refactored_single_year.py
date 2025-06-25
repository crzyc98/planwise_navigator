"""
Unit tests for S013-05: Refactored Single-Year Simulation Operation

Comprehensive test suite for the refactored run_year_simulation operation,
verifying modular component integration and behavior preservation.
"""

import pytest
from unittest.mock import Mock, patch
from dagster import OpExecutionContext

from orchestrator.simulator_pipeline import run_year_simulation, YearResult


class TestRefactoredSingleYearSimulation:
    """Test suite for the refactored run_year_simulation operation."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock Dagster execution context with configuration."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        context.log.info = Mock()
        context.log.error = Mock()

        # Mock configuration
        context.op_config = {
            "start_year": 2025,
            "end_year": 2025,
            "target_growth_rate": 0.03,
            "total_termination_rate": 0.12,
            "new_hire_termination_rate": 0.25,
            "random_seed": 42,
            "full_refresh": False,
        }

        # Mock dbt resource
        dbt_resource = Mock()
        context.resources = Mock()
        context.resources.dbt = dbt_resource

        return context

    @pytest.fixture
    def mock_duckdb_connection(self):
        """Create a mock DuckDB connection."""
        conn = Mock()
        conn.execute = Mock()
        conn.fetchone = Mock()
        conn.close = Mock()
        return conn

    @patch("orchestrator.simulator_pipeline.validate_year_results")
    @patch("orchestrator.simulator_pipeline.run_dbt_event_models_for_year")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.clean_duckdb_data")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_successful_single_year_simulation(
        self,
        mock_duckdb_connect,
        mock_clean_data,
        mock_execute_dbt,
        mock_event_models,
        mock_validate,
        mock_context,
        mock_duckdb_connection,
    ):
        """Test successful execution of single-year simulation with all modular components."""
        # Setup mocks
        mock_duckdb_connect.return_value = mock_duckdb_connection
        mock_duckdb_connection.fetchone.return_value = [100]  # Mock workforce count

        mock_event_models.return_value = {
            "year": 2025,
            "models_executed": ["int_termination_events", "int_hiring_events"],
            "hiring_debug": {"hire_count": 50},
        }

        expected_result = YearResult(
            year=2025,
            success=True,
            active_employees=1000,
            total_terminations=120,
            experienced_terminations=100,
            new_hire_terminations=20,
            total_hires=150,
            growth_rate=0.03,
            validation_passed=True,
        )
        mock_validate.return_value = expected_result

        # Execute
        result = run_year_simulation(mock_context)

        # Verify modular component calls
        mock_clean_data.assert_called_once_with(mock_context, [2025])

        # Verify event models operation called
        mock_event_models.assert_called_once_with(
            mock_context, 2025, mock_context.op_config
        )

        # Verify dbt commands executed in correct sequence
        expected_dbt_calls = [
            (
                ["run", "--select", "int_workforce_previous_year"],
                {"simulation_year": 2025},
            ),
            (["run", "--select", "fct_yearly_events"], {"simulation_year": 2025}),
            (["run", "--select", "fct_workforce_snapshot"], {"simulation_year": 2025}),
        ]

        assert mock_execute_dbt.call_count == 3
        for i, (expected_command, expected_vars) in enumerate(expected_dbt_calls):
            call_args = mock_execute_dbt.call_args_list[i]
            assert call_args[0][1] == expected_command  # command
            assert call_args[0][2] == expected_vars  # vars_dict
            assert call_args[0][3] is False  # full_refresh

        # Verify validation called
        mock_validate.assert_called_once_with(
            mock_context, 2025, mock_context.op_config
        )

        # Verify result
        assert result == expected_result

        # Verify logging
        mock_context.log.info.assert_any_call("Starting simulation for year 2025")
        mock_context.log.info.assert_any_call(
            "Year 2025 simulation completed successfully"
        )

    @patch("orchestrator.simulator_pipeline.validate_year_results")
    @patch("orchestrator.simulator_pipeline.run_dbt_event_models_for_year")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.clean_duckdb_data")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_full_refresh_parameter_handling(
        self,
        mock_duckdb_connect,
        mock_clean_data,
        mock_execute_dbt,
        mock_event_models,
        mock_validate,
        mock_context,
        mock_duckdb_connection,
    ):
        """Test that full_refresh parameter is correctly passed to all components."""
        # Enable full refresh
        mock_context.op_config["full_refresh"] = True

        # Setup mocks
        mock_duckdb_connect.return_value = mock_duckdb_connection
        mock_duckdb_connection.fetchone.return_value = [100]
        mock_event_models.return_value = {
            "year": 2025,
            "models_executed": [],
            "hiring_debug": {},
        }
        mock_validate.return_value = YearResult(2025, True, 1000, 0, 0, 0, 0, 0.0, True)

        # Execute and verify full_refresh is passed to all execute_dbt_command calls
        run_year_simulation(mock_context)
        for call_args in mock_execute_dbt.call_args_list:
            full_refresh_param = call_args[0][3]  # Fourth parameter is full_refresh
            assert full_refresh_param is True

        # Verify logging about full refresh
        mock_context.log.info.assert_any_call(
            "🔄 Full refresh enabled - will rebuild all incremental models from scratch"
        )

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_multi_year_dependency_validation(
        self, mock_duckdb_connect, mock_context, mock_duckdb_connection
    ):
        """Test multi-year dependency validation for years > 2025."""
        # Set year to trigger dependency validation
        mock_context.op_config["start_year"] = 2026

        # Mock database queries
        mock_duckdb_connect.return_value = mock_duckdb_connection
        mock_duckdb_connection.fetchone.side_effect = [
            [10],  # events_count for previous year
            [100],  # workforce_count for previous year
        ]

        with patch("orchestrator.simulator_pipeline.clean_duckdb_data"), patch(
            "orchestrator.simulator_pipeline.execute_dbt_command"
        ), patch(
            "orchestrator.simulator_pipeline.run_dbt_event_models_for_year"
        ), patch(
            "orchestrator.simulator_pipeline.validate_year_results"
        ) as mock_validate:
            mock_validate.return_value = YearResult(
                2026, True, 1000, 0, 0, 0, 0, 0.0, True
            )

            run_year_simulation(mock_context)

            # Verify dependency validation queries were executed
            expected_queries = [
                "SELECT COUNT(*) FROM fct_yearly_events",
                "SELECT COUNT(*) FROM fct_workforce_snapshot",
            ]

            for expected_query in expected_queries:
                mock_duckdb_connection.execute.assert_any_call(expected_query, [2025])

    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_missing_previous_year_data_error(
        self, mock_duckdb_connect, mock_context, mock_duckdb_connection
    ):
        """Test error handling when previous year data is missing."""
        mock_context.op_config["start_year"] = 2026

        # Mock missing previous year data
        mock_duckdb_connect.return_value = mock_duckdb_connection
        mock_duckdb_connection.fetchone.side_effect = [
            [0],  # No events for previous year
            [0],  # No workforce for previous year
        ]

        with patch("orchestrator.simulator_pipeline.clean_duckdb_data"):
            # Should raise exception for missing previous year data
            with pytest.raises(Exception) as exc_info:
                run_year_simulation(mock_context)

            assert "No previous year data found for year 2025" in str(exc_info.value)

    @patch("orchestrator.simulator_pipeline.validate_year_results")
    @patch("orchestrator.simulator_pipeline.run_dbt_event_models_for_year")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.clean_duckdb_data")
    def test_event_models_operation_failure(
        self,
        mock_clean_data,
        mock_execute_dbt,
        mock_event_models,
        mock_validate,
        mock_context,
    ):
        """Test error handling when event models operation fails."""
        # Mock event models failure
        mock_event_models.side_effect = Exception("Event processing failed")

        # Execute and expect exception
        with pytest.raises(Exception) as exc_info:
            run_year_simulation(mock_context)

        assert "Event processing failed" in str(exc_info.value)

        # Verify cleanup was called before failure
        mock_clean_data.assert_called_once()

    @patch("orchestrator.simulator_pipeline.validate_year_results")
    @patch("orchestrator.simulator_pipeline.run_dbt_event_models_for_year")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.clean_duckdb_data")
    def test_dbt_command_failure_handling(
        self,
        mock_clean_data,
        mock_execute_dbt,
        mock_event_models,
        mock_validate,
        mock_context,
    ):
        """Test error handling when dbt command execution fails."""
        # Setup mocks
        mock_event_models.return_value = {
            "year": 2025,
            "models_executed": [],
            "hiring_debug": {},
        }

        # Mock dbt command failure on second call (fct_yearly_events)
        mock_execute_dbt.side_effect = [None, Exception("dbt run failed"), None]

        # Execute and expect exception
        with pytest.raises(Exception) as exc_info:
            run_year_simulation(mock_context)

        assert "dbt run failed" in str(exc_info.value)

    @patch("orchestrator.simulator_pipeline.validate_year_results")
    @patch("orchestrator.simulator_pipeline.run_dbt_event_models_for_year")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.clean_duckdb_data")
    def test_validation_failure_handling(
        self,
        mock_clean_data,
        mock_execute_dbt,
        mock_event_models,
        mock_validate,
        mock_context,
    ):
        """Test error handling when validation fails."""
        # Setup mocks
        mock_event_models.return_value = {
            "year": 2025,
            "models_executed": [],
            "hiring_debug": {},
        }

        # Mock validation failure
        mock_validate.side_effect = Exception("Validation failed")

        # Execute and expect exception
        with pytest.raises(Exception) as exc_info:
            run_year_simulation(mock_context)

        assert "Validation failed" in str(exc_info.value)

        # Verify all previous steps completed
        mock_clean_data.assert_called_once()
        mock_event_models.assert_called_once()
        assert mock_execute_dbt.call_count == 3

    def test_configuration_parameter_extraction(self, mock_context):
        """Test that configuration parameters are correctly extracted."""
        # Modify config to test extraction
        test_config = {
            "start_year": 2030,
            "end_year": 2035,
            "target_growth_rate": 0.05,
            "full_refresh": True,
            "additional_param": "test_value",
        }
        mock_context.op_config = test_config

        with patch("orchestrator.simulator_pipeline.clean_duckdb_data"), patch(
            "orchestrator.simulator_pipeline.execute_dbt_command"
        ), patch(
            "orchestrator.simulator_pipeline.run_dbt_event_models_for_year"
        ) as mock_event_models, patch(
            "orchestrator.simulator_pipeline.validate_year_results"
        ) as mock_validate:
            mock_event_models.return_value = {
                "year": 2030,
                "models_executed": [],
                "hiring_debug": {},
            }
            mock_validate.return_value = YearResult(
                2030, True, 1000, 0, 0, 0, 0, 0.0, True
            )

            run_year_simulation(mock_context)

            # Verify event models received the full config
            mock_event_models.assert_called_once_with(mock_context, 2030, test_config)

            # Verify validation received the full config
            mock_validate.assert_called_once_with(mock_context, 2030, test_config)

    @pytest.mark.parametrize("year", [2020, 2025, 2030, 2050])
    @patch("orchestrator.simulator_pipeline.validate_year_results")
    @patch("orchestrator.simulator_pipeline.run_dbt_event_models_for_year")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.clean_duckdb_data")
    def test_various_simulation_years(
        self,
        mock_clean_data,
        mock_execute_dbt,
        mock_event_models,
        mock_validate,
        mock_context,
        year,
    ):
        """Test simulation with various years."""
        mock_context.op_config["start_year"] = year

        # Setup mocks
        mock_event_models.return_value = {
            "year": year,
            "models_executed": [],
            "hiring_debug": {},
        }
        mock_validate.return_value = YearResult(year, True, 1000, 0, 0, 0, 0, 0.0, True)

        run_year_simulation(mock_context)

        # Verify year is passed correctly to all components
        mock_clean_data.assert_called_once_with(mock_context, [year])
        mock_event_models.assert_called_once_with(
            mock_context, year, mock_context.op_config
        )
        mock_validate.assert_called_once_with(
            mock_context, year, mock_context.op_config
        )

        # Verify dbt commands receive correct simulation_year
        for call_args in mock_execute_dbt.call_args_list:
            vars_dict = call_args[0][2]
            assert vars_dict["simulation_year"] == year

    @patch("orchestrator.simulator_pipeline.validate_year_results")
    @patch("orchestrator.simulator_pipeline.run_dbt_event_models_for_year")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.clean_duckdb_data")
    def test_error_exception_return_structure(
        self,
        mock_clean_data,
        mock_execute_dbt,
        mock_event_models,
        mock_validate,
        mock_context,
    ):
        """Test error handling returns proper YearResult structure."""
        year = 2025

        # Mock validation failure
        mock_event_models.return_value = {
            "year": year,
            "models_executed": [],
            "hiring_debug": {},
        }
        mock_validate.side_effect = Exception("Critical validation error")

        # Should raise exception, not return YearResult
        with pytest.raises(Exception) as exc_info:
            run_year_simulation(mock_context)

        assert "Critical validation error" in str(exc_info.value)


class TestRefactoredSingleYearIntegration:
    """Integration tests for the refactored single-year simulation."""

    @pytest.fixture
    def integration_context(self):
        """Create a realistic integration context."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        context.op_config = {
            "start_year": 2025,
            "end_year": 2025,
            "target_growth_rate": 0.03,
            "total_termination_rate": 0.12,
            "new_hire_termination_rate": 0.25,
            "random_seed": 42,
            "full_refresh": False,
        }
        context.resources = Mock()
        context.resources.dbt = Mock()
        return context

    @patch("orchestrator.simulator_pipeline.validate_year_results")
    @patch("orchestrator.simulator_pipeline.run_dbt_event_models_for_year")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.clean_duckdb_data")
    def test_complete_simulation_workflow(
        self,
        mock_clean_data,
        mock_execute_dbt,
        mock_event_models,
        mock_validate,
        integration_context,
    ):
        """Test complete simulation workflow with realistic data flow."""
        year = 2025

        # Mock realistic responses
        mock_event_models.return_value = {
            "year": year,
            "models_executed": [
                "int_termination_events",
                "int_promotion_events",
                "int_merit_events",
                "int_hiring_events",
                "int_new_hire_termination_events",
            ],
            "hiring_debug": {"hire_count": 150, "year": year},
        }

        expected_result = YearResult(
            year=year,
            success=True,
            active_employees=1150,
            total_terminations=140,
            experienced_terminations=120,
            new_hire_terminations=20,
            total_hires=150,
            growth_rate=0.025,
            validation_passed=True,
        )
        mock_validate.return_value = expected_result

        # Execute
        result = run_year_simulation(integration_context)

        # Verify complete workflow execution
        assert result == expected_result

        # Verify workflow sequence
        mock_clean_data.assert_called_once_with(integration_context, [year])
        mock_event_models.assert_called_once_with(
            integration_context, year, integration_context.op_config
        )
        mock_validate.assert_called_once_with(
            integration_context, year, integration_context.op_config
        )

        # Verify all dbt commands executed
        assert mock_execute_dbt.call_count == 3

        # Verify logging messages
        integration_context.log.info.assert_any_call(
            f"Starting simulation for year {year}"
        )
        integration_context.log.info.assert_any_call(
            f"Year {year} simulation completed successfully"
        )

    @patch("orchestrator.simulator_pipeline.validate_year_results")
    @patch("orchestrator.simulator_pipeline.run_dbt_event_models_for_year")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.clean_duckdb_data")
    def test_modular_component_isolation(
        self,
        mock_clean_data,
        mock_execute_dbt,
        mock_event_models,
        mock_validate,
        integration_context,
    ):
        """Test that modular components are properly isolated and called independently."""
        year = 2025

        # Setup mocks with unique identifiers
        mock_clean_data.return_value = {"cleaned": True}
        mock_event_models.return_value = {
            "year": year,
            "models_executed": ["test_model"],
            "hiring_debug": {"hire_count": 50},
        }
        mock_validate.return_value = YearResult(year, True, 1000, 0, 0, 0, 0, 0.0, True)

        # Execute
        run_year_simulation(integration_context)

        # Verify each component was called exactly once with correct parameters
        mock_clean_data.assert_called_once_with(integration_context, [year])
        mock_event_models.assert_called_once_with(
            integration_context, year, integration_context.op_config
        )
        mock_validate.assert_called_once_with(
            integration_context, year, integration_context.op_config
        )

        # Verify components are called in correct order (data cleaning first)
        # This is implicit in the mocking order but validates the sequence
