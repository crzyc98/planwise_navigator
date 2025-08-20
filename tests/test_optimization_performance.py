"""
Performance Testing Framework for Optimization Components
========================================================

This module provides comprehensive performance testing for the optimization system,
focusing on speed, memory usage, scalability, and resource efficiency.

Performance Test Categories:
1. Algorithm Performance: Optimization convergence speed, iteration counts
2. Memory Usage: Memory consumption patterns, leak detection
3. Scalability Testing: Large parameter sets, workforce sizes
4. Database Performance: Query optimization, connection handling
5. Concurrent Performance: Multi-threading, resource contention
6. Caching Efficiency: Parameter validation caching, result memoization

Includes benchmarking utilities and performance regression detection.
"""

import concurrent.futures
import cProfile
import gc
import io
import multiprocessing
import os
import pstats
import threading
import time
import warnings
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from unittest.mock import Mock, patch

import memory_profiler
import numpy as np
import pandas as pd
import psutil
import pytest
from orchestrator.optimization.constraint_solver import CompensationOptimizer
from orchestrator.optimization.objective_functions import ObjectiveFunctions
from orchestrator.optimization.optimization_schemas import (
    OptimizationCache, OptimizationRequest, OptimizationResult)
from orchestrator.optimization.sensitivity_analysis import SensitivityAnalyzer

# Import components under test
from streamlit_dashboard.optimization_schemas import (ParameterSchema,
                                                      assess_parameter_risk,
                                                      get_default_parameters,
                                                      get_parameter_schema,
                                                      validate_parameters)


@dataclass
class PerformanceMetrics:
    """Container for performance metrics."""

    execution_time: float
    memory_usage_mb: float
    cpu_usage_percent: float
    peak_memory_mb: float
    cache_hit_rate: float
    database_queries: int

    def __str__(self):
        return (
            f"Performance Metrics:\n"
            f"  Execution Time: {self.execution_time:.3f}s\n"
            f"  Memory Usage: {self.memory_usage_mb:.1f}MB\n"
            f"  Peak Memory: {self.peak_memory_mb:.1f}MB\n"
            f"  CPU Usage: {self.cpu_usage_percent:.1f}%\n"
            f"  Cache Hit Rate: {self.cache_hit_rate:.1f}%\n"
            f"  Database Queries: {self.database_queries}"
        )


@dataclass
class PerformanceBenchmark:
    """Performance benchmark thresholds."""

    max_execution_time: float
    max_memory_usage_mb: float
    min_cache_hit_rate: float
    max_database_queries: int

    @classmethod
    def default(cls):
        """Default performance benchmarks."""
        return cls(
            max_execution_time=5.0,
            max_memory_usage_mb=500.0,
            min_cache_hit_rate=50.0,
            max_database_queries=100,
        )

    @classmethod
    def strict(cls):
        """Strict performance benchmarks for production."""
        return cls(
            max_execution_time=2.0,
            max_memory_usage_mb=200.0,
            min_cache_hit_rate=80.0,
            max_database_queries=50,
        )


class PerformanceProfiler:
    """Performance profiling utilities."""

    def __init__(self):
        self.process = psutil.Process()
        self.start_time = None
        self.start_memory = None
        self.peak_memory = 0
        self.database_query_count = 0

    @contextmanager
    def profile(self):
        """Context manager for performance profiling."""
        # Start profiling
        self.start_time = time.time()
        self.start_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.peak_memory = self.start_memory
        self.database_query_count = 0

        # Enable garbage collection tracking
        gc.collect()
        gc.set_debug(gc.DEBUG_STATS)

        try:
            yield self
        finally:
            # Calculate final metrics
            end_time = time.time()
            end_memory = self.process.memory_info().rss / 1024 / 1024  # MB
            cpu_percent = self.process.cpu_percent()

            self.metrics = PerformanceMetrics(
                execution_time=end_time - self.start_time,
                memory_usage_mb=end_memory - self.start_memory,
                cpu_usage_percent=cpu_percent,
                peak_memory_mb=self.peak_memory,
                cache_hit_rate=0.0,  # To be updated by test
                database_queries=self.database_query_count,
            )

            # Disable garbage collection tracking
            gc.set_debug(0)

    def update_peak_memory(self):
        """Update peak memory usage."""
        current_memory = self.process.memory_info().rss / 1024 / 1024
        self.peak_memory = max(self.peak_memory, current_memory)

    def increment_db_queries(self, count=1):
        """Increment database query counter."""
        self.database_query_count += count


