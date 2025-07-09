"""
Unit tests for S013-06: Multi-Year Orchestration Transformation

Comprehensive test suite for the transformed run_multi_year_simulation function,
validating that it operates as a pure orchestrator leveraging modular components.
"""

import pytest
from unittest.mock import Mock, patch
from dagster import build_op_context

from orchestrator.simulator_pipeline import (
    run_multi_year_simulation,
    _create_baseline_snapshot,
    _execute_single_year_with_recovery,
    _log_simulation_summary,
    YearResult
)


class TestRunMultiYearSimulation:
    """Test suite for the transformed run_multi_year_simulation orchestrator."""

    @pytest.fixture
    def mock_context(self):
        """Create a proper Dagster execution context."""
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
                "end_year": 2027,
                "target_growth_rate": 0.03,
                "total_termination_rate": 0.12,
                "new_hire_termination_rate": 0.25,
                "random_seed": 42,
                "full_refresh": False,
            },
            resources={"dbt": dbt_resource}
        )

        return context

    @patch('orchestrator.simulator_pipeline.clean_duckdb_data')
    @patch('orchestrator.simulator_pipeline._create_baseline_snapshot')
    @patch('orchestrator.simulator_pipeline._execute_single_year_with_recovery')
    @patch('orchestrator.simulator_pipeline._log_simulation_summary')
    def test_pure_orchestration_pattern(
        self,
        mock_log_summary,
        mock_execute_year,
        mock_create_baseline,
        mock_clean_data,
        mock_context
    ):
        """Test that the function operates as a pure orchestrator."""
        # Setup successful year results
        mock_execute_year.side_effect = [
            YearResult(year=2025, success=True, active_employees=1030, total_terminations=120,
                      experienced_terminations=100, new_hire_terminations=20, total_hires=150,
                      growth_rate=0.03, validation_passed=True),
            YearResult(year=2026, success=True, active_employees=1061, total_terminations=125,
                      experienced_terminations=105, new_hire_terminations=20, total_hires=156,
                      growth_rate=0.03, validation_passed=True),
            YearResult(year=2027, success=True, active_employees=1093, total_terminations=130,
                      experienced_terminations=110, new_hire_terminations=20, total_hires=162,
                      growth_rate=0.03, validation_passed=True)
        ]

        # Execute
        results = run_multi_year_simulation(mock_context, True)

        # Verify orchestration sequence
        mock_clean_data.assert_called_once_with(mock_context, [2025, 2026, 2027])
        mock_create_baseline.assert_not_called()  # start_year is 2025
        assert mock_execute_year.call_count == 3
        mock_log_summary.assert_called_once()

        # Verify results
        assert len(results) == 3
        assert all(r.success for r in results)
        assert [r.year for r in results] == [2025, 2026, 2027]

    @patch('orchestrator.simulator_pipeline.clean_duckdb_data')
    @patch('orchestrator.simulator_pipeline._create_baseline_snapshot')
    @patch('orchestrator.simulator_pipeline._execute_single_year_with_recovery')
    @patch('orchestrator.simulator_pipeline._log_simulation_summary')
    def test_baseline_snapshot_creation(
        self,
        mock_log_summary,
        mock_execute_year,
        mock_create_baseline,
        mock_clean_data,
        mock_context
    ):
        """Test baseline snapshot creation when start_year > 2025."""
        # Setup for year 2026 start
        mock_context.op_config["start_year"] = 2026
        mock_context.op_config["end_year"] = 2027

        mock_execute_year.side_effect = [
            YearResult(year=2026, success=True, active_employees=1061, total_terminations=125,
                      experienced_terminations=105, new_hire_terminations=20, total_hires=156,
                      growth_rate=0.03, validation_passed=True),
            YearResult(year=2027, success=True, active_employees=1093, total_terminations=130,
                      experienced_terminations=110, new_hire_terminations=20, total_hires=162,
                      growth_rate=0.03, validation_passed=True)
        ]

        # Execute
        results = run_multi_year_simulation(mock_context, True)

        # Verify baseline snapshot was created
        mock_create_baseline.assert_called_once_with(mock_context, 2025)
        mock_clean_data.assert_called_once_with(mock_context, [2026, 2027])
        assert mock_execute_year.call_count == 2

        # Verify results
        assert len(results) == 2
        assert all(r.success for r in results)

    @patch('orchestrator.simulator_pipeline.clean_duckdb_data')
    @patch('orchestrator.simulator_pipeline._create_baseline_snapshot')
    @patch('orchestrator.simulator_pipeline._execute_single_year_with_recovery')
    @patch('orchestrator.simulator_pipeline._log_simulation_summary')
    def test_error_handling_and_continuation(
        self,
        mock_log_summary,
        mock_execute_year,
        mock_create_baseline,
        mock_clean_data,
        mock_context
    ):
        """Test error handling and continuation after failures."""
        # Setup mixed success/failure results
        mock_execute_year.side_effect = [
            YearResult(year=2025, success=True, active_employees=1030, total_terminations=120,
                      experienced_terminations=100, new_hire_terminations=20, total_hires=150,
                      growth_rate=0.03, validation_passed=True),
            YearResult(year=2026, success=False, active_employees=0, total_terminations=0,
                      experienced_terminations=0, new_hire_terminations=0, total_hires=0,
                      growth_rate=0.0, validation_passed=False),
            YearResult(year=2027, success=True, active_employees=1093, total_terminations=130,
                      experienced_terminations=110, new_hire_terminations=20, total_hires=162,
                      growth_rate=0.03, validation_passed=True)
        ]

        # Execute
        results = run_multi_year_simulation(mock_context, True)

        # Verify all years were processed despite failure
        assert len(results) == 3
        assert results[0].success is True
        assert results[1].success is False
        assert results[2].success is True

        # Verify orchestration continued
        assert mock_execute_year.call_count == 3
        mock_log_summary.assert_called_once()

    def test_baseline_validation_failure(self, mock_context):
        """Test that function raises exception when baseline validation fails."""
        with pytest.raises(Exception, match="Baseline workforce validation failed"):
            run_multi_year_simulation(mock_context, False)

    @patch('orchestrator.simulator_pipeline.clean_duckdb_data')
    @patch('orchestrator.simulator_pipeline._create_baseline_snapshot')
    @patch('orchestrator.simulator_pipeline._execute_single_year_with_recovery')
    @patch('orchestrator.simulator_pipeline._log_simulation_summary')
    def test_full_refresh_handling(
        self,
        mock_log_summary,
        mock_execute_year,
        mock_create_baseline,
        mock_clean_data,
        mock_context
    ):
        """Test full_refresh flag handling."""
        # Setup with full_refresh enabled
        mock_context.op_config["full_refresh"] = True

        mock_execute_year.return_value = YearResult(
            year=2025, success=True, active_employees=1030, total_terminations=120,
            experienced_terminations=100, new_hire_terminations=20, total_hires=150,
            growth_rate=0.03, validation_passed=True
        )

        # Execute
        results = run_multi_year_simulation(mock_context, True)

        # Verify orchestration occurred
        mock_clean_data.assert_called_once()
        mock_execute_year.assert_called()
        mock_log_summary.assert_called_once()

        # Verify results
        assert len(results) == 3  # 2025-2027

    @patch('orchestrator.simulator_pipeline.clean_duckdb_data')
    @patch('orchestrator.simulator_pipeline._execute_single_year_with_recovery')
    @patch('orchestrator.simulator_pipeline._log_simulation_summary')
    def test_single_year_range(
        self,
        mock_log_summary,
        mock_execute_year,
        mock_clean_data,
        mock_context
    ):
        """Test orchestration with single year range."""
        # Setup for single year
        mock_context.op_config["start_year"] = 2025
        mock_context.op_config["end_year"] = 2025

        mock_execute_year.return_value = YearResult(
            year=2025, success=True, active_employees=1030, total_terminations=120,
            experienced_terminations=100, new_hire_terminations=20, total_hires=150,
            growth_rate=0.03, validation_passed=True
        )

        # Execute
        results = run_multi_year_simulation(mock_context, True)

        # Verify single year orchestration
        mock_clean_data.assert_called_once_with(mock_context, [2025])
        mock_execute_year.assert_called_once()
        mock_log_summary.assert_called_once()

        # Verify results
        assert len(results) == 1
        assert results[0].year == 2025


