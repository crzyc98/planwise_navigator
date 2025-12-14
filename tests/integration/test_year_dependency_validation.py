"""
Integration tests for year dependency validation in YearExecutor.

Tests that the YearDependencyValidator is properly integrated into the
pipeline and fails fast with clear error messages when year dependencies
are violated during STATE_ACCUMULATION stage.

These tests verify the end-to-end behavior of:
- YearDependencyValidator integration in YearExecutor
- Proper error propagation through the pipeline
- Error message clarity and actionable resolution hints
"""

from __future__ import annotations

from typing import Dict
from unittest.mock import MagicMock, patch

import pytest

from planalign_orchestrator.exceptions import YearDependencyError
from planalign_orchestrator.pipeline.year_executor import YearExecutor
from planalign_orchestrator.pipeline.workflow import StageDefinition, WorkflowStage
from planalign_orchestrator.state_accumulator.registry import StateAccumulatorRegistry
from planalign_orchestrator.state_accumulator.contract import StateAccumulatorContract


class MockDatabaseConnectionManager:
    """Mock database connection manager for integration testing."""

    def __init__(self, table_counts: Dict[str, Dict[int, int]] = None):
        """Initialize with table counts by year.

        Args:
            table_counts: Dict mapping table_name -> {year: count}
                         e.g., {"int_enrollment": {2025: 100, 2026: 0}}
        """
        self.table_counts = table_counts or {}

    def execute_with_retry(self, func):
        """Execute function with mock connection."""
        mock_conn = MagicMock()

        def mock_execute(query, params):
            # Extract table name and year from query
            # Query format: "SELECT COUNT(*) FROM {table} WHERE {col} = ?"
            table_name = query.split("FROM")[1].split("WHERE")[0].strip()
            year = params[0]

            count = self.table_counts.get(table_name, {}).get(year, 0)
            mock_result = MagicMock()
            mock_result.fetchone.return_value = [count]
            return mock_result

        mock_conn.execute = mock_execute
        return func(mock_conn)


@pytest.fixture
def clean_registry():
    """Provide a clean registry state for testing."""
    StateAccumulatorRegistry.clear()
    yield StateAccumulatorRegistry
    StateAccumulatorRegistry.clear()


@pytest.fixture
def sample_contracts(clean_registry):
    """Register sample contracts for testing."""
    enrollment = StateAccumulatorContract(
        model_name="int_enrollment_state_accumulator",
        table_name="int_enrollment_state_accumulator",
        start_year_source="int_baseline_workforce",
    )
    deferral = StateAccumulatorContract(
        model_name="int_deferral_rate_state_accumulator",
        table_name="int_deferral_rate_state_accumulator",
        start_year_source="int_employee_compensation_by_year",
    )
    clean_registry.register(enrollment)
    clean_registry.register(deferral)
    return clean_registry


@pytest.fixture
def mock_config():
    """Create mock SimulationConfig for testing."""
    config = MagicMock()
    config.simulation.start_year = 2025

    # Mock Polars settings (disabled by default)
    config.is_polars_mode_enabled.return_value = False
    config.get_polars_settings.return_value = MagicMock(
        state_accumulation_enabled=False
    )

    return config


@pytest.fixture
def mock_dbt_runner():
    """Create mock DbtRunner for testing."""
    runner = MagicMock()
    result = MagicMock()
    result.success = True
    result.return_code = 0
    runner.execute_command.return_value = result
    return runner


