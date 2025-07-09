"""
Unit tests for S013-01: execute_dbt_command utility

Comprehensive test suite for the centralized dbt command execution utility,
covering all parameter combinations, error scenarios, and edge cases.

Fixed version with correct mock expectations based on actual implementation.
"""

import pytest
from unittest.mock import Mock
from dagster import OpExecutionContext

from orchestrator.simulator_pipeline import execute_dbt_command, execute_dbt_command_streaming


class TestExecuteDbtCommand:
    """Test suite for execute_dbt_command utility."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock Dagster execution context."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        context.log.info = Mock()
        context.log.error = Mock()

        # Mock dbt resource with proper invocation chain
        dbt_resource = Mock()

        # Create the mock invocation with the correct structure
        mock_invocation = Mock()
        mock_process = Mock()
        mock_process.returncode = 0  # Success
        mock_invocation.process = mock_process
        mock_invocation.get_stdout.return_value = "Success output"
        mock_invocation.get_stderr.return_value = ""

        # Set up the chain: dbt.cli(...).wait() returns the invocation
        cli_mock = Mock()
        cli_mock.wait.return_value = mock_invocation
        dbt_resource.cli.return_value = cli_mock

        context.resources = Mock()
        context.resources.dbt = dbt_resource

        return context

    def test_basic_dbt_run_command(self, mock_context):
        """Test basic dbt run command execution."""
        command = ["run", "--select", "test_model"]
        vars_dict = {"simulation_year": 2025}
        description = "test model execution"

        # Execute
        execute_dbt_command(mock_context, command, vars_dict, False, description)

        # Verify dbt.cli was called correctly
        expected_command = ["run", "--select", "test_model", "--vars", "{simulation_year: 2025}"]
        mock_context.resources.dbt.cli.assert_called_once_with(expected_command, context=mock_context)

        # Verify logging
        mock_context.log.info.assert_any_call("Executing: dbt run --select test_model --vars {simulation_year: 2025}")
        mock_context.log.info.assert_any_call("Description: test model execution")
        mock_context.log.info.assert_any_call("Successfully completed: dbt run --select test_model")

    def test_full_refresh_parameter(self, mock_context):
        """Test full_refresh parameter adds --full-refresh flag."""
        command = ["run", "--select", "incremental_model"]
        vars_dict = {"simulation_year": 2025}

        # Execute with full_refresh=True
        execute_dbt_command(mock_context, command, vars_dict, True, "full refresh test")

        # Verify --full-refresh and --vars were added to command
        expected_command = ["run", "--select", "incremental_model", "--vars", "{simulation_year: 2025}", "--full-refresh"]
        mock_context.resources.dbt.cli.assert_called_once_with(
            expected_command, context=mock_context
        )

    def test_empty_vars_dict(self, mock_context):
        """Test execution with empty variables dictionary."""
        command = ["test"]
        vars_dict = {}

        execute_dbt_command(mock_context, command, vars_dict, False, "empty vars test")

        # With empty vars, no --vars should be added
        expected_command = ["test"]
        mock_context.resources.dbt.cli.assert_called_once_with(expected_command, context=mock_context)

    def test_complex_command_with_multiple_flags(self, mock_context):
        """Test complex dbt command with multiple flags and variables."""
        command = ["run", "--select", "model1", "model2", "--exclude", "model3"]
        vars_dict = {"year": 2025, "seed": 42, "rate": 0.03}

        execute_dbt_command(mock_context, command, vars_dict, True, "complex command")

        # Verify command construction
        expected_vars = "{year: 2025, seed: 42, rate: 0.03}"
        expected_command = [
            "run", "--select", "model1", "model2", "--exclude", "model3",
            "--vars", expected_vars, "--full-refresh"
        ]
        mock_context.resources.dbt.cli.assert_called_once_with(expected_command, context=mock_context)

    def test_snapshot_command(self, mock_context):
        """Test snapshot command execution."""
        command = ["snapshot", "--select", "scd_workforce_state"]
        vars_dict = {"simulation_year": 2025}

        execute_dbt_command(mock_context, command, vars_dict, False, "snapshot execution")

        expected_command = ["snapshot", "--select", "scd_workforce_state", "--vars", "{simulation_year: 2025}"]
        mock_context.resources.dbt.cli.assert_called_once_with(expected_command, context=mock_context)

    def test_dbt_command_failure(self, mock_context):
        """Test error handling when dbt command fails."""
        # Configure mock for failure
        mock_invocation = Mock()
        mock_process = Mock()
        mock_process.returncode = 1  # Failure
        mock_invocation.process = mock_process
        mock_invocation.get_stdout.return_value = "stdout error content"
        mock_invocation.get_stderr.return_value = "stderr error content"

        cli_mock = Mock()
        cli_mock.wait.return_value = mock_invocation
        mock_context.resources.dbt.cli.return_value = cli_mock

        command = ["run", "--select", "failure_model"]

        with pytest.raises(Exception) as exc_info:
            execute_dbt_command(mock_context, command, {}, False, "failure test")

        # Verify error message content
        error_msg = str(exc_info.value)
        assert "Failed to run run --select failure_model" in error_msg
        assert "for failure test" in error_msg
        assert "Exit code: 1" in error_msg
        assert "stdout error content" in error_msg
        assert "stderr error content" in error_msg

        # Verify error logging
        mock_context.log.error.assert_called_once()

    def test_default_description_parameter(self, mock_context):
        """Test execution with empty description."""
        command = ["test"]

        execute_dbt_command(mock_context, command, {}, False, "")

        # Verify command was called
        mock_context.resources.dbt.cli.assert_called_once_with(["test"], context=mock_context)

        # Verify no description logging (empty description)
        log_calls = [call[0][0] for call in mock_context.log.info.call_args_list]
        assert not any("Description:" in call for call in log_calls)

    def test_various_variable_types(self, mock_context):
        """Test with various variable types (string, int, float, bool)."""
        command = ["run"]
        vars_dict = {
            "string_var": "test_value",
            "int_var": 42,
            "float_var": 3.14,
            "bool_var": True
        }

        execute_dbt_command(mock_context, command, vars_dict, False, "type test")

        # Verify vars string construction
        expected_vars = "{string_var: test_value, int_var: 42, float_var: 3.14, bool_var: True}"
        expected_command = ["run", "--vars", expected_vars]
        mock_context.resources.dbt.cli.assert_called_once_with(expected_command, context=mock_context)

    def test_none_process_handling(self, mock_context):
        """Test error handling when process is None."""
        # Configure mock for None process
        mock_invocation = Mock()
        mock_invocation.process = None
        mock_invocation.get_stdout.return_value = "no process output"
        mock_invocation.get_stderr.return_value = "no process error"

        cli_mock = Mock()
        cli_mock.wait.return_value = mock_invocation
        mock_context.resources.dbt.cli.return_value = cli_mock

        command = ["run"]

        with pytest.raises(Exception) as exc_info:
            execute_dbt_command(mock_context, command, {}, False, "none process test")

        # Verify error message handles None process
        error_msg = str(exc_info.value)
        assert "Exit code: N/A" in error_msg


class TestExecuteDbtCommandStreaming:
    """Test suite for execute_dbt_command_streaming utility."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock Dagster execution context."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()

        # Mock dbt resource for streaming
        dbt_resource = Mock()
        cli_mock = Mock()

        # Mock the streaming interface
        stream_mock = Mock()
        stream_mock.stream.return_value = iter(["line 1", "line 2", "line 3"])
        cli_mock.return_value = stream_mock
        dbt_resource.cli = cli_mock

        context.resources = Mock()
        context.resources.dbt = dbt_resource

        return context

    def test_streaming_basic_execution(self, mock_context):
        """Test basic streaming command execution."""
        # Execute streaming command
        results = list(execute_dbt_command_streaming(mock_context, ["build"], {}, False, "streaming test"))

        # Verify results were yielded
        assert results == ["line 1", "line 2", "line 3"]

        # Verify logging
        mock_context.log.info.assert_any_call("Executing (streaming): dbt build")
        mock_context.log.info.assert_any_call("Description: streaming test")
        mock_context.log.info.assert_any_call("Successfully completed (streaming): dbt build")