class TestCreateBaselineSnapshot:
    """Test suite for _create_baseline_snapshot helper function."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock context for testing."""
        context = Mock()
        context.log = Mock()
        return context

    @patch('orchestrator.simulator_pipeline.run_dbt_snapshot_for_year')
    def test_successful_baseline_snapshot(self, mock_snapshot, mock_context):
        """Test successful baseline snapshot creation."""
        # Setup successful snapshot result
        mock_snapshot.return_value = {"success": True, "records_created": 1000}

        # Execute
        _create_baseline_snapshot(mock_context, 2024)

        # Verify snapshot was called correctly
        mock_snapshot.assert_called_once_with(mock_context, 2024, "previous_year")

        # Verify no warnings logged
        mock_context.log.warning.assert_not_called()

    @patch('orchestrator.simulator_pipeline.run_dbt_snapshot_for_year')
    def test_failed_baseline_snapshot(self, mock_snapshot, mock_context):
        """Test failed baseline snapshot creation."""
        # Setup failed snapshot result
        mock_snapshot.return_value = {"success": False, "error": "Database connection failed"}

        # Execute
        _create_baseline_snapshot(mock_context, 2024)

        # Verify snapshot was called correctly
        mock_snapshot.assert_called_once_with(mock_context, 2024, "previous_year")

        # Verify warning was logged
        mock_context.log.warning.assert_called_once_with(
            "Baseline snapshot creation had issues: Database connection failed"
        )


