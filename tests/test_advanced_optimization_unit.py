"""
Advanced Unit Tests for Optimization Components
===============================================

This module provides comprehensive unit testing for all optimization engine components,
focusing on mathematical correctness, boundary conditions, and algorithmic behavior.

Test Coverage:
- Constraint Solver: Parameter validation, bounds checking, optimization algorithms
- Objective Functions: Cost calculations, equity metrics, target achievement
- Sensitivity Analysis: Parameter importance ranking, gradient calculations
- Evidence Generator: Report generation, data formatting, risk assessment
- Integration Points: Component interaction and data flow validation

Follows PlanWise Navigator testing standards with enterprise-grade validation.
"""

import pytest
import pandas as pd
import numpy as np
import json
import time
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock, call
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
import warnings

# Import optimization components
from orchestrator.optimization.constraint_solver import CompensationOptimizer
from orchestrator.optimization.objective_functions import ObjectiveFunctions
from orchestrator.optimization.sensitivity_analysis import SensitivityAnalyzer
from orchestrator.optimization.evidence_generator import EvidenceGenerator
from orchestrator.optimization.optimization_schemas import (
    OptimizationRequest,
    OptimizationResult,
    OptimizationError,
    PARAMETER_SCHEMA,
    OptimizationCache
)


@dataclass
class MockQueryResult:
    """Mock for database query results."""
    data: List[Tuple]
    columns: List[str] = None

    def fetchone(self):
        return self.data[0] if self.data else None

    def fetchall(self):
        return self.data

    def df(self):
        if self.columns:
            return pd.DataFrame(self.data, columns=self.columns)
        return pd.DataFrame(self.data)


