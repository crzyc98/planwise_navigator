"""
Tests for S050 Advanced Optimization Features

Comprehensive test suite covering all S050 advanced optimization components:
- Warm-start optimization cache
- Enhanced sensitivity analysis
- Business constraints framework
- A/B testing framework
- Configurable merit distribution
"""

import pytest
import numpy as np
import pandas as pd
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from typing import Dict, List, Any
import time

# Add the orchestrator directory to the path
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'orchestrator'))

from optimization.warm_start_cache import (
    WarmStartOptimizationCache,
    WarmStartCandidate,
    OptimizationHistoryEntry
)
from optimization.enhanced_sensitivity_analysis import (
    EnhancedSensitivityAnalyzer,
    SensitivityResult,
    InteractionEffect,
    SensitivityAnalysisReport
)
from optimization.business_constraints import (
    BusinessConstraintFramework,
    BudgetConstraint,
    EquityConstraint,
    IndividualRaiseConstraint,
    ConstraintEvaluationResult
)
from optimization.ab_testing_framework import (
    OptimizationABTestFramework,
    ABTestConfig,
    ABTestMetric,
    TestVariant,
    ABTestAnalysis
)
from optimization.configurable_merit_distribution import (
    ConfigurableMeritDistributionSystem,
    MeritDistributionConfig,
    DistributionStrategy,
    RiskFactor,
    LinearMeritDistribution
)


class TestWarmStartOptimizationCache:
    """Test suite for warm-start optimization cache."""

    @pytest.fixture
    def mock_duckdb_resource(self):
        """Create mock DuckDB resource."""
        mock = Mock()
        mock_conn = Mock()
        mock_context_manager = Mock()
        mock_context_manager.__enter__.return_value = mock_conn
        mock_context_manager.__exit__.return_value = None
        mock.get_connection.return_value = mock_context_manager
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_conn.execute.return_value.df.return_value = pd.DataFrame()
        return mock

    @pytest.fixture
    def warm_start_cache(self, mock_duckdb_resource):
        """Create warm-start cache instance."""
        return WarmStartOptimizationCache(mock_duckdb_resource)

    def test_record_optimization_result(self, warm_start_cache):
        """Test recording optimization results."""
        run_id = warm_start_cache.record_optimization_result(
            input_parameters={'param1': 0.05, 'param2': 0.03},
            objectives={'cost': 0.5, 'equity': 0.5},
            optimal_parameters={'param1': 0.055, 'param2': 0.032},
            objective_value=0.85,
            converged=True,
            function_evaluations=45,
            runtime_seconds=32.5
        )

        assert isinstance(run_id, str)
        assert len(run_id) > 0

    def test_success_score_calculation(self, warm_start_cache):
        """Test success score calculation logic."""
        # High success case
        high_score = warm_start_cache._calculate_success_score(
            converged=True, objective_value=50, function_evaluations=30, runtime_seconds=15
        )

        # Low success case
        low_score = warm_start_cache._calculate_success_score(
            converged=False, objective_value=200, function_evaluations=150, runtime_seconds=120
        )

        assert high_score > low_score
        assert 0 <= high_score <= 1
        assert 0 <= low_score <= 1

    def test_parameter_normalization(self, warm_start_cache):
        """Test parameter value normalization."""
        # Test known parameter
        normalized = warm_start_cache._normalize_parameter_value('merit_rate_level_1', 0.05)
        assert 0 <= normalized <= 1

        # Test unknown parameter
        normalized_unknown = warm_start_cache._normalize_parameter_value('unknown_param', 0.5)
        assert 0 <= normalized_unknown <= 1

    def test_parameter_similarity_calculation(self, warm_start_cache):
        """Test parameter similarity calculation."""
        params1 = {'param1': 0.05, 'param2': 0.03}
        params2 = {'param1': 0.055, 'param2': 0.032}  # Similar
        params3 = {'param1': 0.08, 'param2': 0.01}   # Different

        similarity_high = warm_start_cache._calculate_parameter_similarity(params1, params2)
        similarity_low = warm_start_cache._calculate_parameter_similarity(params1, params3)

        assert similarity_high > similarity_low
        assert 0 <= similarity_high <= 1
        assert 0 <= similarity_low <= 1

    def test_get_warm_start_candidates_empty_cache(self, warm_start_cache):
        """Test getting warm-start candidates with empty cache."""
        candidates = warm_start_cache.get_warm_start_candidates(
            current_parameters={'param1': 0.05},
            objectives={'cost': 1.0},
            n_candidates=3
        )

        assert isinstance(candidates, list)
        assert len(candidates) == 0  # Empty cache

    def test_cache_statistics(self, warm_start_cache):
        """Test cache statistics generation."""
        stats = warm_start_cache.get_cache_statistics()

        assert isinstance(stats, dict)
        assert 'total_entries' in stats
        assert stats['total_entries'] == 0  # Empty cache


