"""
Tests for Thread-Safe Optimization Engine (S049)

Comprehensive test suite covering thread safety, numerical stability,
and performance characteristics of the robust optimization engine.
"""

import pytest
import threading
import time
import math
import numpy as np
from unittest.mock import Mock, patch
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List

# Add the orchestrator directory to the path
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'orchestrator'))

from optimization.thread_safe_objective_functions import (
    ThreadSafeObjectiveFunctions,
    ThreadSafeParameterCache,
    ThreadSafeAdaptivePenalty,
    RobustNumericalCalculations,
    OptimizationResult
)
from optimization.thread_safe_optimization_engine import (
    ThreadSafeOptimizationEngine,
    OptimizationRequest,
    OptimizationResponse,
    ConcurrentOptimizationResults
)


class TestRobustNumericalCalculations:
    """Test suite for robust numerical calculations."""

    def test_safe_growth_rate_normal_cases(self):
        """Test safe growth rate calculation for normal cases."""
        calc = RobustNumericalCalculations()

        # Normal positive growth
        assert calc.safe_growth_rate(110, 100) == 10.0

        # Normal negative growth
        assert calc.safe_growth_rate(90, 100) == -10.0

        # No growth
        assert calc.safe_growth_rate(100, 100) == 0.0

    def test_safe_growth_rate_division_by_zero_protection(self):
        """Test division-by-zero protection in growth rate calculation."""
        calc = RobustNumericalCalculations()

        # Zero baseline, zero current (should return 0)
        assert calc.safe_growth_rate(0, 0) == 0.0

        # Zero baseline, positive current (should return capped growth)
        result = calc.safe_growth_rate(100, 0)
        assert result > 0
        assert result <= 50.0  # Max growth cap

        # Zero baseline, negative current (should return capped negative growth)
        result = calc.safe_growth_rate(-100, 0)
        assert result < 0
        assert result >= -50.0  # Min growth cap

    def test_safe_growth_rate_nan_inf_handling(self):
        """Test NaN and infinity handling in growth rate calculation."""
        calc = RobustNumericalCalculations()

        # NaN inputs
        assert calc.safe_growth_rate(float('nan'), 100) == 0.0
        assert calc.safe_growth_rate(100, float('nan')) == 0.0

        # Infinity inputs should be capped
        result = calc.safe_growth_rate(float('inf'), 100)
        assert result <= 50.0

        result = calc.safe_growth_rate(100, float('inf'))
        assert not math.isinf(result)

    def test_safe_coefficient_of_variation(self):
        """Test coefficient of variation with protection."""
        calc = RobustNumericalCalculations()

        # Normal case
        cv = calc.safe_coefficient_of_variation(100, 10)
        assert cv == 0.1

        # Zero mean protection
        assert calc.safe_coefficient_of_variation(0, 10) == 0.0

        # NaN protection
        assert calc.safe_coefficient_of_variation(float('nan'), 10) == 0.0
        assert calc.safe_coefficient_of_variation(100, float('nan')) == 0.0

        # High variation capping
        cv = calc.safe_coefficient_of_variation(1, 100)
        assert cv <= 10.0  # Should be capped

    def test_safe_normalize(self):
        """Test safe normalization with range protection."""
        calc = RobustNumericalCalculations()

        # Normal normalization
        assert calc.safe_normalize(5, 0, 10) == 0.5
        assert calc.safe_normalize(0, 0, 10) == 0.0
        assert calc.safe_normalize(10, 0, 10) == 1.0

        # Equal min/max (no range)
        assert calc.safe_normalize(5, 10, 10) == 0.5

        # Out of bounds clamping
        assert calc.safe_normalize(-5, 0, 10) == 0.0
        assert calc.safe_normalize(15, 0, 10) == 1.0


