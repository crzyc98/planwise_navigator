"""
Integration tests for S013-07: Simulation Behavior Comparison

Comprehensive integration tests to validate that the refactored pipeline
produces identical results to the original implementation.
"""

import pytest
from unittest.mock import Mock, patch
from dagster import OpExecutionContext

from orchestrator.simulator_pipeline import (
    run_year_simulation,
    run_multi_year_simulation,
    YearResult,
    clean_duckdb_data,
    run_dbt_event_models_for_year,
    run_dbt_snapshot_for_year,
)


class TestSimulationBehaviorComparison:
    """Test suite for validating behavior preservation in refactored pipeline."""

    @pytest.fixture
    def standard_config(self):
        """Standard simulation configuration for testing."""
        return {
            "start_year": 2023,
            "end_year": 2025,
            "target_growth_rate": 0.03,
            "total_termination_rate": 0.12,
            "new_hire_termination_rate": 0.25,
            "random_seed": 42,
            "full_refresh": False,
        }

    @pytest.fixture
    def mock_context_with_config(self, standard_config):
        """Create a mock context with standard configuration."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        context.op_config = standard_config.copy()

        # Mock dbt resource
        dbt_resource = Mock()
        context.resources = Mock()
        context.resources.dbt = dbt_resource
        context.op_def = Mock()

        return context

    @pytest.fixture
    def realistic_year_result(self):
        """Create realistic YearResult for testing."""
        return YearResult(
            year=2025,
            success=True,
            active_employees=1150,
            total_terminations=140,
            experienced_terminations=120,
            new_hire_terminations=20,
            total_hires=150,
            growth_rate=0.025,
            validation_passed=True,
        )

    @patch("orchestrator.simulator_pipeline.validate_year_results")
    @patch("orchestrator.simulator_pipeline.run_dbt_event_models_for_year")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.clean_duckdb_data")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_single_year_behavior_consistency(
        self,
        mock_duckdb_connect,
        mock_clean_data,
        mock_execute_dbt,
        mock_event_models,
        mock_validate,
        mock_context_with_config,
        realistic_year_result,
    ):
        """Test that single-year simulation produces consistent behavior."""
        # Setup mocks for consistent behavior
        mock_clean_data.return_value = {
            "fct_yearly_events": 1,
            "fct_workforce_snapshot": 1,
        }

        mock_event_models.return_value = {
            "year": 2025,
            "models_executed": [
                "int_termination_events",
                "int_promotion_events",
                "int_merit_events",
                "int_hiring_events",
                "int_new_hire_termination_events",
            ],
            "hiring_debug": {"hire_count": 150, "year": 2025},
        }

        mock_validate.return_value = realistic_year_result

        # Mock database connection
        mock_conn = Mock()
        mock_conn.fetchone.return_value = [100]
        mock_conn.close = Mock()
        mock_duckdb_connect.return_value = mock_conn

        # Update context for single year
        mock_context_with_config.op_config["start_year"] = 2025
        mock_context_with_config.op_config["end_year"] = 2025

        # Execute simulation
        result = run_year_simulation(mock_context_with_config)

        # Verify result structure and values
        assert result == realistic_year_result
        assert result.year == 2025
        assert result.success is True
        assert result.active_employees == 1150
        assert result.total_hires == 150
        assert result.growth_rate == 0.025

        # Verify modular components were called in correct sequence
        mock_clean_data.assert_called_once_with(mock_context_with_config, [2025])
        mock_event_models.assert_called_once_with(
            mock_context_with_config, 2025, mock_context_with_config.op_config
        )
        mock_validate.assert_called_once_with(
            mock_context_with_config, 2025, mock_context_with_config.op_config
        )

        # Verify dbt commands executed in Epic 11.5 sequence
        expected_dbt_commands = [
            ["run", "--select", "int_workforce_previous_year"],
            ["run", "--select", "fct_yearly_events"],
            ["run", "--select", "fct_workforce_snapshot"],
        ]

        assert mock_execute_dbt.call_count == len(expected_dbt_commands)
        for i, expected_command in enumerate(expected_dbt_commands):
            call_args = mock_execute_dbt.call_args_list[i]
            assert call_args[0][1] == expected_command

    @patch("orchestrator.simulator_pipeline.run_year_simulation")
    @patch("orchestrator.simulator_pipeline.run_dbt_snapshot_for_year")
    @patch("orchestrator.simulator_pipeline.clean_duckdb_data")
    @patch("orchestrator.simulator_pipeline.assert_year_complete")
    @patch("dagster.build_op_context")
    def test_multi_year_orchestration_behavior(
        self,
        mock_build_context,
        mock_assert_complete,
        mock_clean_data,
        mock_snapshot,
        mock_single_year,
        mock_context_with_config,
    ):
        """Test multi-year simulation orchestration behavior."""
        # Setup mock responses
        mock_clean_data.return_value = {
            "fct_yearly_events": 3,
            "fct_workforce_snapshot": 3,
        }

        mock_snapshot.return_value = {"success": True, "records_created": 100}

        # Mock single-year simulation results for each year
        year_results = [
            YearResult(2023, True, 1000, 120, 100, 20, 130, 0.02, True),
            YearResult(2024, True, 1100, 130, 110, 20, 140, 0.025, True),
            YearResult(2025, True, 1200, 140, 120, 20, 150, 0.03, True),
        ]
        mock_single_year.side_effect = year_results

        # Mock build_op_context to return contexts for each year
        mock_year_contexts = []
        for year in [2023, 2024, 2025]:
            year_context = Mock()
            year_context.log = mock_context_with_config.log
            mock_year_contexts.append(year_context)
        mock_build_context.side_effect = mock_year_contexts

        # Execute multi-year simulation
        results = run_multi_year_simulation(mock_context_with_config, True)

        # Verify orchestration behavior
        assert len(results) == 3
        assert all(r.success for r in results)
        assert [r.year for r in results] == [2023, 2024, 2025]
        assert [r.active_employees for r in results] == [1000, 1100, 1200]

        # Verify data cleaning called once for all years
        mock_clean_data.assert_called_once_with(
            mock_context_with_config, [2023, 2024, 2025]
        )

        # Verify single-year simulation called for each year
        assert mock_single_year.call_count == 3

        # Verify snapshots created for each year
        expected_snapshot_calls = [
            # Previous year snapshots (for years 2024, 2025)
            (mock_context_with_config, 2023, "previous_year"),
            (mock_context_with_config, 2024, "previous_year"),
            # End-of-year snapshots (for all years)
            (mock_context_with_config, 2023, "end_of_year"),
            (mock_context_with_config, 2024, "end_of_year"),
            (mock_context_with_config, 2025, "end_of_year"),
        ]

        assert mock_snapshot.call_count == 5
        for i, expected_call in enumerate(expected_snapshot_calls):
            actual_call = mock_snapshot.call_args_list[i]
            assert actual_call[0] == expected_call

    @patch("orchestrator.simulator_pipeline.validate_year_results")
    @patch("orchestrator.simulator_pipeline.run_dbt_event_models_for_year")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.clean_duckdb_data")
    def test_configuration_parameter_propagation(
        self,
        mock_clean_data,
        mock_execute_dbt,
        mock_event_models,
        mock_validate,
        mock_context_with_config,
        realistic_year_result,
    ):
        """Test that configuration parameters are correctly propagated through pipeline."""
        # Setup specific configuration values to trace
        test_config = {
            "start_year": 2025,
            "end_year": 2025,
            "target_growth_rate": 0.045,
            "total_termination_rate": 0.15,
            "new_hire_termination_rate": 0.30,
            "random_seed": 123,
            "full_refresh": True,
        }
        mock_context_with_config.op_config = test_config

        # Setup mocks
        mock_event_models.return_value = {
            "year": 2025,
            "models_executed": [],
            "hiring_debug": {"hire_count": 100},
        }
        mock_validate.return_value = realistic_year_result

        # Execute and verify the function runs
        run_year_simulation(mock_context_with_config)

        # Verify configuration propagated to event models
        mock_event_models.assert_called_once_with(
            mock_context_with_config, 2025, test_config
        )

        # Verify configuration propagated to validation
        mock_validate.assert_called_once_with(
            mock_context_with_config, 2025, test_config
        )

        # Verify full_refresh parameter propagated to dbt commands
        for call_args in mock_execute_dbt.call_args_list:
            full_refresh_param = call_args[0][3]
            assert full_refresh_param is True

            # Verify simulation_year in vars_dict
            vars_dict = call_args[0][2]
            assert vars_dict["simulation_year"] == 2025

    @patch("orchestrator.simulator_pipeline.validate_year_results")
    @patch("orchestrator.simulator_pipeline.run_dbt_event_models_for_year")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.clean_duckdb_data")
    def test_error_handling_behavior_consistency(
        self,
        mock_clean_data,
        mock_execute_dbt,
        mock_event_models,
        mock_validate,
        mock_context_with_config,
    ):
        """Test that error handling behavior is consistent with original implementation."""
        # Setup failure scenario
        mock_clean_data.return_value = {
            "fct_yearly_events": 1,
            "fct_workforce_snapshot": 1,
        }
        mock_event_models.return_value = {
            "year": 2025,
            "models_executed": [],
            "hiring_debug": {},
        }

        # Mock dbt command failure
        mock_execute_dbt.side_effect = [None, Exception("dbt command failed"), None]

        # Verify exception is raised (not caught and converted to failure result)
        with pytest.raises(Exception) as exc_info:
            run_year_simulation(mock_context_with_config)

        assert "dbt command failed" in str(exc_info.value)

        # Verify cleanup and event models were called before failure
        mock_clean_data.assert_called_once()
        mock_event_models.assert_called_once()

    @patch("orchestrator.simulator_pipeline.run_year_simulation")
    @patch("orchestrator.simulator_pipeline.run_dbt_snapshot_for_year")
    @patch("orchestrator.simulator_pipeline.clean_duckdb_data")
    @patch("orchestrator.simulator_pipeline.assert_year_complete")
    @patch("dagster.build_op_context")
    def test_multi_year_failure_continuation_behavior(
        self,
        mock_build_context,
        mock_assert_complete,
        mock_clean_data,
        mock_snapshot,
        mock_single_year,
        mock_context_with_config,
    ):
        """Test multi-year simulation failure continuation behavior."""
        # Setup mixed success/failure scenario
        mock_clean_data.return_value = {
            "fct_yearly_events": 3,
            "fct_workforce_snapshot": 3,
        }
        mock_snapshot.return_value = {"success": True, "records_created": 100}

        # Mock year-by-year results: success, failure, success
        year_results = [
            YearResult(2023, True, 1000, 120, 100, 20, 130, 0.02, True),
            Exception("Year 2024 simulation failed"),
            YearResult(2025, True, 1200, 140, 120, 20, 150, 0.03, True),
        ]
        mock_single_year.side_effect = year_results

        # Mock build_op_context
        mock_year_contexts = [Mock() for _ in range(3)]
        for ctx in mock_year_contexts:
            ctx.log = mock_context_with_config.log
        mock_build_context.side_effect = mock_year_contexts

        # Execute multi-year simulation
        results = run_multi_year_simulation(mock_context_with_config, True)

        # Verify continuation behavior
        assert len(results) == 3
        assert results[0].success is True  # Year 2023 succeeded
        assert results[1].success is False  # Year 2024 failed
        assert results[2].success is True  # Year 2025 succeeded

        # Verify failure result structure
        failed_result = results[1]
        assert failed_result.year == 2024
        assert failed_result.active_employees == 0
        assert failed_result.validation_passed is False

    def test_year_result_structure_consistency(self, realistic_year_result):
        """Test that YearResult structure remains consistent."""
        # Verify all required fields are present
        required_fields = [
            "year",
            "success",
            "active_employees",
            "total_terminations",
            "experienced_terminations",
            "new_hire_terminations",
            "total_hires",
            "growth_rate",
            "validation_passed",
        ]

        for field in required_fields:
            assert hasattr(realistic_year_result, field)
            assert getattr(realistic_year_result, field) is not None

        # Verify field types
        assert isinstance(realistic_year_result.year, int)
        assert isinstance(realistic_year_result.success, bool)
        assert isinstance(realistic_year_result.active_employees, int)
        assert isinstance(realistic_year_result.growth_rate, float)
        assert isinstance(realistic_year_result.validation_passed, bool)

    @pytest.mark.parametrize("random_seed", [42, 123, 999])
    @patch("orchestrator.simulator_pipeline.validate_year_results")
    @patch("orchestrator.simulator_pipeline.run_dbt_event_models_for_year")
    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.clean_duckdb_data")
    def test_random_seed_consistency(
        self,
        mock_clean_data,
        mock_execute_dbt,
        mock_event_models,
        mock_validate,
        mock_context_with_config,
        realistic_year_result,
        random_seed,
    ):
        """Test that random seed produces consistent results."""
        # Update configuration with test random seed
        mock_context_with_config.op_config["random_seed"] = random_seed

        # Setup mocks
        mock_event_models.return_value = {
            "year": 2025,
            "models_executed": [],
            "hiring_debug": {"hire_count": 100},
        }
        mock_validate.return_value = realistic_year_result

        # Execute multiple times with same seed
        results = []
        for _ in range(3):
            result = run_year_simulation(mock_context_with_config)
            results.append(result)

        # Verify all results are identical
        for result in results:
            assert result == realistic_year_result

        # Verify random seed was passed to event models
        for call_args in mock_event_models.call_args_list:
            config_param = call_args[0][2]
            assert config_param["random_seed"] == random_seed


class TestPipelineIntegrationPoints:
    """Test integration points between pipeline components."""

    @pytest.fixture
    def integration_context(self):
        """Create context for integration testing."""
        context = Mock(spec=OpExecutionContext)
        context.log = Mock()
        context.op_config = {
            "start_year": 2025,
            "target_growth_rate": 0.03,
            "random_seed": 42,
            "full_refresh": False,
        }
        context.resources = Mock()
        context.resources.dbt = Mock()
        return context

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_data_cleaning_integration(
        self, mock_duckdb_connect, mock_execute_dbt, integration_context
    ):
        """Test data cleaning integration with pipeline."""
        years = [2023, 2024, 2025]

        # Mock database connection
        mock_conn = Mock()
        mock_conn.execute = Mock()
        mock_conn.close = Mock()
        mock_duckdb_connect.return_value = mock_conn

        # Execute data cleaning
        result = clean_duckdb_data(integration_context, years)

        # Verify cleaning results
        assert result["fct_yearly_events"] == 3
        assert result["fct_workforce_snapshot"] == 3

        # Verify database operations for each year
        expected_delete_calls = []
        for year in years:
            expected_delete_calls.extend(
                [
                    ("DELETE FROM fct_yearly_events WHERE simulation_year = ?", [year]),
                    (
                        "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?",
                        [year],
                    ),
                ]
            )

        assert mock_conn.execute.call_count == len(expected_delete_calls)
        for i, (expected_sql, expected_params) in enumerate(expected_delete_calls):
            actual_call = mock_conn.execute.call_args_list[i]
            assert actual_call[0] == (expected_sql, expected_params)

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_event_models_integration(
        self, mock_duckdb_connect, mock_execute_dbt, integration_context
    ):
        """Test event models operation integration."""
        year = 2025
        config = integration_context.op_config

        # Mock database connection for debug logging
        mock_conn = Mock()
        mock_conn.fetchone.return_value = [150]
        mock_conn.close = Mock()
        mock_duckdb_connect.return_value = mock_conn

        # Execute event models operation
        result = run_dbt_event_models_for_year(integration_context, year, config)

        # Verify result structure
        assert result["year"] == year
        assert len(result["models_executed"]) == 5
        assert result["hiring_debug"]["hire_count"] == 150

        # Verify Epic 11.5 sequence was executed
        expected_models = [
            "int_termination_events",
            "int_promotion_events",
            "int_merit_events",
            "int_hiring_events",
            "int_new_hire_termination_events",
        ]
        assert result["models_executed"] == expected_models

        # Verify each model was executed via dbt
        assert mock_execute_dbt.call_count == 5
        for i, expected_model in enumerate(expected_models):
            call_args = mock_execute_dbt.call_args_list[i]
            assert call_args[0][1] == ["run", "--select", expected_model]

    @patch("orchestrator.simulator_pipeline.execute_dbt_command")
    @patch("orchestrator.simulator_pipeline.duckdb.connect")
    def test_snapshot_operation_integration(
        self, mock_duckdb_connect, mock_execute_dbt, integration_context
    ):
        """Test snapshot operation integration with various types."""
        year = 2025

        # Mock database connection
        mock_conn = Mock()
        mock_conn.close = Mock()
        mock_duckdb_connect.return_value = mock_conn

        # Test different snapshot types
        snapshot_tests = [
            ("end_of_year", [0, 100]),
            ("previous_year", [150]),
            ("recovery", [50, 200]),
        ]

        for snapshot_type, fetchone_returns in snapshot_tests:
            mock_conn.fetchone.side_effect = fetchone_returns

            result = run_dbt_snapshot_for_year(integration_context, year, snapshot_type)

            assert result["success"] is True
            assert result["snapshot_type"] == snapshot_type
            assert result["year"] == year

            # Verify dbt snapshot command was executed
            mock_execute_dbt.assert_called_with(
                integration_context,
                ["snapshot", "--select", "scd_workforce_state"],
                {"simulation_year": year},
                False,
                f"workforce state snapshot for year {year} ({snapshot_type})"
                if snapshot_type != "previous_year"
                else f"workforce state snapshot for year {year} (previous year dependency)",
            )
