"""
Comprehensive tests for error handling framework.

This module tests circuit breakers, retry mechanisms, error classification,
and multi-year simulation error handling capabilities.
"""

import time
from datetime import datetime, timedelta
from typing import Any, Dict
from unittest.mock import MagicMock, Mock, patch

import pytest
from orchestrator_mvp.utils.error_handling import (CircuitBreaker,
                                                   CircuitBreakerConfig,
                                                   CircuitBreakerOpenError,
                                                   CircuitState, ErrorCategory,
                                                   ErrorClassifier,
                                                   ErrorContext, ErrorSeverity,
                                                   RetryConfig, RetryHandler,
                                                   with_circuit_breaker,
                                                   with_error_handling,
                                                   with_retry)
from orchestrator_mvp.utils.multi_year_error_handling import (
    CheckpointManager, CheckpointType, MultiYearErrorContext,
    MultiYearStateRecovery, SimulationCheckpoint,
    create_multi_year_error_context)
from orchestrator_mvp.utils.simulation_resilience import (
    MultiYearOrchestrationResilience, ResilientDatabaseManager,
    ResilientDbtExecutor)


class TestErrorClassifier:
    """Test error classification functionality."""

    def test_classify_connection_error(self):
        """Test classification of connection errors."""
        error = ConnectionError("Connection failed")
        severity, category = ErrorClassifier.classify_error(error)

        assert severity == ErrorSeverity.MEDIUM
        assert category == ErrorCategory.TRANSIENT

    def test_classify_memory_error(self):
        """Test classification of memory errors."""
        error = MemoryError("Out of memory")
        severity, category = ErrorClassifier.classify_error(error)

        assert severity == ErrorSeverity.HIGH
        assert category == ErrorCategory.RESOURCE

    def test_classify_syntax_error(self):
        """Test classification of syntax errors."""
        error = SyntaxError("Invalid syntax")
        severity, category = ErrorClassifier.classify_error(error)

        assert severity == ErrorSeverity.HIGH
        assert category == ErrorCategory.PERSISTENT

    def test_classify_custom_error_message(self):
        """Test classification based on error message content."""
        error = Exception("Database timeout occurred")
        severity, category = ErrorClassifier.classify_error(error)

        assert severity == ErrorSeverity.MEDIUM
        assert category == ErrorCategory.TRANSIENT

    def test_is_retryable_transient_error(self):
        """Test that transient errors are retryable."""
        error = ConnectionError("Network timeout")
        assert ErrorClassifier.is_retryable(error)

    def test_is_not_retryable_persistent_error(self):
        """Test that persistent errors are not retryable."""
        error = ValueError("Invalid configuration")
        assert not ErrorClassifier.is_retryable(error)

    def test_is_not_retryable_system_exit(self):
        """Test that SystemExit is not retryable."""
        error = SystemExit("System exit")
        assert not ErrorClassifier.is_retryable(error)