class TestEnhancedSensitivityAnalyzer:
    """Test suite for enhanced sensitivity analysis."""

    @pytest.fixture
    def mock_duckdb_resource(self):
        """Create mock DuckDB resource."""
        mock = Mock()
        mock_conn = Mock()
        mock.get_connection.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchone.return_value = None
        return mock

    @pytest.fixture
    def mock_objective_function(self):
        """Create mock objective function."""
        def objective(params):
            # Simple quadratic function for testing
            return sum(v**2 for v in params.values())
        return objective

    @pytest.fixture
    def parameter_bounds(self):
        """Create parameter bounds."""
        return {
            'param1': (0.01, 0.10),
            'param2': (0.005, 0.05),
            'param3': (1.0, 1.5)
        }

    @pytest.fixture
    def sensitivity_analyzer(self, mock_duckdb_resource, mock_objective_function, parameter_bounds):
        """Create sensitivity analyzer instance."""
        return EnhancedSensitivityAnalyzer(
            duckdb_resource=mock_duckdb_resource,
            objective_function=mock_objective_function,
            parameter_bounds=parameter_bounds,
            step_size=1e-4,
            max_workers=2
        )

    def test_single_gradient_calculation(self, sensitivity_analyzer):
        """Test single parameter gradient calculation."""
        base_parameters = {'param1': 0.05, 'param2': 0.025, 'param3': 1.2}
        objectives = {'test': 1.0}

        sensitivity = sensitivity_analyzer._calculate_single_gradient(
            'param1', base_parameters, objectives, adaptive_step_size=False
        )

        assert isinstance(sensitivity, SensitivityResult)
        assert sensitivity.parameter_name == 'param1'
        assert isinstance(sensitivity.gradient, float)
        assert isinstance(sensitivity.relative_impact, float)
        assert sensitivity.direction in ['increase', 'decrease', 'neutral']

    def test_adaptive_step_size(self, sensitivity_analyzer):
        """Test adaptive step size calculation."""
        step_size = sensitivity_analyzer._adaptive_step_size('param1', 0.05)
        assert step_size > 0
        assert step_size >= 1e-6  # Minimum step size

    def test_parameter_clamping(self, sensitivity_analyzer):
        """Test parameter clamping to bounds."""
        # Test within bounds
        clamped = sensitivity_analyzer._clamp_parameter('param1', 0.05)
        assert clamped == 0.05

        # Test below bounds
        clamped_low = sensitivity_analyzer._clamp_parameter('param1', 0.005)
        assert clamped_low == 0.01

        # Test above bounds
        clamped_high = sensitivity_analyzer._clamp_parameter('param1', 0.15)
        assert clamped_high == 0.10

    def test_objective_evaluation_safety(self, sensitivity_analyzer):
        """Test safe objective function evaluation."""
        parameters = {'param1': 0.05, 'param2': 0.025, 'param3': 1.2}
        objectives = {'test': 1.0}

        result = sensitivity_analyzer._evaluate_objective_safe(parameters, objectives)

        assert isinstance(result, float)
        assert not np.isnan(result)
        assert not np.isinf(result)

    def test_analyze_sensitivity_basic(self, sensitivity_analyzer):
        """Test basic sensitivity analysis."""
        base_parameters = {'param1': 0.05, 'param2': 0.025}
        objectives = {'test': 1.0}

        report = sensitivity_analyzer.analyze_sensitivity(
            base_parameters=base_parameters,
            objectives=objectives,
            include_interactions=False,
            adaptive_step_size=True
        )

        assert isinstance(report, SensitivityAnalysisReport)
        assert len(report.parameter_sensitivities) == 2
        assert len(report.parameter_rankings) == 2
        assert isinstance(report.optimization_recommendations, list)


