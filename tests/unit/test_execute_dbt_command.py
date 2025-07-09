"""
Unit tests for S013-01: execute_dbt_command utility

Comprehensive test suite for the centralized dbt command execution utility,
covering all parameter combinations, error scenarios, and edge cases.
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
        mock_invocation = Mock()
        mock_invocation.process = Mock()
        mock_invocation.process.returncode = 0  # Success
        mock_invocation.get_stdout.return_value = "Success output"
        mock_invocation.get_stderr.return_value = ""

        dbt_resource.cli.return_value.wait.return_value = mock_invocation
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
        mock_context.resources.dbt.cli.assert_called_once_with(
            expected_command, context=mock_context
        )

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

        # Verify --full-refresh was added to command
        expected_command = ["run", "--select", "incremental_model", "--full-refresh"]
        mock_context.resources.dbt.cli.assert_called_once_with(
            expected_command, vars=vars_dict
        )

    def test_empty_vars_dict(self, mock_context):
        """Test execution with empty variables dictionary."""
        command = ["test"]
        vars_dict = {}

        execute_dbt_command(mock_context, command, vars_dict, False, "empty vars test")

        mock_context.resources.dbt.cli.assert_called_once_with(["test"], vars={})

    def test_complex_command_with_multiple_flags(self, mock_context):
        """Test complex dbt command with multiple flags."""
        command = ["run", "--select", "tag:daily", "--exclude", "tag:slow"]
        vars_dict = {"simulation_year": 2025, "random_seed": 42}

        execute_dbt_command(
            mock_context, command, vars_dict, False, "complex command test"
        )

        mock_context.resources.dbt.cli.assert_called_once_with(
            ["run", "--select", "tag:daily", "--exclude", "tag:slow"], vars=vars_dict
        )

    def test_snapshot_command(self, mock_context):
        """Test snapshot command execution."""
        command = ["snapshot", "--select", "scd_workforce_state"]
        vars_dict = {"simulation_year": 2024}

        execute_dbt_command(
            mock_context, command, vars_dict, False, "snapshot execution"
        )

        mock_context.resources.dbt.cli.assert_called_once_with(
            ["snapshot", "--select", "scd_workforce_state"], vars=vars_dict
        )

    def test_dbt_command_failure(self, mock_context):
        """Test error handling when dbt command fails."""
        command = ["run", "--select", "failing_model"]
        vars_dict = {"simulation_year": 2025}

        # Mock dbt command failure
        mock_context.resources.dbt.cli.side_effect = Exception("dbt compilation error")

        # Should raise the exception
        with pytest.raises(Exception) as exc_info:
            execute_dbt_command(
                mock_context, command, vars_dict, False, "failing command"
            )

        assert "dbt compilation error" in str(exc_info.value)

        # Verify error was logged
        mock_context.log.error.assert_called_once()

    def test_default_description_parameter(self, mock_context):
        """Test default empty description parameter."""
        command = ["run"]
        vars_dict = {"year": 2025}

        # Call without description (should use default)
        execute_dbt_command(mock_context, command, vars_dict, False)

        # Should log with generic message for empty description
        mock_context.log.info.assert_called_with("✅ dbt command completed: ")

    def test_description_with_special_characters(self, mock_context):
        """Test description with special characters and formatting."""
        command = ["run"]
        vars_dict = {"simulation_year": 2025}
        description = "test with émojis 🚀 and (special) [characters] & symbols"

        execute_dbt_command(mock_context, command, vars_dict, False, description)

        mock_context.log.info.assert_called_with(
            f"✅ dbt command completed: {description}"
        )

    @pytest.mark.parametrize("full_refresh", [True, False])
    def test_full_refresh_parameter_variations(self, mock_context, full_refresh):
        """Test full_refresh parameter with both True and False values."""
        command = ["run", "--select", "test_model"]
        vars_dict = {"simulation_year": 2025}

        execute_dbt_command(
            mock_context, command, vars_dict, full_refresh, "parametrized test"
        )

        expected_command = command.copy()
        if full_refresh:
            expected_command.append("--full-refresh")

        mock_context.resources.dbt.cli.assert_called_once_with(
            expected_command, vars=vars_dict
        )

    @pytest.mark.parametrize(
        "command_type,expected_command",
        [
            (["run"], ["run"]),
            (["test"], ["test"]),
            (["snapshot"], ["snapshot"]),
            (["run", "--select", "model"], ["run", "--select", "model"]),
            (["test", "--select", "test_name"], ["test", "--select", "test_name"]),
        ],
    )
    def test_various_dbt_command_types(
        self, mock_context, command_type, expected_command
    ):
        """Test various dbt command types."""
        vars_dict = {"simulation_year": 2025}

        execute_dbt_command(
            mock_context, command_type, vars_dict, False, "command type test"
        )

        mock_context.resources.dbt.cli.assert_called_once_with(
            expected_command, vars=vars_dict
        )

    def test_large_vars_dict(self, mock_context):
        """Test execution with large variables dictionary."""
        command = ["run"]
        vars_dict = {
            "simulation_year": 2025,
            "start_year": 2020,
            "end_year": 2030,
            "target_growth_rate": 0.03,
            "total_termination_rate": 0.12,
            "new_hire_termination_rate": 0.25,
            "random_seed": 42,
            "full_refresh": False,
            "additional_param_1": "value1",
            "additional_param_2": "value2",
        }

        execute_dbt_command(mock_context, command, vars_dict, False, "large vars test")

        mock_context.resources.dbt.cli.assert_called_once_with(["run"], vars=vars_dict)

    def test_none_values_in_vars_dict(self, mock_context):
        """Test handling of None values in variables dictionary."""
        command = ["run"]
        vars_dict = {
            "simulation_year": 2025,
            "optional_param": None,
            "another_param": "valid_value",
        }

        execute_dbt_command(mock_context, command, vars_dict, False, "none values test")

        # Should pass the vars_dict as-is, including None values
        mock_context.resources.dbt.cli.assert_called_once_with(["run"], vars=vars_dict)

    def test_concurrent_execution_safety(self, mock_context):
        """Test that function is safe for concurrent execution."""
        command = ["run", "--select", "concurrent_model"]
        vars_dict = {"simulation_year": 2025}

        # Execute multiple times to simulate concurrent calls
        for i in range(3):
            execute_dbt_command(
                mock_context, command, vars_dict, False, f"concurrent test {i}"
            )

        # Should have been called 3 times
        assert mock_context.resources.dbt.cli.call_count == 3

        # All calls should have identical parameters
        for call in mock_context.resources.dbt.cli.call_args_list:
            assert call[0] == (command,)
            assert call[1] == {"vars": vars_dict}


class TestExecuteDbtCommandIntegration:
    """Integration tests for execute_dbt_command with realistic scenarios."""

    @pytest.fixture
    def integration_context(self):
        """Create a more realistic context for integration testing."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        context.resources = Mock()
        context.resources.dbt = Mock()
        return context

    def test_realistic_simulation_workflow(self, integration_context):
        """Test realistic simulation workflow using execute_dbt_command."""
        # Simulate a complete simulation year workflow
        year = 2025
        config = {
            "simulation_year": year,
            "target_growth_rate": 0.03,
            "random_seed": 42,
        }

        workflow_commands = [
            (["run", "--select", "int_workforce_previous_year"], "workforce base"),
            (["run", "--select", "int_termination_events"], "termination events"),
            (["run", "--select", "int_hiring_events"], "hiring events"),
            (["run", "--select", "fct_yearly_events"], "yearly events"),
            (["run", "--select", "fct_workforce_snapshot"], "workforce snapshot"),
            (
                ["snapshot", "--select", "scd_workforce_state"],
                "workforce state snapshot",
            ),
        ]

        for command, description in workflow_commands:
            execute_dbt_command(
                integration_context, command, config, False, description
            )

        # Verify all commands were executed
        assert integration_context.resources.dbt.cli.call_count == len(
            workflow_commands
        )

        # Verify each command was called with correct parameters
        for i, (command, _) in enumerate(workflow_commands):
            call_args = integration_context.resources.dbt.cli.call_args_list[i]
            assert call_args[0] == (command,)
            assert call_args[1] == {"vars": config}

    def test_error_recovery_scenario(self, integration_context):
        """Test error recovery in multi-command scenario."""
        config = {"simulation_year": 2025}

        # First command succeeds
        execute_dbt_command(
            integration_context,
            ["run", "--select", "success_model"],
            config,
            False,
            "success",
        )

        # Second command fails
        integration_context.resources.dbt.cli.side_effect = Exception(
            "Model compilation failed"
        )

        with pytest.raises(Exception):
            execute_dbt_command(
                integration_context,
                ["run", "--select", "fail_model"],
                config,
                False,
                "failure",
            )

        # Reset for third command
        integration_context.resources.dbt.cli.side_effect = None

        # Third command succeeds
        execute_dbt_command(
            integration_context,
            ["run", "--select", "recovery_model"],
            config,
            False,
            "recovery",
        )

        # Verify execution pattern
        assert integration_context.resources.dbt.cli.call_count == 3


