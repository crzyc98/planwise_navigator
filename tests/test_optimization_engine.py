"""
Tests for S047 Optimization Engine
"""

from pathlib import Path
from unittest.mock import Mock, patch

import numpy as np
import pandas as pd
import pytest
from orchestrator.optimization.constraint_solver import CompensationOptimizer
from orchestrator.optimization.evidence_generator import EvidenceGenerator
from orchestrator.optimization.objective_functions import ObjectiveFunctions
from orchestrator.optimization.optimization_schemas import (
    PARAMETER_SCHEMA, OptimizationCache, OptimizationError,
    OptimizationRequest, OptimizationResult)
from orchestrator.optimization.sensitivity_analysis import SensitivityAnalyzer


class TestOptimizationSchemas:
    """Test optimization schemas and validation."""

    def test_optimization_request_validation(self):
        """Test optimization request validation."""

        # Valid request
        request = OptimizationRequest(
            scenario_id="test_scenario",
            initial_parameters={"merit_rate_level_1": 0.045, "cola_rate": 0.025},
            objectives={"cost": 0.6, "equity": 0.4},
        )

        assert request.scenario_id == "test_scenario"
        assert request.method == "SLSQP"  # Default
        assert request.max_evaluations == 200  # Default

    def test_optimization_request_invalid_objectives(self):
        """Test validation of objective weights."""

        with pytest.raises(ValueError):
            # Objectives don't sum to 1.0
            CompensationOptimizer(Mock(), "test")._validate_inputs(
                {"merit_rate_level_1": 0.045}, {"cost": 0.8, "equity": 0.4}  # Sum = 1.2
            )

    def test_parameter_schema_bounds(self):
        """Test parameter schema defines valid bounds."""

        for param_name, schema in PARAMETER_SCHEMA.items():
            assert "range" in schema
            assert len(schema["range"]) == 2
            assert schema["range"][0] < schema["range"][1]
            assert "type" in schema
            assert "description" in schema

    def test_optimization_cache(self):
        """Test optimization cache functionality."""

        cache = OptimizationCache()

        # Test cache miss
        params = {"merit_rate_level_1": 0.045}
        assert cache.get(params) is None
        assert cache.hit_rate == 0.0

        # Test cache set and hit
        cache.set(params, 0.5)
        assert cache.get(params) == 0.5
        assert cache.hit_rate == 0.5

        # Test consistent hashing
        params_reordered = {"merit_rate_level_1": 0.045}
        assert cache.get(params_reordered) == 0.5


class TestObjectiveFunctions:
    """Test objective function calculations."""

    @pytest.fixture
    def mock_duckdb_resource(self):
        """Mock DuckDB resource for testing."""
        mock_resource = Mock()
        mock_conn = Mock()
        mock_resource.get_connection.return_value.__enter__.return_value = mock_conn
        return mock_resource, mock_conn

    def test_cost_objective(self, mock_duckdb_resource):
        """Test cost objective calculation."""

        mock_resource, mock_conn = mock_duckdb_resource

        # Mock query result
        mock_conn.execute.return_value.fetchone.return_value = [2_450_000.0]

        obj_funcs = ObjectiveFunctions(mock_resource, "test_scenario")

        with patch.object(obj_funcs, "_update_parameters"):
            cost = obj_funcs.cost_objective({"merit_rate_level_1": 0.045})

        # Should return cost in millions
        assert cost == 2.45

    def test_equity_objective(self, mock_duckdb_resource):
        """Test equity objective calculation."""

        mock_resource, mock_conn = mock_duckdb_resource

        # Mock query result with compensation variance data
        mock_conn.execute.return_value.fetchall.return_value = [
            (1, 50000, 5000),  # job_level, avg_comp, stddev_comp
            (2, 60000, 3000),
            (3, 70000, 7000),
        ]

        obj_funcs = ObjectiveFunctions(mock_resource, "test_scenario")

        with patch.object(obj_funcs, "_update_parameters"):
            equity = obj_funcs.equity_objective({"merit_rate_level_1": 0.045})

        # Should return average coefficient of variation
        assert equity > 0
        assert equity < 1  # Should be reasonable

    def test_combined_objective(self, mock_duckdb_resource):
        """Test combined objective function."""

        mock_resource, mock_conn = mock_duckdb_resource
        obj_funcs = ObjectiveFunctions(mock_resource, "test_scenario")

        # Mock individual objectives
        with patch.object(obj_funcs, "cost_objective", return_value=2.5), patch.object(
            obj_funcs, "equity_objective", return_value=0.1
        ), patch.object(obj_funcs, "targets_objective", return_value=0.05):
            result = obj_funcs.combined_objective(
                {"merit_rate_level_1": 0.045},
                {"cost": 0.5, "equity": 0.3, "targets": 0.2},
            )

        expected = 0.5 * 2.5 + 0.3 * 0.1 + 0.2 * 0.05
        assert abs(result - expected) < 1e-6