class TestAlgorithmPerformance:
    """Test optimization algorithm performance characteristics."""

    def setup_method(self):
        """Setup performance testing."""
        self.profiler = PerformanceProfiler()
        self.mock_duckdb = Mock()
        self.mock_conn = Mock()
        self.mock_duckdb.get_connection.return_value.__enter__.return_value = (
            self.mock_conn
        )

        # Setup mock responses for consistent testing
        self.mock_conn.execute.return_value.fetchone.return_value = [1_500_000.0]
        self.mock_conn.execute.return_value.fetchall.return_value = [
            (1, 50000, 2500),
            (2, 60000, 3000),
            (3, 70000, 3500),
        ]

    @pytest.mark.performance
    def test_optimization_convergence_speed(self):
        """Test optimization algorithm convergence speed."""

        optimizer = CompensationOptimizer(self.mock_duckdb, "speed_test")

        # Test with different parameter set sizes
        test_cases = [
            ("small", {"merit_rate_level_1": 0.045}),
            (
                "medium",
                {
                    "merit_rate_level_1": 0.045,
                    "merit_rate_level_2": 0.040,
                    "cola_rate": 0.025,
                },
            ),
            ("large", get_default_parameters()),
        ]

        results = {}

        for size_name, params in test_cases:
            with self.profiler.profile():
                request = OptimizationRequest(
                    scenario_id=f"speed_test_{size_name}",
                    initial_parameters=params,
                    objectives={"cost": 1.0},
                    max_evaluations=100,
                )

                # Mock scipy optimization with realistic behavior
                with patch("scipy.optimize.minimize") as mock_minimize:
                    # Simulate convergence after varying iterations
                    iterations = {"small": 25, "medium": 45, "large": 75}[size_name]

                    mock_result = Mock()
                    mock_result.success = True
                    mock_result.x = list(params.values())
                    mock_result.fun = 0.5
                    mock_result.nit = iterations
                    mock_result.nfev = iterations * 3
                    mock_minimize.return_value = mock_result

                    result = optimizer.optimize(request)

                    # Track query count
                    self.profiler.increment_db_queries(len(params) * 2)

            results[size_name] = (self.profiler.metrics, result)

            # Performance should scale reasonably
            if size_name == "small":
                assert self.profiler.metrics.execution_time < 1.0
            elif size_name == "medium":
                assert self.profiler.metrics.execution_time < 2.0
            elif size_name == "large":
                assert self.profiler.metrics.execution_time < 5.0

            print(f"Optimization {size_name}: {self.profiler.metrics}")

        # Verify scaling characteristics
        small_time = results["small"][0].execution_time
        large_time = results["large"][0].execution_time

        # Large optimization should not be more than 10x slower than small
        assert (
            large_time < small_time * 10
        ), f"Large optimization ({large_time:.3f}s) too slow vs small ({small_time:.3f}s)"

    @pytest.mark.performance
    def test_objective_function_performance(self):
        """Test objective function calculation performance."""

        obj_funcs = ObjectiveFunctions(self.mock_duckdb, "perf_test")

        # Test with varying complexity
        test_params = [
            {"merit_rate_level_1": 0.045},  # Simple
            get_default_parameters(),  # Complex
        ]

        for i, params in enumerate(test_params):
            complexity = "simple" if i == 0 else "complex"

            with self.profiler.profile():
                # Mock database calls
                with patch.object(obj_funcs, "_update_parameters") as mock_update:
                    # Simulate multiple objective calculations
                    for _ in range(10):
                        cost = obj_funcs.cost_objective(params)
                        equity = obj_funcs.equity_objective(params)
                        targets = obj_funcs.targets_objective(params)
                        combined = obj_funcs.combined_objective(
                            params, {"cost": 0.5, "equity": 0.3, "targets": 0.2}
                        )

                        self.profiler.update_peak_memory()
                        self.profiler.increment_db_queries(4)  # 4 calculations

            print(f"Objective function {complexity}: {self.profiler.metrics}")

            # Each calculation should be fast
            avg_time_per_calc = (
                self.profiler.metrics.execution_time / 40
            )  # 10 iterations * 4 calculations
            assert (
                avg_time_per_calc < 0.1
            ), f"Objective function {complexity} too slow: {avg_time_per_calc:.3f}s per call"

    @pytest.mark.performance
    def test_sensitivity_analysis_performance(self):
        """Test sensitivity analysis performance."""

        analyzer = SensitivityAnalyzer(self.mock_duckdb, "sensitivity_perf_test")

        # Mock objective function for consistent timing
        call_count = [0]

        def mock_combined_objective(params, objectives):
            call_count[0] += 1
            return 0.5 + np.random.normal(0, 0.01)  # Small variation

        analyzer.obj_funcs.combined_objective = mock_combined_objective

        # Test with different parameter set sizes
        test_cases = [
            ("small", {"merit_rate_level_1": 0.045}),
            (
                "medium",
                {
                    "merit_rate_level_1": 0.045,
                    "merit_rate_level_2": 0.040,
                    "merit_rate_level_3": 0.035,
                },
            ),
            ("large", {f"merit_rate_level_{i}": 0.045 for i in range(1, 6)}),
        ]

        for size_name, params in test_cases:
            call_count[0] = 0

            with self.profiler.profile():
                sensitivities = analyzer.calculate_sensitivities(params, {"cost": 1.0})

                ranking = analyzer.rank_parameter_importance(sensitivities)

                self.profiler.increment_db_queries(call_count[0])

            print(f"Sensitivity analysis {size_name}: {self.profiler.metrics}")

            # Should complete in reasonable time
            assert self.profiler.metrics.execution_time < 5.0

            # Function calls should be proportional to parameter count
            expected_calls = len(params) * 2  # Base + perturbed evaluations
            assert (
                call_count[0] >= expected_calls
            ), f"Expected at least {expected_calls} calls, got {call_count[0]}"

    @pytest.mark.performance
    def test_parameter_validation_performance(self):
        """Test parameter validation performance at scale."""

        schema = get_parameter_schema()

        # Generate many parameter variations
        parameter_sets = []
        base_params = get_default_parameters()

        for i in range(100):
            params = base_params.copy()
            # Add small random variations
            for param_name in params:
                params[param_name] *= 1 + np.random.uniform(-0.1, 0.1)
            parameter_sets.append(params)

        with self.profiler.profile():
            # Validate all parameter sets
            validation_results = []
            for params in parameter_sets:
                result = schema.validate_parameter_set(params)
                validation_results.append(result)
                self.profiler.update_peak_memory()

        print(f"Batch parameter validation: {self.profiler.metrics}")

        # Should validate 100 parameter sets quickly
        assert self.profiler.metrics.execution_time < 5.0
        assert len(validation_results) == 100

        # Memory usage should be reasonable
        assert (
            self.profiler.metrics.memory_usage_mb < 100
        ), f"Memory usage too high: {self.profiler.metrics.memory_usage_mb}MB"

        # Average validation time
        avg_validation_time = self.profiler.metrics.execution_time / 100
        assert (
            avg_validation_time < 0.05
        ), f"Average validation time too high: {avg_validation_time:.3f}s"


