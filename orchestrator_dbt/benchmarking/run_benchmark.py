#!/usr/bin/env python3
"""
Command-line interface for running performance benchmarks for Story S031-03.

This script provides comprehensive performance benchmarking capabilities to
measure and validate the 65% improvement target achieved by migrating event
generation from orchestrator_mvp to orchestrator_dbt.

Usage:
    # Run comprehensive benchmark suite
    python orchestrator_dbt/benchmarking/run_benchmark.py

    # Run specific benchmark categories
    python orchestrator_dbt/benchmarking/run_benchmark.py --categories end_to_end,batch_operations

    # Compare with MVP baseline data
    python orchestrator_dbt/benchmarking/run_benchmark.py --baseline baseline_results.json

    # Run with custom parameters
    python orchestrator_dbt/benchmarking/run_benchmark.py --year 2025 --workforce-size 250000

    # Generate detailed report
    python orchestrator_dbt/benchmarking/run_benchmark.py --report performance_report.json --verbose

Integration with Story S031-03:
- Validates 65% performance improvement target achievement
- Measures batch SQL operation efficiency gains
- Provides comprehensive performance reporting for stakeholders
- Enables performance regression detection in CI/CD pipeline
"""

import argparse
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from orchestrator_dbt.core.database_manager import DatabaseManager
from orchestrator_dbt.core.config import OrchestrationConfig
from orchestrator_dbt.benchmarking import (
    create_performance_benchmark,
    run_comprehensive_benchmark,
    BenchmarkCategory,
    PerformanceBenchmark
)


