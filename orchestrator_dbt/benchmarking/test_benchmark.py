#!/usr/bin/env python3
"""
Test suite for performance benchmarking system.

Tests the benchmarking infrastructure and validates that performance
measurements are accurate and repeatable for Story S031-03.

Test Coverage:
- Benchmark system initialization and configuration
- Performance measurement accuracy and repeatability
- Baseline comparison calculations
- Report generation and serialization
- CLI functionality and argument parsing
- Performance target validation

Integration with Story S031-03:
- Validates benchmark system can measure 65% improvement target
- Tests performance measurement accuracy for stakeholder reporting
- Ensures benchmark results are reproducible and reliable
"""

import unittest
import tempfile
import json
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, List
from unittest.mock import Mock, patch, MagicMock

# Test imports
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from orchestrator_dbt.benchmarking import (
    PerformanceBenchmark,
    BenchmarkSuite,
    PerformanceResult,
    ComparisonResult,
    BenchmarkCategory,
    BenchmarkMetric,
    create_performance_benchmark,
    run_comprehensive_benchmark
)
from orchestrator_dbt.core.database_manager import DatabaseManager
from orchestrator_dbt.core.config import OrchestrationConfig


class MockDatabaseManager:
    """Mock database manager for testing."""

    def __init__(self):
        self.query_history = []

    def get_connection(self):
        return MockConnection(self.query_history)


class MockConnection:
    """Mock database connection for testing."""

    def __init__(self, query_history: List[str]):
        self.query_history = query_history

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def execute(self, query: str, params: List[Any] = None):
        self.query_history.append((query, params))
        return MockQueryResult()


class MockQueryResult:
    """Mock query result for testing."""

    def fetchone(self):
        return (100,)  # Mock result

    def fetchall(self):
        return [(1,), (2,), (3,)]

    def df(self):
        import pandas as pd
        return pd.DataFrame({'employee_id': ['EMP_2025_000001', 'EMP_2025_000002']})


class TestPerformanceResult(unittest.TestCase):
    """Test cases for PerformanceResult."""

    def test_performance_result_creation(self):
        """Test performance result creation and serialization."""
        result = PerformanceResult(
            benchmark_name="test_benchmark",
            category=BenchmarkCategory.EVENT_GENERATION,
            metric=BenchmarkMetric.EXECUTION_TIME,
            value=1.234,
            unit="seconds",
            execution_time=1.234,
            metadata={"test_key": "test_value"}
        )

        self.assertEqual(result.benchmark_name, "test_benchmark")
        self.assertEqual(result.category, BenchmarkCategory.EVENT_GENERATION)
        self.assertEqual(result.metric, BenchmarkMetric.EXECUTION_TIME)
        self.assertEqual(result.value, 1.234)
        self.assertEqual(result.unit, "seconds")
        self.assertEqual(result.execution_time, 1.234)
        self.assertEqual(result.metadata["test_key"], "test_value")

        # Test serialization
        result_dict = result.to_dict()
        self.assertEqual(result_dict['benchmark_name'], "test_benchmark")
        self.assertEqual(result_dict['category'], "event_generation")
        self.assertEqual(result_dict['metric'], "execution_time")
        self.assertEqual(result_dict['value'], 1.234)


class TestBenchmarkSuite(unittest.TestCase):
    """Test cases for BenchmarkSuite."""

    def test_benchmark_suite_creation(self):
        """Test benchmark suite creation and management."""
        suite = BenchmarkSuite(suite_name="test_suite")

        self.assertEqual(suite.suite_name, "test_suite")
        self.assertEqual(len(suite.results), 0)
        self.assertIsNone(suite.start_time)
        self.assertIsNone(suite.end_time)

        # Test adding results
        result = PerformanceResult(
            benchmark_name="test",
            category=BenchmarkCategory.EVENT_GENERATION,
            metric=BenchmarkMetric.EXECUTION_TIME,
            value=1.0,
            unit="seconds",
            execution_time=1.0
        )

        suite.add_result(result)
        self.assertEqual(len(suite.results), 1)
        self.assertEqual(suite.results[0], result)

    def test_suite_duration_calculation(self):
        """Test suite duration calculation."""
        suite = BenchmarkSuite(suite_name="test_suite")

        start_time = datetime.now()
        end_time = start_time + timedelta(seconds=10)

        suite.start_time = start_time
        suite.end_time = end_time

        self.assertEqual(suite.duration, timedelta(seconds=10))

    def test_results_filtering(self):
        """Test results filtering by category and metric."""
        suite = BenchmarkSuite(suite_name="test_suite")

        # Add results with different categories and metrics
        result1 = PerformanceResult(
            "test1", BenchmarkCategory.EVENT_GENERATION,
            BenchmarkMetric.EXECUTION_TIME, 1.0, "seconds", 1.0
        )
        result2 = PerformanceResult(
            "test2", BenchmarkCategory.DATABASE_OPERATIONS,
            BenchmarkMetric.THROUGHPUT, 100.0, "ops/sec", 1.0
        )
        result3 = PerformanceResult(
            "test3", BenchmarkCategory.EVENT_GENERATION,
            BenchmarkMetric.MEMORY_USAGE, 50.0, "MB", 1.0
        )

        suite.add_result(result1)
        suite.add_result(result2)
        suite.add_result(result3)

        # Test category filtering
        event_gen_results = suite.get_results_by_category(BenchmarkCategory.EVENT_GENERATION)
        self.assertEqual(len(event_gen_results), 2)
        self.assertIn(result1, event_gen_results)
        self.assertIn(result3, event_gen_results)

        # Test metric filtering
        execution_time_results = suite.get_results_by_metric(BenchmarkMetric.EXECUTION_TIME)
        self.assertEqual(len(execution_time_results), 1)
        self.assertEqual(execution_time_results[0], result1)