class TestBusinessConstraintFramework:
    """Test suite for business constraints framework."""

    @pytest.fixture
    def mock_duckdb_resource(self):
        """Create mock DuckDB resource."""
        mock = Mock()
        mock_conn = Mock()
        mock.get_connection.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchone.return_value = None
        return mock

    @pytest.fixture
    def constraint_framework(self, mock_duckdb_resource):
        """Create business constraint framework."""
        return BusinessConstraintFramework(mock_duckdb_resource)

    def test_budget_constraint_evaluation(self):
        """Test budget constraint evaluation."""
        constraint = BudgetConstraint(max_total_budget=1_000_000, budget_buffer_pct=0.05)

        # Test under budget
        parameters = {'merit_rate_level_1': 0.03, 'cola_rate': 0.02}
        context = {'workforce_size': 100, 'avg_salary': 50000}

        result = constraint.evaluate(parameters, context)

        assert isinstance(result, ConstraintEvaluationResult)
        assert result.constraint_name == "budget_constraint"
        assert isinstance(result.passed, bool)
        assert isinstance(result.penalty, float)

    def test_equity_constraint_evaluation(self):
        """Test equity constraint evaluation."""
        constraint = EquityConstraint(max_variance_ratio=0.15, min_level_progression=1.05)

        parameters = {
            'merit_rate_level_1': 0.05,
            'merit_rate_level_2': 0.04,
            'merit_rate_level_3': 0.03
        }
        context = {}

        result = constraint.evaluate(parameters, context)

        assert isinstance(result, ConstraintEvaluationResult)
        assert result.constraint_name == "equity_constraint"

    def test_individual_raise_constraint_evaluation(self):
        """Test individual raise constraint evaluation."""
        constraint = IndividualRaiseConstraint(min_raise_pct=0.01, max_raise_pct=0.25)

        # Test valid parameters
        parameters = {'merit_rate_level_1': 0.05, 'promotion_raise_level_1': 0.15}
        context = {}

        result = constraint.evaluate(parameters, context)

        assert isinstance(result, ConstraintEvaluationResult)
        assert result.constraint_name == "individual_raise_constraint"

    def test_framework_evaluate_all_constraints(self, constraint_framework):
        """Test evaluating all constraints in framework."""
        parameters = {
            'merit_rate_level_1': 0.05,
            'merit_rate_level_2': 0.04,
            'cola_rate': 0.03
        }
        context = {'workforce_size': 1000, 'avg_salary': 75000}

        results = constraint_framework.evaluate_all_constraints(parameters, context)

        assert isinstance(results, dict)
        assert 'summary' in results
        assert 'constraint_results' in results
        assert 'violations' in results
        assert 'recommendations' in results

    def test_constraint_statistics(self, constraint_framework):
        """Test constraint framework statistics."""
        stats = constraint_framework.get_constraint_statistics()

        assert isinstance(stats, dict)
        assert 'overall_stats' in stats
        assert 'registered_constraints' in stats


