#!/usr/bin/env python3
"""
Example usage of the multi-year coordination performance benchmark suite.

This script demonstrates how to use the benchmark programmatically
and shows different ways to analyze performance results.
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from scripts.benchmark_multi_year_coordination import CoordinationBenchmark, BenchmarkScenario
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger(__name__)


def example_basic_benchmark():
    """Example: Run a basic benchmark for a single scenario."""
    print("=" * 60)
    print("EXAMPLE 1: Basic Single Scenario Benchmark")
    print("=" * 60)

    # Initialize benchmark
    benchmark = CoordinationBenchmark(verbose=False)

    # Run benchmark for small scenario
    report = benchmark.run_all_scenarios(['small'])

    # Print results
    print(f"\nResults Summary:")
    print(f"Performance Grade: {report.performance_grade}")
    print(f"Average Overhead Reduction: {report.average_overhead_reduction_percent:.1f}%")
    print(f"Target Achieved: {'✅ YES' if report.overall_target_achieved else '❌ NO'}")

    # Show component breakdown
    if 'small' in report.integration_results:
        result = report.integration_results['small']
        print(f"\nComponent Performance Breakdown:")
        for component_name, component_result in result.component_results.items():
            improvement = component_result.time_improvement_percent
            print(f"  {component_name}: {improvement:+.1f}% time improvement")


def example_component_analysis():
    """Example: Analyze individual component performance."""
    print("\n" + "=" * 60)
    print("EXAMPLE 2: Individual Component Analysis")
    print("=" * 60)

    benchmark = CoordinationBenchmark(verbose=False)

    # Create a custom test scenario
    custom_scenario = BenchmarkScenario(
        name='custom',
        workforce_size=500,
        simulation_years=[2024, 2025],
        events_per_employee_per_year=4,
        description='Custom test scenario'
    )

    # Test each component individually
    components = [
        ('CrossYearCostAttributor', benchmark.benchmark_cost_attribution),
        ('IntelligentCacheManager', benchmark.benchmark_cache_manager),
        ('CoordinationOptimizer', benchmark.benchmark_coordination_optimizer),
        ('ResourceOptimizer', benchmark.benchmark_resource_optimizer)
    ]

    print("\nComponent Performance Analysis:")
    print("-" * 40)

    for component_name, benchmark_func in components:
        try:
            # Run baseline
            baseline_result = benchmark_func(custom_scenario, enable_optimization=False)
            # Run optimized
            optimized_result = benchmark_func(custom_scenario, enable_optimization=True)

            # Calculate improvements
            time_improvement = optimized_result.time_improvement_percent if optimized_result.optimized_time_seconds > 0 else 0
            memory_improvement = optimized_result.memory_improvement_percent if optimized_result.memory_optimized_mb > 0 else 0

            print(f"\n{component_name}:")
            print(f"  Time: {baseline_result.baseline_time_seconds:.3f}s → {optimized_result.optimized_time_seconds:.3f}s ({time_improvement:+.1f}%)")
            print(f"  Memory: {baseline_result.memory_baseline_mb:.1f}MB → {optimized_result.memory_optimized_mb:.1f}MB ({memory_improvement:+.1f}%)")

        except Exception as e:
            print(f"\n{component_name}: ❌ Error - {e}")


def example_comprehensive_analysis():
    """Example: Run comprehensive analysis with reporting."""
    print("\n" + "=" * 60)
    print("EXAMPLE 3: Comprehensive Multi-Scenario Analysis")
    print("=" * 60)

    benchmark = CoordinationBenchmark(verbose=False)

    # Run all scenarios
    report = benchmark.run_all_scenarios()

    print(f"\nComprehensive Analysis Results:")
    print(f"Overall Performance Grade: {report.performance_grade}")
    print(f"Average Overhead Reduction: {report.average_overhead_reduction_percent:.1f}%")
    print(f"Scenarios Tested: {len(report.scenarios_tested)}")

    # Analyze by scenario
    print(f"\nResults by Scenario:")
    print("-" * 30)

    for scenario_name, result in report.integration_results.items():
        status = "✅ PASS" if result.target_achieved else "❌ FAIL"
        print(f"{scenario_name.title()}: {result.coordination_overhead_reduction_percent:.1f}% reduction {status}")

    # Find best and worst performing scenarios
    if report.integration_results:
        scenarios_by_performance = sorted(
            report.integration_results.items(),
            key=lambda x: x[1].coordination_overhead_reduction_percent,
            reverse=True
        )

        best_scenario, best_result = scenarios_by_performance[0]
        worst_scenario, worst_result = scenarios_by_performance[-1]

        print(f"\nBest Performer: {best_scenario} ({best_result.coordination_overhead_reduction_percent:.1f}%)")
        print(f"Worst Performer: {worst_scenario} ({worst_result.coordination_overhead_reduction_percent:.1f}%)")

    # Generate detailed report
    detailed_report = benchmark.generate_detailed_report(report)
    print(f"\nDetailed Report Preview:")
    print("-" * 30)
    # Show first 20 lines of the report
    report_lines = detailed_report.split('\n')[:20]
    for line in report_lines:
        print(line)
    print("... (report truncated)")


def example_target_validation():
    """Example: Validate against specific performance targets."""
    print("\n" + "=" * 60)
    print("EXAMPLE 4: Performance Target Validation")
    print("=" * 60)

    benchmark = CoordinationBenchmark(verbose=False)

    # Define performance targets
    targets = {
        'minimum_overhead_reduction': 65.0,  # 65% minimum reduction
        'maximum_acceptable_grade': 'B',     # B grade or better
        'required_scenarios_passing': 0.8   # 80% of scenarios must pass
    }

    print(f"Performance Targets:")
    for target, value in targets.items():
        print(f"  {target}: {value}")

    # Run benchmark
    report = benchmark.run_all_scenarios(['small', 'medium'])  # Test with 2 scenarios

    # Validate against targets
    results = {
        'average_reduction': report.average_overhead_reduction_percent,
        'performance_grade': report.performance_grade,
        'passing_rate': len([r for r in report.integration_results.values() if r.target_achieved]) / len(report.integration_results) if report.integration_results else 0
    }

    print(f"\nActual Results:")
    print(f"  Average Overhead Reduction: {results['average_reduction']:.1f}%")
    print(f"  Performance Grade: {results['performance_grade']}")
    print(f"  Scenarios Passing Rate: {results['passing_rate']:.1%}")

    # Check if targets are met
    target_validations = {
        'overhead_reduction': results['average_reduction'] >= targets['minimum_overhead_reduction'],
        'grade_acceptable': results['performance_grade'] in ['A+', 'A', 'B+', 'B'],
        'passing_rate_ok': results['passing_rate'] >= targets['required_scenarios_passing']
    }

    print(f"\nTarget Validation:")
    for validation, passed in target_validations.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {validation}: {status}")

    overall_pass = all(target_validations.values())
    print(f"\nOverall Target Achievement: {'✅ PASS' if overall_pass else '❌ FAIL'}")

    return overall_pass


def main():
    """Run all benchmark examples."""
    print("Multi-Year Coordination Performance Benchmark Examples")
    print("=" * 60)

    try:
        # Run examples
        example_basic_benchmark()
        example_component_analysis()
        example_comprehensive_analysis()
        target_achieved = example_target_validation()

        print("\n" + "=" * 60)
        print("EXAMPLES COMPLETED")
        print("=" * 60)
        print("\nFor more advanced usage:")
        print("  python scripts/benchmark_multi_year_coordination.py --help")
        print("  python scripts/benchmark_multi_year_coordination.py --all-scenarios --generate-report")

        # Exit with appropriate code based on target achievement
        return 0 if target_achieved else 1

    except KeyboardInterrupt:
        print("\n\nExamples interrupted by user")
        return 130
    except Exception as e:
        print(f"\n\nExample failed with error: {e}")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