class TestComparisonResult(unittest.TestCase):
    """Test cases for ComparisonResult."""

    def test_comparison_result_creation(self):
        """Test comparison result creation and calculations."""
        comparison = ComparisonResult(
            baseline_value=100.0,
            current_value=40.0,
            improvement_percent=60.0,
            improvement_absolute=60.0,
            meets_target=False,  # 60% < 65% target
            target_percent=65.0
        )

        self.assertEqual(comparison.baseline_value, 100.0)
        self.assertEqual(comparison.current_value, 40.0)
        self.assertEqual(comparison.improvement_percent, 60.0)
        self.assertEqual(comparison.improvement_absolute, 60.0)
        self.assertFalse(comparison.meets_target)
        self.assertEqual(comparison.target_percent, 65.0)

        # Test meets target with sufficient improvement
        comparison_target_met = ComparisonResult(
            baseline_value=100.0,
            current_value=30.0,
            improvement_percent=70.0,
            improvement_absolute=70.0,
            meets_target=True,
            target_percent=65.0
        )

        self.assertTrue(comparison_target_met.meets_target)

    def test_comparison_serialization(self):
        """Test comparison result serialization."""
        comparison = ComparisonResult(
            baseline_value=100.0,
            current_value=40.0,
            improvement_percent=60.0,
            improvement_absolute=60.0,
            meets_target=False,
            target_percent=65.0
        )

        comparison_dict = comparison.to_dict()

        self.assertEqual(comparison_dict['baseline_value'], 100.0)
        self.assertEqual(comparison_dict['current_value'], 40.0)
        self.assertEqual(comparison_dict['improvement_percent'], 60.0)
        self.assertEqual(comparison_dict['improvement_absolute'], 60.0)
        self.assertFalse(comparison_dict['meets_target'])
        self.assertEqual(comparison_dict['target_percent'], 65.0)