class TestCircuitBreaker:
    """Test circuit breaker functionality."""

    def test_circuit_breaker_initialization(self):
        """Test circuit breaker initialization."""
        config = CircuitBreakerConfig(failure_threshold=3)
        breaker = CircuitBreaker("test", config)

        assert breaker.name == "test"
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    def test_successful_execution(self):
        """Test successful function execution through circuit breaker."""
        config = CircuitBreakerConfig()
        breaker = CircuitBreaker("test", config)

        def successful_func():
            return "success"

        result = breaker.call(successful_func)
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED

    def test_failure_tracking(self):
        """Test that failures are tracked correctly."""
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker = CircuitBreaker("test", config)

        def failing_func():
            raise Exception("Test failure")

        # First failure
        with pytest.raises(Exception):
            breaker.call(failing_func)

        assert breaker.failure_count == 1
        assert breaker.state == CircuitState.CLOSED

        # Second failure should open circuit
        with pytest.raises(Exception):
            breaker.call(failing_func)

        assert breaker.failure_count == 2
        assert breaker.state == CircuitState.OPEN

    def test_circuit_opens_after_threshold(self):
        """Test that circuit opens after failure threshold."""
        config = CircuitBreakerConfig(failure_threshold=2)
        breaker = CircuitBreaker("test", config)

        def failing_func():
            raise Exception("Test failure")

        # Exceed failure threshold
        for _ in range(2):
            with pytest.raises(Exception):
                breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN

        # Next call should raise CircuitBreakerOpenError
        with pytest.raises(CircuitBreakerOpenError):
            breaker.call(failing_func)

    def test_circuit_recovery(self):
        """Test circuit breaker recovery mechanism."""
        config = CircuitBreakerConfig(
            failure_threshold=1,
            recovery_timeout_seconds=0.1,  # Very short for testing
            success_threshold=1,
        )
        breaker = CircuitBreaker("test", config)

        def failing_func():
            raise Exception("Test failure")

        def successful_func():
            return "success"

        # Open the circuit
        with pytest.raises(Exception):
            breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN

        # Wait for recovery timeout
        time.sleep(0.2)

        # Should transition to half-open and succeed
        result = breaker.call(successful_func)
        assert result == "success"
        assert breaker.state == CircuitState.CLOSED

    def test_get_stats(self):
        """Test circuit breaker statistics."""
        config = CircuitBreakerConfig()
        breaker = CircuitBreaker("test", config)

        stats = breaker.get_stats()

        assert stats["name"] == "test"
        assert stats["state"] == "closed"
        assert stats["failure_count"] == 0
        assert "config" in stats

    def test_reset(self):
        """Test circuit breaker reset functionality."""
        config = CircuitBreakerConfig(failure_threshold=1)
        breaker = CircuitBreaker("test", config)

        def failing_func():
            raise Exception("Test failure")

        # Open the circuit
        with pytest.raises(Exception):
            breaker.call(failing_func)

        assert breaker.state == CircuitState.OPEN

        # Reset should close circuit
        breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0


class TestRetryHandler:
    """Test retry handler functionality."""

    def test_retry_handler_initialization(self):
        """Test retry handler initialization."""
        config = RetryConfig(max_attempts=3)
        handler = RetryHandler("test", config)

        assert handler.name == "test"
        assert handler.config.max_attempts == 3

    def test_successful_execution_no_retry(self):
        """Test successful execution without retries."""
        config = RetryConfig()
        handler = RetryHandler("test", config)

        def successful_func():
            return "success"

        result = handler.execute(successful_func)
        assert result == "success"

    def test_retry_on_transient_error(self):
        """Test retry behavior on transient errors."""
        config = RetryConfig(max_attempts=3, base_delay_seconds=0.01)
        handler = RetryHandler("test", config)

        attempt_count = 0

        def failing_then_success():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count < 3:
                raise ConnectionError("Temporary failure")
            return "success"

        result = handler.execute(failing_then_success)
        assert result == "success"
        assert attempt_count == 3

    def test_no_retry_on_persistent_error(self):
        """Test that persistent errors are not retried."""
        config = RetryConfig(max_attempts=3)
        handler = RetryHandler("test", config)

        attempt_count = 0

        def persistent_failure():
            nonlocal attempt_count
            attempt_count += 1
            raise ValueError("Configuration error")

        with pytest.raises(ValueError):
            handler.execute(persistent_failure)

        assert attempt_count == 1  # Should not retry

    def test_max_attempts_exhausted(self):
        """Test behavior when max attempts are exhausted."""
        config = RetryConfig(max_attempts=2, base_delay_seconds=0.01)
        handler = RetryHandler("test", config)

        attempt_count = 0

        def always_failing():
            nonlocal attempt_count
            attempt_count += 1
            raise ConnectionError("Always fails")

        with pytest.raises(ConnectionError):
            handler.execute(always_failing)

        assert attempt_count == 2

    def test_exponential_backoff(self):
        """Test exponential backoff delay calculation."""
        config = RetryConfig(
            base_delay_seconds=0.1,
            exponential_backoff_multiplier=2.0,
            jitter_enabled=False,
        )
        handler = RetryHandler("test", config)

        # Test delay calculation
        delay1 = handler._calculate_delay(1)
        delay2 = handler._calculate_delay(2)
        delay3 = handler._calculate_delay(3)

        assert delay1 == 0.1
        assert delay2 == 0.2
        assert delay3 == 0.4