class TestABTestingFramework:
    """Test suite for A/B testing framework."""

    @pytest.fixture
    def mock_duckdb_resource(self):
        """Create mock DuckDB resource."""
        mock = Mock()
        mock_conn = Mock()
        mock_context_manager = Mock()
        mock_context_manager.__enter__.return_value = mock_conn
        mock_context_manager.__exit__.return_value = None
        mock.get_connection.return_value = mock_context_manager
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_conn.execute.return_value.df.return_value = pd.DataFrame()
        return mock

    @pytest.fixture
    def ab_framework(self, mock_duckdb_resource):
        """Create A/B testing framework."""
        return OptimizationABTestFramework(mock_duckdb_resource)

    @pytest.fixture
    def sample_metrics(self):
        """Create sample success metrics."""
        return [
            ABTestMetric(
                name="retention_rate",
                description="Employee retention rate",
                metric_type="continuous",
                primary=True,
                expected_direction="increase"
            ),
            ABTestMetric(
                name="satisfaction_score",
                description="Employee satisfaction",
                metric_type="continuous",
                primary=False,
                expected_direction="increase"
            )
        ]

    def test_sample_size_calculation(self, ab_framework):
        """Test sample size calculation."""
        sample_size = ab_framework._calculate_sample_size(
            effect_size=0.05,
            alpha=0.05,
            power=0.8
        )

        assert isinstance(sample_size, int)
        assert sample_size > 0
        assert sample_size >= 30  # Minimum practical size

    def test_design_ab_test(self, ab_framework, sample_metrics):
        """Test A/B test design."""
        control_params = {'param1': 0.04, 'param2': 0.02}
        treatment_params = {'param1': 0.045, 'param2': 0.025}

        config = ab_framework.design_ab_test(
            test_name="Test Optimization",
            description="Test optimization effectiveness",
            control_parameters=control_params,
            treatment_parameters=treatment_params,
            success_metrics=sample_metrics
        )

        assert isinstance(config, ABTestConfig)
        assert config.test_name == "Test Optimization"
        assert config.control_parameters == control_params
        assert config.treatment_parameters == treatment_params
        assert len(config.success_metrics) == 2

    def test_record_observation(self, ab_framework):
        """Test recording test observations."""
        # Setup a test first
        with patch.object(ab_framework, '_store_test_config'):
            config = ABTestConfig(
                test_id="test_123",
                test_name="Test",
                description="Test",
                control_parameters={},
                treatment_parameters={},
                success_metrics=[],
                sample_size_per_group=100,
                test_duration_days=30
            )

        observation_id = ab_framework.record_observation(
            test_id="test_123",
            variant=TestVariant.CONTROL,
            entity_id="entity_1",
            metrics={'retention_rate': 0.85, 'satisfaction_score': 4.2}
        )

        assert isinstance(observation_id, str)
        assert len(observation_id) > 0

    def test_continuous_metric_test(self, ab_framework):
        """Test statistical test for continuous metrics."""
        control_data = np.array([0.8, 0.82, 0.79, 0.85, 0.81])
        treatment_data = np.array([0.85, 0.87, 0.84, 0.90, 0.86])

        test_stat, p_value = ab_framework._continuous_metric_test(control_data, treatment_data)

        assert isinstance(test_stat, float)
        assert isinstance(p_value, float)
        assert 0 <= p_value <= 1

    def test_effect_size_confidence_interval(self, ab_framework):
        """Test effect size confidence interval calculation."""
        control_data = np.array([100, 105, 98, 102, 99])
        treatment_data = np.array([108, 112, 105, 110, 107])

        ci_lower, ci_upper = ab_framework._calculate_effect_size_ci(
            control_data, treatment_data, alpha=0.05
        )

        assert isinstance(ci_lower, float)
        assert isinstance(ci_upper, float)
        assert ci_lower <= ci_upper