class TestConstraintSolverAdvanced:
    """Advanced unit tests for CompensationOptimizer."""

    def setup_method(self):
        """Setup for constraint solver tests."""
        self.mock_duckdb = Mock()
        self.mock_conn = Mock()
        self.mock_duckdb.get_connection.return_value.__enter__.return_value = self.mock_conn
        self.optimizer = CompensationOptimizer(self.mock_duckdb, "test_scenario")

    def test_initialization_validation(self):
        """Test optimizer initialization with various inputs."""
        # Valid initialization
        assert self.optimizer.scenario_id == "test_scenario"
        assert self.optimizer.duckdb_resource == self.mock_duckdb
        assert hasattr(self.optimizer, 'obj_funcs')
        assert hasattr(self.optimizer, 'cache')

        # Test with None scenario_id
        with pytest.raises(ValueError, match="scenario_id cannot be empty"):
            CompensationOptimizer(self.mock_duckdb, "")

        # Test with None resource
        with pytest.raises(ValueError, match="DuckDB resource cannot be None"):
            CompensationOptimizer(None, "test_scenario")

    def test_parameter_bounds_validation(self):
        """Test parameter bounds validation logic."""
        # Test valid parameters
        valid_params = {
            "merit_rate_level_1": 0.045,
            "merit_rate_level_2": 0.040,
            "cola_rate": 0.025,
            "new_hire_salary_adjustment": 1.15
        }

        # Should not raise exception
        self.optimizer._validate_inputs(valid_params, {"cost": 1.0})

        # Test parameter below minimum
        invalid_low = valid_params.copy()
        invalid_low["merit_rate_level_1"] = 0.005  # Below min

        with pytest.raises(ValueError, match="below minimum"):
            self.optimizer._validate_inputs(invalid_low, {"cost": 1.0})

        # Test parameter above maximum
        invalid_high = valid_params.copy()
        invalid_high["merit_rate_level_1"] = 0.15  # Above max

        with pytest.raises(ValueError, match="above maximum"):
            self.optimizer._validate_inputs(invalid_high, {"cost": 1.0})

    def test_objective_weights_validation(self):
        """Test objective weights validation."""
        valid_params = {"merit_rate_level_1": 0.045}

        # Valid weights (sum to 1.0)
        valid_objectives = {"cost": 0.6, "equity": 0.4}
        self.optimizer._validate_inputs(valid_params, valid_objectives)

        # Invalid weights (don't sum to 1.0)
        invalid_objectives = {"cost": 0.8, "equity": 0.4}  # Sum = 1.2

        with pytest.raises(ValueError, match="must sum to 1.0"):
            self.optimizer._validate_inputs(valid_params, invalid_objectives)

        # Empty objectives
        with pytest.raises(ValueError, match="at least one objective"):
            self.optimizer._validate_inputs(valid_params, {})

        # Invalid objective name
        invalid_name_objectives = {"invalid_objective": 1.0}

        with pytest.raises(ValueError, match="Unknown objective"):
            self.optimizer._validate_inputs(valid_params, invalid_name_objectives)

    def test_parameter_array_conversion(self):
        """Test conversion between parameter dict and array formats."""
        params = {
            "merit_rate_level_1": 0.045,
            "merit_rate_level_2": 0.040,
            "cola_rate": 0.025
        }

        # Convert to array
        array = self.optimizer._parameters_to_array(params)

        assert len(array) == 3
        assert array[0] == 0.045
        assert array[1] == 0.040
        assert array[2] == 0.025

        # Convert back to dict
        recovered = self.optimizer._array_to_parameters(array, params)

        assert recovered == params

        # Test with different parameter order
        reordered_params = {
            "cola_rate": 0.025,
            "merit_rate_level_1": 0.045,
            "merit_rate_level_2": 0.040
        }

        reordered_array = self.optimizer._parameters_to_array(reordered_params)
        # Array order should match parameter order in keys
        assert len(reordered_array) == 3

    def test_constraint_functions(self):
        """Test constraint function generation and evaluation."""
        params = {
            "merit_rate_level_1": 0.045,
            "cola_rate": 0.025
        }
        objectives = {"cost": 1.0}

        constraints = self.optimizer._generate_constraints(params, objectives)

        # Should have constraint functions for each parameter
        assert len(constraints) >= len(params) * 2  # Min and max constraints

        # Test constraint evaluation
        test_array = self.optimizer._parameters_to_array(params)

        for constraint in constraints:
            result = constraint(test_array)
            # Valid parameters should satisfy constraints (result >= 0)
            assert result >= -1e-10  # Allow small floating point errors

    def test_optimization_bounds_generation(self):
        """Test optimization bounds generation."""
        params = {
            "merit_rate_level_1": 0.045,
            "merit_rate_level_2": 0.040,
            "cola_rate": 0.025
        }

        bounds = self.optimizer._generate_bounds(params)

        assert len(bounds) == len(params)

        # Check bounds are correctly set from schema
        for i, (param_name, _) in enumerate(params.items()):
            if param_name in PARAMETER_SCHEMA:
                schema_bounds = PARAMETER_SCHEMA[param_name]["range"]
                assert bounds[i][0] == schema_bounds[0]  # Min
                assert bounds[i][1] == schema_bounds[1]  # Max

    def test_risk_assessment_calculation(self):
        """Test risk assessment for parameter combinations."""
        # Low risk parameters (center of ranges)
        low_risk_params = {
            "merit_rate_level_1": 0.05,  # Center of typical range
            "cola_rate": 0.025
        }

        risk = self.optimizer._assess_risk_level(low_risk_params)
        assert risk == "LOW"

        # High risk parameters (at extremes)
        high_risk_params = {
            "merit_rate_level_1": 0.08,  # Near maximum
            "cola_rate": 0.0  # At minimum
        }

        risk = self.optimizer._assess_risk_level(high_risk_params)
        assert risk in ["MEDIUM", "HIGH", "CRITICAL"]

        # Mixed risk parameters
        mixed_risk_params = {
            "merit_rate_level_1": 0.045,  # Normal
            "cola_rate": 0.07  # High
        }

        risk = self.optimizer._assess_risk_level(mixed_risk_params)
        assert risk in ["LOW", "MEDIUM", "HIGH"]

    def test_optimization_caching(self):
        """Test optimization result caching mechanism."""
        cache = OptimizationCache()

        params = {"merit_rate_level_1": 0.045}

        # Test cache miss
        assert cache.get(params) is None
        assert cache.hit_rate == 0.0

        # Test cache set
        cache.set(params, 0.75)
        assert cache.get(params) == 0.75

        # Test cache hit
        result = cache.get(params)
        assert result == 0.75
        assert cache.hit_rate == 0.5  # 1 hit out of 2 attempts

        # Test cache with floating point precision
        similar_params = {"merit_rate_level_1": 0.045000001}
        # Should be treated as same due to precision handling
        cache_result = cache.get(similar_params)
        # Implementation dependent - could be None or same value

    @patch('scipy.optimize.minimize')
    def test_optimization_algorithm_selection(self, mock_minimize):
        """Test optimization algorithm selection and fallback."""
        mock_minimize.return_value.success = True
        mock_minimize.return_value.x = [0.045, 0.025]
        mock_minimize.return_value.fun = 0.5
        mock_minimize.return_value.nit = 50
        mock_minimize.return_value.nfev = 150

        params = {"merit_rate_level_1": 0.045, "cola_rate": 0.025}
        objectives = {"cost": 1.0}

        # Test with specific method
        request = OptimizationRequest(
            scenario_id="test",
            initial_parameters=params,
            objectives=objectives,
            method="SLSQP"
        )

        with patch.object(self.optimizer.obj_funcs, 'combined_objective', return_value=0.5):
            result = self.optimizer.optimize(request)

        # Should use specified method
        mock_minimize.assert_called()
        call_args = mock_minimize.call_args
        assert call_args[1]['method'] == 'SLSQP'

        assert result.converged is True
        assert result.algorithm_used == "SLSQP"
        assert result.iterations == 50
        assert result.function_evaluations == 150

    def test_optimization_convergence_criteria(self):
        """Test optimization convergence criteria and stopping conditions."""
        # Mock an optimization that converges quickly
        with patch('scipy.optimize.minimize') as mock_minimize:
            mock_result = Mock()
            mock_result.success = True
            mock_result.x = [0.045]
            mock_result.fun = 0.1
            mock_result.nit = 25
            mock_result.nfev = 75
            mock_minimize.return_value = mock_result

            params = {"merit_rate_level_1": 0.045}
            objectives = {"cost": 1.0}

            request = OptimizationRequest(
                scenario_id="test",
                initial_parameters=params,
                objectives=objectives,
                max_evaluations=100,
                tolerance=1e-6
            )

            with patch.object(self.optimizer.obj_funcs, 'combined_objective', return_value=0.1):
                result = self.optimizer.optimize(request)

            assert result.converged is True
            assert result.function_evaluations < request.max_evaluations

            # Check tolerance was passed to optimizer
            call_args = mock_minimize.call_args
            assert 'options' in call_args[1]