def setup_logging(verbose: bool = False) -> None:
    """Set up logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO

    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(sys.stdout),
        ]
    )


def parse_benchmark_categories(categories_arg: Optional[str]) -> Optional[List[BenchmarkCategory]]:
    """Parse benchmark categories argument."""
    if not categories_arg:
        return None

    category_mapping = {
        'event_generation': BenchmarkCategory.EVENT_GENERATION,
        'workforce_calculation': BenchmarkCategory.WORKFORCE_CALCULATION,
        'compensation_processing': BenchmarkCategory.COMPENSATION_PROCESSING,
        'eligibility_processing': BenchmarkCategory.ELIGIBILITY_PROCESSING,
        'id_generation': BenchmarkCategory.ID_GENERATION,
        'database_operations': BenchmarkCategory.DATABASE_OPERATIONS,
        'end_to_end': BenchmarkCategory.END_TO_END,
        'batch_operations': BenchmarkCategory.DATABASE_OPERATIONS  # Alias
    }

    categories = [s.strip() for s in categories_arg.split(',')]
    selected_categories = []

    for category in categories:
        if category in category_mapping:
            selected_categories.append(category_mapping[category])
        else:
            print(f"⚠️ Unknown benchmark category: {category}")
            print(f"Available categories: {', '.join(category_mapping.keys())}")
            sys.exit(1)

    return selected_categories


def print_benchmark_summary(report: Dict[str, Any], verbose: bool = False) -> None:
    """Print benchmark summary to console."""
    print("\n" + "="*80)
    print("🚀 PERFORMANCE BENCHMARK RESULTS - STORY S031-03")
    print("="*80)

    suite_info = report['suite_info']
    perf_summary = report['performance_summary']

    # Overall summary
    print(f"\n📊 Benchmark Suite: {suite_info['name']}")
    print(f"⏱️  Total Duration: {suite_info['duration_seconds']:.3f}s")
    print(f"📈 Total Benchmarks: {perf_summary['total_benchmarks']}")
    print(f"🎯 Categories Tested: {perf_summary['categories_tested']}")

    # Key performance metrics
    if 'best_end_to_end_time' in perf_summary:
        print(f"\n🏆 Key Performance Metrics:")
        print(f"   Best End-to-End Time: {perf_summary['best_end_to_end_time']:.3f}s")
        if 'best_end_to_end_throughput' in perf_summary:
            print(f"   Peak Throughput: {perf_summary['best_end_to_end_throughput']:.0f} events/sec")

    # Baseline comparison
    baseline_comparisons = report.get('baseline_comparisons', {})
    if baseline_comparisons.get('available', False):
        print(f"\n📊 Baseline Comparison (vs MVP):")

        end_to_end_comparison = baseline_comparisons.get('results', {}).get('end_to_end', {})
        if end_to_end_comparison:
            improvement = end_to_end_comparison['improvement_percent']
            meets_target = end_to_end_comparison['meets_target']

            status_icon = "✅" if meets_target else "❌"
            target_status = "TARGET MET" if meets_target else "TARGET MISSED"

            print(f"   {status_icon} End-to-End Performance: {improvement:+.1f}% improvement ({target_status})")
            print(f"   📍 Target: 65% improvement")
            print(f"   📊 Baseline: {end_to_end_comparison['baseline_value']:.3f}s")
            print(f"   📊 Current: {end_to_end_comparison['current_value']:.3f}s")
    else:
        print(f"\n📊 Baseline Comparison: No baseline data available")

    # Category analysis
    if verbose:
        category_analysis = report.get('category_analysis', {})
        if category_analysis:
            print(f"\n📂 Performance by Category:")
            for category, analysis in category_analysis.items():
                print(f"   {category}:")
                print(f"      Benchmarks: {analysis['benchmark_count']}")
                print(f"      Avg Execution: {analysis['avg_execution_time']:.3f}s")
                if 'peak_throughput' in analysis:
                    print(f"      Peak Throughput: {analysis['peak_throughput']:.0f}/sec")

    # Recommendations
    recommendations = report.get('recommendations', [])
    if recommendations:
        print(f"\n💡 Performance Recommendations:")
        for i, rec in enumerate(recommendations, 1):
            print(f"   {i}. {rec}")

    # System info
    if verbose:
        system_info = report.get('metadata', {}).get('system_info', {})
        if system_info:
            print(f"\n🖥️ System Information:")
            print(f"   CPU Cores: {system_info.get('cpu_count', 'Unknown')}")
            print(f"   Memory: {system_info.get('memory_total_gb', 0):.1f} GB")
            print(f"   Platform: {system_info.get('platform', 'Unknown')}")


def run_targeted_benchmarks(
    benchmark: PerformanceBenchmark,
    categories: List[BenchmarkCategory],
    simulation_year: int,
    workforce_size: int
) -> None:
    """Run specific benchmark categories."""
    print(f"🎯 Running targeted benchmarks for categories: {[c.value for c in categories]}")

    suite = benchmark.start_benchmark_suite(f"targeted_s031_03_{simulation_year}")

    try:
        for category in categories:
            print(f"\n🔍 Running {category.value} benchmarks...")

            if category == BenchmarkCategory.END_TO_END:
                benchmark.benchmark_event_generation_end_to_end(
                    simulation_year, workforce_size, iterations=3
                )

            elif category == BenchmarkCategory.DATABASE_OPERATIONS:
                benchmark.benchmark_batch_sql_operations(simulation_year)

            elif category == BenchmarkCategory.EVENT_GENERATION:
                benchmark.benchmark_memory_efficiency(simulation_year)

            elif category in [
                BenchmarkCategory.WORKFORCE_CALCULATION,
                BenchmarkCategory.COMPENSATION_PROCESSING,
                BenchmarkCategory.ELIGIBILITY_PROCESSING,
                BenchmarkCategory.ID_GENERATION
            ]:
                benchmark.benchmark_component_performance(simulation_year)

            else:
                print(f"⚠️ Category {category.value} not implemented in targeted mode")

    finally:
        benchmark.finish_benchmark_suite()


def validate_performance_target(report: Dict[str, Any]) -> bool:
    """Validate if performance target is met."""
    baseline_comparisons = report.get('baseline_comparisons', {})

    if not baseline_comparisons.get('available', False):
        print("⚠️ Cannot validate performance target - no baseline data available")
        return False

    end_to_end_comparison = baseline_comparisons.get('results', {}).get('end_to_end', {})
    if not end_to_end_comparison:
        print("⚠️ Cannot validate performance target - no end-to-end comparison data")
        return False

    improvement = end_to_end_comparison['improvement_percent']
    meets_target = end_to_end_comparison['meets_target']

    if meets_target:
        print(f"🎉 Performance target achieved! {improvement:.1f}% improvement (target: 65%)")
        return True
    else:
        print(f"💔 Performance target missed. {improvement:.1f}% improvement (target: 65%)")
        return False


def create_baseline_data_template() -> Dict[str, Any]:
    """Create template baseline data for testing purposes."""
    return {
        'end_to_end_execution_time': 180.0,  # 3 minutes (simulated MVP baseline)
        'workforce_calculation_time': 15.0,
        'compensation_processing_time': 45.0,
        'eligibility_processing_time': 20.0,
        'id_generation_throughput': 5000.0,
        'metadata': {
            'system': 'orchestrator_mvp',
            'version': '1.0.0',
            'generated_at': '2024-12-15T10:00:00',
            'description': 'Baseline performance data from MVP system'
        }
    }


def main():
    """Main benchmark CLI entry point."""
    parser = argparse.ArgumentParser(
        description='Run performance benchmarks for Story S031-03 event generation migration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                                    # Run comprehensive benchmark
  %(prog)s --categories end_to_end            # Run only end-to-end benchmark
  %(prog)s --baseline baseline.json          # Compare with MVP baseline
  %(prog)s --year 2025 --workforce-size 500000  # Custom parameters
  %(prog)s --report results.json --verbose   # Detailed reporting
        """
    )

    parser.add_argument(
        '--year',
        type=int,
        default=2025,
        help='Simulation year for benchmarking (default: 2025)'
    )

    parser.add_argument(
        '--workforce-size',
        type=int,
        default=100000,
        help='Workforce size for benchmarking (default: 100000)'
    )

    parser.add_argument(
        '--categories',
        type=str,
        help='Comma-separated list of benchmark categories (end_to_end, batch_operations, event_generation, workforce_calculation, compensation_processing, eligibility_processing, id_generation)'
    )

    parser.add_argument(
        '--baseline',
        type=Path,
        help='Path to baseline performance data (MVP results) for comparison'
    )

    parser.add_argument(
        '--create-baseline-template',
        action='store_true',
        help='Create a baseline data template file for testing'
    )

    parser.add_argument(
        '--report',
        type=Path,
        help='Save detailed performance report to JSON file'
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output with detailed metrics'
    )

    parser.add_argument(
        '--config',
        type=Path,
        help='Path to custom configuration file'
    )

    parser.add_argument(
        '--iterations',
        type=int,
        default=3,
        help='Number of iterations for benchmarks (default: 3)'
    )

    args = parser.parse_args()

    # Create baseline template if requested
    if args.create_baseline_template:
        template_path = Path('baseline_template.json')
        template_data = create_baseline_data_template()

        with open(template_path, 'w') as f:
            json.dump(template_data, f, indent=2)

        print(f"📄 Created baseline template: {template_path}")
        print("Edit this file with actual MVP performance data for comparison")
        return

    # Set up logging
    setup_logging(args.verbose)

    print("🚀 Starting Performance Benchmark Suite")
    print(f"📅 Story: S031-03 Event Generation Performance")
    print(f"🎯 Target: 65% performance improvement over MVP")
    print(f"📊 Year: {args.year}, Workforce: {args.workforce_size:,}")

    try:
        # Load configuration
        if args.config:
            config = OrchestrationConfig(args.config)
            print(f"📁 Using custom config: {args.config}")
        else:
            config = OrchestrationConfig()
            print(f"📁 Using default configuration")

        # Initialize database manager
        database_manager = DatabaseManager(config)
        print(f"🗄️ Connected to database: {config.database.path}")

        # Parse benchmark categories
        benchmark_categories = parse_benchmark_categories(args.categories)
        if benchmark_categories:
            category_names = [cat.value for cat in benchmark_categories]
            print(f"🎯 Benchmark scope: {', '.join(category_names)}")
        else:
            print(f"🎯 Benchmark scope: ALL categories")

        # Create benchmark system
        benchmark = create_performance_benchmark(
            database_manager=database_manager,
            config=config,
            baseline_data_path=args.baseline
        )

        if args.baseline:
            print(f"📊 Using baseline data: {args.baseline}")
        else:
            print(f"📊 No baseline data - performance improvements cannot be calculated")

        print(f"\n🏁 Starting benchmark execution...")

        # Run benchmarks
        start_time = time.time()

        if benchmark_categories:
            # Run targeted benchmarks
            run_targeted_benchmarks(
                benchmark, benchmark_categories, args.year, args.workforce_size
            )

            # Generate report manually
            suite = benchmark.current_suite or benchmark.start_benchmark_suite("targeted")
            benchmark.finish_benchmark_suite()
            report = benchmark.generate_performance_report(suite, args.report)

        else:
            # Run comprehensive benchmarks
            report = run_comprehensive_benchmark(
                database_manager=database_manager,
                config=config,
                simulation_year=args.year,
                output_path=args.report
            )

        total_time = time.time() - start_time

        # Print results
        print_benchmark_summary(report, args.verbose)

        # Validate performance target
        target_met = validate_performance_target(report)

        print(f"\n⏱️ Total benchmark time: {total_time:.3f}s")

        if args.report:
            print(f"📄 Detailed report saved to: {args.report}")

        # Exit with appropriate code
        if target_met:
            print(f"\n🎉 Benchmark completed successfully - performance target achieved!")
            sys.exit(0)
        else:
            baseline_available = report.get('baseline_comparisons', {}).get('available', False)
            if baseline_available:
                print(f"\n⚠️ Benchmark completed - performance target not achieved")
                sys.exit(1)
            else:
                print(f"\n✅ Benchmark completed - unable to validate target without baseline data")
                sys.exit(0)

    except KeyboardInterrupt:
        print(f"\n⏹️ Benchmark interrupted by user")
        sys.exit(130)

    except Exception as e:
        print(f"\n💥 Benchmark failed with error: {str(e)}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