class TestYearDependencyValidationIntegration:
    """Integration tests for year dependency validation in YearExecutor."""

    def test_state_accumulation_validates_dependencies_before_execution(
        self, sample_contracts, mock_config, mock_dbt_runner
    ):
        """Test that STATE_ACCUMULATION stage validates year dependencies first."""
        # Setup: No data for 2025 (prior year check will fail)
        db_manager = MockDatabaseConnectionManager({})

        executor = YearExecutor(
            config=mock_config,
            dbt_runner=mock_dbt_runner,
            db_manager=db_manager,
            dbt_vars={"scenario_id": "baseline"},
            dbt_threads=1,
            start_year=2025,
            verbose=False,
        )

        # Create STATE_ACCUMULATION stage
        stage = StageDefinition(
            name=WorkflowStage.STATE_ACCUMULATION,
            dependencies=[WorkflowStage.EVENT_GENERATION],
            models=["int_enrollment_state_accumulator", "fct_workforce_snapshot"],
            validation_rules=[],
        )

        # Execute year 2026 (which requires 2025 data)
        result = executor.execute_workflow_stage(stage, year=2026)

        # Should fail due to missing 2025 data
        assert result["success"] is False
        assert "YearDependencyError" in result.get("error", "") or "missing" in result.get("error", "").lower()

        # dbt should NOT have been called (fail-fast behavior)
        mock_dbt_runner.execute_command.assert_not_called()

    def test_start_year_executes_without_validation_failure(
        self, sample_contracts, mock_config, mock_dbt_runner
    ):
        """Test that start year (2025) executes without dependency validation failure."""
        # Setup: Empty database - but start year should not require prior data
        db_manager = MockDatabaseConnectionManager({})

        executor = YearExecutor(
            config=mock_config,
            dbt_runner=mock_dbt_runner,
            db_manager=db_manager,
            dbt_vars={"scenario_id": "baseline"},
            dbt_threads=1,
            start_year=2025,
            verbose=False,
        )

        # Create STATE_ACCUMULATION stage
        stage = StageDefinition(
            name=WorkflowStage.STATE_ACCUMULATION,
            dependencies=[WorkflowStage.EVENT_GENERATION],
            models=["int_enrollment_state_accumulator"],
            validation_rules=[],
        )

        # Execute start year - should NOT fail on dependency validation
        result = executor.execute_workflow_stage(stage, year=2025)

        # Start year should pass dependency validation
        # (may fail later due to mock, but not on year dependency)
        assert "YearDependencyError" not in result.get("error", "")

    def test_validation_passes_when_prior_year_data_exists(
        self, sample_contracts, mock_config, mock_dbt_runner
    ):
        """Test that validation passes when prior year data exists."""
        # Setup: Data exists for 2025
        db_manager = MockDatabaseConnectionManager({
            "int_enrollment_state_accumulator": {2025: 100},
            "int_deferral_rate_state_accumulator": {2025: 100},
        })

        executor = YearExecutor(
            config=mock_config,
            dbt_runner=mock_dbt_runner,
            db_manager=db_manager,
            dbt_vars={"scenario_id": "baseline"},
            dbt_threads=1,
            start_year=2025,
            verbose=False,
        )

        # Create STATE_ACCUMULATION stage
        stage = StageDefinition(
            name=WorkflowStage.STATE_ACCUMULATION,
            dependencies=[WorkflowStage.EVENT_GENERATION],
            models=["int_enrollment_state_accumulator"],
            validation_rules=[],
        )

        # Execute year 2026 (2025 data exists)
        result = executor.execute_workflow_stage(stage, year=2026)

        # Should pass validation (may succeed or fail on dbt execution, but not on validation)
        assert "YearDependencyError" not in result.get("error", "")

    def test_event_generation_stage_does_not_trigger_validation(
        self, sample_contracts, mock_config, mock_dbt_runner
    ):
        """Test that EVENT_GENERATION stage does not trigger year dependency validation."""
        # Setup: No data for any year
        db_manager = MockDatabaseConnectionManager({})

        executor = YearExecutor(
            config=mock_config,
            dbt_runner=mock_dbt_runner,
            db_manager=db_manager,
            dbt_vars={"scenario_id": "baseline"},
            dbt_threads=1,
            start_year=2025,
            verbose=False,
        )

        # Create EVENT_GENERATION stage
        stage = StageDefinition(
            name=WorkflowStage.EVENT_GENERATION,
            dependencies=[WorkflowStage.FOUNDATION],
            models=["int_termination_events"],
            validation_rules=[],
        )

        # Execute year 2026 - should NOT fail on year dependency validation
        # (EVENT_GENERATION doesn't have temporal dependencies)
        result = executor.execute_workflow_stage(stage, year=2026)

        # Should not fail on YearDependencyError
        assert "YearDependencyError" not in result.get("error", "")


class TestYearDependencyErrorMessages:
    """Tests for error message clarity and resolution hints."""

    def test_error_message_contains_actionable_information(
        self, sample_contracts, mock_config, mock_dbt_runner
    ):
        """Test that error messages contain actionable resolution information."""
        # Setup: No data for 2025
        db_manager = MockDatabaseConnectionManager({})

        executor = YearExecutor(
            config=mock_config,
            dbt_runner=mock_dbt_runner,
            db_manager=db_manager,
            dbt_vars={"scenario_id": "baseline"},
            dbt_threads=1,
            start_year=2025,
            verbose=False,
        )

        # Create STATE_ACCUMULATION stage
        stage = StageDefinition(
            name=WorkflowStage.STATE_ACCUMULATION,
            dependencies=[WorkflowStage.EVENT_GENERATION],
            models=["int_enrollment_state_accumulator"],
            validation_rules=[],
        )

        # Execute year 2026 (will fail)
        result = executor.execute_workflow_stage(stage, year=2026)

        # Error message should be informative
        error_msg = result.get("error", "")
        assert len(error_msg) > 0
        # Should mention the year or dependency issue
        assert "2026" in error_msg or "2025" in error_msg or "dependency" in error_msg.lower()

    def test_error_lists_missing_tables(
        self, sample_contracts, mock_config, mock_dbt_runner
    ):
        """Test that error message lists which tables are missing data."""
        # Setup: Only enrollment has data, deferral does not
        db_manager = MockDatabaseConnectionManager({
            "int_enrollment_state_accumulator": {2025: 100},
            "int_deferral_rate_state_accumulator": {2025: 0},
        })

        executor = YearExecutor(
            config=mock_config,
            dbt_runner=mock_dbt_runner,
            db_manager=db_manager,
            dbt_vars={"scenario_id": "baseline"},
            dbt_threads=1,
            start_year=2025,
            verbose=False,
        )

        # Create STATE_ACCUMULATION stage
        stage = StageDefinition(
            name=WorkflowStage.STATE_ACCUMULATION,
            dependencies=[WorkflowStage.EVENT_GENERATION],
            models=["int_enrollment_state_accumulator", "int_deferral_rate_state_accumulator"],
            validation_rules=[],
        )

        # Execute year 2026 (will fail on deferral)
        result = executor.execute_workflow_stage(stage, year=2026)

        # Should fail and mention the missing table
        assert result["success"] is False
        error_msg = result.get("error", "")
        assert "deferral" in error_msg.lower() or "missing" in error_msg.lower()