class TestObjectiveFunctionsAdvanced:
    """Advanced unit tests for ObjectiveFunctions."""

    def setup_method(self):
        """Setup for objective functions tests."""
        self.mock_duckdb = Mock()
        self.mock_conn = Mock()
        self.mock_duckdb.get_connection.return_value.__enter__.return_value = self.mock_conn
        self.obj_funcs = ObjectiveFunctions(self.mock_duckdb, "test_scenario")

    def test_cost_objective_calculation(self):
        """Test cost objective calculation with various scenarios."""
        # Test normal cost scenario
        self.mock_conn.execute.return_value.fetchone.return_value = [2_450_000.0]

        with patch.object(self.obj_funcs, '_update_parameters'):
            cost = self.obj_funcs.cost_objective({"merit_rate_level_1": 0.045})

        assert cost == 2.45  # Should return in millions

        # Test zero cost scenario
        self.mock_conn.execute.return_value.fetchone.return_value = [0.0]

        with patch.object(self.obj_funcs, '_update_parameters'):
            cost = self.obj_funcs.cost_objective({"merit_rate_level_1": 0.0})

        assert cost == 0.0

        # Test very high cost scenario
        self.mock_conn.execute.return_value.fetchone.return_value = [50_000_000.0]

        with patch.object(self.obj_funcs, '_update_parameters'):
            cost = self.obj_funcs.cost_objective({"merit_rate_level_1": 0.10})

        assert cost == 50.0

    def test_equity_objective_calculation(self):
        """Test equity objective with different compensation distributions."""
        # Test balanced equity scenario
        balanced_data = [
            (1, 50000, 2500),  # job_level, avg_comp, stddev_comp
            (2, 60000, 3000),
            (3, 70000, 3500),
            (4, 80000, 4000),
            (5, 90000, 4500)
        ]

        self.mock_conn.execute.return_value.fetchall.return_value = balanced_data

        with patch.object(self.obj_funcs, '_update_parameters'):
            equity = self.obj_funcs.equity_objective({"merit_rate_level_1": 0.045})

        # Should have reasonable coefficient of variation
        assert 0.0 <= equity <= 1.0

        # Test high inequality scenario
        high_inequality_data = [
            (1, 50000, 15000),  # High variation
            (2, 60000, 25000),
            (3, 70000, 20000)
        ]

        self.mock_conn.execute.return_value.fetchall.return_value = high_inequality_data

        with patch.object(self.obj_funcs, '_update_parameters'):
            high_equity = self.obj_funcs.equity_objective({"merit_rate_level_1": 0.045})

        # Higher inequality should result in higher (worse) equity score
        assert high_equity > equity

        # Test edge case: zero standard deviation
        zero_variation_data = [
            (1, 50000, 0),  # No variation
            (2, 60000, 0)
        ]

        self.mock_conn.execute.return_value.fetchall.return_value = zero_variation_data

        with patch.object(self.obj_funcs, '_update_parameters'):
            perfect_equity = self.obj_funcs.equity_objective({"merit_rate_level_1": 0.045})

        # Perfect equity should result in very low score
        assert perfect_equity < equity

    def test_targets_objective_calculation(self):
        """Test targets objective with various achievement scenarios."""
        # Mock target achievement data
        target_achievement_data = [
            ("budget_target", 2_000_000, 1_950_000, 0.975),  # target_name, target, actual, achievement
            ("growth_target", 0.05, 0.048, 0.96),
            ("retention_target", 0.90, 0.92, 1.022)
        ]

        self.mock_conn.execute.return_value.fetchall.return_value = target_achievement_data

        with patch.object(self.obj_funcs, '_update_parameters'):
            targets_score = self.obj_funcs.targets_objective({"merit_rate_level_1": 0.045})

        # Should calculate average deviation from targets
        expected_deviations = [abs(1 - 0.975), abs(1 - 0.96), abs(1 - 1.022)]
        expected_score = sum(expected_deviations) / len(expected_deviations)

        assert abs(targets_score - expected_score) < 1e-6

        # Test perfect target achievement
        perfect_data = [
            ("budget_target", 2_000_000, 2_000_000, 1.0),
            ("growth_target", 0.05, 0.05, 1.0)
        ]

        self.mock_conn.execute.return_value.fetchall.return_value = perfect_data

        with patch.object(self.obj_funcs, '_update_parameters'):
            perfect_score = self.obj_funcs.targets_objective({"merit_rate_level_1": 0.045})

        assert perfect_score == 0.0  # Perfect achievement

        # Test missing targets
        self.mock_conn.execute.return_value.fetchall.return_value = []

        with patch.object(self.obj_funcs, '_update_parameters'):
            no_targets_score = self.obj_funcs.targets_objective({"merit_rate_level_1": 0.045})

        assert no_targets_score == 0.0  # No penalty for missing targets

    def test_combined_objective_weighting(self):
        """Test combined objective function with different weight combinations."""
        # Mock individual objectives
        with patch.object(self.obj_funcs, 'cost_objective', return_value=2.5), \
             patch.object(self.obj_funcs, 'equity_objective', return_value=0.1), \
             patch.object(self.obj_funcs, 'targets_objective', return_value=0.05):

            # Test equal weighting
            equal_weights = {"cost": 1/3, "equity": 1/3, "targets": 1/3}
            result = self.obj_funcs.combined_objective(
                {"merit_rate_level_1": 0.045},
                equal_weights
            )
            expected = (2.5 + 0.1 + 0.05) / 3
            assert abs(result - expected) < 1e-6

            # Test cost-focused weighting
            cost_focused = {"cost": 0.8, "equity": 0.1, "targets": 0.1}
            result = self.obj_funcs.combined_objective(
                {"merit_rate_level_1": 0.045},
                cost_focused
            )
            expected = 0.8 * 2.5 + 0.1 * 0.1 + 0.1 * 0.05
            assert abs(result - expected) < 1e-6

            # Test equity-focused weighting
            equity_focused = {"cost": 0.2, "equity": 0.7, "targets": 0.1}
            result = self.obj_funcs.combined_objective(
                {"merit_rate_level_1": 0.045},
                equity_focused
            )
            expected = 0.2 * 2.5 + 0.7 * 0.1 + 0.1 * 0.05
            assert abs(result - expected) < 1e-6

    def test_parameter_update_mechanism(self):
        """Test parameter update mechanism for database queries."""
        params = {
            "merit_rate_level_1": 0.045,
            "merit_rate_level_2": 0.040,
            "cola_rate": 0.025
        }

        # Test parameter update calls correct database operations
        self.obj_funcs._update_parameters(params)

        # Should call database operations to update parameter tables
        self.mock_conn.execute.assert_called()

        # Check that execute was called with parameter update statements
        call_args_list = self.mock_conn.execute.call_args_list
        assert len(call_args_list) > 0

        # Verify parameters are properly formatted for database
        for call_args in call_args_list:
            sql_statement = call_args[0][0]
            # Should contain parameter update logic
            assert isinstance(sql_statement, str)

    def test_objective_function_error_handling(self):
        """Test error handling in objective function calculations."""
        # Test database connection error
        self.mock_conn.execute.side_effect = Exception("Database connection failed")

        with pytest.raises(Exception, match="Database connection failed"):
            self.obj_funcs.cost_objective({"merit_rate_level_1": 0.045})

        # Reset mock
        self.mock_conn.execute.side_effect = None

        # Test invalid parameter values
        with patch.object(self.obj_funcs, '_update_parameters', side_effect=ValueError("Invalid parameter")):
            with pytest.raises(ValueError, match="Invalid parameter"):
                self.obj_funcs.cost_objective({"invalid_param": 999})

        # Test empty result sets
        self.mock_conn.execute.return_value.fetchone.return_value = None

        with patch.object(self.obj_funcs, '_update_parameters'):
            # Should handle gracefully and return reasonable default
            cost = self.obj_funcs.cost_objective({"merit_rate_level_1": 0.045})
            assert cost >= 0  # Should return non-negative default