class TestConfigurableMeritDistribution:
    """Test suite for configurable merit distribution."""

    @pytest.fixture
    def mock_duckdb_resource(self):
        """Create mock DuckDB resource."""
        mock = Mock()
        mock_conn = Mock()
        mock.get_connection.return_value.__enter__.return_value = mock_conn
        mock_conn.execute.return_value.fetchone.return_value = None
        return mock

    @pytest.fixture
    def merit_system(self, mock_duckdb_resource):
        """Create merit distribution system."""
        return ConfigurableMeritDistributionSystem(mock_duckdb_resource)

    def test_linear_merit_distribution(self):
        """Test linear merit distribution strategy."""
        config = MeritDistributionConfig(
            strategy=DistributionStrategy.LINEAR,
            base_merit_rate=0.04,
            level_count=5,
            parameters={'slope': 0.1}
        )

        strategy = LinearMeritDistribution(config)
        rates = strategy.calculate_distribution()

        assert len(rates) == 5
        assert all(isinstance(rate, float) for rate in rates)
        assert rates[0] == 0.04  # Base rate for level 1
        assert rates[1] > rates[0]  # Increasing progression

    def test_merit_distribution_validation(self):
        """Test merit distribution validation."""
        config = MeritDistributionConfig(
            strategy=DistributionStrategy.LINEAR,
            base_merit_rate=0.04,
            constraints={'min_rate': 0.02, 'max_rate': 0.08}
        )

        strategy = LinearMeritDistribution(config)

        # Valid rates
        valid_rates = [0.03, 0.04, 0.05, 0.06, 0.07]
        violations = strategy.validate_distribution(valid_rates)
        assert len(violations) == 0

        # Invalid rates
        invalid_rates = [0.01, 0.04, 0.05, 0.06, 0.09]  # One too low, one too high
        violations = strategy.validate_distribution(invalid_rates)
        assert len(violations) > 0

    def test_risk_adjusted_distribution(self, merit_system):
        """Test risk-adjusted merit distribution."""
        config = MeritDistributionConfig(
            strategy=DistributionStrategy.RISK_ADJUSTED,
            base_merit_rate=0.04,
            level_count=5,
            risk_adjustments={
                RiskFactor.FLIGHT_RISK: 0.1,
                RiskFactor.MARKET_PRESSURE: 0.15
            }
        )

        context = {
            'flight_risk_by_level': {'1': 0.05, '2': 0.08, '3': 0.12},
            'market_pressure_by_level': {'1': 0.05, '2': 0.10, '3': 0.15}
        }

        result = merit_system.calculate_merit_distribution(config, context)

        assert len(result.level_results) == 5
        assert result.strategy_used == DistributionStrategy.RISK_ADJUSTED
        assert isinstance(result.total_cost_impact, float)

    def test_strategy_comparison(self, merit_system):
        """Test comparing multiple distribution strategies."""
        comparison = merit_system.get_strategy_comparison(
            base_merit_rate=0.04,
            strategies=[DistributionStrategy.LINEAR, DistributionStrategy.FLAT],
            context={'workforce_size': 1000, 'avg_salary': 75000}
        )

        assert len(comparison) == 2
        assert 'linear' in comparison
        assert 'flat' in comparison

        for strategy_name, result in comparison.items():
            assert len(result.level_results) > 0
            assert isinstance(result.total_cost_impact, float)

    def test_distribution_statistics_calculation(self, merit_system):
        """Test distribution statistics calculation."""
        rates = [0.03, 0.04, 0.05, 0.06, 0.07]
        stats = merit_system._calculate_distribution_statistics(rates)

        assert 'mean' in stats
        assert 'std_dev' in stats
        assert 'coefficient_of_variation' in stats
        assert 'progression_slope' in stats

        assert stats['mean'] == 0.05
        assert stats['min'] == 0.03
        assert stats['max'] == 0.07

    def test_cost_impact_calculation(self, merit_system):
        """Test cost impact calculation."""
        from optimization.configurable_merit_distribution import LevelMeritResult

        level_results = [
            LevelMeritResult(
                level_id=1,
                base_merit_rate=0.04,
                risk_adjusted_rate=0.042,
                final_merit_rate=0.042,
                adjustment_factors={},
                constraint_violations=[]
            ),
            LevelMeritResult(
                level_id=2,
                base_merit_rate=0.045,
                risk_adjusted_rate=0.047,
                final_merit_rate=0.047,
                adjustment_factors={},
                constraint_violations=[]
            )
        ]

        context = {
            'workforce_size': 1000,
            'avg_salary': 75000,
            'level_distribution': [0.5, 0.5]
        }

        cost_impact = merit_system._calculate_cost_impact(level_results, context)

        assert isinstance(cost_impact, float)
        assert cost_impact > 0


