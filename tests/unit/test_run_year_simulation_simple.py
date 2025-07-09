"""
Simplified unit tests for S013-05: run_year_simulation refactoring

Basic tests to verify the refactored function works correctly with modular components.
"""

import pytest
from unittest.mock import Mock, patch
from dagster import build_op_context

from orchestrator.simulator_pipeline import run_year_simulation, YearResult


class TestRunYearSimulationSimple:
    """Simplified test suite for the refactored run_year_simulation function."""

    def test_function_uses_modular_components(self):
        """Test that the refactored function uses all expected modular components."""

        # Create proper Dagster context
        dbt_resource = Mock()
        mock_invocation = Mock()
        mock_invocation.process = Mock()
        mock_invocation.process.returncode = 0
        mock_invocation.get_stdout.return_value = "Success output"
        mock_invocation.get_stderr.return_value = ""

        dbt_resource.cli.return_value.wait.return_value = mock_invocation

        context = build_op_context(
            op_config={
                "start_year": 2025,
                "end_year": 2029,
                "target_growth_rate": 0.03,
                "total_termination_rate": 0.12,
                "new_hire_termination_rate": 0.25,
                "random_seed": 42,
                "full_refresh": False,
            },
            resources={"dbt": dbt_resource}
        )

        with patch('orchestrator.simulator_pipeline.duckdb.connect') as mock_connect, \
             patch('orchestrator.simulator_pipeline.clean_duckdb_data') as mock_clean, \
             patch('orchestrator.simulator_pipeline.execute_dbt_command') as mock_execute_dbt, \
             patch('orchestrator.simulator_pipeline._run_dbt_event_models_for_year_internal') as mock_event_models, \
             patch('orchestrator.simulator_pipeline.validate_year_results') as mock_validate:

            # Setup mocks
            mock_conn = Mock()
            mock_conn.execute.return_value.fetchone.return_value = [1000]
            mock_conn.close = Mock()
            mock_connect.return_value = mock_conn

            mock_validate.return_value = YearResult(
                year=2025,
                success=True,
                active_employees=1030,
                total_terminations=120,
                experienced_terminations=100,
                new_hire_terminations=20,
                total_hires=150,
                growth_rate=0.03,
                validation_passed=True
            )

            # Execute
            result = run_year_simulation(context)

            # Verify modular components were called
            mock_clean.assert_called_once_with(context, [2025])
            mock_event_models.assert_called_once_with(context, 2025, context.op_config)
            mock_validate.assert_called_once_with(context, 2025, context.op_config)

            # Verify execute_dbt_command was called 3 times (workforce_previous_year, yearly_events, workforce_snapshot)
            assert mock_execute_dbt.call_count == 3

            # Verify result
            assert result.year == 2025
            assert result.success is True
            assert result.active_employees == 1030

    def test_function_handles_errors_correctly(self):
        """Test that the function handles errors and returns proper error result."""

        dbt_resource = Mock()
        context = build_op_context(
            op_config={
                "start_year": 2025,
                "end_year": 2029,
                "target_growth_rate": 0.03,
                "total_termination_rate": 0.12,
                "new_hire_termination_rate": 0.25,
                "random_seed": 42,
                "full_refresh": False,
            },
            resources={"dbt": dbt_resource}
        )

        with patch('orchestrator.simulator_pipeline.duckdb.connect') as mock_connect, \
             patch('orchestrator.simulator_pipeline.clean_duckdb_data') as mock_clean, \
             patch('orchestrator.simulator_pipeline.execute_dbt_command') as mock_execute_dbt:

            # Setup mocks
            mock_conn = Mock()
            mock_conn.close = Mock()
            mock_connect.return_value = mock_conn

            # Make execute_dbt_command fail
            mock_execute_dbt.side_effect = Exception("Test error")

            # Execute
            result = run_year_simulation(context)

            # Verify error result
            assert result.success is False
            assert result.year == 2025
            assert result.active_employees == 0
            assert result.validation_passed is False

    def test_function_configuration_passed_correctly(self):
        """Test that configuration is passed correctly to modular components."""

        dbt_resource = Mock()
        context = build_op_context(
            op_config={
                "start_year": 2027,
                "end_year": 2030,
                "target_growth_rate": 0.05,
                "total_termination_rate": 0.15,
                "new_hire_termination_rate": 0.30,
                "random_seed": 123,
                "full_refresh": True,
            },
            resources={"dbt": dbt_resource}
        )

        with patch('orchestrator.simulator_pipeline.duckdb.connect') as mock_connect, \
             patch('orchestrator.simulator_pipeline.clean_duckdb_data') as mock_clean, \
             patch('orchestrator.simulator_pipeline.execute_dbt_command') as mock_execute_dbt, \
             patch('orchestrator.simulator_pipeline._run_dbt_event_models_for_year_internal') as mock_event_models, \
             patch('orchestrator.simulator_pipeline.validate_year_results') as mock_validate:

            # Setup mocks
            mock_conn = Mock()
            mock_conn.execute.return_value.fetchone.return_value = [1000]
            mock_conn.close = Mock()
            mock_connect.return_value = mock_conn

            mock_validate.return_value = YearResult(
                year=2027,
                success=True,
                active_employees=1100,
                total_terminations=150,
                experienced_terminations=120,
                new_hire_terminations=30,
                total_hires=180,
                growth_rate=0.05,
                validation_passed=True
            )

            # Execute
            result = run_year_simulation(context)

            # Verify configuration was passed to event models
            mock_event_models.assert_called_once_with(context, 2027, context.op_config)

            # Verify configuration was passed to validation
            mock_validate.assert_called_once_with(context, 2027, context.op_config)

            # Verify full_refresh was passed to dbt commands
            for call_args in mock_execute_dbt.call_args_list:
                assert call_args[0][3] is True  # full_refresh parameter
                vars_dict = call_args[0][2]
                assert vars_dict["simulation_year"] == 2027
