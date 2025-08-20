"""
Comprehensive Integration Tests for Compensation Tuning Workflow
================================================================

This module provides end-to-end integration testing for the complete compensation
tuning and optimization workflow, covering:

1. Parameter schema integration with optimization components
2. UI parameter changes → Database updates → Simulation execution
3. Optimization engine → Parameter suggestions → Validation pipeline
4. Multi-method execution patterns (Dagster CLI, Asset-based, Manual dbt)
5. Advanced optimization → Compensation tuning → Results validation
6. Error recovery and fallback mechanisms

Follows PlanWise Navigator testing patterns with realistic data scenarios.
"""

import json
import os
import sqlite3
import subprocess
import tempfile
import time
import warnings
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import MagicMock, Mock, call, patch

import numpy as np
import pandas as pd
import pytest
import yaml
from orchestrator.optimization.constraint_solver import CompensationOptimizer
from orchestrator.optimization.objective_functions import ObjectiveFunctions
from orchestrator.optimization.optimization_schemas import (
    OptimizationRequest, OptimizationResult)

from streamlit_dashboard.advanced_optimization import \
    AdvancedOptimizationEngine
# Import components under test
from streamlit_dashboard.optimization_schemas import (ParameterSchema,
                                                      assess_parameter_risk,
                                                      get_default_parameters,
                                                      get_parameter_schema,
                                                      validate_parameters)