class TestThreadSafeParameterCache:
    """Test suite for thread-safe parameter caching."""

    def test_canonical_key_generation(self):
        """Test canonical key generation for parameters."""
        cache = ThreadSafeParameterCache()

        # Same parameters should generate same key
        params1 = {'a': 1.0, 'b': 2.0}
        params2 = {'b': 2.0, 'a': 1.0}  # Different order

        key1 = cache.get_canonical_key(params1)
        key2 = cache.get_canonical_key(params2)

        assert key1 == key2
        assert isinstance(key1, str)
        assert len(key1) > 0

    def test_cache_hit_miss_behavior(self):
        """Test cache hit and miss behavior."""
        cache = ThreadSafeParameterCache()

        def mock_compute(params, obj_type):
            return sum(params.values()) * 100

        params = {'a': 1.0, 'b': 2.0}

        # First call should be a miss
        result1 = cache.get_or_compute(params, 'test', mock_compute)
        assert not result1.cache_hit
        assert result1.objective_value == 300.0

        # Second call should be a hit
        result2 = cache.get_or_compute(params, 'test', mock_compute)
        assert result2.cache_hit
        assert result2.objective_value == 300.0

    def test_concurrent_cache_access(self):
        """Test concurrent access to cache."""
        cache = ThreadSafeParameterCache()
        call_count = 0

        def mock_compute(params, obj_type):
            nonlocal call_count
            call_count += 1
            time.sleep(0.1)  # Simulate computation time
            return sum(params.values())

        params = {'a': 1.0, 'b': 2.0}

        # Launch multiple threads accessing same parameters
        def access_cache():
            return cache.get_or_compute(params, 'test', mock_compute)

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(access_cache) for _ in range(10)]
            results = [f.result() for f in futures]

        # All results should be the same
        values = [r.objective_value for r in results]
        assert all(v == values[0] for v in values)

        # Compute function should be called only once (or very few times due to racing)
        assert call_count <= 3  # Allow for some racing, but not 10 calls

    def test_cache_eviction(self):
        """Test cache eviction when max size is reached."""
        cache = ThreadSafeParameterCache(max_size=3)

        def mock_compute(params, obj_type):
            return sum(params.values())

        # Fill cache beyond capacity
        for i in range(5):
            params = {'param': float(i)}
            cache.get_or_compute(params, 'test', mock_compute)

        # Cache should not exceed max size
        assert len(cache._cache) <= 3


class TestThreadSafeAdaptivePenalty:
    """Test suite for thread-safe adaptive penalty calculation."""

    def test_penalty_calculation_empty_history(self):
        """Test penalty calculation with empty history."""
        penalty_calc = ThreadSafeAdaptivePenalty(initial_penalty=1000.0)

        penalty = penalty_calc.calculate_penalty(1, [])
        assert penalty == 1000.0

    def test_penalty_calculation_with_history(self):
        """Test penalty calculation with error history."""
        penalty_calc = ThreadSafeAdaptivePenalty()

        # Small errors should result in lower penalties
        small_errors = [10.0, 12.0, 11.0, 9.0, 13.0]
        penalty1 = penalty_calc.calculate_penalty(1, small_errors)

        # Large errors should result in higher penalties
        large_errors = [1000.0, 1200.0, 1100.0, 900.0, 1300.0]
        penalty2 = penalty_calc.calculate_penalty(2, large_errors)

        assert penalty2 > penalty1

    def test_thread_isolation(self):
        """Test that penalty histories are isolated by thread."""
        penalty_calc = ThreadSafeAdaptivePenalty()

        # Different threads should have independent histories
        penalty1 = penalty_calc.calculate_penalty(1, [100.0])
        penalty2 = penalty_calc.calculate_penalty(2, [1000.0])

        # Next calculations should use thread-specific history
        penalty1_next = penalty_calc.calculate_penalty(1, [110.0])
        penalty2_next = penalty_calc.calculate_penalty(2, [1100.0])

        # Thread 1 should have lower penalties due to lower error history
        assert penalty1_next < penalty2_next

    def test_penalty_bounds(self):
        """Test that penalties are within reasonable bounds."""
        penalty_calc = ThreadSafeAdaptivePenalty()

        # Very small errors
        tiny_errors = [0.001, 0.002, 0.001]
        penalty_tiny = penalty_calc.calculate_penalty(1, tiny_errors)

        # Very large errors
        huge_errors = [1e6, 2e6, 1.5e6]
        penalty_huge = penalty_calc.calculate_penalty(2, huge_errors)

        # Penalties should be bounded
        assert 10.0 <= penalty_tiny <= 10000.0
        assert 10.0 <= penalty_huge <= 10000.0