class TestS050Integration:
    """Integration tests for S050 features working together."""

    @pytest.fixture
    def mock_duckdb_resource(self):
        """Create mock DuckDB resource."""
        mock = Mock()
        mock_conn = Mock()
        mock_context_manager = Mock()
        mock_context_manager.__enter__.return_value = mock_conn
        mock_context_manager.__exit__.return_value = None
        mock.get_connection.return_value = mock_context_manager
        mock_conn.execute.return_value.fetchone.return_value = None
        mock_conn.execute.return_value.df.return_value = pd.DataFrame()
        return mock

    def test_end_to_end_optimization_workflow(self, mock_duckdb_resource):
        """Test complete S050 optimization workflow."""
        # Initialize all components
        warm_start_cache = WarmStartOptimizationCache(mock_duckdb_resource)
        constraint_framework = BusinessConstraintFramework(mock_duckdb_resource)
        merit_system = ConfigurableMeritDistributionSystem(mock_duckdb_resource)
        ab_framework = OptimizationABTestFramework(mock_duckdb_resource)

        # Test parameters
        base_parameters = {
            'merit_rate_level_1': 0.045,
            'merit_rate_level_2': 0.040,
            'cola_rate': 0.025
        }

        # 1. Check constraints
        constraint_result = constraint_framework.evaluate_all_constraints(
            base_parameters,
            {'workforce_size': 1000, 'avg_salary': 75000}
        )

        assert 'summary' in constraint_result

        # 2. Calculate merit distribution
        merit_config = MeritDistributionConfig(
            strategy=DistributionStrategy.LINEAR,
            base_merit_rate=0.04,
            level_count=3
        )

        merit_result = merit_system.calculate_merit_distribution(merit_config)

        assert len(merit_result.level_results) == 3

        # 3. Record in warm-start cache
        run_id = warm_start_cache.record_optimization_result(
            input_parameters=base_parameters,
            objectives={'cost': 0.5, 'equity': 0.5},
            optimal_parameters=base_parameters,
            objective_value=0.8,
            converged=True,
            function_evaluations=50,
            runtime_seconds=30
        )

        assert isinstance(run_id, str)

        # 4. Design A/B test
        ab_config = ab_framework.design_ab_test(
            test_name="Integration Test",
            description="Test S050 integration",
            control_parameters=base_parameters,
            treatment_parameters=base_parameters,  # Same for testing
            success_metrics=[
                ABTestMetric(
                    name="test_metric",
                    description="Test metric",
                    metric_type="continuous",
                    primary=True
                )
            ]
        )

        assert isinstance(ab_config, ABTestConfig)

    def test_performance_benchmark(self, mock_duckdb_resource):
        """Test S050 performance characteristics."""
        # Test warm-start cache performance
        cache = WarmStartOptimizationCache(mock_duckdb_resource)

        start_time = time.time()

        # Simulate multiple optimization recordings
        for i in range(10):
            cache.record_optimization_result(
                input_parameters={'param1': 0.04 + i*0.001},
                objectives={'cost': 1.0},
                optimal_parameters={'param1': 0.045 + i*0.001},
                objective_value=0.8 + i*0.01,
                converged=True,
                function_evaluations=50,
                runtime_seconds=30
            )

        cache_time = time.time() - start_time

        # Should be fast
        assert cache_time < 5.0  # 5 seconds max for 10 operations

        # Test sensitivity analysis performance
        def simple_objective(params):
            return sum(v**2 for v in params.values())

        analyzer = EnhancedSensitivityAnalyzer(
            duckdb_resource=mock_duckdb_resource,
            objective_function=simple_objective,
            parameter_bounds={'param1': (0.01, 0.1), 'param2': (0.01, 0.1)},
            max_workers=2
        )

        start_time = time.time()

        report = analyzer.analyze_sensitivity(
            base_parameters={'param1': 0.05, 'param2': 0.03},
            objectives={'test': 1.0},
            include_interactions=False
        )

        sensitivity_time = time.time() - start_time

        # Should complete reasonably quickly
        assert sensitivity_time < 10.0  # 10 seconds max
        assert len(report.parameter_sensitivities) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