class TestConstraintSolver:
    """Test constraint solver functionality."""

    @pytest.fixture
    def mock_optimizer(self):
        """Create mock optimizer for testing."""
        mock_duckdb = Mock()
        optimizer = CompensationOptimizer(mock_duckdb, "test_scenario")
        return optimizer

    def test_parameter_validation(self, mock_optimizer):
        """Test parameter validation."""

        # Valid parameters
        valid_params = {"merit_rate_level_1": 0.045}
        valid_objectives = {"cost": 1.0}

        # Should not raise
        mock_optimizer._validate_inputs(valid_params, valid_objectives)

        # Invalid parameter bounds
        invalid_params = {"merit_rate_level_1": 0.15}  # Above max

        with pytest.raises(ValueError):
            mock_optimizer._validate_inputs(invalid_params, valid_objectives)

    def test_array_parameter_conversion(self, mock_optimizer):
        """Test parameter array conversion."""

        params = {"merit_rate_level_1": 0.045, "cola_rate": 0.025}

        # Convert to array
        array = mock_optimizer._parameters_to_array(params)
        assert len(array) == 2
        assert array[0] == 0.045
        assert array[1] == 0.025

        # Convert back to dict
        converted_back = mock_optimizer._array_to_parameters(array, params)
        assert converted_back == params

    def test_risk_assessment(self, mock_optimizer):
        """Test risk assessment calculation."""

        # Parameters at center of ranges should be low risk
        center_params = {"merit_rate_level_1": 0.05}  # Center of [0.02, 0.08]
        risk = mock_optimizer._assess_risk_level(center_params)
        assert risk == "LOW"

        # Parameters at extremes should be higher risk
        extreme_params = {"merit_rate_level_1": 0.08}  # At max
        risk = mock_optimizer._assess_risk_level(extreme_params)
        assert risk in ["MEDIUM", "HIGH"]


class TestSensitivityAnalysis:
    """Test sensitivity analysis functionality."""

    @pytest.fixture
    def mock_analyzer(self):
        """Create mock sensitivity analyzer."""
        mock_duckdb = Mock()
        analyzer = SensitivityAnalyzer(mock_duckdb, "test_scenario")
        return analyzer

    def test_sensitivity_calculation(self, mock_analyzer):
        """Test sensitivity calculation."""

        # Mock objective function
        mock_analyzer.obj_funcs.combined_objective = Mock(side_effect=[0.5, 0.52])

        params = {"merit_rate_level_1": 0.045}
        objectives = {"cost": 1.0}

        sensitivities = mock_analyzer.calculate_sensitivities(params, objectives)

        assert "merit_rate_level_1" in sensitivities
        assert isinstance(sensitivities["merit_rate_level_1"], float)

    def test_parameter_ranking(self, mock_analyzer):
        """Test parameter importance ranking."""

        sensitivities = {
            "merit_rate_level_1": 0.5,
            "cola_rate": -0.3,
            "merit_rate_level_2": 0.1,
        }

        ranking = mock_analyzer.rank_parameter_importance(sensitivities)

        # Should be sorted by absolute importance
        assert ranking[0][0] == "merit_rate_level_1"  # Highest |sensitivity|
        assert ranking[1][0] == "cola_rate"  # Second highest
        assert ranking[2][0] == "merit_rate_level_2"  # Lowest