class TestExecuteSingleYearWithRecovery:
    """Test suite for _execute_single_year_with_recovery helper function."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock context for testing."""
        context = Mock()
        context.log = Mock()
        return context

    @patch('orchestrator.simulator_pipeline.assert_year_complete')
    @patch('orchestrator.simulator_pipeline.run_dbt_snapshot_for_year')
    @patch('orchestrator.simulator_pipeline.run_year_simulation_for_multi_year')
    def test_successful_year_execution(
        self,
        mock_simulation,
        mock_snapshot,
        mock_assert_year,
        mock_context
    ):
        """Test successful year execution."""
        # Setup successful simulation result
        expected_result = YearResult(
            year=2025, success=True, active_employees=1030, total_terminations=120,
            experienced_terminations=100, new_hire_terminations=20, total_hires=150,
            growth_rate=0.03, validation_passed=True
        )
        mock_simulation.return_value = expected_result

        # Execute first year (no previous year validation)
        result = _execute_single_year_with_recovery(mock_context, 2025, 2025)

        # Verify no previous year validation
        mock_assert_year.assert_not_called()

        # Verify simulation was called
        mock_simulation.assert_called_once_with(mock_context, 2025)

        # Verify end-of-year snapshot was created
        mock_snapshot.assert_called_once_with(mock_context, 2025, "end_of_year")

        # Verify result
        assert result == expected_result

    @patch('orchestrator.simulator_pipeline.assert_year_complete')
    @patch('orchestrator.simulator_pipeline.run_dbt_snapshot_for_year')
    @patch('orchestrator.simulator_pipeline.run_year_simulation_for_multi_year')
    def test_subsequent_year_execution(
        self,
        mock_simulation,
        mock_snapshot,
        mock_assert_year,
        mock_context
    ):
        """Test subsequent year execution with previous year validation."""
        # Setup successful simulation result
        expected_result = YearResult(
            year=2026, success=True, active_employees=1061, total_terminations=125,
            experienced_terminations=105, new_hire_terminations=20, total_hires=156,
            growth_rate=0.03, validation_passed=True
        )
        mock_simulation.return_value = expected_result

        # Execute subsequent year
        result = _execute_single_year_with_recovery(mock_context, 2026, 2025)

        # Verify previous year validation
        mock_assert_year.assert_called_once_with(mock_context, 2025)

        # Verify previous year snapshot was created
        assert mock_snapshot.call_count == 2
        mock_snapshot.assert_any_call(mock_context, 2025, "previous_year")
        mock_snapshot.assert_any_call(mock_context, 2026, "end_of_year")

        # Verify simulation was called
        mock_simulation.assert_called_once_with(mock_context, 2026)

        # Verify result
        assert result == expected_result

    @patch('orchestrator.simulator_pipeline.assert_year_complete')
    @patch('orchestrator.simulator_pipeline.run_dbt_snapshot_for_year')
    @patch('orchestrator.simulator_pipeline.run_year_simulation_for_multi_year')
    def test_year_execution_failure(
        self,
        mock_simulation,
        mock_snapshot,
        mock_assert_year,
        mock_context
    ):
        """Test year execution failure handling."""
        # Setup simulation failure
        mock_simulation.side_effect = Exception("Simulation processing failed")

        # Execute
        result = _execute_single_year_with_recovery(mock_context, 2025, 2025)

        # Verify error was logged
        mock_context.log.error.assert_called_once_with("❌ Year 2025 failed: Simulation processing failed")

        # Verify failure result
        assert result.success is False
        assert result.year == 2025
        assert result.active_employees == 0
        assert result.validation_passed is False

    @patch('orchestrator.simulator_pipeline.assert_year_complete')
    @patch('orchestrator.simulator_pipeline.run_dbt_snapshot_for_year')
    @patch('orchestrator.simulator_pipeline.run_year_simulation_for_multi_year')
    def test_previous_year_validation_failure(
        self,
        mock_simulation,
        mock_snapshot,
        mock_assert_year,
        mock_context
    ):
        """Test previous year validation failure."""
        # Setup assertion failure
        mock_assert_year.side_effect = Exception("Previous year data missing")

        # Execute
        result = _execute_single_year_with_recovery(mock_context, 2026, 2025)

        # Verify error was logged
        mock_context.log.error.assert_called_once_with("❌ Year 2026 failed: Previous year data missing")

        # Verify simulation was not called
        mock_simulation.assert_not_called()

        # Verify failure result
        assert result.success is False
        assert result.year == 2026