class TestThreadSafeObjectiveFunctions:
    """Test suite for thread-safe objective functions."""

    @pytest.fixture
    def mock_duckdb_resource(self):
        """Create mock DuckDB resource."""
        mock = Mock()
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [1000, 75000.0, 15000.0]
        mock.get_connection.return_value.__enter__.return_value = mock_conn
        return mock

    @pytest.fixture
    def objective_functions(self, mock_duckdb_resource):
        """Create thread-safe objective functions instance."""
        return ThreadSafeObjectiveFunctions(mock_duckdb_resource, 'test_scenario', use_synthetic=True)

    def test_cost_objective_thread_safety(self, objective_functions):
        """Test cost objective function thread safety."""
        params = {'merit_rate_level_1': 0.05, 'cola_rate': 0.02}

        def call_cost_objective():
            return objective_functions.cost_objective(params)

        # Run multiple threads calling the same objective
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(call_cost_objective) for _ in range(10)]
            results = [f.result() for f in futures]

        # All results should be consistent
        assert all(isinstance(r, float) for r in results)
        assert all(r == results[0] for r in results)

    def test_equity_objective_thread_safety(self, objective_functions):
        """Test equity objective function thread safety."""
        params = {'merit_rate_level_1': 0.05, 'merit_rate_level_2': 0.04}

        def call_equity_objective():
            return objective_functions.equity_objective(params)

        # Run multiple threads calling the same objective
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(call_equity_objective) for _ in range(10)]
            results = [f.result() for f in futures]

        # All results should be consistent
        assert all(isinstance(r, float) for r in results)
        assert all(r == results[0] for r in results)

    def test_targets_objective_thread_safety(self, objective_functions):
        """Test targets objective function thread safety."""
        params = {'merit_rate_level_1': 0.05, 'new_hire_salary_adjustment': 1.15}

        def call_targets_objective():
            return objective_functions.targets_objective(params)

        # Run multiple threads calling the same objective
        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(call_targets_objective) for _ in range(10)]
            results = [f.result() for f in futures]

        # All results should be consistent
        assert all(isinstance(r, float) for r in results)
        assert all(r == results[0] for r in results)

    def test_cache_performance(self, objective_functions):
        """Test cache performance statistics."""
        params = {'merit_rate_level_1': 0.05}

        # Make several calls to populate cache
        for _ in range(5):
            objective_functions.cost_objective(params)

        stats = objective_functions.get_cache_stats()

        assert 'cache_size' in stats
        assert 'total_accesses' in stats
        assert 'unique_computations' in stats
        assert stats['total_accesses'] >= 5