class TestErrorHandlingDecorators:
    """Test error handling decorators."""

    def test_with_circuit_breaker_decorator(self):
        """Test circuit breaker decorator."""
        config = CircuitBreakerConfig(failure_threshold=1)

        @with_circuit_breaker("test_decorator", config)
        def test_func():
            return "success"

        result = test_func()
        assert result == "success"

    def test_with_retry_decorator(self):
        """Test retry decorator."""
        config = RetryConfig(max_attempts=2, base_delay_seconds=0.01)

        attempt_count = 0

        @with_retry("test_retry", config)
        def test_func():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count == 1:
                raise ConnectionError("First attempt fails")
            return "success"

        result = test_func()
        assert result == "success"
        assert attempt_count == 2

    def test_comprehensive_error_handling_decorator(self):
        """Test comprehensive error handling decorator."""
        circuit_config = CircuitBreakerConfig(failure_threshold=2)
        retry_config = RetryConfig(max_attempts=2, base_delay_seconds=0.01)

        attempt_count = 0

        @with_error_handling("test_comprehensive", circuit_config, retry_config)
        def test_func():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count == 1:
                raise ConnectionError("First attempt fails")
            return "success"

        result = test_func()
        assert result == "success"
        assert attempt_count == 2


class TestCheckpointManager:
    """Test checkpoint management functionality."""

    @pytest.fixture
    def checkpoint_manager(self, tmp_path):
        """Create a checkpoint manager with temporary directory."""
        return CheckpointManager(str(tmp_path / "checkpoints"))

    def test_create_checkpoint(self, checkpoint_manager):
        """Test checkpoint creation."""
        state_data = {"year": 2025, "status": "completed"}

        checkpoint = checkpoint_manager.create_checkpoint(
            CheckpointType.YEAR_COMPLETE, 2025, state_data, metadata={"test": True}
        )

        assert checkpoint.checkpoint_type == CheckpointType.YEAR_COMPLETE
        assert checkpoint.simulation_year == 2025
        assert checkpoint.state_data == state_data
        assert checkpoint.metadata["test"] is True
        assert checkpoint.data_hash is not None

    def test_get_latest_checkpoint(self, checkpoint_manager):
        """Test getting latest checkpoint."""
        # Create multiple checkpoints
        checkpoint1 = checkpoint_manager.create_checkpoint(
            CheckpointType.YEAR_START, 2025, {"status": "starting"}
        )

        time.sleep(0.01)  # Ensure different timestamps

        checkpoint2 = checkpoint_manager.create_checkpoint(
            CheckpointType.YEAR_COMPLETE, 2025, {"status": "completed"}
        )

        # Get latest checkpoint
        latest = checkpoint_manager.get_latest_checkpoint(2025)
        assert latest.checkpoint_id == checkpoint2.checkpoint_id

        # Get latest of specific type
        latest_start = checkpoint_manager.get_latest_checkpoint(
            2025, CheckpointType.YEAR_START
        )
        assert latest_start.checkpoint_id == checkpoint1.checkpoint_id

    def test_checkpoint_validation(self, checkpoint_manager):
        """Test checkpoint validation."""
        state_data = {"year": 2025, "status": "test"}

        checkpoint = checkpoint_manager.create_checkpoint(
            CheckpointType.YEAR_COMPLETE, 2025, state_data
        )

        # Should validate successfully
        assert checkpoint_manager._validate_checkpoint(checkpoint)

        # Corrupt the data hash
        checkpoint.data_hash = "invalid_hash"
        assert not checkpoint_manager._validate_checkpoint(checkpoint)

    def test_get_resume_checkpoint(self, checkpoint_manager):
        """Test getting resume checkpoint."""
        # Create year complete checkpoints
        checkpoint_2025 = checkpoint_manager.create_checkpoint(
            CheckpointType.YEAR_COMPLETE, 2025, {"year": 2025, "status": "completed"}
        )

        checkpoint_2026 = checkpoint_manager.create_checkpoint(
            CheckpointType.YEAR_COMPLETE, 2026, {"year": 2026, "status": "completed"}
        )

        # Should resume from 2027 (after latest completed year)
        resume_info = checkpoint_manager.get_resume_checkpoint(2025, 2028)

        assert resume_info is not None
        resume_year, checkpoint = resume_info
        assert resume_year == 2027  # Year after latest completed
        assert checkpoint.checkpoint_id == checkpoint_2026.checkpoint_id

    def test_checkpoint_summary(self, checkpoint_manager):
        """Test checkpoint summary functionality."""
        # Create various checkpoints
        checkpoint_manager.create_checkpoint(
            CheckpointType.YEAR_START, 2025, {"status": "starting"}
        )

        checkpoint_manager.create_checkpoint(
            CheckpointType.YEAR_COMPLETE, 2025, {"status": "completed"}
        )

        summary = checkpoint_manager.get_checkpoint_summary()

        assert summary["total_checkpoints"] == 2
        assert 2025 in summary["years_with_checkpoints"]
        assert "year_start" in summary["checkpoint_types"]
        assert "year_complete" in summary["checkpoint_types"]
        assert summary["latest_checkpoint"] is not None