class TestLogSimulationSummary:
    """Test suite for _log_simulation_summary helper function."""

    @pytest.fixture
    def mock_context(self):
        """Create a mock context for testing."""
        context = Mock()
        context.log = Mock()
        return context

    def test_all_successful_years(self, mock_context):
        """Test summary logging for all successful years."""
        results = [
            YearResult(year=2025, success=True, active_employees=1030, total_terminations=120,
                      experienced_terminations=100, new_hire_terminations=20, total_hires=150,
                      growth_rate=0.03, validation_passed=True),
            YearResult(year=2026, success=True, active_employees=1061, total_terminations=125,
                      experienced_terminations=105, new_hire_terminations=20, total_hires=156,
                      growth_rate=0.03, validation_passed=True),
        ]

        # Execute
        _log_simulation_summary(mock_context, results)

        # Verify summary logging
        mock_context.log.info.assert_any_call("📊 === Multi-year simulation summary ===")
        mock_context.log.info.assert_any_call("🎯 Simulation completed: 2/2 years successful")
        mock_context.log.info.assert_any_call("  ✅ Year 2025: 1,030 employees, 3.0% growth")
        mock_context.log.info.assert_any_call("  ✅ Year 2026: 1,061 employees, 3.0% growth")

        # Verify no warnings
        mock_context.log.warning.assert_not_called()

    def test_mixed_success_failure_years(self, mock_context):
        """Test summary logging for mixed success/failure years."""
        results = [
            YearResult(year=2025, success=True, active_employees=1030, total_terminations=120,
                      experienced_terminations=100, new_hire_terminations=20, total_hires=150,
                      growth_rate=0.03, validation_passed=True),
            YearResult(year=2026, success=False, active_employees=0, total_terminations=0,
                      experienced_terminations=0, new_hire_terminations=0, total_hires=0,
                      growth_rate=0.0, validation_passed=False),
            YearResult(year=2027, success=True, active_employees=1093, total_terminations=130,
                      experienced_terminations=110, new_hire_terminations=20, total_hires=162,
                      growth_rate=0.03, validation_passed=True),
        ]

        # Execute
        _log_simulation_summary(mock_context, results)

        # Verify summary logging
        mock_context.log.info.assert_any_call("📊 === Multi-year simulation summary ===")
        mock_context.log.info.assert_any_call("🎯 Simulation completed: 2/3 years successful")
        mock_context.log.info.assert_any_call("  ✅ Year 2025: 1,030 employees, 3.0% growth")
        mock_context.log.error.assert_any_call("  ❌ Year 2026: FAILED")
        mock_context.log.info.assert_any_call("  ✅ Year 2027: 1,093 employees, 3.0% growth")

        # Verify failure warning
        mock_context.log.warning.assert_called_once_with("⚠️  1 year(s) failed - check logs for details")

    def test_all_failed_years(self, mock_context):
        """Test summary logging for all failed years."""
        results = [
            YearResult(year=2025, success=False, active_employees=0, total_terminations=0,
                      experienced_terminations=0, new_hire_terminations=0, total_hires=0,
                      growth_rate=0.0, validation_passed=False),
            YearResult(year=2026, success=False, active_employees=0, total_terminations=0,
                      experienced_terminations=0, new_hire_terminations=0, total_hires=0,
                      growth_rate=0.0, validation_passed=False),
        ]

        # Execute
        _log_simulation_summary(mock_context, results)

        # Verify summary logging
        mock_context.log.info.assert_any_call("📊 === Multi-year simulation summary ===")
        mock_context.log.info.assert_any_call("🎯 Simulation completed: 0/2 years successful")
        mock_context.log.error.assert_any_call("  ❌ Year 2025: FAILED")
        mock_context.log.error.assert_any_call("  ❌ Year 2026: FAILED")

        # Verify failure warning
        mock_context.log.warning.assert_called_once_with("⚠️  2 year(s) failed - check logs for details")

    def test_empty_results(self, mock_context):
        """Test summary logging for empty results."""
        results = []

        # Execute
        _log_simulation_summary(mock_context, results)

        # Verify summary logging
        mock_context.log.info.assert_any_call("📊 === Multi-year simulation summary ===")
        mock_context.log.info.assert_any_call("🎯 Simulation completed: 0/0 years successful")

        # Verify no warnings
        mock_context.log.warning.assert_not_called()


