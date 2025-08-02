"""
Performance Benchmarking Suite for orchestrator_dbt.

This package provides comprehensive performance benchmarking capabilities
to measure and validate the 65% improvement target achieved by migrating
event generation from orchestrator_mvp to orchestrator_dbt.

Key Components:
- PerformanceBenchmark: Main benchmarking system with comprehensive metrics
- BenchmarkSuite: Collection of related performance benchmarks
- PerformanceResult: Individual performance measurement results
- ComparisonResult: Baseline comparison analysis

Usage:
    from orchestrator_dbt.benchmarking import (
        create_performance_benchmark,
        run_comprehensive_benchmark
    )

    # Create benchmark system
    benchmark = create_performance_benchmark(database_manager, config)

    # Run comprehensive benchmarks
    report = run_comprehensive_benchmark(
        database_manager,
        config,
        simulation_year=2025,
        output_path=Path("performance_report.json")
    )

    # Check if performance target is met
    if report['baseline_comparisons']['available']:
        improvement = report['baseline_comparisons']['results']['end_to_end']['improvement_percent']
        if improvement >= 65.0:
            print(f"✅ Target achieved: {improvement:.1f}% improvement")
        else:
            print(f"❌ Target missed: {improvement:.1f}% improvement")
"""

from .performance_benchmark import (
    PerformanceBenchmark,
    BenchmarkSuite,
    PerformanceResult,
    ComparisonResult,
    BenchmarkCategory,
    BenchmarkMetric,
    create_performance_benchmark,
    run_comprehensive_benchmark
)

__all__ = [
    'PerformanceBenchmark',
    'BenchmarkSuite',
    'PerformanceResult',
    'ComparisonResult',
    'BenchmarkCategory',
    'BenchmarkMetric',
    'create_performance_benchmark',
    'run_comprehensive_benchmark'
]
