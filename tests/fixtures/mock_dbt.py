"""Mock dbt runner and result fixtures."""

import pytest
from unittest.mock import Mock, MagicMock
from navigator_orchestrator.dbt_runner import DbtRunner, DbtResult


@pytest.fixture
def mock_dbt_result() -> DbtResult:
    """
    Mock successful dbt execution result.

    Usage:
        def test_result_handling(mock_dbt_result):
            assert mock_dbt_result.success is True
            assert mock_dbt_result.return_code == 0
    """
    return DbtResult(
        success=True,
        return_code=0,
        stdout="Completed successfully\n1 of 1 OK created",
        stderr="",
        execution_time=0.5,
        command=["run", "--select", "test_model"]
    )


@pytest.fixture
def mock_dbt_runner() -> Mock:
    """
    Mock DbtRunner with successful execution.

    Simulates successful dbt command execution without
    actual database operations.

    Usage:
        @pytest.mark.fast
        @pytest.mark.unit
        def test_orchestrator_integration(mock_dbt_runner):
            orchestrator = PipelineOrchestrator(config, dbt_runner=mock_dbt_runner)
            orchestrator.run_single_year(2025)
            mock_dbt_runner.execute_command.assert_called()
    """
    runner = Mock(spec=DbtRunner)
    runner.execute_command.return_value = DbtResult(
        success=True,
        return_code=0,
        stdout="Completed successfully",
        stderr="",
        execution_time=0.5,
        command=["run"]
    )
    return runner


@pytest.fixture
def failing_dbt_runner() -> Mock:
    """
    Mock DbtRunner with failed execution.

    Simulates dbt failures for error handling tests.

    Usage:
        @pytest.mark.fast
        @pytest.mark.unit
        def test_error_handling(failing_dbt_runner):
            orchestrator = PipelineOrchestrator(config, dbt_runner=failing_dbt_runner)
            with pytest.raises(RuntimeError):
                orchestrator.run_single_year(2025)
    """
    runner = Mock(spec=DbtRunner)
    runner.execute_command.return_value = DbtResult(
        success=False,
        return_code=1,
        stdout="",
        stderr="Database locked: could not acquire lock",
        execution_time=0.1,
        command=["run"]
    )
    return runner