@pytest.fixture
def mock_database_connection():
    """Mock database connection for testing."""
    mock_conn = Mock()
    mock_conn.execute.return_value.fetchone.return_value = [100]  # Default return value
    mock_conn.close.return_value = None
    return mock_conn


class TestMultiYearStateRecovery:
    """Test multi-year state recovery functionality."""

    @pytest.fixture
    def checkpoint_manager(self, tmp_path):
        """Create a checkpoint manager for testing."""
        return CheckpointManager(str(tmp_path / "checkpoints"))

    @pytest.fixture
    def state_recovery(self, checkpoint_manager):
        """Create a state recovery manager for testing."""
        return MultiYearStateRecovery(checkpoint_manager)

    @patch("orchestrator_mvp.utils.multi_year_error_handling.get_connection")
    def test_detect_incomplete_simulation(
        self, mock_get_connection, state_recovery, mock_database_connection
    ):
        """Test detection of incomplete simulation."""
        mock_get_connection.return_value = mock_database_connection

        # Mock database responses for completed and missing years
        def mock_execute(query, params):
            result = Mock()
            year = params[0]
            if year == 2025:
                result.fetchone.return_value = [100]  # Completed year
            else:
                result.fetchone.return_value = [0]  # Missing year
            return result

        mock_database_connection.execute.side_effect = mock_execute

        detection = state_recovery.detect_incomplete_simulation(2025, 2027)

        assert detection["incomplete_simulation_detected"] is True
        assert 2025 in detection["completed_years"]
        assert 2026 in detection["missing_years"]
        assert 2027 in detection["missing_years"]
        assert detection["resume_recommendation"] == 2026

    @patch("orchestrator_mvp.utils.multi_year_error_handling.get_connection")
    def test_validate_multi_year_consistency(
        self, mock_get_connection, state_recovery, mock_database_connection
    ):
        """Test multi-year consistency validation."""
        mock_get_connection.return_value = mock_database_connection

        # Mock consistent data
        mock_database_connection.execute.return_value.fetchone.return_value = [100]

        validation = state_recovery.validate_multi_year_consistency(2025, 2026)

        assert validation["consistent"] is True
        assert 2025 in validation["year_validations"]
        assert 2026 in validation["year_validations"]

    def test_create_multi_year_error_context(self):
        """Test creation of multi-year error context."""
        error = Exception("Test error")

        context = create_multi_year_error_context(
            error, "test_operation", 2025, "test_step", 5, [2024], []
        )

        assert context.simulation_year == 2025
        assert context.step_name == "test_step"
        assert context.total_years == 5
        assert context.years_completed == [2024]
        assert context.can_resume is True
        assert "Resume from year" in context.recovery_options[0]


class TestResilientDbtExecutor:
    """Test resilient dbt executor functionality."""

    def test_initialization(self):
        """Test resilient dbt executor initialization."""
        executor = ResilientDbtExecutor("test_executor")

        assert executor.name == "test_executor"
        assert hasattr(executor, "model_config")
        assert hasattr(executor, "retry_config")
        assert len(executor.fallback_strategies) > 0

    def test_error_classification(self):
        """Test dbt error classification."""
        executor = ResilientDbtExecutor()

        compilation_error = Exception("compilation failed")
        assert executor._classify_dbt_error(compilation_error, "test") == "compilation"

        dependency_error = Exception("missing dependency")
        assert executor._classify_dbt_error(dependency_error, "test") == "dependency"

        resource_error = Exception("memory exceeded")
        assert executor._classify_dbt_error(resource_error, "test") == "resource"

    @patch("orchestrator_mvp.utils.simulation_resilience.run_dbt_model_with_vars")
    def test_run_model_with_resilience_success(self, mock_run_dbt):
        """Test successful model execution with resilience."""
        mock_run_dbt.return_value = {"success": True}

        executor = ResilientDbtExecutor()
        result = executor.run_model_with_resilience("test_model", {"year": 2025})

        assert result["success"] is True
        mock_run_dbt.assert_called_once()

    def test_get_execution_stats(self):
        """Test getting execution statistics."""
        executor = ResilientDbtExecutor()
        stats = executor.get_execution_stats()

        assert "total_dbt_operations" in stats
        assert "circuit_breaker_stats" in stats
        assert "overall_health" in stats


