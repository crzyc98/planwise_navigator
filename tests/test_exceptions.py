"""
Unit tests for structured exception hierarchy (E074-01).

Tests exception serialization, context formatting, and resolution hints.
"""

from __future__ import annotations

import pytest
from navigator_orchestrator.exceptions import (
    NavigatorError,
    ExecutionContext,
    ResolutionHint,
    ErrorSeverity,
    ErrorCategory,
    DatabaseLockError,
    DbtCompilationError,
    DbtExecutionError,
    MissingConfigurationError,
    MemoryExhaustedError,
    PipelineStageError,
)


class TestExecutionContext:
    """Test ExecutionContext dataclass"""

    def test_default_context(self):
        """Test default context creation"""
        context = ExecutionContext()
        assert context.correlation_id is not None
        assert len(context.correlation_id) == 8
        assert context.timestamp is not None

    def test_full_context(self):
        """Test fully populated context"""
        context = ExecutionContext(
            simulation_year=2025,
            workflow_stage="EVENT_GENERATION",
            model_name="int_termination_events",
            scenario_id="baseline",
            plan_design_id="default",
            random_seed=42,
            thread_count=4,
            memory_mb=256.5,
            metadata={"custom": "value"}
        )

        assert context.simulation_year == 2025
        assert context.workflow_stage == "EVENT_GENERATION"
        assert context.model_name == "int_termination_events"
        assert context.metadata["custom"] == "value"

    def test_context_serialization(self):
        """Test context to_dict serialization"""
        context = ExecutionContext(
            simulation_year=2025,
            workflow_stage="FOUNDATION",
            model_name="int_baseline_workforce"
        )

        ctx_dict = context.to_dict()
        assert ctx_dict["simulation_year"] == 2025
        assert ctx_dict["workflow_stage"] == "FOUNDATION"
        assert "correlation_id" in ctx_dict
        assert "timestamp" in ctx_dict

    def test_context_format_summary(self):
        """Test human-readable summary formatting"""
        context = ExecutionContext(
            simulation_year=2026,
            workflow_stage="STATE_ACCUMULATION",
            model_name="fct_workforce_snapshot"
        )

        summary = context.format_summary()
        assert "year=2026" in summary
        assert "stage=STATE_ACCUMULATION" in summary
        assert "model=fct_workforce_snapshot" in summary
        assert "correlation_id=" in summary


class TestResolutionHint:
    """Test ResolutionHint dataclass"""

    def test_resolution_hint_creation(self):
        """Test creating resolution hints"""
        hint = ResolutionHint(
            title="Fix Database Lock",
            description="Close IDE connections",
            steps=["Close VS Code", "Retry simulation"],
            estimated_resolution_time="2 minutes"
        )

        assert hint.title == "Fix Database Lock"
        assert len(hint.steps) == 2
        assert hint.estimated_resolution_time == "2 minutes"


