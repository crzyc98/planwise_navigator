"""
Unit tests for S013-05: run_year_simulation refactoring

Comprehensive test suite for the refactored run_year_simulation function,
validating that behavior is preserved while using new modular components.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
import duckdb
from dagster import OpExecutionContext, build_op_context

from orchestrator.simulator_pipeline import run_year_simulation, YearResult


class TestRunYearSimulation:
    """Test suite for the refactored run_year_simulation function."""

    @pytest.fixture
    def mock_context(self):
        """Create a proper Dagster execution context."""
        # Create mock dbt resource
        dbt_resource = Mock()
        mock_invocation = Mock()
        mock_invocation.process = Mock()
        mock_invocation.process.returncode = 0
        mock_invocation.get_stdout.return_value = "Success output"
        mock_invocation.get_stderr.return_value = ""

        dbt_resource.cli.return_value.wait.return_value = mock_invocation

        # Create proper Dagster context
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

        return context

    @pytest.fixture
    def mock_db_connection(self):
        """Create a mock DuckDB connection."""
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [1000]  # Default count
        mock_conn.execute.return_value.fetchall.return_value = [
            ("hire", 100),
            ("termination", 80),
        ]
        mock_conn.close = Mock()
        return mock_conn

    @patch('orchestrator.simulator_pipeline.duckdb.connect')
    @patch('orchestrator.simulator_pipeline.clean_duckdb_data')
    @patch('orchestrator.simulator_pipeline.execute_dbt_command')
    @patch('orchestrator.simulator_pipeline._run_dbt_event_models_for_year_internal')
    @patch('orchestrator.simulator_pipeline.validate_year_results')
    def test_successful_single_year_simulation_2025(
        self,
        mock_validate,
        mock_event_models,
        mock_execute_dbt,
        mock_clean_data,
        mock_connect,
        mock_context,
        mock_db_connection
    ):
        """Test successful simulation for base year 2025."""
        # Setup
        mock_connect.return_value = mock_db_connection
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
        result = run_year_simulation(mock_context)

        # Verify result
        assert result.year == 2025
        assert result.success is True
        assert result.active_employees == 1030

        # Verify clean_duckdb_data was called with correct year
        mock_clean_data.assert_called_once_with(mock_context, [2025])

        # Verify execute_dbt_command was called for required models
        expected_calls = [
            # int_workforce_previous_year
            (["run", "--select", "int_workforce_previous_year"], {"simulation_year": 2025}, False, "int_workforce_previous_year for year 2025"),
            # fct_yearly_events
            (["run", "--select", "fct_yearly_events"], {"simulation_year": 2025}, False, "fct_yearly_events for year 2025"),
            # fct_workforce_snapshot
            (["run", "--select", "fct_workforce_snapshot"], {"simulation_year": 2025}, False, "fct_workforce_snapshot for year 2025"),
        ]

        assert mock_execute_dbt.call_count == 3
        for i, (command, vars_dict, full_refresh, description) in enumerate(expected_calls):
            call_args = mock_execute_dbt.call_args_list[i]
            assert call_args[0][1] == command  # command
            assert call_args[0][2] == vars_dict  # vars_dict
            assert call_args[0][3] == full_refresh  # full_refresh
            assert call_args[0][4] == description  # description

        # Verify event models were run
        mock_event_models.assert_called_once_with(mock_context, 2025, mock_context.op_config)

        # Verify validation was called
        mock_validate.assert_called_once_with(mock_context, 2025, mock_context.op_config)

        # Verify logging
        mock_context.log.info.assert_any_call("Starting simulation for year 2025")
        mock_context.log.info.assert_any_call("Year 2025 simulation completed successfully")

    @patch('orchestrator.simulator_pipeline.duckdb.connect')
    @patch('orchestrator.simulator_pipeline.clean_duckdb_data')
    @patch('orchestrator.simulator_pipeline.execute_dbt_command')
    @patch('orchestrator.simulator_pipeline._run_dbt_event_models_for_year_internal')
    @patch('orchestrator.simulator_pipeline.validate_year_results')
    def test_successful_multi_year_simulation_2026(
        self,
        mock_validate,
        mock_event_models,
        mock_execute_dbt,
        mock_clean_data,
        mock_connect,
        mock_context,
        mock_db_connection
    ):
        """Test successful simulation for year 2026 (multi-year dependency)."""
        # Setup for year 2026
        mock_context.op_config["start_year"] = 2026

        # Mock database responses for previous year validation
        mock_db_connection.execute.return_value.fetchone.side_effect = [
            [50],   # events_count for 2025
            [1000], # workforce_count for 2025
        ]
        mock_connect.return_value = mock_db_connection

        mock_validate.return_value = YearResult(
            year=2026,
            success=True,
            active_employees=1060,
            total_terminations=125,
            experienced_terminations=105,
            new_hire_terminations=20,
            total_hires=155,
            growth_rate=0.03,
            validation_passed=True
        )

        # Execute
        result = run_year_simulation(mock_context)

        # Verify result
        assert result.year == 2026
        assert result.success is True

        # Verify previous year validation was performed
        expected_validation_calls = [
            ("SELECT COUNT(*) FROM fct_yearly_events\n                    WHERE simulation_year = ?", [2025]),
            ("SELECT COUNT(*) FROM fct_workforce_snapshot\n                    WHERE simulation_year = ? AND employment_status = 'active'", [2025]),
        ]

        # Verify database validation calls
        assert mock_db_connection.execute.call_count >= 2
        mock_context.log.info.assert_any_call("Previous year validation passed: 50 events, 1000 active employees from 2025")

        # Verify clean_duckdb_data was called with correct year
        mock_clean_data.assert_called_once_with(mock_context, [2026])

    @patch('orchestrator.simulator_pipeline.duckdb.connect')
    @patch('orchestrator.simulator_pipeline.clean_duckdb_data')
    @patch('orchestrator.simulator_pipeline.execute_dbt_command')
    @patch('orchestrator.simulator_pipeline._run_dbt_event_models_for_year_internal')
    @patch('orchestrator.simulator_pipeline.validate_year_results')
    def test_full_refresh_flag_handling(
        self,
        mock_validate,
        mock_event_models,
        mock_execute_dbt,
        mock_clean_data,
        mock_connect,
        mock_context,
        mock_db_connection
    ):
        """Test that full_refresh flag is properly passed to all dbt commands."""
        # Setup with full_refresh enabled
        mock_context.op_config["full_refresh"] = True
        mock_connect.return_value = mock_db_connection

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
        result = run_year_simulation(mock_context)

        # Verify full_refresh flag logging
        mock_context.log.info.assert_any_call("🔄 Full refresh enabled - will rebuild all incremental models from scratch")

        # Verify that all execute_dbt_command calls received full_refresh=True
        for call_args in mock_execute_dbt.call_args_list:
            assert call_args[0][3] is True  # full_refresh parameter

    @patch('orchestrator.simulator_pipeline.duckdb.connect')
    @patch('orchestrator.simulator_pipeline.clean_duckdb_data')
    @patch('orchestrator.simulator_pipeline.execute_dbt_command')
    @patch('orchestrator.simulator_pipeline._run_dbt_event_models_for_year_internal')
    def test_error_handling_in_dbt_command(
        self,
        mock_event_models,
        mock_execute_dbt,
        mock_clean_data,
        mock_connect,
        mock_context,
        mock_db_connection
    ):
        """Test error handling when dbt command fails."""
        # Setup
        mock_connect.return_value = mock_db_connection
        mock_execute_dbt.side_effect = Exception("dbt model compilation failed")

        # Execute
        result = run_year_simulation(mock_context)

        # Verify error result
        assert result.success is False
        assert result.year == 2025
        assert result.active_employees == 0
        assert result.validation_passed is False

        # Verify error logging
        mock_context.log.error.assert_called_once()
        error_call = mock_context.log.error.call_args[0][0]
        assert "Simulation failed for year 2025" in error_call
        assert "dbt model compilation failed" in error_call

    @patch('orchestrator.simulator_pipeline.duckdb.connect')
    @patch('orchestrator.simulator_pipeline.clean_duckdb_data')
    @patch('orchestrator.simulator_pipeline.execute_dbt_command')
    @patch('orchestrator.simulator_pipeline._run_dbt_event_models_for_year_internal')
    def test_error_handling_in_event_models(
        self,
        mock_event_models,
        mock_execute_dbt,
        mock_clean_data,
        mock_connect,
        mock_context,
        mock_db_connection
    ):
        """Test error handling when event models fail."""
        # Setup
        mock_connect.return_value = mock_db_connection
        mock_event_models.side_effect = Exception("Event model processing failed")

        # Execute
        result = run_year_simulation(mock_context)

        # Verify error result
        assert result.success is False
        assert result.year == 2025

        # Verify error logging
        mock_context.log.error.assert_called_once()
        error_call = mock_context.log.error.call_args[0][0]
        assert "Simulation failed for year 2025" in error_call
        assert "Event model processing failed" in error_call

    @patch('orchestrator.simulator_pipeline.duckdb.connect')
    @patch('orchestrator.simulator_pipeline.clean_duckdb_data')
    @patch('orchestrator.simulator_pipeline.execute_dbt_command')
    @patch('orchestrator.simulator_pipeline._run_dbt_event_models_for_year_internal')
    def test_missing_previous_year_data_error(
        self,
        mock_event_models,
        mock_execute_dbt,
        mock_clean_data,
        mock_connect,
        mock_context,
        mock_db_connection
    ):
        """Test error handling when previous year data is missing."""
        # Setup for year 2026 with missing previous year data
        mock_context.op_config["start_year"] = 2026

        # Mock database responses indicating no previous year data
        mock_db_connection.execute.return_value.fetchone.side_effect = [
            [0],  # events_count for 2025 (missing)
            [0],  # workforce_count for 2025 (missing)
        ]
        mock_connect.return_value = mock_db_connection

        # Execute
        result = run_year_simulation(mock_context)

        # Verify error result
        assert result.success is False
        assert result.year == 2026

        # Verify error logging
        mock_context.log.error.assert_called_once()
        error_call = mock_context.log.error.call_args[0][0]
        assert "Simulation failed for year 2026" in error_call
        assert "No previous year data found for year 2025" in error_call

    @patch('orchestrator.simulator_pipeline.duckdb.connect')
    @patch('orchestrator.simulator_pipeline.clean_duckdb_data')
    @patch('orchestrator.simulator_pipeline.execute_dbt_command')
    @patch('orchestrator.simulator_pipeline._run_dbt_event_models_for_year_internal')
    def test_missing_workforce_snapshot_recovery(
        self,
        mock_event_models,
        mock_execute_dbt,
        mock_clean_data,
        mock_connect,
        mock_context,
        mock_db_connection
    ):
        """Test recovery when previous year has events but missing workforce snapshot."""
        # Setup for year 2026 with events but missing workforce snapshot
        mock_context.op_config["start_year"] = 2026

        # Mock database responses: events exist, workforce missing initially, then recovered
        mock_db_connection.execute.return_value.fetchone.side_effect = [
            [50],   # events_count for 2025 (exists)
            [0],    # workforce_count for 2025 (missing initially)
            [1000], # workforce_count for 2025 (recovered after rebuild)
        ]
        mock_connect.return_value = mock_db_connection

        # Execute
        result = run_year_simulation(mock_context)

        # Verify recovery was attempted
        mock_context.log.warning.assert_called_once()
        warning_call = mock_context.log.warning.call_args[0][0]
        assert "Previous year 2025 has events (50) but no workforce snapshot" in warning_call

        # Verify recovery execute_dbt_command was called
        recovery_call_found = False
        for call_args in mock_execute_dbt.call_args_list:
            if call_args[0][4] == "missing workforce snapshot for year 2025":
                recovery_call_found = True
                break
        assert recovery_call_found, "Recovery dbt command was not called"

        # Verify success logging after recovery
        mock_context.log.info.assert_any_call("Successfully recovered workforce snapshot for year 2025: 1000 active employees")

    @patch('orchestrator.simulator_pipeline.duckdb.connect')
    @patch('orchestrator.simulator_pipeline.clean_duckdb_data')
    @patch('orchestrator.simulator_pipeline.execute_dbt_command')
    @patch('orchestrator.simulator_pipeline._run_dbt_event_models_for_year_internal')
    @patch('orchestrator.simulator_pipeline.validate_year_results')
    def test_modular_component_integration(
        self,
        mock_validate,
        mock_event_models,
        mock_execute_dbt,
        mock_clean_data,
        mock_connect,
        mock_context,
        mock_db_connection
    ):
        """Test integration with all modular components."""
        # Setup
        mock_connect.return_value = mock_db_connection
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
        result = run_year_simulation(mock_context)

        # Verify all modular components were called
        mock_clean_data.assert_called_once_with(mock_context, [2025])
        mock_event_models.assert_called_once_with(mock_context, 2025, mock_context.op_config)
        mock_validate.assert_called_once_with(mock_context, 2025, mock_context.op_config)

        # Verify execute_dbt_command was called 3 times (workforce_previous_year, yearly_events, workforce_snapshot)
        assert mock_execute_dbt.call_count == 3

        # Verify success
        assert result.success is True

    @patch('orchestrator.simulator_pipeline.duckdb.connect')
    @patch('orchestrator.simulator_pipeline.clean_duckdb_data')
    @patch('orchestrator.simulator_pipeline.execute_dbt_command')
    @patch('orchestrator.simulator_pipeline._run_dbt_event_models_for_year_internal')
    @patch('orchestrator.simulator_pipeline.validate_year_results')
    def test_configuration_parameter_passing(
        self,
        mock_validate,
        mock_event_models,
        mock_execute_dbt,
        mock_clean_data,
        mock_connect,
        mock_context,
        mock_db_connection
    ):
        """Test that configuration parameters are passed correctly to all components."""
        # Setup with specific configuration
        mock_context.op_config.update({
            "start_year": 2027,
            "target_growth_rate": 0.05,
            "total_termination_rate": 0.15,
            "new_hire_termination_rate": 0.30,
            "random_seed": 123,
            "full_refresh": True,
        })

        mock_connect.return_value = mock_db_connection
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
        result = run_year_simulation(mock_context)

        # Verify configuration was passed to event models
        mock_event_models.assert_called_once_with(mock_context, 2027, mock_context.op_config)

        # Verify configuration was passed to validation
        mock_validate.assert_called_once_with(mock_context, 2027, mock_context.op_config)

        # Verify variables were passed to dbt commands
        for call_args in mock_execute_dbt.call_args_list:
            vars_dict = call_args[0][2]
            assert vars_dict["simulation_year"] == 2027
            assert call_args[0][3] is True  # full_refresh

    def test_year_result_structure_consistency(self, mock_context):
        """Test that YearResult structure is consistent in success and failure cases."""
        # Test success case structure
        with patch('orchestrator.simulator_pipeline.duckdb.connect') as mock_connect, \
             patch('orchestrator.simulator_pipeline.clean_duckdb_data'), \
             patch('orchestrator.simulator_pipeline.execute_dbt_command'), \
             patch('orchestrator.simulator_pipeline._run_dbt_event_models_for_year_internal'), \
             patch('orchestrator.simulator_pipeline.validate_year_results') as mock_validate:

            mock_connect.return_value = Mock()
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

            success_result = run_year_simulation(mock_context)

            # Verify success result structure
            assert hasattr(success_result, 'year')
            assert hasattr(success_result, 'success')
            assert hasattr(success_result, 'active_employees')
            assert hasattr(success_result, 'total_terminations')
            assert hasattr(success_result, 'experienced_terminations')
            assert hasattr(success_result, 'new_hire_terminations')
            assert hasattr(success_result, 'total_hires')
            assert hasattr(success_result, 'growth_rate')
            assert hasattr(success_result, 'validation_passed')

        # Test failure case structure
        with patch('orchestrator.simulator_pipeline.duckdb.connect') as mock_connect, \
             patch('orchestrator.simulator_pipeline.clean_duckdb_data'), \
             patch('orchestrator.simulator_pipeline.execute_dbt_command') as mock_execute_dbt:

            mock_connect.return_value = Mock()
            mock_execute_dbt.side_effect = Exception("Test failure")

            failure_result = run_year_simulation(mock_context)

            # Verify failure result structure
            assert hasattr(failure_result, 'year')
            assert hasattr(failure_result, 'success')
            assert hasattr(failure_result, 'active_employees')
            assert hasattr(failure_result, 'total_terminations')
            assert hasattr(failure_result, 'experienced_terminations')
            assert hasattr(failure_result, 'new_hire_terminations')
            assert hasattr(failure_result, 'total_hires')
            assert hasattr(failure_result, 'growth_rate')
            assert hasattr(failure_result, 'validation_passed')

            # Verify failure result values
            assert failure_result.success is False
            assert failure_result.year == 2025
            assert failure_result.active_employees == 0
            assert failure_result.validation_passed is False


class TestRunYearSimulationIntegration:
    """Integration tests for run_year_simulation with realistic scenarios."""

    @pytest.fixture
    def integration_context(self):
        """Create a realistic context for integration testing."""
        # Create mock dbt resource
        dbt_resource = Mock()

        # Create proper Dagster context
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

        return context

    @patch('orchestrator.simulator_pipeline.duckdb.connect')
    @patch('orchestrator.simulator_pipeline.clean_duckdb_data')
    @patch('orchestrator.simulator_pipeline.execute_dbt_command')
    @patch('orchestrator.simulator_pipeline._run_dbt_event_models_for_year_internal')
    @patch('orchestrator.simulator_pipeline.validate_year_results')
    def test_complete_simulation_workflow(
        self,
        mock_validate,
        mock_event_models,
        mock_execute_dbt,
        mock_clean_data,
        mock_connect,
        integration_context
    ):
        """Test complete simulation workflow with all components."""
        # Setup realistic mock responses
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
        result = run_year_simulation(integration_context)

        # Verify execution order and integration
        assert mock_clean_data.called
        assert mock_execute_dbt.called
        assert mock_event_models.called
        assert mock_validate.called

        # Verify result
        assert result.success is True
        assert result.year == 2025
        assert result.active_employees == 1030

        # Verify logging shows complete workflow
        integration_context.log.info.assert_any_call("Starting simulation for year 2025")
        integration_context.log.info.assert_any_call("Running int_workforce_previous_year for year 2025")
        integration_context.log.info.assert_any_call("Running event models for year 2025")
        integration_context.log.info.assert_any_call("Running fct_yearly_events for year 2025")
        integration_context.log.info.assert_any_call("Running fct_workforce_snapshot for year 2025")
        integration_context.log.info.assert_any_call("Year 2025 simulation completed successfully")