class TestResilientDatabaseManager:
    """Test resilient database manager functionality."""

    def test_initialization(self):
        """Test resilient database manager initialization."""
        manager = ResilientDatabaseManager("test_manager")

        assert manager.name == "test_manager"
        assert hasattr(manager, "db_config")
        assert hasattr(manager, "retry_config")

    @patch("orchestrator_mvp.utils.simulation_resilience.get_connection")
    def test_execute_query_with_resilience(self, mock_get_connection):
        """Test resilient query execution."""
        mock_conn = Mock()
        mock_conn.execute.return_value = "query_result"
        mock_get_connection.return_value = mock_conn

        manager = ResilientDatabaseManager()
        result = manager.execute_query_with_resilience(
            "SELECT * FROM test", operation_name="test_query"
        )

        assert result == "query_result"
        mock_conn.execute.assert_called_once_with("SELECT * FROM test")
        mock_conn.close.assert_called_once()

    @patch("orchestrator_mvp.utils.simulation_resilience.get_connection")
    def test_validate_data_consistency(self, mock_get_connection):
        """Test data consistency validation."""
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [100]
        mock_get_connection.return_value = mock_conn

        manager = ResilientDatabaseManager()
        result = manager.validate_data_consistency("test_table", 2025)

        assert result["consistent"] is True
        assert result["metrics"]["row_count"] == 100
        assert result["table_name"] == "test_table"
        assert result["year"] == 2025


class TestMultiYearOrchestrationResilience:
    """Test multi-year orchestration resilience functionality."""

    @pytest.fixture
    def orchestration_resilience(self, tmp_path):
        """Create orchestration resilience manager for testing."""
        # Mock checkpoint manager with temporary directory
        with patch(
            "orchestrator_mvp.utils.simulation_resilience.get_checkpoint_manager"
        ) as mock_get_cm:
            mock_cm = CheckpointManager(str(tmp_path / "checkpoints"))
            mock_get_cm.return_value = mock_cm

            return MultiYearOrchestrationResilience("test_orchestrator")

    def test_initialization(self, orchestration_resilience):
        """Test orchestration resilience initialization."""
        assert orchestration_resilience.orchestrator_name == "test_orchestrator"
        assert hasattr(orchestration_resilience, "checkpoint_manager")
        assert hasattr(orchestration_resilience, "state_recovery")
        assert hasattr(orchestration_resilience, "circuit_breaker")

    def test_resilient_year_execution_success(self, orchestration_resilience):
        """Test successful year execution with resilience."""
        with orchestration_resilience.resilient_year_execution(2025, 5):
            # Simulate successful year execution
            pass

        # Check that year complete checkpoint was created
        latest_checkpoint = (
            orchestration_resilience.checkpoint_manager.get_latest_checkpoint(
                2025, CheckpointType.YEAR_COMPLETE
            )
        )
        assert latest_checkpoint is not None
        assert latest_checkpoint.simulation_year == 2025

    def test_resilient_year_execution_failure(self, orchestration_resilience):
        """Test year execution failure handling."""
        with pytest.raises(ValueError):
            with orchestration_resilience.resilient_year_execution(2025, 5):
                # Simulate year execution failure
                raise ValueError("Simulated failure")

        # Check that error checkpoint was created
        error_checkpoint = (
            orchestration_resilience.checkpoint_manager.get_latest_checkpoint(
                2025, CheckpointType.ERROR_CHECKPOINT
            )
        )
        assert error_checkpoint is not None
        assert "failed" in error_checkpoint.state_data["status"]

    def test_resilient_step_execution_success(self, orchestration_resilience):
        """Test successful step execution with resilience."""
        with orchestration_resilience.resilient_step_execution("test_step", 2025):
            # Simulate successful step execution
            time.sleep(0.01)  # Brief execution time

        # Check that step complete checkpoint was created
        step_checkpoint = (
            orchestration_resilience.checkpoint_manager.get_latest_checkpoint(
                2025, CheckpointType.STEP_COMPLETE
            )
        )
        assert step_checkpoint is not None
        assert step_checkpoint.step_name == "test_step"

    def test_resilient_step_execution_failure(self, orchestration_resilience):
        """Test step execution failure handling."""
        with pytest.raises(RuntimeError):
            with orchestration_resilience.resilient_step_execution("test_step", 2025):
                # Simulate step execution failure
                raise RuntimeError("Step failed")

        # Check that error checkpoint was created
        error_checkpoint = (
            orchestration_resilience.checkpoint_manager.get_latest_checkpoint(
                2025, CheckpointType.ERROR_CHECKPOINT
            )
        )
        assert error_checkpoint is not None
        assert error_checkpoint.step_name == "test_step"

    @patch("orchestrator_mvp.utils.simulation_resilience.get_connection")
    def test_validate_resume_conditions(
        self, mock_get_connection, orchestration_resilience
    ):
        """Test validation of resume conditions."""
        # Mock database connection
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [100]  # Valid data
        mock_get_connection.return_value = mock_conn

        # Create a year complete checkpoint
        orchestration_resilience.checkpoint_manager.create_checkpoint(
            CheckpointType.YEAR_COMPLETE, 2025, {"year": 2025, "status": "completed"}
        )

        validation = orchestration_resilience.validate_resume_conditions(2025, 2027)

        assert "can_resume" in validation
        assert "resume_year" in validation
        assert "validation_results" in validation
        assert "recommendations" in validation


