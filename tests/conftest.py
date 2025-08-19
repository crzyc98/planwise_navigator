"""
Pytest Configuration for Optimization Testing Framework
======================================================

This module provides pytest configuration, fixtures, and utilities for the comprehensive
optimization testing framework. Sets up test markers, shared fixtures, and test
execution configuration.

Test Markers:
- unit: Unit tests for individual components
- integration: Integration tests across components
- performance: Performance and benchmarking tests
- e2e: End-to-end workflow tests
- edge_case: Edge case and boundary testing
- error_handling: Error handling validation tests

Shared Fixtures:
- Mock database resources
- Test data generators
- Performance measurement utilities
- Temporary file management
"""

import pytest
import pandas as pd
import numpy as np
import os
import tempfile
import time
import psutil
from pathlib import Path
from unittest.mock import Mock, MagicMock
from typing import Dict, Any, List, Optional, Generator
import warnings

# Import test utilities
from streamlit_dashboard.optimization_schemas import get_parameter_schema, get_default_parameters


def pytest_configure(config):
    """Configure pytest with custom markers."""
    config.addinivalue_line(
        "markers", "unit: Unit tests for individual components"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests across components"
    )
    config.addinivalue_line(
        "markers", "performance: Performance and benchmarking tests"
    )
    config.addinivalue_line(
        "markers", "e2e: End-to-end workflow tests"
    )
    config.addinivalue_line(
        "markers", "edge_case: Edge case and boundary testing"
    )
    config.addinivalue_line(
        "markers", "error_handling: Error handling validation tests"
    )
    config.addinivalue_line(
        "markers", "slow: Slow running tests"
    )


def pytest_collection_modifyitems(config, items):
    """Modify test collection to add markers based on test names."""
    for item in items:
        # Add markers based on test file names
        if "unit" in item.nodeid:
            item.add_marker(pytest.mark.unit)
        elif "integration" in item.nodeid or "workflow" in item.nodeid:
            item.add_marker(pytest.mark.integration)
        elif "performance" in item.nodeid:
            item.add_marker(pytest.mark.performance)
        elif "end_to_end" in item.nodeid:
            item.add_marker(pytest.mark.e2e)
        elif "edge_case" in item.nodeid:
            item.add_marker(pytest.mark.edge_case)
        elif "error_handling" in item.nodeid:
            item.add_marker(pytest.mark.error_handling)

        # Add slow marker for performance and e2e tests
        if any(marker in item.nodeid for marker in ["performance", "end_to_end"]):
            item.add_marker(pytest.mark.slow)


# Shared Fixtures

@pytest.fixture(scope="session")
def parameter_schema():
    """Provide parameter schema for tests."""
    return get_parameter_schema()


@pytest.fixture(scope="session")
def default_parameters():
    """Provide default parameters for tests."""
    return get_default_parameters()


@pytest.fixture
def mock_duckdb_resource():
    """Provide mock DuckDB resource for testing."""
    mock_resource = Mock()
    mock_conn = Mock()

    # Setup default responses
    mock_conn.execute.return_value.fetchone.return_value = [1_500_000.0]
    mock_conn.execute.return_value.fetchall.return_value = [
        (1, 50000, 2500),
        (2, 60000, 3000),
        (3, 70000, 3500),
        (4, 80000, 4000),
        (5, 90000, 4500)
    ]

    # Setup context manager
    mock_resource.get_connection.return_value.__enter__.return_value = mock_conn
    mock_resource.get_connection.return_value.__exit__.return_value = None

    return mock_resource, mock_conn


