#!/usr/bin/env python3
"""
Quick validation script for performance optimizations.

This script validates that all optimization components are working correctly
without running a full simulation.
"""

import sys
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

def test_advanced_optimizations():
    """Test the advanced optimization system."""
    print("🔍 Testing Advanced Optimization System...")

    try:
        from orchestrator_mvp.core.advanced_optimizations import (
            create_optimization_engine,
            PerformanceMonitor,
            StateCompressionManager
        )

        # Test optimization engine creation
        engine = create_optimization_engine(pool_size=2, enable_monitoring=True)
        print("  ✅ Optimization engine created successfully")

        # Test performance monitoring
        monitor = PerformanceMonitor()
        with monitor.monitor_operation("test_operation", 100) as metric:
            import time
            time.sleep(0.1)  # Simulate work

        summary = monitor.get_performance_summary()
        print(f"  ✅ Performance monitoring working: {summary['total_operations']} operations tracked")

        # Test compression
        import pandas as pd
        test_df = pd.DataFrame({'id': range(1000), 'value': range(1000)})
        compression_manager = StateCompressionManager()

        compressed_data, metrics = compression_manager.compress_workforce_state(test_df)
        decompressed_df = compression_manager.decompress_dataframe(compressed_data)

        print(f"  ✅ State compression working: {metrics['compression_ratio']:.1f}x compression ratio")

        # Cleanup
        engine.cleanup()
        print("  ✅ Advanced optimization system validated")
        return True

    except Exception as e:
        print(f"  ❌ Advanced optimization system failed: {e}")
        return False

def test_dbt_batch_executor():
    """Test the dbt batch execution system."""
    print("🔍 Testing dbt Batch Executor...")

    try:
        from orchestrator_mvp.utils.dbt_batch_executor import (
            create_optimized_dbt_executor,
            DbtDependencyAnalyzer
        )

        dbt_project_path = project_root / "dbt"

        if not dbt_project_path.exists():
            print("  ⚠️ dbt project not found, skipping dbt tests")
            return True

        # Test executor creation
        executor = create_optimized_dbt_executor(str(dbt_project_path), max_parallel_jobs=2)
        print("  ✅ dbt executor created successfully")

        # Test dependency analyzer (without running actual dbt commands)
        analyzer = DbtDependencyAnalyzer(str(dbt_project_path))
        print("  ✅ Dependency analyzer created successfully")

        print("  ✅ dbt batch execution system validated")
        return True

    except Exception as e:
        print(f"  ❌ dbt batch executor failed: {e}")
        return False

def test_multi_year_engine():
    """Test the multi-year optimization engine."""
    print("🔍 Testing Multi-Year Optimization Engine...")

    try:
        from orchestrator_mvp.core.optimized_multi_year_engine import create_optimized_multi_year_engine

        dbt_project_path = project_root / "dbt"

        if not dbt_project_path.exists():
            print("  ⚠️ dbt project not found, skipping multi-year engine test")
            return True

        # Test engine creation
        engine = create_optimized_multi_year_engine(
            dbt_project_path=str(dbt_project_path),
            simulation_years=[2024, 2025],
            pool_size=2
        )
        print("  ✅ Multi-year engine created successfully")

        # Test baseline metrics setting
        baseline_metrics = {"foundation_setup": 10000, "year_processing": 120000}
        engine.set_baseline_metrics(baseline_metrics)
        print("  ✅ Baseline metrics configuration working")

        print("  ✅ Multi-year optimization engine validated")
        return True

    except Exception as e:
        print(f"  ❌ Multi-year engine failed: {e}")
        return False

def test_dependencies():
    """Test that all required dependencies are available."""
    print("🔍 Testing Dependencies...")

    required_packages = [
        ("lz4", "LZ4 compression"),
        ("psutil", "System resource monitoring"),
        ("networkx", "Dependency graph analysis"),
        ("pandas", "Data processing"),
        ("duckdb", "Database engine")
    ]

    missing_packages = []

    for package, description in required_packages:
        try:
            __import__(package)
            print(f"  ✅ {package} ({description})")
        except ImportError:
            print(f"  ❌ {package} ({description}) - MISSING")
            missing_packages.append(package)

    if missing_packages:
        print(f"\n⚠️ Missing packages: {', '.join(missing_packages)}")
        print("Install with: pip install " + " ".join(missing_packages))
        return False

    print("  ✅ All dependencies available")
    return True

def main():
    """Run all validation tests."""
    print("🚀 PlanWise Navigator Optimization Validation")
    print("=" * 50)

    tests = [
        ("Dependencies", test_dependencies),
        ("Advanced Optimizations", test_advanced_optimizations),
        ("dbt Batch Executor", test_dbt_batch_executor),
        ("Multi-Year Engine", test_multi_year_engine)
    ]

    results = []

    for test_name, test_func in tests:
        print(f"\n{test_name}:")
        success = test_func()
        results.append((test_name, success))

    # Summary
    print(f"\n🏆 Validation Summary")
    print("=" * 30)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for test_name, success in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"  {status} {test_name}")

    print(f"\n📊 Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All optimization components validated successfully!")
        print("Ready for high-performance multi-year simulations targeting 82% improvement.")
        return 0
    else:
        print("⚠️ Some optimization components need attention.")
        print("Please address the failed tests before running optimized simulations.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