class TestMultiYearSimulationIntegration:
    """Integration tests for the transformed multi-year simulation."""

    @pytest.fixture
    def integration_context(self):
        """Create a realistic context for integration testing."""
        dbt_resource = Mock()

        context = build_op_context(
            op_config={
                "start_year": 2025,
                "end_year": 2026,
                "target_growth_rate": 0.03,
                "total_termination_rate": 0.12,
                "new_hire_termination_rate": 0.25,
                "random_seed": 42,
                "full_refresh": False,
            },
            resources={"dbt": dbt_resource}
        )

        return context

    @patch('orchestrator.simulator_pipeline.clean_duckdb_data')
    @patch('orchestrator.simulator_pipeline.run_dbt_snapshot_for_year')
    @patch('orchestrator.simulator_pipeline.assert_year_complete')
    @patch('orchestrator.simulator_pipeline.run_year_simulation_for_multi_year')
    def test_complete_orchestration_workflow(
        self,
        mock_simulation,
        mock_assert_year,
        mock_snapshot,
        mock_clean_data,
        integration_context
    ):
        """Test complete orchestration workflow with realistic integration."""
        # Setup successful simulation results
        mock_simulation.side_effect = [
            YearResult(year=2025, success=True, active_employees=1030, total_terminations=120,
                      experienced_terminations=100, new_hire_terminations=20, total_hires=150,
                      growth_rate=0.03, validation_passed=True),
            YearResult(year=2026, success=True, active_employees=1061, total_terminations=125,
                      experienced_terminations=105, new_hire_terminations=20, total_hires=156,
                      growth_rate=0.03, validation_passed=True)
        ]

        # Execute complete workflow
        results = run_multi_year_simulation(integration_context, True)

        # Verify complete orchestration sequence
        mock_clean_data.assert_called_once_with(integration_context, [2025, 2026])

        # Verify year-by-year execution
        assert mock_simulation.call_count == 2
        mock_simulation.assert_any_call(integration_context, 2025)
        mock_simulation.assert_any_call(integration_context, 2026)

        # Verify previous year validation for second year
        mock_assert_year.assert_called_once_with(integration_context, 2025)

        # Verify snapshots were created
        assert mock_snapshot.call_count == 3  # previous_year 2025, end_of_year 2025, end_of_year 2026

        # Verify results
        assert len(results) == 2
        assert all(r.success for r in results)
        assert [r.year for r in results] == [2025, 2026]
        assert [r.active_employees for r in results] == [1030, 1061]