class TestExecuteDbtCommandStreaming:
    """Test suite for execute_dbt_command_streaming utility."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock Dagster execution context."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        context.log.info = Mock()
        context.log.error = Mock()

        # Mock dbt resource
        dbt_resource = Mock()
        dbt_resource.cli = Mock()
        context.resources = Mock()
        context.resources.dbt = dbt_resource

        return context

    def test_basic_streaming_build_command(self, mock_context):
        """Test basic streaming build command execution."""
        command = ["build"]
        description = "full dbt build pipeline"

        # Mock streaming response
        mock_stream = Mock()
        mock_stream.stream.return_value = iter(["result1", "result2"])
        mock_context.resources.dbt.cli.return_value = mock_stream

        # Execute and collect results
        results = list(execute_dbt_command_streaming(mock_context, command, {}, False, description))

        # Verify dbt.cli was called correctly
        mock_context.resources.dbt.cli.assert_called_once_with(
            ["build"], context=mock_context
        )

        # Verify streaming results
        assert results == ["result1", "result2"]

        # Verify logging
        mock_context.log.info.assert_any_call("Executing (streaming): dbt build")
        mock_context.log.info.assert_any_call(f"Description: {description}")
        mock_context.log.info.assert_any_call("Successfully completed (streaming): dbt build")

    def test_streaming_with_variables(self, mock_context):
        """Test streaming command with variables."""
        command = ["run", "--select", "test_model"]
        vars_dict = {"simulation_year": 2025, "random_seed": 42}
        description = "test model with variables"

        # Mock streaming response
        mock_stream = Mock()
        mock_stream.stream.return_value = iter(["result"])
        mock_context.resources.dbt.cli.return_value = mock_stream

        # Execute
        results = list(execute_dbt_command_streaming(mock_context, command, vars_dict, False, description))

        # Verify dbt.cli was called with variables
        expected_command = ["run", "--select", "test_model", "--vars", "{simulation_year: 2025, random_seed: 42}"]
        mock_context.resources.dbt.cli.assert_called_once_with(expected_command, context=mock_context)

        # Verify results
        assert results == ["result"]

    def test_streaming_with_full_refresh(self, mock_context):
        """Test streaming command with full refresh flag."""
        command = ["run", "--select", "test_model"]

        # Mock streaming response
        mock_stream = Mock()
        mock_stream.stream.return_value = iter(["result"])
        mock_context.resources.dbt.cli.return_value = mock_stream

        # Execute
        results = list(execute_dbt_command_streaming(mock_context, command, {}, True, "full refresh test"))

        # Verify dbt.cli was called with full refresh
        expected_command = ["run", "--select", "test_model", "--full-refresh"]
        mock_context.resources.dbt.cli.assert_called_once_with(expected_command, context=mock_context)

        # Verify results
        assert results == ["result"]

    def test_streaming_error_handling(self, mock_context):
        """Test error handling in streaming execution."""
        command = ["build"]
        description = "failing build"

        # Mock streaming failure
        mock_stream = Mock()
        mock_stream.stream.side_effect = Exception("Stream failed")
        mock_context.resources.dbt.cli.return_value = mock_stream

        # Execute and expect exception
        with pytest.raises(Exception) as exc_info:
            list(execute_dbt_command_streaming(mock_context, command, {}, False, description))

        # Verify error message
        assert "Failed to run build for failing build" in str(exc_info.value)
        assert "Stream failed" in str(exc_info.value)

        # Verify error logging
        mock_context.log.error.assert_called_once()

    def test_streaming_no_variables(self, mock_context):
        """Test streaming command with no variables (None case)."""
        command = ["build"]

        # Mock streaming response
        mock_stream = Mock()
        mock_stream.stream.return_value = iter(["result"])
        mock_context.resources.dbt.cli.return_value = mock_stream

        # Execute with None variables
        results = list(execute_dbt_command_streaming(mock_context, command, None, False, "no vars test"))

        # Verify dbt.cli was called without variables
        mock_context.resources.dbt.cli.assert_called_once_with(["build"], context=mock_context)

        # Verify results
        assert results == ["result"]

    def test_streaming_empty_description(self, mock_context):
        """Test streaming command with empty description."""
        command = ["build"]

        # Mock streaming response
        mock_stream = Mock()
        mock_stream.stream.return_value = iter(["result"])
        mock_context.resources.dbt.cli.return_value = mock_stream

        # Execute with empty description
        results = list(execute_dbt_command_streaming(mock_context, command, {}, False, ""))

        # Verify logging (description should not be logged)
        mock_context.log.info.assert_any_call("Executing (streaming): dbt build")
        mock_context.log.info.assert_any_call("Successfully completed (streaming): dbt build")

        # Verify results
        assert results == ["result"]
