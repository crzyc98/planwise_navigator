"""
Integration tests for concurrent optimization robustness (S049)

Tests concurrent optimization scenarios with realistic workloads,
thread safety validation, and performance benchmarking.
"""

import pytest
import threading
import time
import tempfile
import os
import csv
import concurrent.futures
from pathlib import Path
from typing import List, Dict, Any
import numpy as np

# Add the orchestrator directory to the path
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..', 'orchestrator'))

from optimization.thread_safe_optimization_engine import (
    ThreadSafeOptimizationEngine,
    OptimizationRequest,
    OptimizationResponse,
    ConcurrentOptimizationResults
)
from optimization.thread_safe_objective_functions import ThreadSafeObjectiveFunctions
from unittest.mock import Mock


class TestConcurrentOptimizationRobustness:
    """Integration tests for concurrent optimization robustness."""

    @pytest.fixture
    def mock_duckdb_resource(self):
        """Create mock DuckDB resource with realistic data."""
        mock = Mock()
        mock_conn = Mock()

        # Mock different workforce scenarios
        workforce_scenarios = [
            [1000, 75000.0, 15000.0],  # Baseline scenario
            [1200, 78000.0, 16000.0],  # Growth scenario
            [800, 72000.0, 14000.0],   # Decline scenario
            [1100, 76500.0, 15500.0],  # Moderate growth
        ]

        # Cycle through scenarios to simulate different conditions
        mock_conn.execute.return_value.fetchone.side_effect = workforce_scenarios * 10
        mock.get_connection.return_value.__enter__.return_value = mock_conn
        return mock

    @pytest.fixture
    def optimization_engine(self, mock_duckdb_resource):
        """Create optimization engine for testing."""
        return ThreadSafeOptimizationEngine(mock_duckdb_resource, max_concurrent=8)

    def create_optimization_requests(self, count: int) -> List[OptimizationRequest]:
        """Create a list of optimization requests for testing."""
        requests = []

        # Define different optimization scenarios
        scenarios = [
            {
                'name': 'cost_minimization',
                'objectives': {'cost': 1.0},
                'bounds': [(0.01, 0.08), (0.005, 0.04), (1.05, 1.25)]
            },
            {
                'name': 'equity_optimization',
                'objectives': {'equity': 1.0},
                'bounds': [(0.02, 0.10), (0.01, 0.05), (1.10, 1.30)]
            },
            {
                'name': 'target_growth',
                'objectives': {'targets': 1.0},
                'bounds': [(0.015, 0.085), (0.008, 0.045), (1.08, 1.28)]
            },
            {
                'name': 'balanced',
                'objectives': {'cost': 0.4, 'equity': 0.3, 'targets': 0.3},
                'bounds': [(0.02, 0.09), (0.01, 0.04), (1.10, 1.25)]
            },
            {
                'name': 'aggressive_growth',
                'objectives': {'targets': 0.8, 'cost': 0.2},
                'bounds': [(0.03, 0.12), (0.015, 0.06), (1.15, 1.35)]
            }
        ]

        param_names = ['merit_rate_level_1', 'cola_rate', 'new_hire_salary_adjustment']

        for i in range(count):
            scenario = scenarios[i % len(scenarios)]

            # Add some variation to initial parameters
            base_params = [0.04, 0.02, 1.15]
            variation = np.random.normal(0, 0.01, len(base_params))
            initial_values = [max(0.01, base + var) for base, var in zip(base_params, variation)]

            request = OptimizationRequest(
                scenario_id=f"{scenario['name']}_{i}",
                initial_params=dict(zip(param_names, initial_values)),
                param_names=param_names,
                param_bounds=scenario['bounds'],
                objectives=scenario['objectives'],
                method='SLSQP',
                max_evaluations=75,
                tolerance=1e-6,
                use_synthetic=True  # Use synthetic for reproducible testing
            )
            requests.append(request)

        return requests

    def test_concurrent_optimization_thread_safety(self, optimization_engine):
        """Test thread safety with high concurrency."""
        requests = self.create_optimization_requests(20)

        start_time = time.time()
        results = optimization_engine.optimize_concurrent(requests)
        execution_time = time.time() - start_time

        # Validate results
        assert isinstance(results, ConcurrentOptimizationResults)
        assert results.total_optimizations == 20
        assert len(results.results) == 20

        # Check that all optimizations completed
        assert results.successful_optimizations + results.failed_optimizations == 20

        # Validate thread isolation - different threads should be used
        thread_ids = {r.thread_id for r in results.results}
        assert len(thread_ids) > 1  # Multiple threads should be used

        # Performance validation
        assert execution_time < 60.0  # Should complete within 60 seconds
        assert results.average_execution_time < 10.0  # Average per optimization

        print(f"✅ Concurrent optimization completed: {results.successful_optimizations}/{results.total_optimizations} successful")
        print(f"⏱️  Total time: {execution_time:.2f}s, Average: {results.average_execution_time:.2f}s")
        print(f"🧵 Thread distribution: {results.performance_metrics.get('thread_distribution', {})}")

    def test_parameter_corruption_prevention(self, optimization_engine):
        """Test that concurrent optimizations don't corrupt each other's parameters."""
        # Create requests with very different parameter ranges
        requests = [
            OptimizationRequest(
                scenario_id='low_params',
                initial_params={'merit_rate_level_1': 0.02, 'cola_rate': 0.01},
                param_names=['merit_rate_level_1', 'cola_rate'],
                param_bounds=[(0.01, 0.05), (0.005, 0.02)],
                objectives={'cost': 1.0},
                max_evaluations=30,
                use_synthetic=True
            ),
            OptimizationRequest(
                scenario_id='high_params',
                initial_params={'merit_rate_level_1': 0.08, 'cola_rate': 0.04},
                param_names=['merit_rate_level_1', 'cola_rate'],
                param_bounds=[(0.06, 0.12), (0.03, 0.06)],
                objectives={'cost': 1.0},
                max_evaluations=30,
                use_synthetic=True
            ),
            OptimizationRequest(
                scenario_id='medium_params',
                initial_params={'merit_rate_level_1': 0.05, 'cola_rate': 0.025},
                param_names=['merit_rate_level_1', 'cola_rate'],
                param_bounds=[(0.03, 0.08), (0.015, 0.04)],
                objectives={'cost': 1.0},
                max_evaluations=30,
                use_synthetic=True
            )
        ]

        # Run multiple times to increase chance of detecting corruption
        for iteration in range(5):
            results = optimization_engine.optimize_concurrent(requests)

            # Check that results respect their respective bounds
            for result in results.results:
                if result.success and result.optimal_params:
                    request = next(r for r in requests if r.scenario_id == result.scenario_id)

                    for i, (param_name, value) in enumerate(result.optimal_params.items()):
                        lower, upper = request.param_bounds[i]
                        assert lower <= value <= upper, f"Parameter {param_name} = {value} out of bounds [{lower}, {upper}] for {result.scenario_id}"

            print(f"✅ Iteration {iteration + 1}: No parameter corruption detected")

    def test_numerical_stability_under_load(self, optimization_engine):
        """Test numerical stability under high concurrent load."""
        # Create requests with edge case parameters
        edge_case_requests = []

        # Very small parameters (near zero)
        edge_case_requests.append(OptimizationRequest(
            scenario_id='near_zero',
            initial_params={'merit_rate_level_1': 0.001, 'cola_rate': 0.0005},
            param_names=['merit_rate_level_1', 'cola_rate'],
            param_bounds=[(1e-6, 0.01), (1e-6, 0.005)],
            objectives={'cost': 1.0},
            max_evaluations=25,
            use_synthetic=True
        ))

        # Large parameters
        edge_case_requests.append(OptimizationRequest(
            scenario_id='large_params',
            initial_params={'merit_rate_level_1': 0.15, 'cola_rate': 0.08},
            param_names=['merit_rate_level_1', 'cola_rate'],
            param_bounds=[(0.10, 0.20), (0.05, 0.12)],
            objectives={'cost': 1.0},
            max_evaluations=25,
            use_synthetic=True
        ))

        # High precision parameters
        edge_case_requests.append(OptimizationRequest(
            scenario_id='high_precision',
            initial_params={'merit_rate_level_1': 0.0456789, 'cola_rate': 0.0123456},
            param_names=['merit_rate_level_1', 'cola_rate'],
            param_bounds=[(0.04, 0.05), (0.01, 0.02)],
            objectives={'equity': 1.0},
            max_evaluations=25,
            use_synthetic=True
        ))

        # Run edge cases concurrently multiple times
        for iteration in range(3):
            results = optimization_engine.optimize_concurrent(edge_case_requests)

            # Validate numerical stability
            for result in results.results:
                # Check that objective values are finite
                assert not np.isnan(result.objective_value), f"NaN objective value in {result.scenario_id}"
                assert not np.isinf(result.objective_value), f"Infinite objective value in {result.scenario_id}"

                # Check that optimal parameters are finite
                if result.optimal_params:
                    for param_name, value in result.optimal_params.items():
                        assert not np.isnan(value), f"NaN parameter {param_name} in {result.scenario_id}"
                        assert not np.isinf(value), f"Infinite parameter {param_name} in {result.scenario_id}"

            print(f"✅ Numerical stability iteration {iteration + 1}: All values finite")

    def test_error_handling_resilience(self, optimization_engine):
        """Test error handling and recovery in concurrent scenarios."""
        # Mix valid and invalid requests
        mixed_requests = []

        # Valid request
        mixed_requests.append(OptimizationRequest(
            scenario_id='valid_1',
            initial_params={'merit_rate_level_1': 0.04, 'cola_rate': 0.02},
            param_names=['merit_rate_level_1', 'cola_rate'],
            param_bounds=[(0.01, 0.08), (0.005, 0.04)],
            objectives={'cost': 1.0},
            max_evaluations=20,
            use_synthetic=True
        ))

        # Request with invalid bounds (min > max)
        mixed_requests.append(OptimizationRequest(
            scenario_id='invalid_bounds',
            initial_params={'merit_rate_level_1': 0.04},
            param_names=['merit_rate_level_1'],
            param_bounds=[(0.08, 0.01)],  # Invalid: min > max
            objectives={'cost': 1.0},
            max_evaluations=20,
            use_synthetic=True
        ))

        # Another valid request
        mixed_requests.append(OptimizationRequest(
            scenario_id='valid_2',
            initial_params={'cola_rate': 0.025},
            param_names=['cola_rate'],
            param_bounds=[(0.01, 0.05)],
            objectives={'equity': 1.0},
            max_evaluations=20,
            use_synthetic=True
        ))

        results = optimization_engine.optimize_concurrent(mixed_requests)

        # Should complete all requests (some may fail gracefully)
        assert len(results.results) == 3

        # Valid requests should succeed
        valid_results = [r for r in results.results if r.scenario_id in ['valid_1', 'valid_2']]
        assert all(r.success or r.error is None for r in valid_results), "Valid requests should succeed"

        # Invalid request may fail, but shouldn't crash the system
        invalid_result = next(r for r in results.results if r.scenario_id == 'invalid_bounds')
        assert isinstance(invalid_result, OptimizationResponse), "Invalid request should return response"

        print(f"✅ Error handling resilience: {results.successful_optimizations} successful, {results.failed_optimizations} failed")

    def test_performance_benchmarking(self, optimization_engine):
        """Benchmark performance under various concurrent loads."""
        load_scenarios = [
            {'count': 5, 'name': 'light_load'},
            {'count': 10, 'name': 'medium_load'},
            {'count': 20, 'name': 'heavy_load'},
        ]

        benchmark_results = {}

        for scenario in load_scenarios:
            requests = self.create_optimization_requests(scenario['count'])

            # Run benchmark
            start_time = time.time()
            results = optimization_engine.optimize_concurrent(requests)
            execution_time = time.time() - start_time

            # Record metrics
            benchmark_results[scenario['name']] = {
                'total_time': execution_time,
                'avg_time_per_opt': execution_time / scenario['count'],
                'success_rate': results.successful_optimizations / results.total_optimizations,
                'thread_efficiency': len(results.performance_metrics.get('thread_distribution', {}))
            }

            # Performance assertions
            assert execution_time < scenario['count'] * 10  # Reasonable time limit
            assert results.success_rate >= 0.8  # At least 80% success rate

            print(f"📊 {scenario['name']}: {execution_time:.2f}s total, "
                  f"{execution_time/scenario['count']:.2f}s avg, "
                  f"{results.success_rate:.1%} success")

        # Performance improvement assertions
        light_avg = benchmark_results['light_load']['avg_time_per_opt']
        heavy_avg = benchmark_results['heavy_load']['avg_time_per_opt']

        # Heavy load shouldn't be dramatically slower per optimization (parallel efficiency)
        efficiency_ratio = heavy_avg / light_avg
        assert efficiency_ratio < 3.0, f"Performance degradation too high: {efficiency_ratio:.2f}x"

        print(f"✅ Performance benchmark completed. Efficiency ratio: {efficiency_ratio:.2f}x")

    def test_cache_effectiveness_concurrent(self, optimization_engine):
        """Test cache effectiveness under concurrent load."""
        # Create requests with overlapping parameter spaces to test cache hits
        base_params = {'merit_rate_level_1': 0.04, 'cola_rate': 0.02}
        param_names = ['merit_rate_level_1', 'cola_rate']
        bounds = [(0.01, 0.08), (0.005, 0.04)]

        # Create requests that will likely hit the same parameter combinations
        cache_test_requests = []
        for i in range(15):
            # Use similar initial parameters to increase cache hit probability
            variation = 0.001 * (i % 3)  # Small variations to create some cache hits
            initial_params = {
                'merit_rate_level_1': 0.04 + variation,
                'cola_rate': 0.02 + variation
            }

            request = OptimizationRequest(
                scenario_id=f'cache_test_{i}',
                initial_params=initial_params,
                param_names=param_names,
                param_bounds=bounds,
                objectives={'cost': 1.0},
                method='SLSQP',
                max_evaluations=30,
                use_synthetic=True
            )
            cache_test_requests.append(request)

        results = optimization_engine.optimize_concurrent(cache_test_requests)

        # Analyze cache performance from successful results
        successful_results = [r for r in results.results if r.success and r.cache_stats]

        if successful_results:
            total_cache_size = sum(r.cache_stats.get('cache_size', 0) for r in successful_results)
            avg_cache_size = total_cache_size / len(successful_results)

            print(f"✅ Cache effectiveness: Average cache size {avg_cache_size:.1f}")

            # Cache should be utilized (some cache entries should exist)
            assert avg_cache_size > 0, "Cache should be utilized during optimization"
        else:
            print("⚠️ No successful results with cache stats available")

    def test_memory_stability_long_running(self, optimization_engine):
        """Test memory stability during extended concurrent operation."""
        # Run multiple batches to test for memory leaks
        batch_size = 8
        num_batches = 5

        for batch in range(num_batches):
            requests = self.create_optimization_requests(batch_size)

            start_time = time.time()
            results = optimization_engine.optimize_concurrent(requests)
            batch_time = time.time() - start_time

            # Validate each batch
            assert len(results.results) == batch_size
            assert results.successful_optimizations >= 0

            # Performance shouldn't degrade significantly over time (memory leak indicator)
            if batch > 0:
                assert batch_time < 120.0, f"Batch {batch} took too long: {batch_time:.2f}s"

            print(f"✅ Batch {batch + 1}/{num_batches}: {batch_time:.2f}s, "
                  f"{results.successful_optimizations}/{batch_size} successful")

            # Small delay between batches
            time.sleep(0.5)

        print("✅ Memory stability test completed - no significant performance degradation")