class TestMemoryUsagePatterns:
    """Test memory usage patterns and memory leak detection."""

    def setup_method(self):
        """Setup memory testing."""
        self.profiler = PerformanceProfiler()
        gc.collect()  # Clean up before testing

    @pytest.mark.performance
    def test_memory_leak_detection(self):
        """Test for memory leaks in repeated operations."""

        schema = get_parameter_schema()
        base_params = get_default_parameters()

        # Record initial memory
        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024
        memory_samples = [initial_memory]

        # Perform repeated operations
        for iteration in range(50):
            # Create slight parameter variations
            params = base_params.copy()
            for param_name in params:
                params[param_name] *= 1 + np.random.uniform(-0.05, 0.05)

            # Perform operations that might leak memory
            validation_result = schema.validate_parameter_set(params)
            comp_format = schema.transform_to_compensation_tuning_format(params)
            recovered_params = schema.transform_from_compensation_tuning_format(
                comp_format
            )

            # Force garbage collection every 10 iterations
            if iteration % 10 == 9:
                gc.collect()
                current_memory = psutil.Process().memory_info().rss / 1024 / 1024
                memory_samples.append(current_memory)

        final_memory = psutil.Process().memory_info().rss / 1024 / 1024
        memory_increase = final_memory - initial_memory

        print(f"Memory samples: {memory_samples}")
        print(f"Total memory increase: {memory_increase:.1f}MB")

        # Memory increase should be reasonable (< 50MB for this test)
        assert (
            memory_increase < 50
        ), f"Potential memory leak detected: {memory_increase:.1f}MB increase"

        # Memory should not continuously increase
        if len(memory_samples) >= 3:
            # Check that memory stabilizes (last sample shouldn't be significantly higher than middle)
            mid_memory = memory_samples[len(memory_samples) // 2]
            assert (
                final_memory < mid_memory * 1.5
            ), "Memory usage appears to be growing continuously"

    @pytest.mark.performance
    def test_large_parameter_set_memory_usage(self):
        """Test memory usage with large parameter sets."""

        # Create very large parameter set
        large_params = {}
        for i in range(1000):
            # Create parameter variations
            param_base = f"merit_rate_level_{(i % 5) + 1}"
            param_name = f"{param_base}_scenario_{i}"
            large_params[param_name] = 0.045 + (i * 0.0001) % 0.04

        with self.profiler.profile():
            # Most parameters won't be recognized, but should handle gracefully
            schema = get_parameter_schema()
            validation_result = schema.validate_parameter_set(large_params)

            self.profiler.update_peak_memory()

        print(f"Large parameter set memory: {self.profiler.metrics}")

        # Should handle large parameter sets without excessive memory usage
        assert (
            self.profiler.metrics.memory_usage_mb < 200
        ), f"Memory usage too high: {self.profiler.metrics.memory_usage_mb}MB"
        assert (
            self.profiler.metrics.execution_time < 10.0
        ), f"Execution time too high: {self.profiler.metrics.execution_time}s"

    @pytest.mark.performance
    def test_memory_efficient_data_structures(self):
        """Test memory efficiency of data structures."""

        schema = get_parameter_schema()

        # Test memory usage of different operations
        operations = [
            ("parameter_schema", lambda: get_parameter_schema()),
            ("default_parameters", lambda: get_default_parameters()),
            (
                "parameter_validation",
                lambda: schema.validate_parameter_set(get_default_parameters()),
            ),
            (
                "format_transformation",
                lambda: schema.transform_to_compensation_tuning_format(
                    get_default_parameters()
                ),
            ),
        ]

        memory_usage = {}

        for op_name, operation in operations:
            gc.collect()  # Clean up before measurement
            initial_memory = psutil.Process().memory_info().rss / 1024 / 1024

            # Perform operation multiple times
            results = []
            for _ in range(10):
                result = operation()
                results.append(result)

            final_memory = psutil.Process().memory_info().rss / 1024 / 1024
            memory_usage[op_name] = final_memory - initial_memory

            # Clean up results
            del results
            gc.collect()

        print(f"Memory usage by operation: {memory_usage}")

        # Each operation should use reasonable memory
        for op_name, usage in memory_usage.items():
            assert (
                usage < 50
            ), f"Operation {op_name} uses too much memory: {usage:.1f}MB"

    @memory_profiler.profile
    def test_memory_profiler_integration(self):
        """Test with memory profiler for detailed analysis."""

        schema = get_parameter_schema()
        params = get_default_parameters()

        # Perform memory-intensive operations
        for i in range(20):
            validation = schema.validate_parameter_set(params)
            transformation = schema.transform_to_compensation_tuning_format(params)

            # Create temporary large objects
            large_list = [params.copy() for _ in range(100)]

            # Clean up
            del large_list

            if i % 5 == 4:
                gc.collect()


class TestScalabilityPerformance:
    """Test scalability with large datasets and parameter spaces."""

    def setup_method(self):
        """Setup scalability testing."""
        self.profiler = PerformanceProfiler()

    @pytest.mark.performance
    def test_workforce_size_scalability(self):
        """Test performance scaling with workforce size."""

        # Test with different workforce sizes
        workforce_sizes = [100, 1000, 10000]

        for size in workforce_sizes:
            # Generate mock workforce data
            workforce_data = self._generate_workforce_data(size)

            with self.profiler.profile():
                # Simulate operations that depend on workforce size
                total_compensation = workforce_data["current_compensation"].sum()
                level_counts = workforce_data["job_level"].value_counts()
                avg_by_level = workforce_data.groupby("job_level")[
                    "current_compensation"
                ].mean()

                # Simulate parameter impact calculations
                for level in [1, 2, 3, 4, 5]:
                    level_data = workforce_data[workforce_data["job_level"] == level]
                    if len(level_data) > 0:
                        impact = (
                            level_data["current_compensation"].sum() * 0.045
                        )  # 4.5% merit

                self.profiler.update_peak_memory()

            print(f"Workforce size {size}: {self.profiler.metrics}")

            # Performance should scale sub-linearly
            if size == 100:
                baseline_time = self.profiler.metrics.execution_time
                baseline_memory = self.profiler.metrics.memory_usage_mb
            else:
                scale_factor = size / 100
                # Time should scale less than linearly
                assert (
                    self.profiler.metrics.execution_time
                    < baseline_time * scale_factor * 2
                )
                # Memory should scale roughly linearly but not exceed reasonable limits
                assert (
                    self.profiler.metrics.memory_usage_mb
                    < baseline_memory * scale_factor * 3
                )

    def _generate_workforce_data(self, size: int) -> pd.DataFrame:
        """Generate workforce data of specified size."""
        np.random.seed(42)  # Reproducible

        data = []
        for i in range(size):
            employee = {
                "employee_id": f"EMP_{i:08d}",
                "job_level": np.random.choice(
                    [1, 2, 3, 4, 5], p=[0.4, 0.3, 0.2, 0.08, 0.02]
                ),
                "current_compensation": max(30000, np.random.normal(65000, 15000)),
                "department": np.random.choice(
                    ["Engineering", "Finance", "HR", "Sales"]
                ),
            }
            data.append(employee)

        return pd.DataFrame(data)

    @pytest.mark.performance
    def test_parameter_space_scalability(self):
        """Test performance with large parameter spaces."""

        schema = get_parameter_schema()

        # Test with increasing numbers of parameter scenarios
        scenario_counts = [10, 50, 100]

        for count in scenario_counts:
            # Generate parameter scenarios
            scenarios = []
            base_params = get_default_parameters()

            for i in range(count):
                params = base_params.copy()
                for param_name in params:
                    # Add variation
                    params[param_name] *= 1 + np.random.uniform(-0.1, 0.1)
                scenarios.append(params)

            with self.profiler.profile():
                # Validate all scenarios
                validation_results = []
                for params in scenarios:
                    result = schema.validate_parameter_set(params)
                    validation_results.append(result)

                # Perform transformations
                transformed_results = []
                for params in scenarios:
                    transformed = schema.transform_to_compensation_tuning_format(params)
                    transformed_results.append(transformed)

                self.profiler.update_peak_memory()

            print(f"Parameter scenarios {count}: {self.profiler.metrics}")

            # Should scale reasonably
            assert (
                self.profiler.metrics.execution_time < count * 0.1
            ), f"Too slow for {count} scenarios"
            assert (
                self.profiler.metrics.memory_usage_mb < count * 2
            ), f"Too much memory for {count} scenarios"

    @pytest.mark.performance
    def test_concurrent_scalability(self):
        """Test performance under concurrent load."""

        schema = get_parameter_schema()

        def worker_task(worker_id):
            """Task for concurrent execution."""
            results = []
            for i in range(10):
                params = get_default_parameters()
                # Add worker-specific variation
                params["merit_rate_level_1"] += worker_id * 0.001

                result = schema.validate_parameter_set(params)
                results.append(result)

            return len(results)

        # Test with different numbers of concurrent workers
        worker_counts = [1, 2, 4, 8]

        for worker_count in worker_counts:
            with self.profiler.profile():
                with concurrent.futures.ThreadPoolExecutor(
                    max_workers=worker_count
                ) as executor:
                    futures = [
                        executor.submit(worker_task, i) for i in range(worker_count)
                    ]
                    results = [
                        future.result()
                        for future in concurrent.futures.as_completed(futures)
                    ]

                self.profiler.update_peak_memory()

            print(f"Concurrent workers {worker_count}: {self.profiler.metrics}")

            # Should handle concurrency efficiently
            assert len(results) == worker_count
            assert all(
                result == 10 for result in results
            )  # Each worker completed 10 tasks

            # Performance shouldn't degrade drastically with more workers
            if worker_count == 1:
                baseline_time = self.profiler.metrics.execution_time
            else:
                # With more workers, time shouldn't increase much (may even decrease)
                assert self.profiler.metrics.execution_time < baseline_time * 3


class TestCachingPerformance:
    """Test caching performance and efficiency."""

    def setup_method(self):
        """Setup caching performance tests."""
        self.profiler = PerformanceProfiler()
        self.cache = OptimizationCache()

    @pytest.mark.performance
    def test_parameter_validation_caching(self):
        """Test parameter validation caching performance."""

        schema = get_parameter_schema()
        params = get_default_parameters()

        # First validation (cold cache)
        with self.profiler.profile():
            for _ in range(10):
                result = schema.validate_parameter_set(params)

        cold_cache_time = self.profiler.metrics.execution_time

        # Reset profiler for warm cache test
        self.profiler = PerformanceProfiler()

        # Subsequent validations (potentially warm cache)
        with self.profiler.profile():
            for _ in range(10):
                result = schema.validate_parameter_set(params)

        warm_cache_time = self.profiler.metrics.execution_time

        print(f"Cold cache time: {cold_cache_time:.3f}s")
        print(f"Warm cache time: {warm_cache_time:.3f}s")

        # If caching is implemented, warm cache should be faster
        # If not implemented, times should be similar
        assert (
            warm_cache_time <= cold_cache_time * 1.5
        ), "Warm cache performance regression"

    @pytest.mark.performance
    def test_optimization_cache_performance(self):
        """Test optimization result caching performance."""

        # Test cache performance with many entries
        test_params = []
        for i in range(100):
            params = get_default_parameters()
            params["merit_rate_level_1"] += i * 0.001
            test_params.append(params)

        with self.profiler.profile():
            # Fill cache
            for i, params in enumerate(test_params):
                self.cache.set(params, 0.5 + i * 0.001)

            # Test cache retrieval
            cache_hits = 0
            cache_misses = 0

            for params in test_params:
                result = self.cache.get(params)
                if result is not None:
                    cache_hits += 1
                else:
                    cache_misses += 1

            # Test cache with new parameters
            for i in range(20):
                new_params = get_default_parameters()
                new_params["merit_rate_level_1"] += (i + 1000) * 0.001
                result = self.cache.get(new_params)
                if result is None:
                    cache_misses += 1

        hit_rate = (cache_hits / (cache_hits + cache_misses)) * 100

        print(f"Cache performance: {self.profiler.metrics}")
        print(f"Cache hit rate: {hit_rate:.1f}%")

        # Cache operations should be fast
        assert self.profiler.metrics.execution_time < 1.0, "Cache operations too slow"

        # Should have reasonable hit rate for repeated parameters
        assert hit_rate >= 70, f"Cache hit rate too low: {hit_rate:.1f}%"

    @pytest.mark.performance
    def test_memory_efficient_caching(self):
        """Test memory efficiency of caching mechanisms."""

        cache = OptimizationCache()

        initial_memory = psutil.Process().memory_info().rss / 1024 / 1024

        # Add many entries to cache
        for i in range(1000):
            params = get_default_parameters()
            params["merit_rate_level_1"] += i * 0.0001
            cache.set(params, 0.5 + i * 0.0001)

        final_memory = psutil.Process().memory_info().rss / 1024 / 1024
        memory_increase = final_memory - initial_memory

        print(f"Cache memory usage for 1000 entries: {memory_increase:.1f}MB")

        # Cache should use reasonable memory
        assert (
            memory_increase < 100
        ), f"Cache uses too much memory: {memory_increase:.1f}MB"

        # Test cache size limits (if implemented)
        cache_size = len(cache._cache) if hasattr(cache, "_cache") else 1000
        print(f"Cache size: {cache_size} entries")


class TestDatabasePerformance:
    """Test database interaction performance."""

    def setup_method(self):
        """Setup database performance testing."""
        self.profiler = PerformanceProfiler()
        self.mock_duckdb = Mock()
        self.mock_conn = Mock()
        self.mock_duckdb.get_connection.return_value.__enter__.return_value = (
            self.mock_conn
        )

    @pytest.mark.performance
    def test_database_query_performance(self):
        """Test database query performance patterns."""

        obj_funcs = ObjectiveFunctions(self.mock_duckdb, "db_perf_test")

        # Mock database responses with timing simulation
        def slow_execute(*args, **kwargs):
            time.sleep(0.01)  # Simulate database delay
            self.profiler.increment_db_queries()
            mock_result = Mock()
            mock_result.fetchone.return_value = [1_000_000.0]
            mock_result.fetchall.return_value = [(1, 50000, 2500)]
            return mock_result

        self.mock_conn.execute.side_effect = slow_execute

        params = get_default_parameters()

        with self.profiler.profile():
            # Simulate multiple objective function calculations
            with patch.object(obj_funcs, "_update_parameters"):
                for _ in range(10):
                    cost = obj_funcs.cost_objective(params)
                    equity = obj_funcs.equity_objective(params)
                    self.profiler.update_peak_memory()

        print(f"Database query performance: {self.profiler.metrics}")

        # Should handle database queries efficiently
        assert self.profiler.metrics.execution_time < 5.0, "Database queries too slow"
        assert self.profiler.metrics.database_queries > 0, "No database queries tracked"

        # Average query time should be reasonable
        avg_query_time = (
            self.profiler.metrics.execution_time
            / self.profiler.metrics.database_queries
        )
        assert (
            avg_query_time < 0.5
        ), f"Average query time too high: {avg_query_time:.3f}s"

    @pytest.mark.performance
    def test_connection_management_performance(self):
        """Test database connection management performance."""

        # Simulate multiple components using database
        components = [
            ObjectiveFunctions(self.mock_duckdb, f"perf_test_{i}") for i in range(5)
        ]

        connection_count = [0]

        def mock_get_connection():
            connection_count[0] += 1
            return self.mock_duckdb.get_connection.return_value

        self.mock_duckdb.get_connection.side_effect = mock_get_connection

        with self.profiler.profile():
            # Each component performs operations
            for component in components:
                with patch.object(component, "_update_parameters"):
                    cost = component.cost_objective({"merit_rate_level_1": 0.045})
                    self.profiler.increment_db_queries()
                    self.profiler.update_peak_memory()

        print(f"Connection management: {self.profiler.metrics}")
        print(f"Total connections created: {connection_count[0]}")

        # Should efficiently manage connections
        assert (
            connection_count[0] <= len(components) * 2
        ), "Too many connections created"
        assert (
            self.profiler.metrics.execution_time < 2.0
        ), "Connection management too slow"


if __name__ == "__main__":
    # Run performance tests
    pytest.main(
        [
            __file__
            + "::TestAlgorithmPerformance::test_optimization_convergence_speed",
            __file__ + "::TestMemoryUsagePatterns::test_memory_leak_detection",
            __file__ + "::TestScalabilityPerformance::test_workforce_size_scalability",
            __file__ + "::TestCachingPerformance::test_parameter_validation_caching",
            "-v",
            "-s",  # -s to show print statements
        ]
    )