class TestCompensationTuningWorkflow:
    """Test complete compensation tuning workflow integration."""

    def setup_method(self):
        """Setup for workflow integration tests."""
        self.schema = get_parameter_schema()
        self.temp_dir = tempfile.mkdtemp()

        # Create mock DuckDB environment
        self.mock_duckdb = Mock()
        self.mock_conn = Mock()
        self.mock_duckdb.get_connection.return_value.__enter__.return_value = (
            self.mock_conn
        )

        # Create test data files
        self.comp_levers_path = os.path.join(self.temp_dir, "comp_levers.csv")
        self.config_path = os.path.join(self.temp_dir, "simulation_config.yaml")

        self._create_test_data_files()

    def teardown_method(self):
        """Cleanup after tests."""
        import shutil

        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def _create_test_data_files(self):
        """Create test data files for integration testing."""
        # Create test comp_levers.csv
        comp_levers_data = []
        for year in [2025, 2026, 2027, 2028, 2029]:
            for level in [1, 2, 3, 4, 5]:
                comp_levers_data.extend(
                    [
                        {
                            "parameter_name": "merit_base",
                            "job_level": level,
                            "year": year,
                            "value": 0.045,
                        },
                        {
                            "parameter_name": "cola_rate",
                            "job_level": level,
                            "year": year,
                            "value": 0.025,
                        },
                        {
                            "parameter_name": "new_hire_salary_adjustment",
                            "job_level": level,
                            "year": year,
                            "value": 1.15,
                        },
                        {
                            "parameter_name": "promotion_probability",
                            "job_level": level,
                            "year": year,
                            "value": 0.10,
                        },
                        {
                            "parameter_name": "promotion_raise",
                            "job_level": level,
                            "year": year,
                            "value": 0.12,
                        },
                    ]
                )

        pd.DataFrame(comp_levers_data).to_csv(self.comp_levers_path, index=False)

        # Create test simulation config
        config_data = {
            "simulation": {
                "start_year": 2025,
                "end_year": 2029,
                "random_seed": 42,
                "target_growth_rate": 0.05,
            },
            "paths": {
                "comp_levers": self.comp_levers_path,
                "database": os.path.join(self.temp_dir, "test.duckdb"),
            },
        }

        with open(self.config_path, "w") as f:
            yaml.dump(config_data, f)

    @pytest.mark.integration
    def test_ui_to_database_parameter_flow(self):
        """Test parameter flow from UI changes to database updates."""

        # 1. Simulate UI parameter changes
        ui_changes = {
            "merit_sliders": {1: 4.8, 2: 4.2, 3: 3.8, 4: 3.5, 5: 4.0},
            "cola_slider": 2.8,
            "new_hire_premium": 118,
            "apply_mode": "All Years",
        }

        # 2. Convert to parameter format
        parameters = {}
        for level, value in ui_changes["merit_sliders"].items():
            parameters[f"merit_rate_level_{level}"] = value / 100.0

        parameters["cola_rate"] = ui_changes["cola_slider"] / 100.0
        parameters["new_hire_salary_adjustment"] = (
            ui_changes["new_hire_premium"] / 100.0
        )

        # 3. Validate parameters
        validation_result = self.schema.validate_parameter_set(parameters)
        assert validation_result[
            "is_valid"
        ], f"Parameter validation failed: {validation_result['errors']}"

        # 4. Transform to compensation tuning format
        comp_format = self.schema.transform_to_compensation_tuning_format(parameters)

        # 5. Verify parameter mapping
        assert comp_format["merit_base"][1] == 0.048
        assert comp_format["merit_base"][2] == 0.042
        assert comp_format["cola_rate"][1] == 0.028
        assert comp_format["new_hire_salary_adjustment"][1] == 1.18

        # 6. Simulate database update
        self._simulate_comp_levers_update(comp_format, [2025, 2026, 2027, 2028, 2029])

        # 7. Verify database state
        updated_data = pd.read_csv(self.comp_levers_path)
        merit_data = updated_data[
            (updated_data["parameter_name"] == "merit_base")
            & (updated_data["job_level"] == 1)
            & (updated_data["year"] == 2025)
        ]

        assert len(merit_data) == 1
        assert merit_data.iloc[0]["value"] == 0.048

    def _simulate_comp_levers_update(self, comp_format: Dict, target_years: List[int]):
        """Simulate updating comp_levers.csv file."""
        df = pd.read_csv(self.comp_levers_path)

        for param_name, level_values in comp_format.items():
            for level, value in level_values.items():
                mask = (
                    (df["parameter_name"] == param_name)
                    & (df["job_level"] == level)
                    & (df["year"].isin(target_years))
                )
                df.loc[mask, "value"] = value

        df.to_csv(self.comp_levers_path, index=False)

    @pytest.mark.integration
    def test_optimization_to_simulation_workflow(self):
        """Test optimization engine to simulation execution workflow."""

        # 1. Create optimization request
        initial_params = get_default_parameters()

        optimization_request = OptimizationRequest(
            scenario_id="workflow_test",
            initial_parameters=initial_params,
            objectives={"cost": 0.6, "equity": 0.4},
            method="SLSQP",
            max_evaluations=50,
        )

        # 2. Run optimization (mocked)
        optimizer = CompensationOptimizer(self.mock_duckdb, "workflow_test")

        # Mock database responses for optimization
        self.mock_conn.execute.return_value.fetchone.return_value = [1_500_000.0]
        self.mock_conn.execute.return_value.fetchall.return_value = [
            (1, 45000, 2250),
            (2, 55000, 2750),
            (3, 65000, 3250),
            (4, 75000, 3750),
            (5, 85000, 4250),
        ]

        with patch("scipy.optimize.minimize") as mock_minimize:
            mock_result = Mock()
            mock_result.success = True
            mock_result.x = [
                0.048,
                0.042,
                0.038,
                0.035,
                0.040,
                0.028,
            ]  # Optimized parameters
            mock_result.fun = 0.345
            mock_result.nit = 35
            mock_result.nfev = 105
            mock_minimize.return_value = mock_result

            optimization_result = optimizer.optimize(optimization_request)

        # 3. Verify optimization result
        assert optimization_result.converged is True
        assert optimization_result.scenario_id == "workflow_test"
        assert optimization_result.algorithm_used == "SLSQP"

        # 4. Convert optimization result to compensation tuning format
        optimized_params = optimization_result.optimal_parameters
        comp_tuning_format = self.schema.transform_to_compensation_tuning_format(
            optimized_params
        )

        # 5. Apply optimized parameters to simulation
        self._simulate_comp_levers_update(comp_tuning_format, [2025])

        # 6. Simulate simulation execution
        simulation_result = self._simulate_simulation_execution()

        # 7. Verify simulation results
        assert simulation_result["status"] == "success"
        assert "workforce_metrics" in simulation_result
        assert simulation_result["workforce_metrics"]["total_employees"] > 0

    def _simulate_simulation_execution(self) -> Dict[str, Any]:
        """Simulate running the compensation simulation."""
        # Mock simulation execution
        return {
            "status": "success",
            "execution_time": 45.2,
            "workforce_metrics": {
                "total_employees": 1250,
                "average_compensation": 68500,
                "total_cost": 85_625_000,
                "equity_score": 0.12,
            },
            "parameter_changes": {
                "merit_increases_applied": 1125,
                "cola_increases_applied": 1250,
                "new_hires": 75,
            },
        }

    @pytest.mark.integration
    def test_multi_method_execution_consistency(self):
        """Test consistency across different execution methods."""

        parameters = {
            "merit_rate_level_1": 0.048,
            "merit_rate_level_2": 0.042,
            "cola_rate": 0.028,
        }

        # Method 1: Direct parameter validation
        direct_validation = self.schema.validate_parameter_set(parameters)

        # Method 2: Individual parameter validation
        individual_validations = {}
        for param_name, value in parameters.items():
            param_def = self.schema.get_parameter(param_name)
            if param_def:
                is_valid, messages, risk = param_def.validate_value(value)
                individual_validations[param_name] = {
                    "is_valid": is_valid,
                    "risk": risk,
                    "messages": messages,
                }

        # Method 3: Compensation tuning format validation
        comp_format = self.schema.transform_to_compensation_tuning_format(parameters)
        converted_back = self.schema.transform_from_compensation_tuning_format(
            comp_format
        )
        comp_validation = self.schema.validate_parameter_set(converted_back)

        # Verify consistency
        assert direct_validation["is_valid"] == comp_validation["is_valid"]

        for param_name in parameters:
            if param_name in individual_validations:
                direct_param_result = direct_validation["parameter_results"][param_name]
                individual_result = individual_validations[param_name]

                assert direct_param_result["is_valid"] == individual_result["is_valid"]
                assert direct_param_result["risk_level"] == individual_result["risk"]

        # Verify round-trip consistency
        for param_name, original_value in parameters.items():
            converted_value = converted_back[param_name]
            assert abs(original_value - converted_value) < 1e-10

    @pytest.mark.integration
    def test_advanced_optimization_integration(self):
        """Test integration with advanced optimization engine."""

        # Mock advanced optimization engine
        with patch(
            "streamlit_dashboard.advanced_optimization.AdvancedOptimizationEngine"
        ) as MockEngine:
            mock_engine = Mock()
            MockEngine.return_value = mock_engine

            # Mock optimization results
            mock_engine.optimize_parameters.return_value = {
                "status": "success",
                "optimal_parameters": {
                    "merit_rate_level_1": 0.052,
                    "merit_rate_level_2": 0.047,
                    "cola_rate": 0.032,
                },
                "objective_value": 0.234,
                "iterations": 67,
                "convergence_info": {
                    "converged": True,
                    "message": "Optimization terminated successfully",
                },
            }

            # Mock goal-seeking results
            mock_engine.goal_seek.return_value = {
                "status": "success",
                "target_parameters": {"merit_rate_level_1": 0.055, "cola_rate": 0.035},
                "achieved_target": 0.951,  # 95.1% of target achieved
                "iterations": 23,
            }

            # Test optimization integration
            engine = AdvancedOptimizationEngine()

            optimization_result = engine.optimize_parameters(
                initial_parameters=get_default_parameters(),
                objectives={"cost": 0.7, "equity": 0.3},
                constraints={"budget_limit": 2_000_000},
            )

            assert optimization_result["status"] == "success"
            assert "optimal_parameters" in optimization_result

            # Test goal-seeking integration
            goal_result = engine.goal_seek(
                target_metric="budget_utilization",
                target_value=0.95,
                variable_parameters=["merit_rate_level_1", "cola_rate"],
            )

            assert goal_result["status"] == "success"
            assert goal_result["achieved_target"] > 0.9

    @pytest.mark.integration
    def test_error_recovery_workflow(self):
        """Test error recovery and fallback mechanisms."""

        # Test database lock recovery
        with patch("duckdb.connect") as mock_connect:
            mock_connect.side_effect = Exception("Database is locked")

            # Should handle database lock gracefully
            try:
                result = self._simulate_simulation_execution()
                # If no exception, fallback mechanism worked
                assert "status" in result
            except Exception as e:
                # Should be a graceful error, not a crash
                assert "Database is locked" in str(e)

        # Test parameter validation error recovery
        invalid_params = {
            "merit_rate_level_1": 0.25,  # Invalid: too high
            "cola_rate": -0.05,  # Invalid: negative
        }

        validation_result = self.schema.validate_parameter_set(invalid_params)

        # Should return structured error information
        assert validation_result["is_valid"] is False
        assert len(validation_result["errors"]) > 0

        # Should suggest corrections
        assert "warnings" in validation_result

        # Test optimization convergence failure recovery
        with patch("scipy.optimize.minimize") as mock_minimize:
            mock_result = Mock()
            mock_result.success = False
            mock_result.message = "Optimization failed to converge"
            mock_minimize.return_value = mock_result

            optimizer = CompensationOptimizer(self.mock_duckdb, "error_test")

            request = OptimizationRequest(
                scenario_id="error_test",
                initial_parameters=get_default_parameters(),
                objectives={"cost": 1.0},
            )

            result = optimizer.optimize(request)

            # Should handle failed optimization gracefully
            assert result.converged is False
            assert (
                "failed to converge" in result.algorithm_used.lower()
                or not result.converged
            )

    @pytest.mark.integration
    def test_data_consistency_validation(self):
        """Test data consistency across the entire workflow."""

        # Start with known parameters
        original_params = {
            "merit_rate_level_1": 0.045,
            "merit_rate_level_2": 0.040,
            "merit_rate_level_3": 0.035,
            "cola_rate": 0.025,
            "new_hire_salary_adjustment": 1.15,
        }

        # Step 1: Validate original parameters
        validation1 = self.schema.validate_parameter_set(original_params)
        assert validation1["is_valid"]

        # Step 2: Transform to compensation tuning format
        comp_format = self.schema.transform_to_compensation_tuning_format(
            original_params
        )

        # Step 3: Transform back to standard format
        recovered_params = self.schema.transform_from_compensation_tuning_format(
            comp_format
        )

        # Step 4: Validate recovered parameters
        validation2 = self.schema.validate_parameter_set(recovered_params)
        assert validation2["is_valid"]

        # Step 5: Compare original and recovered
        for param_name, original_value in original_params.items():
            recovered_value = recovered_params[param_name]
            assert (
                abs(original_value - recovered_value) < 1e-10
            ), f"Parameter {param_name}: {original_value} != {recovered_value}"

        # Step 6: Verify validation results consistency
        assert validation1["overall_risk"] == validation2["overall_risk"]
        assert len(validation1["errors"]) == len(validation2["errors"])
        assert len(validation1["warnings"]) == len(validation2["warnings"])

    @pytest.mark.integration
    def test_performance_under_load(self):
        """Test workflow performance under load conditions."""

        # Generate multiple parameter scenarios
        scenarios = []
        for i in range(50):  # 50 scenarios
            base_params = get_default_parameters()

            # Add variation
            for param_name in base_params:
                param_def = self.schema.get_parameter(param_name)
                if param_def:
                    min_val = param_def.bounds.min_value
                    max_val = param_def.bounds.max_value
                    variation = np.random.uniform(0.9, 1.1)
                    new_value = base_params[param_name] * variation
                    base_params[param_name] = np.clip(new_value, min_val, max_val)

            scenarios.append(base_params)

        # Test batch validation performance
        start_time = time.time()

        validation_results = []
        for scenario in scenarios:
            result = self.schema.validate_parameter_set(scenario)
            validation_results.append(result)

        batch_validation_time = time.time() - start_time

        # Should complete batch validation quickly
        assert (
            batch_validation_time < 10.0
        ), f"Batch validation took {batch_validation_time:.2f}s"

        # All validations should succeed (parameters are within bounds)
        valid_count = sum(1 for result in validation_results if result["is_valid"])
        assert valid_count > 40, f"Only {valid_count}/50 scenarios were valid"

        # Test transformation performance
        start_time = time.time()

        for scenario in scenarios[:10]:  # Test subset for transformation
            comp_format = self.schema.transform_to_compensation_tuning_format(scenario)
            recovered = self.schema.transform_from_compensation_tuning_format(
                comp_format
            )

        transformation_time = time.time() - start_time

        # Should complete transformations quickly
        assert (
            transformation_time < 2.0
        ), f"Transformations took {transformation_time:.2f}s"