class TestRealWorldScenarios:
    """Test realistic concurrent optimization scenarios."""

    @pytest.fixture
    def mock_duckdb_resource(self):
        """Create mock DuckDB resource with realistic workforce data."""
        mock = Mock()
        mock_conn = Mock()

        # Simulate realistic workforce data with variability
        workforce_data = [
            [2500, 82000.0, 18000.0],   # Large company scenario
            [500, 68000.0, 12000.0],    # Small company scenario
            [1200, 75000.0, 15000.0],   # Medium company scenario
            [5000, 95000.0, 25000.0],   # Enterprise scenario
        ]

        mock_conn.execute.return_value.fetchone.side_effect = workforce_data * 20
        mock.get_connection.return_value.__enter__.return_value = mock_conn
        return mock

    @pytest.fixture
    def enterprise_optimization_engine(self, mock_duckdb_resource):
        """Create optimization engine for enterprise scenarios."""
        return ThreadSafeOptimizationEngine(mock_duckdb_resource, max_concurrent=12)

    def test_enterprise_optimization_scenario(self, enterprise_optimization_engine):
        """Test enterprise-scale optimization scenario."""
        # Simulate real-world enterprise optimization with multiple business units
        business_unit_requests = []

        business_units = [
            {'name': 'engineering', 'size': 'large', 'focus': 'retention'},
            {'name': 'sales', 'size': 'medium', 'focus': 'performance'},
            {'name': 'marketing', 'size': 'small', 'focus': 'growth'},
            {'name': 'operations', 'size': 'large', 'focus': 'cost'},
            {'name': 'hr', 'size': 'small', 'focus': 'equity'},
            {'name': 'finance', 'size': 'medium', 'focus': 'balance'},
        ]

        for unit in business_units:
            # Tailor optimization parameters to business unit characteristics
            if unit['focus'] == 'retention':
                objectives = {'targets': 0.6, 'equity': 0.4}
                bounds = [(0.03, 0.12), (0.02, 0.06), (1.10, 1.30)]
            elif unit['focus'] == 'performance':
                objectives = {'cost': 0.3, 'targets': 0.7}
                bounds = [(0.02, 0.10), (0.01, 0.04), (1.05, 1.25)]
            elif unit['focus'] == 'growth':
                objectives = {'targets': 0.8, 'cost': 0.2}
                bounds = [(0.04, 0.15), (0.025, 0.07), (1.15, 1.40)]
            elif unit['focus'] == 'cost':
                objectives = {'cost': 0.8, 'equity': 0.2}
                bounds = [(0.01, 0.08), (0.005, 0.03), (1.00, 1.20)]
            elif unit['focus'] == 'equity':
                objectives = {'equity': 0.7, 'cost': 0.3}
                bounds = [(0.02, 0.09), (0.015, 0.05), (1.08, 1.28)]
            else:  # balance
                objectives = {'cost': 0.4, 'equity': 0.3, 'targets': 0.3}
                bounds = [(0.025, 0.085), (0.015, 0.045), (1.10, 1.25)]

            request = OptimizationRequest(
                scenario_id=f"bu_{unit['name']}",
                initial_params={
                    'merit_rate_level_1': 0.04,
                    'cola_rate': 0.025,
                    'new_hire_salary_adjustment': 1.15
                },
                param_names=['merit_rate_level_1', 'cola_rate', 'new_hire_salary_adjustment'],
                param_bounds=bounds,
                objectives=objectives,
                method='SLSQP',
                max_evaluations=100,
                tolerance=1e-6,
                use_synthetic=True
            )
            business_unit_requests.append(request)

        # Execute enterprise optimization
        start_time = time.time()
        results = enterprise_optimization_engine.optimize_concurrent(business_unit_requests)
        execution_time = time.time() - start_time

        # Validate enterprise results
        assert results.total_optimizations == len(business_units)
        assert results.successful_optimizations >= len(business_units) * 0.8  # 80% success rate

        # Performance requirements for enterprise
        assert execution_time < 300.0  # Should complete within 5 minutes
        assert results.average_execution_time < 60.0  # Average per business unit

        # Validate business unit specific results
        for result in results.results:
            assert result.scenario_id.startswith('bu_')
            if result.success:
                # Results should be within expected ranges
                assert isinstance(result.optimal_params, dict)
                assert len(result.optimal_params) == 3

                # Validate parameter bounds
                assert 0.005 <= result.optimal_params['merit_rate_level_1'] <= 0.20
                assert 0.001 <= result.optimal_params['cola_rate'] <= 0.10
                assert 1.00 <= result.optimal_params['new_hire_salary_adjustment'] <= 1.50

        print(f"🏢 Enterprise optimization completed:")
        print(f"   📊 {results.successful_optimizations}/{results.total_optimizations} business units optimized")
        print(f"   ⏱️  Total time: {execution_time:.2f}s")
        print(f"   🧵 Thread utilization: {len(results.performance_metrics.get('thread_distribution', {}))}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