class TestExecuteDbtCommandIntegration:
    """Integration tests for execute_dbt_command."""

    @pytest.fixture
    def integration_context(self):
        """Create a realistic context for integration testing."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()

        # Mock realistic dbt resource
        dbt_resource = Mock()
        mock_invocation = Mock()
        mock_process = Mock()
        mock_process.returncode = 0
        mock_invocation.process = mock_process
        mock_invocation.get_stdout.return_value = "1 model compiled successfully"
        mock_invocation.get_stderr.return_value = ""

        cli_mock = Mock()
        cli_mock.wait.return_value = mock_invocation
        dbt_resource.cli.return_value = cli_mock

        context.resources = Mock()
        context.resources.dbt = dbt_resource

        return context

    def test_realistic_simulation_workflow(self, integration_context):
        """Test realistic simulation workflow commands."""
        # Test sequence of commands that would be used in simulation
        commands = [
            (["run", "--select", "int_workforce_previous_year"], {"simulation_year": 2025}),
            (["run", "--select", "int_termination_events"], {"simulation_year": 2025, "random_seed": 42}),
            (["run", "--select", "fct_yearly_events"], {"simulation_year": 2025}),
            (["snapshot", "--select", "scd_workforce_state"], {"simulation_year": 2025}),
        ]

        for command, vars_dict in commands:
            execute_dbt_command(integration_context, command, vars_dict, False, f"workflow {command[2]}")

        # Verify all commands were executed
        assert integration_context.resources.dbt.cli.call_count == 4

    def test_error_recovery_scenario(self, integration_context):
        """Test error handling and recovery in realistic scenario."""
        # First command succeeds
        execute_dbt_command(integration_context, ["run", "--select", "model1"], {"year": 2025}, False, "first")

        # Second command fails
        mock_invocation_fail = Mock()
        mock_process_fail = Mock()
        mock_process_fail.returncode = 1
        mock_invocation_fail.process = mock_process_fail
        mock_invocation_fail.get_stdout.return_value = "compilation error"
        mock_invocation_fail.get_stderr.return_value = "model not found"

        cli_mock_fail = Mock()
        cli_mock_fail.wait.return_value = mock_invocation_fail
        integration_context.resources.dbt.cli.return_value = cli_mock_fail

        with pytest.raises(Exception):
            execute_dbt_command(integration_context, ["run", "--select", "model2"], {"year": 2025}, False, "second")

        # Reset for third command
        mock_invocation_success = Mock()
        mock_process_success = Mock()
        mock_process_success.returncode = 0
        mock_invocation_success.process = mock_process_success
        mock_invocation_success.get_stdout.return_value = "success"
        mock_invocation_success.get_stderr.return_value = ""

        cli_mock_success = Mock()
        cli_mock_success.wait.return_value = mock_invocation_success
        integration_context.resources.dbt.cli.return_value = cli_mock_success

        # Third command succeeds (recovery)
        execute_dbt_command(integration_context, ["run", "--select", "model3"], {"year": 2025}, False, "third")

        # Verify error was logged for failed command
        integration_context.log.error.assert_called_once()