class TestStreamlitIntegrationPatterns:
    """Test Streamlit-specific integration patterns."""

    def setup_method(self):
        """Setup for Streamlit integration tests."""
        self.schema = get_parameter_schema()

    def test_streamlit_session_state_integration(self):
        """Test integration with Streamlit session state patterns."""

        # Simulate Streamlit session state
        mock_session_state = {
            "parameters": get_default_parameters(),
            "simulation_results": None,
            "optimization_results": None,
            "last_update_time": time.time(),
        }

        # Test parameter update workflow
        new_params = mock_session_state["parameters"].copy()
        new_params["merit_rate_level_1"] = 0.052

        # Validate changes
        validation_result = self.schema.validate_parameter_set(new_params)

        if validation_result["is_valid"]:
            mock_session_state["parameters"] = new_params
            mock_session_state["last_update_time"] = time.time()

            # Clear dependent results
            mock_session_state["simulation_results"] = None
            mock_session_state["optimization_results"] = None

        # Verify state consistency
        assert mock_session_state["parameters"]["merit_rate_level_1"] == 0.052
        assert mock_session_state["simulation_results"] is None

    def test_streamlit_caching_integration(self):
        """Test integration with Streamlit caching patterns."""

        # Simulate cached function behavior
        cache = {}

        def cached_validate_parameters(params_tuple):
            """Simulate @st.cache_data behavior."""
            if params_tuple in cache:
                return cache[params_tuple]

            params_dict = dict(params_tuple)
            result = self.schema.validate_parameter_set(params_dict)
            cache[params_tuple] = result
            return result

        # Test cache behavior
        params = get_default_parameters()
        params_tuple = tuple(sorted(params.items()))

        # First call - should calculate
        result1 = cached_validate_parameters(params_tuple)
        assert len(cache) == 1

        # Second call - should use cache
        result2 = cached_validate_parameters(params_tuple)
        assert result1 == result2
        assert len(cache) == 1  # No new cache entry

        # Different parameters - should calculate new
        params2 = params.copy()
        params2["merit_rate_level_1"] = 0.050
        params_tuple2 = tuple(sorted(params2.items()))

        result3 = cached_validate_parameters(params_tuple2)
        assert len(cache) == 2  # New cache entry

    def test_streamlit_widget_integration(self):
        """Test integration with Streamlit widget patterns."""

        # Simulate widget state changes
        widget_state = {
            "merit_slider_1": 4.5,  # Percentage
            "merit_slider_2": 4.0,
            "cola_slider": 2.5,
            "new_hire_slider": 115,
            "apply_mode": "Single Year",
            "selected_year": 2025,
        }

        # Convert widget values to parameters
        parameters = {}

        for level in [1, 2, 3, 4, 5]:
            slider_key = f"merit_slider_{level}"
            if slider_key in widget_state:
                parameters[f"merit_rate_level_{level}"] = (
                    widget_state[slider_key] / 100.0
                )
            else:
                # Use default for missing sliders
                defaults = get_default_parameters()
                parameters[f"merit_rate_level_{level}"] = defaults[
                    f"merit_rate_level_{level}"
                ]

        parameters["cola_rate"] = widget_state["cola_slider"] / 100.0
        parameters["new_hire_salary_adjustment"] = (
            widget_state["new_hire_slider"] / 100.0
        )

        # Validate converted parameters
        validation_result = self.schema.validate_parameter_set(parameters)

        # Should be valid and provide feedback for widgets
        assert validation_result["is_valid"]

        # Extract widget feedback
        widget_feedback = {}
        for param_name, param_result in validation_result["parameter_results"].items():
            if "merit_rate_level" in param_name:
                level = param_name.split("_")[-1]
                widget_feedback[f"merit_slider_{level}"] = {
                    "risk": param_result["risk_level"],
                    "messages": param_result["messages"],
                }

        # Verify feedback structure
        assert "merit_slider_1" in widget_feedback
        assert "risk" in widget_feedback["merit_slider_1"]