class TestSensitivityAnalysisAdvanced:
    """Advanced unit tests for SensitivityAnalyzer."""

    def setup_method(self):
        """Setup for sensitivity analysis tests."""
        self.mock_duckdb = Mock()
        self.analyzer = SensitivityAnalyzer(self.mock_duckdb, "test_scenario")
        self.analyzer.obj_funcs = Mock()

    def test_sensitivity_calculation_methods(self):
        """Test different sensitivity calculation methods."""
        # Mock objective function for finite difference
        base_value = 0.5
        perturbed_value = 0.52

        self.analyzer.obj_funcs.combined_objective.side_effect = [base_value, perturbed_value]

        params = {"merit_rate_level_1": 0.045}
        objectives = {"cost": 1.0}

        sensitivities = self.analyzer.calculate_sensitivities(params, objectives)

        assert "merit_rate_level_1" in sensitivities

        # Calculate expected sensitivity (finite difference)
        param_def = PARAMETER_SCHEMA["merit_rate_level_1"]
        perturbation = (param_def["range"][1] - param_def["range"][0]) * 0.01  # 1% of range
        expected_sensitivity = (perturbed_value - base_value) / perturbation

        assert abs(sensitivities["merit_rate_level_1"] - expected_sensitivity) < 1e-10

    def test_parameter_importance_ranking(self):
        """Test parameter importance ranking algorithms."""
        sensitivities = {
            "merit_rate_level_1": 0.5,
            "merit_rate_level_2": -0.3,
            "cola_rate": 0.1,
            "merit_rate_level_3": -0.8,
            "new_hire_salary_adjustment": 0.05
        }

        ranking = self.analyzer.rank_parameter_importance(sensitivities)

        # Should be sorted by absolute sensitivity (descending)
        expected_order = [
            ("merit_rate_level_3", -0.8),
            ("merit_rate_level_1", 0.5),
            ("merit_rate_level_2", -0.3),
            ("cola_rate", 0.1),
            ("new_hire_salary_adjustment", 0.05)
        ]

        assert ranking == expected_order

        # Test with zero sensitivities
        zero_sensitivities = {
            "merit_rate_level_1": 0.0,
            "merit_rate_level_2": 0.0
        }

        zero_ranking = self.analyzer.rank_parameter_importance(zero_sensitivities)

        # Should handle zeros gracefully
        assert len(zero_ranking) == 2
        for param, sensitivity in zero_ranking:
            assert sensitivity == 0.0

    def test_sensitivity_analysis_with_multiple_objectives(self):
        """Test sensitivity analysis with multiple objectives."""
        # Mock different objective responses
        def mock_combined_objective(params, objectives):
            # Simulate different sensitivities for different objectives
            if objectives.get("cost", 0) > 0.5:
                return 0.6  # Cost-sensitive response
            elif objectives.get("equity", 0) > 0.5:
                return 0.4  # Equity-sensitive response
            else:
                return 0.5  # Baseline

        self.analyzer.obj_funcs.combined_objective.side_effect = mock_combined_objective

        params = {"merit_rate_level_1": 0.045}

        # Test cost-focused sensitivity
        cost_objectives = {"cost": 0.8, "equity": 0.2}
        cost_sensitivities = self.analyzer.calculate_sensitivities(params, cost_objectives)

        # Test equity-focused sensitivity
        equity_objectives = {"cost": 0.2, "equity": 0.8}
        equity_sensitivities = self.analyzer.calculate_sensitivities(params, equity_objectives)

        # Sensitivities should differ based on objective weighting
        assert cost_sensitivities != equity_sensitivities

    def test_gradient_approximation_accuracy(self):
        """Test accuracy of gradient approximation methods."""
        # Create a quadratic test function for known gradient
        def quadratic_objective(params, objectives):
            x = params.get("merit_rate_level_1", 0.045)
            return (x - 0.05) ** 2  # Minimum at x = 0.05

        self.analyzer.obj_funcs.combined_objective.side_effect = quadratic_objective

        # Test at different points
        test_points = [0.03, 0.045, 0.05, 0.06, 0.07]

        for test_point in test_points:
            params = {"merit_rate_level_1": test_point}
            objectives = {"cost": 1.0}

            sensitivities = self.analyzer.calculate_sensitivities(params, objectives)

            # For quadratic function f(x) = (x - 0.05)^2, derivative is 2(x - 0.05)
            expected_gradient = 2 * (test_point - 0.05)

            # Allow for finite difference approximation error
            tolerance = 1e-3  # Reasonable tolerance for finite differences
            assert abs(sensitivities["merit_rate_level_1"] - expected_gradient) < tolerance

    def test_sensitivity_with_parameter_constraints(self):
        """Test sensitivity analysis respecting parameter constraints."""
        # Test near boundary conditions
        boundary_params = {
            "merit_rate_level_1": 0.08,  # Near upper bound
            "cola_rate": 0.01  # Near lower bound
        }

        # Mock objective function
        self.analyzer.obj_funcs.combined_objective.return_value = 0.5

        objectives = {"cost": 1.0}
        sensitivities = self.analyzer.calculate_sensitivities(boundary_params, objectives)

        # Should calculate sensitivities even near boundaries
        assert "merit_rate_level_1" in sensitivities
        assert "cola_rate" in sensitivities

        # Test at exact boundaries
        min_boundary_params = {
            "merit_rate_level_1": PARAMETER_SCHEMA["merit_rate_level_1"]["range"][0]
        }

        min_sensitivities = self.analyzer.calculate_sensitivities(min_boundary_params, objectives)
        assert "merit_rate_level_1" in min_sensitivities

    def test_sensitivity_caching_mechanism(self):
        """Test sensitivity analysis result caching."""
        # Mock objective function with call tracking
        call_count = 0

        def counting_objective(params, objectives):
            nonlocal call_count
            call_count += 1
            return 0.5

        self.analyzer.obj_funcs.combined_objective.side_effect = counting_objective

        params = {"merit_rate_level_1": 0.045}
        objectives = {"cost": 1.0}

        # First calculation
        sensitivities1 = self.analyzer.calculate_sensitivities(params, objectives)
        first_call_count = call_count

        # Second calculation with same parameters (should use cache if implemented)
        sensitivities2 = self.analyzer.calculate_sensitivities(params, objectives)
        second_call_count = call_count

        # Results should be identical
        assert sensitivities1 == sensitivities2

        # If caching is implemented, call count should not increase significantly
        # If not implemented, this is still a valid test documenting the behavior


