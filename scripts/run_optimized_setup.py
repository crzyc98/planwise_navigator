#!/usr/bin/env python3
"""
Demonstration script for the optimized orchestrator_dbt system.

This script showcases the performance improvements achieved through:
- Batch dbt operations
- Parallel processing
- DuckDB optimizations
- Intelligent fallback strategies
"""

import sys
import os
import time
from pathlib import Path

# Add the project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from orchestrator_mvp.core.common_workflow import (
    run_full_optimized_setup,
    load_seed_data_and_build_staging_optimized,
    clear_database_and_setup
)
from orchestrator_mvp.core.duckdb_optimizations import (
    apply_duckdb_optimizations,
    optimize_dbt_execution_environment,
    create_performance_indexes
)
from orchestrator_mvp.utils.performance_benchmark import PerformanceBenchmark


def demonstrate_optimizations():
    """Demonstrate the optimized orchestrator_dbt system."""

    print("🚀 ORCHESTRATOR_DBT OPTIMIZATION DEMONSTRATION")
    print("="*80)
    print("This script demonstrates significant performance improvements through:")
    print("  • Batch dbt operations (reduce startup overhead)")
    print("  • Parallel processing (utilize multiple cores)")
    print("  • DuckDB optimizations (memory and query tuning)")
    print("  • Intelligent fallback strategies (robust error handling)")
    print("="*80)

    benchmark = PerformanceBenchmark()

    # Step 1: Environment optimization
    print("\n📋 STEP 1: ENVIRONMENT OPTIMIZATION")
    print("-" * 50)

    with benchmark.measure("environment_optimization"):
        env_results = optimize_dbt_execution_environment()
        print(f"Applied {len(env_results['environment_variables'])} environment optimizations")

    # Step 2: DuckDB optimizations
    print("\n📋 STEP 2: DUCKDB OPTIMIZATIONS")
    print("-" * 50)

    with benchmark.measure("duckdb_optimizations"):
        duck_results = apply_duckdb_optimizations()
        total_settings = (len(duck_results['memory_optimizations']) +
                         len(duck_results['query_optimizations']) +
                         len(duck_results['io_optimizations']))
        print(f"Applied {total_settings} DuckDB performance settings")

    # Step 3: Full optimized setup
    print("\n📋 STEP 3: OPTIMIZED SETUP WORKFLOW")
    print("-" * 50)

    with benchmark.measure("full_optimized_setup"):
        run_full_optimized_setup()

    # Step 4: Create performance indexes
    print("\n📋 STEP 4: PERFORMANCE INDEX CREATION")
    print("-" * 50)

    with benchmark.measure("performance_indexes"):
        index_results = create_performance_indexes()
        print(f"Created {len(index_results['indexes_created'])} performance indexes")

    # Step 5: Performance summary
    print("\n📋 STEP 5: PERFORMANCE SUMMARY")
    print("-" * 50)

    benchmark.print_summary()

    # Calculate expected vs actual improvements
    setup_time = next(r.execution_time for r in benchmark.results if r.name == "full_optimized_setup")

    print(f"\n🎯 OPTIMIZATION RESULTS:")
    print(f"  • Total optimized setup time: {setup_time:.2f}s")
    print(f"  • Estimated traditional time: ~47s (based on current metrics)")
    print(f"  • Performance improvement: ~{((47 - setup_time) / 47) * 100:.0f}% faster")
    print(f"  • Time saved: ~{47 - setup_time:.1f}s")

    print("\n✅ OPTIMIZATION DEMONSTRATION COMPLETE!")
    print("The system is now ready for high-performance simulation workloads.")

    return benchmark


def run_quick_benchmark():
    """Run a quick performance benchmark of key operations."""

    print("\n🏁 QUICK PERFORMANCE BENCHMARK")
    print("="*60)

    benchmark = PerformanceBenchmark()

    # Test batch vs individual operations
    from orchestrator_mvp.loaders import run_dbt_batch_seeds, run_dbt_seed

    # Quick seed loading test
    test_seeds = ["config_job_levels", "comp_levers", "config_cola_by_year"]

    def individual_approach():
        for seed in test_seeds:
            run_dbt_seed(seed)

    def batch_approach():
        run_dbt_batch_seeds(test_seeds)

    approaches = {
        "individual_seeds": individual_approach,
        "batch_seeds": batch_approach
    }

    results = benchmark.compare_approaches(approaches)

    benchmark.print_summary()

    return benchmark


def main():
    """Main demonstration function."""

    if len(sys.argv) > 1 and sys.argv[1] == "--quick":
        # Quick benchmark mode
        run_quick_benchmark()
    else:
        # Full demonstration mode
        demonstrate_optimizations()


if __name__ == "__main__":
    main()