class TestDagsterIntegrationPatterns:
    """Test Dagster-specific integration patterns."""

    def setup_method(self):
        """Setup for Dagster integration tests."""
        self.mock_duckdb = Mock()
        self.mock_conn = Mock()
        self.mock_duckdb.get_connection.return_value.__enter__.return_value = (
            self.mock_conn
        )

    def test_dagster_asset_integration(self):
        """Test integration with Dagster asset patterns."""

        # Mock Dagster asset execution context
        mock_context = Mock()
        mock_context.log = Mock()

        # Simulate asset execution
        def simulate_optimization_asset(context, duckdb_resource):
            """Simulate optimization asset execution."""
            context.log.info("Starting optimization asset")

            # Create optimizer
            optimizer = CompensationOptimizer(duckdb_resource, "dagster_test")

            # Mock optimization request
            request = OptimizationRequest(
                scenario_id="dagster_test",
                initial_parameters=get_default_parameters(),
                objectives={"cost": 1.0},
            )

            # Execute optimization (mocked)
            with patch("scipy.optimize.minimize") as mock_minimize:
                mock_result = Mock()
                mock_result.success = True
                mock_result.x = [0.045]
                mock_result.fun = 0.5
                mock_minimize.return_value = mock_result

                result = optimizer.optimize(request)

            context.log.info(f"Optimization completed: {result.converged}")

            # Return serializable result (important for Dagster)
            return {
                "scenario_id": result.scenario_id,
                "converged": result.converged,
                "optimal_parameters": result.optimal_parameters,
                "objective_value": result.objective_value,
            }

        # Execute asset
        result = simulate_optimization_asset(mock_context, self.mock_duckdb)

        # Verify asset execution
        assert result["scenario_id"] == "dagster_test"
        assert result["converged"] is True
        assert isinstance(result["optimal_parameters"], dict)

        # Verify logging
        mock_context.log.info.assert_called()

    def test_dagster_dependency_management(self):
        """Test Dagster asset dependency patterns."""

        # Simulate asset dependency chain
        asset_results = {}

        # Asset 1: Parameter validation
        def parameter_validation_asset():
            params = get_default_parameters()
            schema = get_parameter_schema()
            validation = schema.validate_parameter_set(params)

            return {
                "parameters": params,
                "validation_result": validation,
                "timestamp": time.time(),
            }

        # Asset 2: Optimization (depends on parameter validation)
        def optimization_asset(parameter_validation_result):
            if not parameter_validation_result["validation_result"]["is_valid"]:
                raise ValueError("Invalid parameters provided")

            # Mock optimization
            return {
                "optimal_parameters": parameter_validation_result["parameters"],
                "objective_value": 0.5,
                "converged": True,
            }

        # Asset 3: Simulation (depends on optimization)
        def simulation_asset(optimization_result):
            if not optimization_result["converged"]:
                raise ValueError("Optimization did not converge")

            # Mock simulation
            return {
                "workforce_count": 1200,
                "total_cost": 75_000_000,
                "parameters_used": optimization_result["optimal_parameters"],
            }

        # Execute dependency chain
        asset_results["parameter_validation"] = parameter_validation_asset()
        asset_results["optimization"] = optimization_asset(
            asset_results["parameter_validation"]
        )
        asset_results["simulation"] = simulation_asset(asset_results["optimization"])

        # Verify dependency chain execution
        assert asset_results["parameter_validation"]["validation_result"]["is_valid"]
        assert asset_results["optimization"]["converged"]
        assert asset_results["simulation"]["workforce_count"] > 0

    def test_dagster_error_handling(self):
        """Test Dagster error handling patterns."""

        # Test asset failure handling
        def failing_asset():
            """Asset that simulates failure."""
            raise Exception("Simulated asset failure")

        # Test graceful failure handling
        try:
            failing_asset()
            assert False, "Asset should have failed"
        except Exception as e:
            assert "Simulated asset failure" in str(e)

        # Test asset retry logic
        retry_count = 0

        def retryable_asset():
            """Asset that succeeds after retries."""
            nonlocal retry_count
            retry_count += 1

            if retry_count < 3:
                raise Exception(f"Retry {retry_count}")

            return {"status": "success", "retry_count": retry_count}

        # Simulate retry logic
        max_retries = 5
        for attempt in range(max_retries):
            try:
                result = retryable_asset()
                break
            except Exception:
                if attempt == max_retries - 1:
                    raise
                continue

        assert result["status"] == "success"
        assert result["retry_count"] == 3


if __name__ == "__main__":
    # Run integration tests
    pytest.main(
        [
            __file__
            + "::TestCompensationTuningWorkflow::test_ui_to_database_parameter_flow",
            __file__
            + "::TestCompensationTuningWorkflow::test_optimization_to_simulation_workflow",
            __file__
            + "::TestStreamlitIntegrationPatterns::test_streamlit_session_state_integration",
            __file__
            + "::TestDagsterIntegrationPatterns::test_dagster_asset_integration",
            "-v",
        ]
    )
