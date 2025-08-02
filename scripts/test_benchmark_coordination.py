#!/usr/bin/env python3
"""
Quick validation test for the multi-year coordination benchmark suite.

This script validates that the benchmark can run successfully with the existing
codebase and produces meaningful results. It runs a minimal test to verify
all components work together correctly.

Usage:
    python scripts/test_benchmark_coordination.py
"""

import sys
import logging
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.benchmark_multi_year_coordination import CoordinationBenchmark, BenchmarkScenario

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def create_minimal_test_scenario() -> BenchmarkScenario:
    """Create a minimal test scenario for validation."""
    return BenchmarkScenario(
        name='test',
        workforce_size=100,  # Very small workforce for quick testing
        simulation_years=[2024, 2025],
        events_per_employee_per_year=2,
        description='Minimal test scenario for validation'
    )


def test_component_benchmarks():
    """Test individual component benchmarks."""
    logger.info("Testing individual component benchmarks...")

    benchmark = CoordinationBenchmark(verbose=False)
    scenario = create_minimal_test_scenario()

    components_to_test = [
        ('CrossYearCostAttributor', benchmark.benchmark_cost_attribution),
        ('IntelligentCacheManager', benchmark.benchmark_cache_manager),
        ('CoordinationOptimizer', benchmark.benchmark_coordination_optimizer),
        ('ResourceOptimizer', benchmark.benchmark_resource_optimizer)
    ]

    success_count = 0
    total_count = len(components_to_test)

    for component_name, benchmark_func in components_to_test:
        try:
            logger.info(f"Testing {component_name}...")

            # Test baseline
            baseline_result = benchmark_func(scenario, enable_optimization=False)
            logger.info(f"  Baseline: {baseline_result.baseline_time_seconds:.3f}s")

            # Test optimized
            optimized_result = benchmark_func(scenario, enable_optimization=True)
            logger.info(f"  Optimized: {optimized_result.optimized_time_seconds:.3f}s")

            success_count += 1
            logger.info(f"✅ {component_name} benchmark test passed")

        except Exception as e:
            logger.error(f"❌ {component_name} benchmark test failed: {e}")

    logger.info(f"Component benchmark tests: {success_count}/{total_count} passed")
    return success_count == total_count


def test_integration_benchmark():
    """Test integration benchmark."""
    logger.info("Testing integration benchmark...")

    try:
        benchmark = CoordinationBenchmark(verbose=False)
        scenario = create_minimal_test_scenario()

        integration_result = benchmark.run_integration_benchmark(scenario)

        logger.info(f"Integration test results:")
        logger.info(f"  Total time improvement: {integration_result.total_time_improvement_percent:.1f}%")
        logger.info(f"  Coordination overhead reduction: {integration_result.coordination_overhead_reduction_percent:.1f}%")
        logger.info(f"  Target achieved: {integration_result.target_achieved}")

        # Verify we got results for all components
        expected_components = {'cost_attribution', 'cache_manager', 'coordination_optimizer', 'resource_optimizer'}
        actual_components = set(integration_result.component_results.keys())

        if expected_components == actual_components:
            logger.info("✅ Integration benchmark test passed")
            return True
        else:
            missing = expected_components - actual_components
            logger.error(f"❌ Integration benchmark test failed: missing components {missing}")
            return False

    except Exception as e:
        logger.error(f"❌ Integration benchmark test failed: {e}")
        return False


def test_report_generation():
    """Test report generation."""
    logger.info("Testing report generation...")

    try:
        benchmark = CoordinationBenchmark(verbose=False)

        # Run a minimal benchmark
        report = benchmark.run_all_scenarios(['small'])  # Use built-in small scenario

        # Test detailed report generation
        detailed_report = benchmark.generate_detailed_report(report)

        # Verify report contains expected sections
        expected_sections = [
            'EXECUTIVE SUMMARY',
            'SYSTEM INFORMATION',
            'DETAILED RESULTS BY SCENARIO',
            'PERFORMANCE ANALYSIS',
            'RECOMMENDATIONS'
        ]

        missing_sections = []
        for section in expected_sections:
            if section not in detailed_report:
                missing_sections.append(section)

        if not missing_sections:
            logger.info("✅ Report generation test passed")
            return True
        else:
            logger.error(f"❌ Report generation test failed: missing sections {missing_sections}")
            return False

    except Exception as e:
        logger.error(f"❌ Report generation test failed: {e}")
        return False


def main():
    """Run validation tests."""
    logger.info("Starting multi-year coordination benchmark validation tests")
    logger.info("=" * 60)

    tests = [
        ('Component Benchmarks', test_component_benchmarks),
        ('Integration Benchmark', test_integration_benchmark),
        ('Report Generation', test_report_generation)
    ]

    passed_tests = 0
    total_tests = len(tests)

    for test_name, test_func in tests:
        logger.info(f"\nRunning {test_name} test...")
        logger.info("-" * 40)

        try:
            if test_func():
                passed_tests += 1
            else:
                logger.error(f"Test failed: {test_name}")
        except Exception as e:
            logger.error(f"Test error in {test_name}: {e}")

    logger.info("\n" + "=" * 60)
    logger.info(f"Validation Results: {passed_tests}/{total_tests} tests passed")

    if passed_tests == total_tests:
        logger.info("🎉 All validation tests passed! Benchmark suite is ready to use.")
        logger.info("\nTo run the full benchmark suite:")
        logger.info("  python scripts/benchmark_multi_year_coordination.py --scenario small")
        logger.info("  python scripts/benchmark_multi_year_coordination.py --all-scenarios --generate-report")
        return True
    else:
        logger.error("❌ Some validation tests failed. Please check the errors above.")
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