class TestPerformanceBenchmark(unittest.TestCase):
    """Test cases for PerformanceBenchmark."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_db_manager = MockDatabaseManager()
        self.mock_config = Mock(spec=OrchestrationConfig)

        # Mock component creation to avoid complex initialization
        with patch('orchestrator_dbt.benchmarking.performance_benchmark.BatchEventGenerator'), \
             patch('orchestrator_dbt.benchmarking.performance_benchmark.WorkforceCalculator'), \
             patch('orchestrator_dbt.benchmarking.performance_benchmark.CompensationProcessor'), \
             patch('orchestrator_dbt.benchmarking.performance_benchmark.EligibilityProcessor'), \
             patch('orchestrator_dbt.benchmarking.performance_benchmark.create_id_generator_from_config'):

            self.benchmark = PerformanceBenchmark(
                database_manager=self.mock_db_manager,
                config=self.mock_config,
                enable_memory_monitoring=False,  # Disable for testing
                enable_cpu_monitoring=False
            )

    def test_benchmark_initialization(self):
        """Test benchmark system initialization."""
        self.assertEqual(self.benchmark.db_manager, self.mock_db_manager)
        self.assertEqual(self.benchmark.config, self.mock_config)
        self.assertFalse(self.benchmark.enable_memory_monitoring)
        self.assertFalse(self.benchmark.enable_cpu_monitoring)
        self.assertIsNone(self.benchmark.current_suite)
        self.assertIsNone(self.benchmark.baseline_data)

    def test_benchmark_suite_lifecycle(self):
        """Test benchmark suite start/finish lifecycle."""
        # Start suite
        suite = self.benchmark.start_benchmark_suite("test_suite")

        self.assertIsNotNone(suite)
        self.assertEqual(suite.suite_name, "test_suite")
        self.assertIsNotNone(suite.start_time)
        self.assertIsNone(suite.end_time)
        self.assertEqual(self.benchmark.current_suite, suite)

        # Add some mock results
        result = PerformanceResult(
            "test", BenchmarkCategory.EVENT_GENERATION,
            BenchmarkMetric.EXECUTION_TIME, 1.0, "seconds", 1.0
        )
        suite.add_result(result)

        # Finish suite
        time.sleep(0.01)  # Ensure some time passes
        finished_suite = self.benchmark.finish_benchmark_suite()

        self.assertEqual(finished_suite, suite)
        self.assertIsNotNone(finished_suite.end_time)
        self.assertGreater(finished_suite.total_execution_time, 0)
        self.assertIsNone(self.benchmark.current_suite)

    def test_baseline_comparison_calculation(self):
        """Test baseline comparison calculations."""
        # Set up baseline data
        self.benchmark.baseline_data = {
            'end_to_end_execution_time': 180.0  # 3 minutes baseline
        }

        # Create current result (1 minute = 66.7% improvement)
        current_result = PerformanceResult(
            "end_to_end_test",
            BenchmarkCategory.END_TO_END,
            BenchmarkMetric.EXECUTION_TIME,
            60.0,  # 1 minute
            "seconds",
            60.0
        )

        comparison = self.benchmark.compare_with_baseline(
            current_result, 'end_to_end_execution_time'
        )

        self.assertIsNotNone(comparison)
        self.assertEqual(comparison.baseline_value, 180.0)
        self.assertEqual(comparison.current_value, 60.0)
        self.assertAlmostEqual(comparison.improvement_percent, 66.67, places=1)
        self.assertAlmostEqual(comparison.improvement_absolute, 120.0, places=1)
        self.assertTrue(comparison.meets_target)  # 66.7% > 65% target

    def test_baseline_comparison_miss_target(self):
        """Test baseline comparison when target is missed."""
        # Set up baseline data
        self.benchmark.baseline_data = {
            'end_to_end_execution_time': 180.0
        }

        # Create current result (90 seconds = 50% improvement)
        current_result = PerformanceResult(
            "end_to_end_test",
            BenchmarkCategory.END_TO_END,
            BenchmarkMetric.EXECUTION_TIME,
            90.0,
            "seconds",
            90.0
        )

        comparison = self.benchmark.compare_with_baseline(
            current_result, 'end_to_end_execution_time'
        )

        self.assertIsNotNone(comparison)
        self.assertEqual(comparison.baseline_value, 180.0)
        self.assertEqual(comparison.current_value, 90.0)
        self.assertEqual(comparison.improvement_percent, 50.0)
        self.assertEqual(comparison.improvement_absolute, 90.0)
        self.assertFalse(comparison.meets_target)  # 50% < 65% target

    def test_baseline_comparison_no_data(self):
        """Test baseline comparison with no baseline data."""
        current_result = PerformanceResult(
            "test", BenchmarkCategory.END_TO_END,
            BenchmarkMetric.EXECUTION_TIME, 60.0, "seconds", 60.0
        )

        comparison = self.benchmark.compare_with_baseline(
            current_result, 'nonexistent_key'
        )

        self.assertIsNone(comparison)

    def test_performance_report_generation(self):
        """Test performance report generation."""
        # Create a suite with some results
        suite = BenchmarkSuite("test_suite")
        suite.start_time = datetime.now()
        suite.end_time = suite.start_time + timedelta(seconds=10)
        suite.total_execution_time = 10.0

        # Add various results
        result1 = PerformanceResult(
            "end_to_end", BenchmarkCategory.END_TO_END,
            BenchmarkMetric.EXECUTION_TIME, 60.0, "seconds", 60.0,
            metadata={'events_per_second': 1000}
        )
        result2 = PerformanceResult(
            "batch_ops", BenchmarkCategory.DATABASE_OPERATIONS,
            BenchmarkMetric.THROUGHPUT, 500.0, "ops/sec", 2.0
        )

        suite.add_result(result1)
        suite.add_result(result2)

        # Set baseline data for comparison
        self.benchmark.baseline_data = {
            'end_to_end_execution_time': 180.0
        }

        report = self.benchmark.generate_performance_report(suite)

        # Validate report structure
        self.assertIn('suite_info', report)
        self.assertIn('performance_summary', report)
        self.assertIn('category_analysis', report)
        self.assertIn('baseline_comparisons', report)
        self.assertIn('recommendations', report)
        self.assertIn('detailed_results', report)
        self.assertIn('metadata', report)

        # Validate suite info
        suite_info = report['suite_info']
        self.assertEqual(suite_info['name'], 'test_suite')
        self.assertEqual(suite_info['total_results'], 2)
        self.assertEqual(suite_info['duration_seconds'], 10.0)

        # Validate performance summary
        perf_summary = report['performance_summary']
        self.assertEqual(perf_summary['total_benchmarks'], 2)
        self.assertEqual(perf_summary['categories_tested'], 2)
        self.assertEqual(perf_summary['best_end_to_end_time'], 60.0)
        self.assertEqual(perf_summary['best_end_to_end_throughput'], 1000)

        # Validate baseline comparisons
        baseline_comparisons = report['baseline_comparisons']
        self.assertTrue(baseline_comparisons['available'])
        self.assertIn('end_to_end', baseline_comparisons['results'])


class TestBenchmarkUtilities(unittest.TestCase):
    """Test cases for benchmark utility functions."""

    def test_create_performance_benchmark(self):
        """Test benchmark factory function."""
        mock_db_manager = Mock(spec=DatabaseManager)
        mock_config = Mock(spec=OrchestrationConfig)

        with patch('orchestrator_dbt.benchmarking.performance_benchmark.BatchEventGenerator'), \
             patch('orchestrator_dbt.benchmarking.performance_benchmark.WorkforceCalculator'), \
             patch('orchestrator_dbt.benchmarking.performance_benchmark.CompensationProcessor'), \
             patch('orchestrator_dbt.benchmarking.performance_benchmark.EligibilityProcessor'), \
             patch('orchestrator_dbt.benchmarking.performance_benchmark.create_id_generator_from_config'):

            benchmark = create_performance_benchmark(
                database_manager=mock_db_manager,
                config=mock_config
            )

            self.assertIsInstance(benchmark, PerformanceBenchmark)
            self.assertEqual(benchmark.db_manager, mock_db_manager)
            self.assertEqual(benchmark.config, mock_config)
            self.assertTrue(benchmark.enable_memory_monitoring)
            self.assertTrue(benchmark.enable_cpu_monitoring)


class TestBenchmarkCLI(unittest.TestCase):
    """Test cases for benchmark CLI functionality."""

    def test_cli_imports(self):
        """Test CLI script imports work correctly."""
        try:
            from orchestrator_dbt.benchmarking.run_benchmark import (
                setup_logging,
                parse_benchmark_categories,
                create_baseline_data_template
            )
            self.assertTrue(True)  # Import successful
        except ImportError as e:
            self.fail(f"CLI import failed: {str(e)}")

    def test_category_parsing(self):
        """Test benchmark category parsing."""
        from orchestrator_dbt.benchmarking.run_benchmark import parse_benchmark_categories

        # Test single category
        result = parse_benchmark_categories("end_to_end")
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0], BenchmarkCategory.END_TO_END)

        # Test multiple categories
        result = parse_benchmark_categories("end_to_end,batch_operations")
        self.assertEqual(len(result), 2)
        self.assertIn(BenchmarkCategory.END_TO_END, result)
        self.assertIn(BenchmarkCategory.DATABASE_OPERATIONS, result)

        # Test None input
        result = parse_benchmark_categories(None)
        self.assertIsNone(result)

    def test_baseline_template_creation(self):
        """Test baseline data template creation."""
        from orchestrator_dbt.benchmarking.run_benchmark import create_baseline_data_template

        template = create_baseline_data_template()

        self.assertIsInstance(template, dict)
        self.assertIn('end_to_end_execution_time', template)
        self.assertIn('metadata', template)
        self.assertEqual(template['metadata']['system'], 'orchestrator_mvp')


class TestBenchmarkIntegration(unittest.TestCase):
    """Integration tests for benchmark system."""

    def setUp(self):
        """Set up integration test fixtures."""
        self.temp_dir = tempfile.mkdtemp()
        self.temp_path = Path(self.temp_dir)

    def tearDown(self):
        """Clean up test fixtures."""
        import shutil
        shutil.rmtree(self.temp_dir)

    @patch('orchestrator_dbt.benchmarking.performance_benchmark.BatchEventGenerator')
    @patch('orchestrator_dbt.benchmarking.performance_benchmark.WorkforceCalculator')
    @patch('orchestrator_dbt.benchmarking.performance_benchmark.CompensationProcessor')
    @patch('orchestrator_dbt.benchmarking.performance_benchmark.EligibilityProcessor')
    @patch('orchestrator_dbt.benchmarking.performance_benchmark.create_id_generator_from_config')
    def test_report_generation_and_save(self, mock_id_gen, mock_eligibility, mock_comp, mock_workforce, mock_event_gen):
        """Test report generation and file saving."""
        # Mock component methods to return quickly
        mock_event_gen.return_value.generate_termination_events.return_value = []
        mock_event_gen.return_value.generate_hiring_events.return_value = []
        mock_event_gen.return_value.generate_merit_events.return_value = []
        mock_event_gen.return_value.generate_promotion_events.return_value = []
        mock_event_gen.return_value.store_events_in_database.return_value = None

        mock_workforce.return_value.calculate_workforce_requirements.return_value = Mock(
            terminations_needed=100, hires_needed=150
        )

        mock_comp.return_value.process_annual_compensation_cycle.return_value = {
            'merit_calculations': []
        }

        mock_eligibility.return_value.get_eligible_employees.return_value = []
        mock_id_gen.return_value.generate_batch_employee_ids.return_value = []

        # Create benchmark system
        mock_db_manager = MockDatabaseManager()
        mock_config = Mock(spec=OrchestrationConfig)

        benchmark = PerformanceBenchmark(
            database_manager=mock_db_manager,
            config=mock_config,
            enable_memory_monitoring=False,
            enable_cpu_monitoring=False
        )

        # Run a simple benchmark
        suite = benchmark.start_benchmark_suite("integration_test")

        # Simulate end-to-end benchmark with mocked timing
        start_time = time.time()
        time.sleep(0.01)  # Minimal actual work
        end_time = time.time()

        result = PerformanceResult(
            benchmark_name="mock_end_to_end",
            category=BenchmarkCategory.END_TO_END,
            metric=BenchmarkMetric.EXECUTION_TIME,
            value=end_time - start_time,
            unit="seconds",
            execution_time=end_time - start_time,
            metadata={'events_per_second': 1000, 'simulation_year': 2025}
        )

        suite.add_result(result)
        suite = benchmark.finish_benchmark_suite()

        # Generate and save report
        report_path = self.temp_path / "test_report.json"
        report = benchmark.generate_performance_report(suite, report_path)

        # Verify report structure
        self.assertIn('suite_info', report)
        self.assertIn('performance_summary', report)
        self.assertIn('detailed_results', report)

        # Verify file was created and is valid JSON
        self.assertTrue(report_path.exists())

        with open(report_path, 'r') as f:
            loaded_report = json.load(f)

        self.assertEqual(loaded_report['suite_info']['name'], 'integration_test')
        self.assertEqual(loaded_report['performance_summary']['total_benchmarks'], 1)


def run_test_suite():
    """Run the complete benchmark test suite."""
    print("🧪 Running Performance Benchmark Test Suite")
    print("="*60)

    # Create test suite
    loader = unittest.TestLoader()
    suite = unittest.TestSuite()

    # Add test cases
    suite.addTests(loader.loadTestsFromTestCase(TestPerformanceResult))
    suite.addTests(loader.loadTestsFromTestCase(TestBenchmarkSuite))
    suite.addTests(loader.loadTestsFromTestCase(TestComparisonResult))
    suite.addTests(loader.loadTestsFromTestCase(TestPerformanceBenchmark))
    suite.addTests(loader.loadTestsFromTestCase(TestBenchmarkUtilities))
    suite.addTests(loader.loadTestsFromTestCase(TestBenchmarkCLI))
    suite.addTests(loader.loadTestsFromTestCase(TestBenchmarkIntegration))

    # Run tests
    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)

    # Print summary
    print("\n" + "="*60)
    print(f"🧪 Test Summary:")
    print(f"   Tests run: {result.testsRun}")
    print(f"   Failures: {len(result.failures)}")
    print(f"   Errors: {len(result.errors)}")
    print(f"   Success rate: {((result.testsRun - len(result.failures) - len(result.errors)) / result.testsRun * 100):.1f}%")

    if result.wasSuccessful():
        print("✅ All benchmark tests passed!")
        return True
    else:
        print("❌ Some benchmark tests failed!")
        return False


if __name__ == '__main__':
    success = run_test_suite()
    exit(0 if success else 1)