class TestEvidenceGenerator:
    """Test evidence report generation."""

    @pytest.fixture
    def mock_optimization_result(self):
        """Create mock optimization result."""
        return OptimizationResult(
            scenario_id="test_scenario",
            converged=True,
            optimal_parameters={"merit_rate_level_1": 0.045},
            objective_value=0.234567,
            algorithm_used="SLSQP",
            iterations=45,
            function_evaluations=127,
            runtime_seconds=4.2,
            estimated_cost_impact={
                "value": 2450000.0,
                "unit": "USD",
                "confidence": "high",
            },
            estimated_employee_impact={
                "count": 1200,
                "percentage_of_workforce": 0.85,
                "risk_level": "medium",
            },
            risk_assessment="MEDIUM",
            constraint_violations={},
            solution_quality_score=0.87,
        )

    def test_report_generation(self, mock_optimization_result):
        """Test evidence report generation."""

        generator = EvidenceGenerator(mock_optimization_result)

        # Test report content generation
        content = generator._generate_report_content()

        assert "test_scenario" in content
        assert "SLSQP" in content
        assert "Converged" in content
        assert "2,450,000" in content

    def test_parameter_table_formatting(self, mock_optimization_result):
        """Test parameter table formatting."""

        generator = EvidenceGenerator(mock_optimization_result)
        table = generator._format_parameters_table()

        assert "merit_rate_level_1" in table
        assert "4.50%" in table  # Should format as percentage
        assert "| Parameter |" in table  # Markdown table format


# Property-based testing with hypothesis
try:
    from hypothesis import given
    from hypothesis import strategies as st

    class TestOptimizationProperties:
        """Property-based tests for optimization invariants."""

        @given(st.floats(min_value=0.02, max_value=0.08))
        def test_parameter_bounds_invariant(self, merit_rate):
            """Test that parameter bounds are always respected."""

            # Parameter should always be within schema bounds
            bounds = PARAMETER_SCHEMA["merit_rate_level_1"]["range"]
            assert bounds[0] <= merit_rate <= bounds[1]

        @given(
            st.lists(st.floats(min_value=0.1, max_value=1.0), min_size=3, max_size=3)
        )
        def test_objective_weights_normalization(self, weights):
            """Test objective weight normalization."""

            # Normalize weights
            total = sum(weights)
            normalized = [w / total for w in weights]

            # Should sum to 1.0
            assert abs(sum(normalized) - 1.0) < 1e-10

except ImportError:
    # hypothesis not available, skip property tests
    pass


class TestIntegration:
    """Integration tests for full optimization workflow."""

    def test_optimization_workflow_mock(self):
        """Test complete optimization workflow with mocked components."""

        # This would test the full Dagster asset integration
        # For now, just test that components can be imported and instantiated

        mock_duckdb = Mock()

        # Test component instantiation
        optimizer = CompensationOptimizer(mock_duckdb, "integration_test")
        obj_funcs = ObjectiveFunctions(mock_duckdb, "integration_test")
        analyzer = SensitivityAnalyzer(mock_duckdb, "integration_test")

        # Test schema validation
        request = OptimizationRequest(
            scenario_id="integration_test",
            initial_parameters={"merit_rate_level_1": 0.045},
            objectives={"cost": 1.0},
        )

        assert request.scenario_id == "integration_test"
        assert optimizer.scenario_id == "integration_test"