class TestIntegration:
    """Integration tests for the complete error handling system."""

    def test_error_handling_integration(self):
        """Test integration of circuit breaker and retry mechanisms."""
        # Configure circuit breaker to open quickly
        circuit_config = CircuitBreakerConfig(failure_threshold=2)
        retry_config = RetryConfig(max_attempts=3, base_delay_seconds=0.01)

        attempt_count = 0

        @with_error_handling("integration_test", circuit_config, retry_config)
        def test_function():
            nonlocal attempt_count
            attempt_count += 1
            if attempt_count <= 4:  # Fail first 4 attempts
                raise ConnectionError("Network issue")
            return "success"

        # First call should exhaust retries and open circuit
        with pytest.raises(ConnectionError):
            test_function()

        # Circuit should now be open
        with pytest.raises(CircuitBreakerOpenError):
            test_function()

        # Check that we made the expected number of attempts
        assert attempt_count == 3  # Max attempts from retry config

    @patch("orchestrator_mvp.utils.multi_year_error_handling.get_connection")
    def test_multi_year_error_recovery_integration(self, mock_get_connection, tmp_path):
        """Test integration of multi-year error recovery."""
        # Setup mock database
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [100]
        mock_get_connection.return_value = mock_conn

        # Create checkpoint manager and state recovery
        checkpoint_manager = CheckpointManager(str(tmp_path / "checkpoints"))
        state_recovery = MultiYearStateRecovery(checkpoint_manager)

        # Create some checkpoints
        checkpoint_manager.create_checkpoint(
            CheckpointType.YEAR_COMPLETE, 2025, {"year": 2025, "status": "completed"}
        )

        # Test incomplete simulation detection
        detection = state_recovery.detect_incomplete_simulation(2025, 2027)

        # Should detect incomplete simulation and suggest resume
        assert detection["incomplete_simulation_detected"] is True
        assert detection["resume_recommendation"] is not None

        # Test validation
        validation = state_recovery.validate_multi_year_consistency(2025, 2026)
        assert "consistent" in validation

    def test_resilient_operations_integration(self):
        """Test integration of resilient operation utilities."""
        # Test that resilient utilities can be created and used together
        dbt_executor = ResilientDbtExecutor("test")
        db_manager = ResilientDatabaseManager("test")

        # Test that they have proper error handling configurations
        assert dbt_executor.model_config.failure_threshold > 0
        assert db_manager.db_config.failure_threshold > 0

        # Test that statistics can be retrieved
        dbt_stats = dbt_executor.get_execution_stats()
        assert "total_dbt_operations" in dbt_stats

        # Test error classification
        error_type = dbt_executor._classify_dbt_error(
            Exception("compilation error"), "test"
        )
        assert error_type == "compilation"


if __name__ == "__main__":
    pytest.main([__file__])