class TestNavigatorError:
    """Test base NavigatorError exception"""

    def test_basic_error_creation(self):
        """Test basic error without context"""
        error = NavigatorError("Test error message")
        assert str(error) == "Test error message"
        assert error.severity == ErrorSeverity.ERROR
        assert error.category == ErrorCategory.DATABASE

    def test_error_with_context(self):
        """Test error with execution context"""
        context = ExecutionContext(
            simulation_year=2025,
            workflow_stage="EVENT_GENERATION"
        )

        error = NavigatorError(
            "Database query failed",
            context=context,
            category=ErrorCategory.DATABASE,
            severity=ErrorSeverity.RECOVERABLE
        )

        assert error.context.simulation_year == 2025
        assert error.severity == ErrorSeverity.RECOVERABLE

    def test_error_with_resolution_hints(self):
        """Test error with resolution hints"""
        hints = [
            ResolutionHint(
                title="Solution 1",
                description="First approach",
                steps=["Step 1", "Step 2"]
            )
        ]

        error = NavigatorError("Test error", resolution_hints=hints)
        assert len(error.resolution_hints) == 1
        assert error.resolution_hints[0].title == "Solution 1"

    def test_error_serialization(self):
        """Test error to_dict serialization"""
        context = ExecutionContext(simulation_year=2025)
        error = NavigatorError(
            "Test error",
            context=context,
            category=ErrorCategory.CONFIGURATION
        )

        error_dict = error.to_dict()
        assert error_dict["error_type"] == "NavigatorError"
        assert error_dict["message"] == "Test error"
        assert error_dict["category"] == "configuration"
        assert error_dict["severity"] == "error"
        assert "context" in error_dict

    def test_diagnostic_message_formatting(self):
        """Test comprehensive diagnostic message formatting"""
        context = ExecutionContext(
            simulation_year=2025,
            workflow_stage="EVENT_GENERATION",
            model_name="int_termination_events"
        )

        hints = [
            ResolutionHint(
                title="Check Database Lock",
                description="Close IDE connections",
                steps=["Close VS Code", "Retry"],
                estimated_resolution_time="2 minutes"
            )
        ]

        error = NavigatorError(
            "Database execution failed",
            context=context,
            resolution_hints=hints,
            category=ErrorCategory.DATABASE,
            severity=ErrorSeverity.RECOVERABLE
        )

        diagnostic = error.format_diagnostic_message()

        # Verify all sections are present
        assert "ERROR: Database execution failed" in diagnostic
        assert "Severity: RECOVERABLE" in diagnostic
        assert "Category: database" in diagnostic
        assert "EXECUTION CONTEXT:" in diagnostic
        assert "simulation_year: 2025" in diagnostic
        assert "workflow_stage: EVENT_GENERATION" in diagnostic
        assert "RESOLUTION HINTS:" in diagnostic
        assert "Check Database Lock" in diagnostic
        assert "Close VS Code" in diagnostic
        assert "Est. Time: 2 minutes" in diagnostic


class TestDatabaseErrors:
    """Test database-specific exception classes"""

    def test_database_lock_error(self):
        """Test DatabaseLockError with built-in hints"""
        error = DatabaseLockError()

        assert error.category == ErrorCategory.DATABASE
        assert error.severity == ErrorSeverity.RECOVERABLE
        assert len(error.resolution_hints) > 0
        assert "Close IDE" in error.resolution_hints[0].title

    def test_database_lock_custom_message(self):
        """Test DatabaseLockError with custom message"""
        context = ExecutionContext(
            simulation_year=2025,
            model_name="fct_yearly_events"
        )

        error = DatabaseLockError(
            message="Lock detected during event generation",
            context=context
        )

        assert "Lock detected" in error.message
        assert error.context.simulation_year == 2025


class TestDbtErrors:
    """Test dbt-specific exception classes"""

    def test_dbt_compilation_error(self):
        """Test DbtCompilationError"""
        context = ExecutionContext(
            simulation_year=2025,
            model_name="int_baseline_workforce"
        )

        error = DbtCompilationError(
            "SQL syntax error in model",
            context=context
        )

        assert error.category == ErrorCategory.DATABASE
        assert error.severity == ErrorSeverity.ERROR
        assert len(error.resolution_hints) > 0
        assert "Syntax" in error.resolution_hints[0].title

    def test_dbt_execution_error(self):
        """Test DbtExecutionError"""
        error = DbtExecutionError("Query execution failed")

        assert error.severity == ErrorSeverity.RECOVERABLE
        assert len(error.resolution_hints) > 0


class TestConfigurationErrors:
    """Test configuration-specific exception classes"""

    def test_missing_configuration_error(self):
        """Test MissingConfigurationError"""
        error = MissingConfigurationError("random_seed")

        assert "random_seed" in error.message
        assert error.severity == ErrorSeverity.ERROR
        assert error.category == ErrorCategory.CONFIGURATION
        assert len(error.resolution_hints) > 0

    def test_missing_config_with_context(self):
        """Test MissingConfigurationError with execution context"""
        context = ExecutionContext(simulation_year=2025)
        error = MissingConfigurationError(
            "target_growth_rate",
            context=context
        )

        assert error.context.simulation_year == 2025