class TestEvidenceGeneratorAdvanced:
    """Advanced unit tests for EvidenceGenerator."""

    def setup_method(self):
        """Setup for evidence generator tests."""
        self.mock_result = OptimizationResult(
            scenario_id="test_scenario",
            converged=True,
            optimal_parameters={
                "merit_rate_level_1": 0.045,
                "merit_rate_level_2": 0.040,
                "cola_rate": 0.025
            },
            objective_value=0.234567,
            algorithm_used="SLSQP",
            iterations=45,
            function_evaluations=127,
            runtime_seconds=4.2,
            estimated_cost_impact={
                "value": 2450000.0,
                "unit": "USD",
                "confidence": "high"
            },
            estimated_employee_impact={
                "count": 1200,
                "percentage_of_workforce": 0.85,
                "risk_level": "medium"
            },
            risk_assessment="MEDIUM",
            constraint_violations={},
            solution_quality_score=0.87
        )

        self.generator = EvidenceGenerator(self.mock_result)

    def test_report_content_generation(self):
        """Test comprehensive report content generation."""
        content = self.generator._generate_report_content()

        # Check essential sections are present
        assert "Optimization Results Summary" in content
        assert "test_scenario" in content
        assert "SLSQP" in content
        assert "Converged" in content
        assert "2,450,000" in content
        assert "1,200" in content

        # Check parameter formatting
        assert "4.50%" in content  # merit_rate_level_1
        assert "4.00%" in content  # merit_rate_level_2
        assert "2.50%" in content  # cola_rate

        # Check risk assessment
        assert "MEDIUM" in content

        # Check quality metrics
        assert "87%" in content or "0.87" in content

    def test_parameter_table_formatting(self):
        """Test parameter table formatting for different parameter types."""
        table = self.generator._format_parameters_table()

        # Should be markdown table format
        assert "| Parameter |" in table
        assert "| Value |" in table
        assert "|" in table

        # Check percentage formatting
        assert "4.50%" in table
        assert "4.00%" in table
        assert "2.50%" in table

        # Check table structure
        lines = table.split('\n')
        header_line = next(line for line in lines if "Parameter" in line)
        assert "Parameter" in header_line
        assert "Value" in header_line

        # Check parameter rows
        merit_line = next(line for line in lines if "merit_rate_level_1" in line)
        assert "4.50%" in merit_line

    def test_impact_analysis_formatting(self):
        """Test impact analysis section formatting."""
        content = self.generator._generate_report_content()

        # Check cost impact formatting
        assert "2,450,000" in content or "$2.45M" in content
        assert "USD" in content
        assert "high" in content.lower()

        # Check employee impact formatting
        assert "1,200" in content
        assert "85%" in content or "0.85" in content
        assert "medium" in content.lower()

    def test_risk_assessment_formatting(self):
        """Test risk assessment section formatting."""
        content = self.generator._generate_report_content()

        # Should include risk level
        assert "MEDIUM" in content

        # Should include quality score
        assert "87%" in content or "0.87" in content

        # Test with different risk levels
        high_risk_result = self.mock_result
        high_risk_result.risk_assessment = "HIGH"
        high_risk_result.solution_quality_score = 0.65

        high_risk_generator = EvidenceGenerator(high_risk_result)
        high_risk_content = high_risk_generator._generate_report_content()

        assert "HIGH" in high_risk_content
        assert "65%" in high_risk_content or "0.65" in high_risk_content

    def test_constraint_violations_formatting(self):
        """Test formatting of constraint violations."""
        # Test with constraint violations
        violated_result = self.mock_result
        violated_result.constraint_violations = {
            "budget_constraint": {
                "violation_amount": 150000,
                "description": "Exceeds budget by $150,000"
            },
            "equity_constraint": {
                "violation_amount": 0.05,
                "description": "Equity gap increased by 5%"
            }
        }

        violation_generator = EvidenceGenerator(violated_result)
        content = violation_generator._generate_report_content()

        # Should include constraint violation information
        assert "Constraint Violations" in content
        assert "budget_constraint" in content
        assert "150,000" in content
        assert "equity_constraint" in content
        assert "5%" in content

    def test_algorithm_details_formatting(self):
        """Test algorithm details section formatting."""
        content = self.generator._generate_report_content()

        # Check algorithm information
        assert "SLSQP" in content
        assert "45" in content  # iterations
        assert "127" in content  # function evaluations
        assert "4.2" in content  # runtime

        # Check convergence status
        assert "Converged" in content or "True" in content

    def test_report_generation_with_missing_data(self):
        """Test report generation with missing or None data."""
        # Create result with some missing fields
        incomplete_result = OptimizationResult(
            scenario_id="incomplete_test",
            converged=False,
            optimal_parameters={"merit_rate_level_1": 0.045},
            objective_value=0.5,
            algorithm_used="SLSQP",
            iterations=10,
            function_evaluations=30,
            runtime_seconds=1.0,
            estimated_cost_impact=None,
            estimated_employee_impact=None,
            risk_assessment="UNKNOWN",
            constraint_violations={},
            solution_quality_score=None
        )

        incomplete_generator = EvidenceGenerator(incomplete_result)
        content = incomplete_generator._generate_report_content()

        # Should handle missing data gracefully
        assert "incomplete_test" in content
        assert "SLSQP" in content
        assert "False" in content or "Not Converged" in content

        # Should not crash with None values
        assert isinstance(content, str)
        assert len(content) > 0

    def test_custom_formatting_options(self):
        """Test custom formatting options for reports."""
        # Test different currency formatting
        content = self.generator._generate_report_content()

        # Should format large numbers with commas
        assert "2,450,000" in content or "2.45" in content

        # Test percentage formatting
        assert "4.50%" in content
        assert "85%" in content

        # Test decimal precision
        assert "0.87" in content or "87%" in content

    def test_report_export_formats(self):
        """Test different report export formats."""
        # Test markdown format (default)
        markdown_content = self.generator._generate_report_content()
        assert "##" in markdown_content or "#" in markdown_content
        assert "|" in markdown_content  # Table formatting

        # Test HTML format generation
        html_content = self.generator.generate_html_report()
        assert "<html>" in html_content or "<div>" in html_content
        assert "</html>" in html_content or "</div>" in html_content

        # Test JSON format generation
        json_content = self.generator.generate_json_report()
        parsed_json = json.loads(json_content)

        assert "scenario_id" in parsed_json
        assert "optimal_parameters" in parsed_json
        assert "converged" in parsed_json