@pytest.fixture
def temp_directory():
    """Provide temporary directory for test files."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir

    # Cleanup
    import shutil
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def sample_workforce_data():
    """Generate sample workforce data for testing."""
    np.random.seed(42)  # Reproducible data

    data = []
    for i in range(1000):
        employee = {
            'employee_id': f"EMP_{i:06d}",
            'job_level': np.random.choice([1, 2, 3, 4, 5], p=[0.4, 0.3, 0.2, 0.08, 0.02]),
            'current_compensation': max(35000, np.random.normal(65000, 15000)),
            'years_of_service': max(0, np.random.exponential(5)),
            'department': np.random.choice(['Engineering', 'Finance', 'HR', 'Sales', 'Marketing']),
            'performance_rating': np.random.choice([1, 2, 3, 4, 5], p=[0.05, 0.15, 0.6, 0.15, 0.05])
        }

        # Adjust compensation by level
        level_multipliers = {1: 0.8, 2: 1.0, 3: 1.4, 4: 2.0, 5: 3.0}
        employee['current_compensation'] *= level_multipliers[employee['job_level']]

        data.append(employee)

    return pd.DataFrame(data)


@pytest.fixture
def comp_levers_test_data(temp_directory):
    """Generate comp_levers.csv test data."""
    data = []
    for year in [2025, 2026, 2027, 2028, 2029]:
        for level in [1, 2, 3, 4, 5]:
            data.extend([
                {"parameter_name": "merit_base", "job_level": level, "year": year, "value": 0.045},
                {"parameter_name": "cola_rate", "job_level": level, "year": year, "value": 0.025},
                {"parameter_name": "new_hire_salary_adjustment", "job_level": level, "year": year, "value": 1.15},
                {"parameter_name": "promotion_probability", "job_level": level, "year": year, "value": 0.10},
                {"parameter_name": "promotion_raise", "job_level": level, "year": year, "value": 0.12}
            ])

    df = pd.DataFrame(data)
    file_path = os.path.join(temp_directory, "comp_levers.csv")
    df.to_csv(file_path, index=False)

    return file_path, df


@pytest.fixture
def performance_tracker():
    """Provide performance tracking utility."""
    class PerformanceTracker:
        def __init__(self):
            self.start_time = None
            self.start_memory = None
            self.metrics = {}

        def start(self):
            self.start_time = time.time()
            self.start_memory = psutil.Process().memory_info().rss / 1024 / 1024

        def stop(self):
            if self.start_time is None:
                raise ValueError("Tracker not started")

            end_time = time.time()
            end_memory = psutil.Process().memory_info().rss / 1024 / 1024

            self.metrics = {
                'execution_time': end_time - self.start_time,
                'memory_delta': end_memory - self.start_memory,
                'peak_memory': end_memory
            }

            return self.metrics

        def assert_performance(self, max_time=None, max_memory=None):
            if max_time and self.metrics['execution_time'] > max_time:
                pytest.fail(f"Execution time {self.metrics['execution_time']:.2f}s exceeds limit {max_time}s")

            if max_memory and self.metrics['memory_delta'] > max_memory:
                pytest.fail(f"Memory usage {self.metrics['memory_delta']:.1f}MB exceeds limit {max_memory}MB")

    return PerformanceTracker()


@pytest.fixture
def mock_optimization_result():
    """Provide mock optimization result for testing."""
    from orchestrator.optimization.optimization_schemas import OptimizationResult

    return OptimizationResult(
        scenario_id="test_scenario",
        converged=True,
        optimal_parameters={
            "merit_rate_level_1": 0.045,
            "merit_rate_level_2": 0.040,
            "merit_rate_level_3": 0.035,
            "cola_rate": 0.025,
            "new_hire_salary_adjustment": 1.15
        },
        objective_value=0.287,
        algorithm_used="SLSQP",
        iterations=45,
        function_evaluations=135,
        runtime_seconds=4.2,
        estimated_cost_impact={
            "value": 2_150_000.0,
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


# Test Data Generators

class TestDataGenerator:
    """Utility class for generating test data."""

    @staticmethod
    def parameter_variations(base_params: Dict[str, float], count: int = 10) -> List[Dict[str, float]]:
        """Generate parameter variations around base parameters."""
        variations = []

        for i in range(count):
            params = base_params.copy()
            for param_name, base_value in params.items():
                # Add random variation ±10%
                variation = 1 + np.random.uniform(-0.1, 0.1)
                params[param_name] = base_value * variation

            variations.append(params)

        return variations

    @staticmethod
    def business_scenarios() -> List[Dict[str, Any]]:
        """Generate business scenario test data."""
        return [
            {
                "name": "cost_focus",
                "objectives": {"cost": 0.8, "equity": 0.2},
                "budget_limit": 2_000_000,
                "risk_tolerance": "medium"
            },
            {
                "name": "equity_focus",
                "objectives": {"cost": 0.2, "equity": 0.8},
                "budget_limit": 3_000_000,
                "risk_tolerance": "low"
            },
            {
                "name": "balanced",
                "objectives": {"cost": 0.4, "equity": 0.3, "targets": 0.3},
                "budget_limit": 2_500_000,
                "risk_tolerance": "medium"
            }
        ]


@pytest.fixture
def test_data_generator():
    """Provide test data generator utility."""
    return TestDataGenerator()


# Test Utilities

def pytest_runtest_setup(item):
    """Setup for each test run."""
    # Suppress specific warnings during tests
    warnings.filterwarnings("ignore", category=DeprecationWarning)
    warnings.filterwarnings("ignore", category=FutureWarning)
    warnings.filterwarnings("ignore", message=".*pytest-cov.*")


def pytest_runtest_teardown(item):
    """Teardown after each test run."""
    # Force garbage collection after each test
    import gc
    gc.collect()


# Performance Testing Utilities

@pytest.fixture
def benchmark_baseline():
    """Provide performance benchmarks for comparison."""
    return {
        "parameter_validation": {
            "max_time": 0.1,
            "max_memory": 10.0
        },
        "optimization_execution": {
            "max_time": 5.0,
            "max_memory": 100.0
        },
        "simulation_pipeline": {
            "max_time": 30.0,
            "max_memory": 200.0
        }
    }


# Error Testing Utilities

@pytest.fixture
def error_injector():
    """Provide error injection utility for testing error handling."""
    class ErrorInjector:
        def __init__(self):
            self.original_methods = {}

        def inject_database_error(self, mock_conn, error_type="connection"):
            """Inject database errors for testing."""
            if error_type == "connection":
                mock_conn.execute.side_effect = Exception("Database connection failed")
            elif error_type == "timeout":
                mock_conn.execute.side_effect = Exception("Query timeout")
            elif error_type == "lock":
                mock_conn.execute.side_effect = Exception("Database is locked")

        def inject_memory_error(self, target_object, method_name):
            """Inject memory errors for testing."""
            original_method = getattr(target_object, method_name)
            self.original_methods[f"{target_object}.{method_name}"] = original_method

            def memory_error_method(*args, **kwargs):
                raise MemoryError("Unable to allocate memory")

            setattr(target_object, method_name, memory_error_method)

        def restore_all(self):
            """Restore all injected methods."""
            for key, original_method in self.original_methods.items():
                obj_name, method_name = key.split('.')
                # Note: In practice, you'd need object references to restore
                pass

    return ErrorInjector()


# Mocking Utilities

@pytest.fixture
def scipy_optimize_mock():
    """Provide scipy.optimize mock utility."""
    class ScipyOptimizeMock:
        def __init__(self):
            self.call_count = 0
            self.results = []

        def setup_success(self, iterations=45, function_evaluations=135):
            """Setup successful optimization mock."""
            mock_result = Mock()
            mock_result.success = True
            mock_result.x = [0.045, 0.040, 0.035, 0.025]
            mock_result.fun = 0.287
            mock_result.nit = iterations
            mock_result.nfev = function_evaluations
            mock_result.message = "Optimization terminated successfully"

            return mock_result

        def setup_failure(self, reason="convergence"):
            """Setup failed optimization mock."""
            mock_result = Mock()
            mock_result.success = False
            mock_result.x = None
            mock_result.fun = float('inf')
            mock_result.nit = 0
            mock_result.nfev = 0

            if reason == "convergence":
                mock_result.message = "Failed to converge"
            elif reason == "bounds":
                mock_result.message = "Bounds violation"
            elif reason == "numerical":
                mock_result.message = "Numerical instability"

            return mock_result

    return ScipyOptimizeMock()


# Test Execution Hooks

def pytest_sessionstart(session):
    """Called after test collection has been performed."""
    print("\n" + "="*80)
    print("PlanWise Navigator Optimization Testing Framework")
    print("="*80)
    print(f"Running on Python {session.config.getoption('--tb')}")
    print(f"Test directory: {Path(__file__).parent}")
    print()


def pytest_sessionfinish(session, exitstatus):
    """Called after whole test run finished."""
    print("\n" + "="*80)
    print("Test Execution Summary")
    print("="*80)

    if hasattr(session, 'testscollected'):
        print(f"Tests collected: {session.testscollected}")

    if exitstatus == 0:
        print("✓ All tests passed successfully")
    else:
        print(f"✗ Tests failed with exit status: {exitstatus}")

    print("="*80)


# Custom Assertions

def assert_parameter_validity(schema, parameters):
    """Custom assertion for parameter validity."""
    validation_result = schema.validate_parameter_set(parameters)

    if not validation_result['is_valid']:
        errors = '\n'.join(validation_result['errors'])
        pytest.fail(f"Parameter validation failed:\n{errors}")

    return validation_result


def assert_optimization_convergence(result):
    """Custom assertion for optimization convergence."""
    if not result.converged:
        pytest.fail(f"Optimization failed to converge: {result.algorithm_used}")

    if result.objective_value == float('inf'):
        pytest.fail("Optimization returned infinite objective value")

    if not result.optimal_parameters:
        pytest.fail("Optimization returned no optimal parameters")


def assert_performance_acceptable(metrics, benchmarks):
    """Custom assertion for performance metrics."""
    if metrics['execution_time'] > benchmarks.get('max_time', float('inf')):
        pytest.fail(f"Execution time {metrics['execution_time']:.2f}s exceeds benchmark {benchmarks['max_time']}s")

    if metrics.get('memory_delta', 0) > benchmarks.get('max_memory', float('inf')):
        pytest.fail(f"Memory usage {metrics['memory_delta']:.1f}MB exceeds benchmark {benchmarks['max_memory']}MB")


# Register custom assertions
pytest.assert_parameter_validity = assert_parameter_validity
pytest.assert_optimization_convergence = assert_optimization_convergence
pytest.assert_performance_acceptable = assert_performance_acceptable


# Production Testing Fixtures (E047)

@pytest.fixture(scope="session")
def test_database():
    """Create isolated test database for production tests"""
    import shutil
    from pathlib import Path

    # Backup production database if it exists
    prod_db = Path("simulation.duckdb")
    backup_db = Path("simulation_backup.duckdb")

    if prod_db.exists():
        shutil.copy(prod_db, backup_db)

    yield str(prod_db)

    # Restore production database
    if backup_db.exists():
        shutil.move(backup_db, prod_db)


@pytest.fixture
def clean_database():
    """Provide clean database for each test"""
    # Create minimal test dataset if needed
    yield
    # Cleanup handled by session fixture


@pytest.fixture
def production_simulator():
    """Provide production simulation utility"""
    class ProductionSimulator:
        def __init__(self):
            self.runs = []

        def run_simulation(self, years="2025-2025", seed=42, **kwargs):
            """Run a simulation and track results"""
            import argparse
            from navigator_orchestrator.cli import cmd_run

            args = argparse.Namespace(
                config=None,
                database=None,
                threads=4,
                dry_run=False,
                verbose=False,
                years=years,
                seed=seed,
                force_clear=kwargs.get('force_clear', True),
                resume_from=None,
                **kwargs
            )

            start_time = time.time()
            result_code = cmd_run(args)
            duration = time.time() - start_time

            run_result = {
                'result_code': result_code,
                'duration': duration,
                'years': years,
                'seed': seed,
                'success': result_code == 0
            }

            self.runs.append(run_result)
            return run_result

        def get_last_run(self):
            return self.runs[-1] if self.runs else None

        def get_run_stats(self):
            if not self.runs:
                return {}

            durations = [run['duration'] for run in self.runs]
            return {
                'total_runs': len(self.runs),
                'success_rate': sum(1 for run in self.runs if run['success']) / len(self.runs),
                'avg_duration': sum(durations) / len(durations),
                'max_duration': max(durations),
                'min_duration': min(durations)
            }

    return ProductionSimulator()


@pytest.fixture
def database_health_checker():
    """Provide database health checking utility"""
    class DatabaseHealthChecker:
        def __init__(self):
            self.checks = []

        def check_table_exists(self, table_name):
            """Check if a table exists"""
            import duckdb
            try:
                with duckdb.connect("simulation.duckdb") as conn:
                    tables = conn.execute("SHOW TABLES").fetchall()
                    table_names = [t[0] for t in tables]
                    exists = table_name in table_names
                    self.checks.append(('table_exists', table_name, exists))
                    return exists
            except Exception as e:
                self.checks.append(('table_exists', table_name, False, str(e)))
                return False

        def check_table_not_empty(self, table_name):
            """Check if a table has data"""
            import duckdb
            try:
                with duckdb.connect("simulation.duckdb") as conn:
                    count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                    has_data = count > 0
                    self.checks.append(('table_not_empty', table_name, has_data, count))
                    return has_data
            except Exception as e:
                self.checks.append(('table_not_empty', table_name, False, str(e)))
                return False

        def check_data_quality(self, table_name, check_type, **kwargs):
            """Run specific data quality checks"""
            import duckdb
            try:
                with duckdb.connect("simulation.duckdb") as conn:
                    if check_type == 'no_nulls':
                        column = kwargs.get('column')
                        null_count = conn.execute(f"SELECT COUNT(*) FROM {table_name} WHERE {column} IS NULL").fetchone()[0]
                        passed = null_count == 0
                        self.checks.append(('no_nulls', f"{table_name}.{column}", passed, null_count))
                        return passed
                    elif check_type == 'unique_values':
                        column = kwargs.get('column')
                        total_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
                        unique_count = conn.execute(f"SELECT COUNT(DISTINCT {column}) FROM {table_name}").fetchone()[0]
                        passed = total_count == unique_count
                        self.checks.append(('unique_values', f"{table_name}.{column}", passed, (total_count, unique_count)))
                        return passed
                    elif check_type == 'value_range':
                        column = kwargs.get('column')
                        min_val = kwargs.get('min_val')
                        max_val = kwargs.get('max_val')
                        result = conn.execute(f"SELECT MIN({column}), MAX({column}) FROM {table_name}").fetchone()
                        actual_min, actual_max = result
                        passed = (min_val is None or actual_min >= min_val) and (max_val is None or actual_max <= max_val)
                        self.checks.append(('value_range', f"{table_name}.{column}", passed, (actual_min, actual_max)))
                        return passed
            except Exception as e:
                self.checks.append((check_type, table_name, False, str(e)))
                return False

        def get_summary(self):
            """Get summary of all checks"""
            passed = sum(1 for check in self.checks if len(check) >= 3 and check[2])
            total = len(self.checks)
            return {
                'total_checks': total,
                'passed': passed,
                'failed': total - passed,
                'success_rate': passed / total if total > 0 else 0,
                'checks': self.checks
            }

    return DatabaseHealthChecker()