class TestThreadSafeOptimizationEngine:
    """Test suite for thread-safe optimization engine."""

    @pytest.fixture
    def mock_duckdb_resource(self):
        """Create mock DuckDB resource."""
        mock = Mock()
        mock_conn = Mock()
        mock_conn.execute.return_value.fetchone.return_value = [1000, 75000.0, 15000.0]
        mock.get_connection.return_value.__enter__.return_value = mock_conn
        return mock

    @pytest.fixture
    def optimization_engine(self, mock_duckdb_resource):
        """Create thread-safe optimization engine."""
        return ThreadSafeOptimizationEngine(mock_duckdb_resource, max_concurrent=4)

    @pytest.fixture
    def sample_request(self):
        """Create sample optimization request."""
        return OptimizationRequest(
            scenario_id='test_scenario',
            initial_params={'merit_rate_level_1': 0.04, 'cola_rate': 0.02},
            param_names=['merit_rate_level_1', 'cola_rate'],
            param_bounds=[(0.01, 0.10), (0.005, 0.05)],
            objectives={'cost': 0.5, 'equity': 0.3, 'targets': 0.2},
            method='SLSQP',
            max_evaluations=50,
            use_synthetic=True
        )

    def test_single_optimization(self, optimization_engine, sample_request):
        """Test single optimization run."""
        result = optimization_engine.optimize_single(sample_request)

        assert isinstance(result, OptimizationResponse)
        assert result.scenario_id == 'test_scenario'
        assert isinstance(result.success, bool)
        assert isinstance(result.optimal_params, dict)
        assert isinstance(result.objective_value, float)
        assert result.thread_id > 0

    def test_concurrent_optimization(self, optimization_engine, sample_request):
        """Test concurrent optimization runs."""
        # Create multiple requests with different scenario IDs
        requests = []
        for i in range(5):
            request = OptimizationRequest(
                scenario_id=f'scenario_{i}',
                initial_params=sample_request.initial_params,
                param_names=sample_request.param_names,
                param_bounds=sample_request.param_bounds,
                objectives=sample_request.objectives,
                method=sample_request.method,
                max_evaluations=20,  # Shorter for faster testing
                use_synthetic=True
            )
            requests.append(request)

        result = optimization_engine.optimize_concurrent(requests)

        assert isinstance(result, ConcurrentOptimizationResults)
        assert result.total_optimizations == 5
        assert len(result.results) == 5
        assert result.successful_optimizations >= 0
        assert result.failed_optimizations >= 0
        assert result.successful_optimizations + result.failed_optimizations == 5

    def test_parameter_bounds_validation(self, optimization_engine):
        """Test parameter bounds validation."""
        # Test with out-of-bounds initial parameters
        out_of_bounds_request = OptimizationRequest(
            scenario_id='bounds_test',
            initial_params={'merit_rate_level_1': 0.20, 'cola_rate': 0.10},  # Above bounds
            param_names=['merit_rate_level_1', 'cola_rate'],
            param_bounds=[(0.01, 0.10), (0.005, 0.05)],
            objectives={'cost': 1.0},
            max_evaluations=10,
            use_synthetic=True
        )

        result = optimization_engine.optimize_single(out_of_bounds_request)

        # Should still complete (with clamped parameters)
        assert isinstance(result, OptimizationResponse)

        # Optimal parameters should be within bounds
        for i, (param_name, value) in enumerate(result.optimal_params.items()):
            lower, upper = out_of_bounds_request.param_bounds[i]
            assert lower <= value <= upper

    def test_thread_isolation(self, optimization_engine, sample_request):
        """Test that optimization runs are properly isolated."""
        # Run optimizations with different objectives concurrently
        requests = [
            OptimizationRequest(
                scenario_id='cost_focused',
                initial_params=sample_request.initial_params,
                param_names=sample_request.param_names,
                param_bounds=sample_request.param_bounds,
                objectives={'cost': 1.0},  # Cost-only objective
                max_evaluations=20,
                use_synthetic=True
            ),
            OptimizationRequest(
                scenario_id='equity_focused',
                initial_params=sample_request.initial_params,
                param_names=sample_request.param_names,
                param_bounds=sample_request.param_bounds,
                objectives={'equity': 1.0},  # Equity-only objective
                max_evaluations=20,
                use_synthetic=True
            )
        ]

        result = optimization_engine.optimize_concurrent(requests)

        # Results should be different due to different objectives
        cost_result = next(r for r in result.results if r.scenario_id == 'cost_focused')
        equity_result = next(r for r in result.results if r.scenario_id == 'equity_focused')

        # Should have different thread IDs (if run concurrently)
        assert cost_result.thread_id != equity_result.thread_id

        # Results should be valid
        assert isinstance(cost_result.objective_value, float)
        assert isinstance(equity_result.objective_value, float)

    def test_performance_metrics(self, optimization_engine, sample_request):
        """Test performance metrics tracking."""
        # Run some optimizations
        optimization_engine.optimize_single(sample_request)

        # Check performance metrics
        metrics = optimization_engine.get_performance_metrics()

        assert 'total_optimizations' in metrics
        assert 'successful_optimizations' in metrics
        assert 'failed_optimizations' in metrics
        assert 'total_execution_time' in metrics
        assert metrics['total_optimizations'] >= 1

    def test_error_handling(self, optimization_engine):
        """Test error handling in optimization."""
        # Create request with invalid configuration
        invalid_request = OptimizationRequest(
            scenario_id='invalid_test',
            initial_params={'invalid_param': 0.05},
            param_names=['invalid_param'],
            param_bounds=[(0.01, 0.10)],
            objectives={'invalid_objective': 1.0},  # Invalid objective
            max_evaluations=10,
            use_synthetic=True
        )

        result = optimization_engine.optimize_single(invalid_request)

        # Should handle error gracefully
        assert isinstance(result, OptimizationResponse)
        assert not result.success or result.error is not None


# Property-based tests using hypothesis (if available)
try:
    from hypothesis import given, strategies as st
    import hypothesis

    class TestPropertyBasedOptimization:
        """Property-based tests for optimization robustness."""

        @given(
            baseline=st.floats(min_value=0, max_value=1e6),
            current=st.floats(min_value=0, max_value=1e6)
        )
        def test_growth_rate_properties(self, baseline, current):
            """Test growth rate calculation properties."""
            calc = RobustNumericalCalculations()
            growth = calc.safe_growth_rate(current, baseline)

            # Growth should never be NaN or infinite
            assert not math.isnan(growth)
            assert not math.isinf(growth)

            # Growth should be bounded
            assert -50.0 <= growth <= 50.0

        @given(
            params=st.dictionaries(
                st.text(min_size=1, max_size=20),
                st.floats(min_value=0.001, max_value=1.0),
                min_size=1, max_size=10
            )
        )
        def test_cache_key_consistency(self, params):
            """Test that cache keys are consistent."""
            cache = ThreadSafeParameterCache()

            # Same parameters should always generate same key
            key1 = cache.get_canonical_key(params)
            key2 = cache.get_canonical_key(params)

            assert key1 == key2
            assert isinstance(key1, str)
            assert len(key1) > 0

except ImportError:
    # Hypothesis not available, skip property-based tests
    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