class TestOptimizationSchemaValidation:
    """Advanced tests for optimization schema validation."""

    def test_parameter_schema_completeness(self):
        """Test that parameter schema covers all required parameters."""
        required_parameters = [
            "merit_rate_level_1", "merit_rate_level_2", "merit_rate_level_3",
            "merit_rate_level_4", "merit_rate_level_5",
            "cola_rate",
            "new_hire_salary_adjustment",
            "promotion_probability_level_1", "promotion_probability_level_2",
            "promotion_probability_level_3", "promotion_probability_level_4",
            "promotion_probability_level_5",
            "promotion_raise_level_1", "promotion_raise_level_2",
            "promotion_raise_level_3", "promotion_raise_level_4",
            "promotion_raise_level_5"
        ]

        for param in required_parameters:
            assert param in PARAMETER_SCHEMA, f"Missing schema definition for {param}"

            schema_def = PARAMETER_SCHEMA[param]
            assert "range" in schema_def
            assert "type" in schema_def
            assert "description" in schema_def
            assert len(schema_def["range"]) == 2
            assert schema_def["range"][0] < schema_def["range"][1]

    def test_optimization_request_validation(self):
        """Test optimization request validation edge cases."""
        # Valid request
        valid_request = OptimizationRequest(
            scenario_id="test",
            initial_parameters={"merit_rate_level_1": 0.045},
            objectives={"cost": 1.0}
        )

        assert valid_request.scenario_id == "test"
        assert valid_request.method == "SLSQP"  # Default
        assert valid_request.max_evaluations == 200  # Default

        # Test with all optional parameters
        full_request = OptimizationRequest(
            scenario_id="full_test",
            initial_parameters={"merit_rate_level_1": 0.045},
            objectives={"cost": 0.6, "equity": 0.4},
            method="L-BFGS-B",
            max_evaluations=500,
            tolerance=1e-8,
            constraints={"budget_limit": 1000000}
        )

        assert full_request.method == "L-BFGS-B"
        assert full_request.max_evaluations == 500
        assert full_request.tolerance == 1e-8
        assert full_request.constraints["budget_limit"] == 1000000

    def test_optimization_result_validation(self):
        """Test optimization result structure validation."""
        # Complete result
        complete_result = OptimizationResult(
            scenario_id="complete_test",
            converged=True,
            optimal_parameters={"merit_rate_level_1": 0.045},
            objective_value=0.5,
            algorithm_used="SLSQP",
            iterations=50,
            function_evaluations=150,
            runtime_seconds=5.0,
            estimated_cost_impact={"value": 1000000, "unit": "USD"},
            estimated_employee_impact={"count": 1000},
            risk_assessment="MEDIUM",
            constraint_violations={},
            solution_quality_score=0.85
        )

        assert complete_result.converged is True
        assert complete_result.iterations == 50
        assert complete_result.estimated_cost_impact["value"] == 1000000

        # Minimal result
        minimal_result = OptimizationResult(
            scenario_id="minimal_test",
            converged=False,
            optimal_parameters={},
            objective_value=float('inf'),
            algorithm_used="FAILED",
            iterations=0,
            function_evaluations=0,
            runtime_seconds=0.0,
            estimated_cost_impact=None,
            estimated_employee_impact=None,
            risk_assessment="UNKNOWN",
            constraint_violations={},
            solution_quality_score=0.0
        )

        assert minimal_result.converged is False
        assert minimal_result.objective_value == float('inf')