class TestResourceErrors:
    """Test resource exhaustion exception classes"""

    def test_memory_exhausted_error(self):
        """Test MemoryExhaustedError"""
        error = MemoryExhaustedError(
            "Simulation ran out of memory",
            memory_used_mb=4096.5
        )

        assert error.category == ErrorCategory.RESOURCE
        assert error.severity == ErrorSeverity.CRITICAL
        assert "4096.5MB" in error.message
        assert len(error.resolution_hints) > 0
        assert "Reduce Memory" in error.resolution_hints[0].title


class TestPipelineErrors:
    """Test pipeline orchestration exception classes"""

    def test_pipeline_stage_error(self):
        """Test PipelineStageError"""
        context = ExecutionContext(
            simulation_year=2025,
            workflow_stage="EVENT_GENERATION"
        )

        error = PipelineStageError(
            "Event generation failed",
            stage_name="EVENT_GENERATION",
            failed_models=["int_termination_events", "int_hiring_events"],
            context=context
        )

        assert error.category == ErrorCategory.DEPENDENCY
        assert error.severity == ErrorSeverity.ERROR
        assert "EVENT_GENERATION" in error.message
        assert len(error.additional_data.get("metadata", {}).get("failed_models", [])) == 2


class TestErrorWithOriginalException:
    """Test exception chaining and original exception tracking"""

    def test_error_with_original_exception(self):
        """Test NavigatorError wrapping original exception"""
        original = ValueError("Original error message")

        error = NavigatorError(
            "Wrapper error",
            original_exception=original
        )

        assert error.original_exception is original
        assert isinstance(error.original_exception, ValueError)

    def test_diagnostic_includes_original(self):
        """Test diagnostic message includes original exception"""
        original = RuntimeError("Database connection lost")
        context = ExecutionContext(simulation_year=2025)

        error = DatabaseLockError(
            "Failed to acquire lock",
            context=context,
            original_exception=original
        )

        diagnostic = error.format_diagnostic_message()
        assert "ORIGINAL EXCEPTION:" in diagnostic
        assert "RuntimeError" in diagnostic
        assert "Database connection lost" in diagnostic


class TestErrorSerialization:
    """Test comprehensive error serialization for logging"""

    def test_full_error_serialization(self):
        """Test complete error serialization"""
        context = ExecutionContext(
            simulation_year=2025,
            workflow_stage="STATE_ACCUMULATION",
            model_name="fct_workforce_snapshot",
            scenario_id="baseline",
            metadata={"retry_count": 3}
        )

        hints = [
            ResolutionHint(
                title="Retry Operation",
                description="Transient failure",
                steps=["Wait 30 seconds", "Retry"],
                estimated_resolution_time="1 minute"
            )
        ]

        original = ConnectionError("Network timeout")

        error = NavigatorError(
            "Database operation failed",
            context=context,
            category=ErrorCategory.NETWORK,
            severity=ErrorSeverity.RECOVERABLE,
            resolution_hints=hints,
            original_exception=original
        )

        serialized = error.to_dict()

        # Verify all fields are serialized
        assert serialized["error_type"] == "NavigatorError"
        assert serialized["message"] == "Database operation failed"
        assert serialized["category"] == "network"
        assert serialized["severity"] == "recoverable"
        assert serialized["context"]["simulation_year"] == 2025
        assert serialized["context"]["scenario_id"] == "baseline"
        assert len(serialized["resolution_hints"]) == 1
        assert serialized["resolution_hints"][0]["title"] == "Retry Operation"
        assert "Network timeout" in serialized["original_exception"]