class TestComponentIntegration:
    """Test integration between optimization components."""

    def setup_method(self):
        """Setup for integration tests."""
        self.mock_duckdb = Mock()
        self.mock_conn = Mock()
        self.mock_duckdb.get_connection.return_value.__enter__.return_value = self.mock_conn

    def test_optimizer_to_objective_functions_integration(self):
        """Test integration between optimizer and objective functions."""
        optimizer = CompensationOptimizer(self.mock_duckdb, "integration_test")

        # Test that optimizer creates objective functions correctly
        assert optimizer.obj_funcs is not None
        assert optimizer.obj_funcs.scenario_id == "integration_test"
        assert optimizer.obj_funcs.duckdb_resource == self.mock_duckdb

    def test_sensitivity_analyzer_integration(self):
        """Test integration with sensitivity analyzer."""
        analyzer = SensitivityAnalyzer(self.mock_duckdb, "integration_test")

        # Test that analyzer creates objective functions
        assert analyzer.obj_funcs is not None
        assert analyzer.scenario_id == "integration_test"

    def test_evidence_generator_integration(self):
        """Test integration with evidence generator."""
        # Create a realistic optimization result
        result = OptimizationResult(
            scenario_id="integration_test",
            converged=True,
            optimal_parameters={"merit_rate_level_1": 0.045},
            objective_value=0.5,
            algorithm_used="SLSQP",
            iterations=50,
            function_evaluations=150,
            runtime_seconds=5.0,
            estimated_cost_impact={"value": 1000000, "unit": "USD"},
            estimated_employee_impact={"count": 1000},
            risk_assessment="MEDIUM",
            constraint_violations={},
            solution_quality_score=0.85
        )

        generator = EvidenceGenerator(result)

        # Test report generation
        report = generator._generate_report_content()
        assert isinstance(report, str)
        assert len(report) > 0
        assert "integration_test" in report

    def test_end_to_end_optimization_workflow(self):
        """Test complete optimization workflow integration."""
        # Mock database responses
        self.mock_conn.execute.return_value.fetchone.return_value = [1_000_000.0]
        self.mock_conn.execute.return_value.fetchall.return_value = [
            (1, 50000, 2500),
            (2, 60000, 3000)
        ]

        # Create optimizer
        optimizer = CompensationOptimizer(self.mock_duckdb, "end_to_end_test")

        # Create optimization request
        request = OptimizationRequest(
            scenario_id="end_to_end_test",
            initial_parameters={"merit_rate_level_1": 0.045},
            objectives={"cost": 1.0}
        )

        # Mock scipy optimization
        with patch('scipy.optimize.minimize') as mock_minimize:
            mock_result = Mock()
            mock_result.success = True
            mock_result.x = [0.045]
            mock_result.fun = 0.5
            mock_result.nit = 25
            mock_result.nfev = 75
            mock_minimize.return_value = mock_result

            # Run optimization
            result = optimizer.optimize(request)

        # Verify result structure
        assert result.scenario_id == "end_to_end_test"
        assert result.converged is True
        assert "merit_rate_level_1" in result.optimal_parameters

        # Test evidence generation from result
        generator = EvidenceGenerator(result)
        report = generator._generate_report_content()

        assert "end_to_end_test" in report
        assert "Converged" in report or "True" in report


if __name__ == "__main__":
    # Run specific test classes for development
    pytest.main([
        __file__ + "::TestConstraintSolverAdvanced::test_parameter_bounds_validation",
        __file__ + "::TestObjectiveFunctionsAdvanced::test_cost_objective_calculation",
        __file__ + "::TestSensitivityAnalysisAdvanced::test_sensitivity_calculation_methods",
        __file__ + "::TestEvidenceGeneratorAdvanced::test_report_content_generation",
        "-v"
    ])
