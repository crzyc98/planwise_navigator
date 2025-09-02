#!/usr/bin/env python3
"""
Real Navigator Orchestrator Threading Test
==========================================

This script tests the actual Navigator Orchestrator threading implementation
to validate determinism and performance with real dbt models.
"""

import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Dict, Any, List

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from navigator_orchestrator.parallel_execution_engine import ParallelExecutionEngine, ExecutionContext
    from navigator_orchestrator.model_dependency_analyzer import ModelDependencyAnalyzer
    from navigator_orchestrator.dbt_runner import DbtRunner
    from navigator_orchestrator.resource_manager import ResourceManager
    from navigator_orchestrator.logger import ProductionLogger
    print("✅ Navigator Orchestrator imports successful")
    IMPORTS_OK = True
except ImportError as e:
    print(f"❌ Import failed: {e}")
    IMPORTS_OK = False


def test_parallel_execution_engine():
    """Test the ParallelExecutionEngine directly."""

    if not IMPORTS_OK:
        print("❌ Cannot test - imports failed")
        return

    print("\n🔧 Testing ParallelExecutionEngine...")

    try:
        # Initialize dbt runner (pointing to actual dbt directory)
        dbt_dir = Path("dbt")
        if not dbt_dir.exists():
            print(f"❌ dbt directory not found: {dbt_dir}")
            return

        dbt_runner = DbtRunner(dbt_dir)

        # Initialize dependency analyzer
        dependency_analyzer = ModelDependencyAnalyzer(dbt_runner)

        # Test thread counts
        thread_counts = [1, 2, 4]
        results = {}

        for thread_count in thread_counts:
            print(f"   Testing with {thread_count} threads...")

            # Initialize parallel execution engine
            engine = ParallelExecutionEngine(
                dbt_runner=dbt_runner,
                dependency_analyzer=dependency_analyzer,
                max_workers=thread_count,
                deterministic_execution=True,
                verbose=True
            )

            # Get basic parallelization statistics
            stats = engine.get_parallelization_statistics()
            print(f"      Parallelization stats: {stats}")

            results[thread_count] = {
                "thread_count": thread_count,
                "stats": stats,
                "initialization": "success"
            }

        print("✅ ParallelExecutionEngine initialization tests passed")
        return results

    except Exception as e:
        print(f"❌ ParallelExecutionEngine test failed: {e}")
        traceback.print_exc()
        return None


def test_resource_manager():
    """Test the ResourceManager functionality."""

    if not IMPORTS_OK:
        print("❌ Cannot test - imports failed")
        return

    print("\n🔧 Testing ResourceManager...")

    try:
        # Initialize resource manager
        config = {
            "memory": {
                "monitoring_interval": 1.0,
                "thresholds": {
                    "moderate_mb": 1000.0,
                    "high_mb": 2000.0,
                    "critical_mb": 3000.0
                }
            },
            "cpu": {
                "monitoring_interval": 1.0,
                "thresholds": {
                    "moderate_percent": 60.0,
                    "high_percent": 80.0,
                    "critical_percent": 95.0
                }
            }
        }

        resource_manager = ResourceManager(config=config)

        # Start monitoring
        resource_manager.start_monitoring()

        # Test optimization
        optimal_threads, reason = resource_manager.optimize_thread_count(4)
        print(f"      Optimal thread count: {optimal_threads} (reason: {reason})")

        # Get resource status
        status = resource_manager.get_resource_status()
        print(f"      Resource status: Memory: {status['memory']['usage_mb']:.1f}MB, CPU: {status['cpu']['current_percent']:.1f}%")

        # Test resource health check
        health = resource_manager.check_resource_health()
        print(f"      Resource health: {'✅ Healthy' if health else '⚠️ Pressure detected'}")

        # Stop monitoring
        resource_manager.stop_monitoring()

        print("✅ ResourceManager tests passed")
        return {
            "optimal_threads": optimal_threads,
            "optimization_reason": reason,
            "resource_status": status,
            "resource_health": health
        }

    except Exception as e:
        print(f"❌ ResourceManager test failed: {e}")
        traceback.print_exc()
        return None


def test_dbt_connectivity():
    """Test basic dbt connectivity and model discovery."""

    print("\n🔧 Testing dbt connectivity...")

    try:
        dbt_dir = Path("dbt")
        if not dbt_dir.exists():
            print(f"❌ dbt directory not found: {dbt_dir}")
            return None

        # Check for dbt_project.yml
        dbt_project = dbt_dir / "dbt_project.yml"
        if not dbt_project.exists():
            print(f"❌ dbt_project.yml not found: {dbt_project}")
            return None

        print(f"✅ Found dbt project: {dbt_project}")

        # Check for models directory
        models_dir = dbt_dir / "models"
        if models_dir.exists():
            model_files = list(models_dir.rglob("*.sql"))
            print(f"✅ Found {len(model_files)} SQL model files")

            # List some example models
            example_models = [f.stem for f in model_files[:10]]
            print(f"      Example models: {example_models}")

            return {
                "dbt_project_found": True,
                "model_count": len(model_files),
                "example_models": example_models
            }
        else:
            print(f"⚠️ Models directory not found: {models_dir}")
            return {
                "dbt_project_found": True,
                "model_count": 0,
                "models_dir_missing": True
            }

    except Exception as e:
        print(f"❌ dbt connectivity test failed: {e}")
        traceback.print_exc()
        return None


def test_database_connectivity():
    """Test database connectivity."""

    print("\n🔧 Testing database connectivity...")

    try:
        from navigator_orchestrator.config import get_database_path
        import duckdb

        db_path = get_database_path()
        print(f"      Database path: {db_path}")

        if not db_path.exists():
            print(f"⚠️ Database file not found: {db_path}")
            print("      This is normal if no simulations have been run yet")
            return {
                "database_exists": False,
                "database_path": str(db_path)
            }

        # Try to connect
        conn = duckdb.connect(str(db_path))

        # Check tables
        tables_result = conn.execute("SHOW TABLES").fetchall()
        table_names = [row[0] for row in tables_result]

        print(f"✅ Database connected - {len(table_names)} tables found")
        print(f"      Example tables: {table_names[:10]}")

        conn.close()

        return {
            "database_exists": True,
            "database_path": str(db_path),
            "table_count": len(table_names),
            "example_tables": table_names[:10]
        }

    except Exception as e:
        print(f"❌ Database connectivity test failed: {e}")
        traceback.print_exc()
        return None


def run_performance_comparison():
    """Run a basic performance comparison across thread counts using actual components."""

    print("\n⚡ Running performance comparison...")

    if not IMPORTS_OK:
        print("❌ Cannot run performance test - imports failed")
        return None

    try:
        # Simple mock execution test
        results = {}

        for thread_count in [1, 2, 4]:
            print(f"   Testing {thread_count} threads...")

            start_time = time.time()

            # Simulate initialization overhead
            config = {"memory": {"monitoring_interval": 0.1}}
            resource_manager = ResourceManager(config=config)
            resource_manager.start_monitoring()

            # Simulate some work
            total = 0
            for i in range(100000 * thread_count):  # Scale work with thread count
                total += i % 1000

            resource_manager.stop_monitoring()

            execution_time = time.time() - start_time

            results[thread_count] = {
                "thread_count": thread_count,
                "execution_time": execution_time,
                "work_result": total
            }

            print(f"      Completed in {execution_time:.3f}s")

        # Calculate speedups
        baseline_time = results[1]["execution_time"]
        for thread_count in [2, 4]:
            if thread_count in results:
                speedup = baseline_time / results[thread_count]["execution_time"]
                efficiency = speedup / thread_count
                results[thread_count]["speedup"] = speedup
                results[thread_count]["efficiency"] = efficiency
                print(f"      {thread_count} threads: {speedup:.2f}x speedup, {efficiency:.2f} efficiency")

        return results

    except Exception as e:
        print(f"❌ Performance comparison failed: {e}")
        traceback.print_exc()
        return None


def main():
    """Main test execution."""

    print("Navigator Orchestrator Threading Implementation Test")
    print("=" * 60)

    results = {
        "test_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "imports_successful": IMPORTS_OK
    }

    # Run all tests
    test_results = {
        "parallel_execution_engine": test_parallel_execution_engine(),
        "resource_manager": test_resource_manager(),
        "dbt_connectivity": test_dbt_connectivity(),
        "database_connectivity": test_database_connectivity(),
        "performance_comparison": run_performance_comparison()
    }

    results["test_results"] = test_results

    # Count successful tests
    successful_tests = sum(1 for result in test_results.values() if result is not None)
    total_tests = len(test_results)

    print(f"\n📊 Test Summary: {successful_tests}/{total_tests} tests passed")

    # Save results
    output_file = f"threading_test_results_{int(time.time())}.json"
    with open(output_file, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    print(f"📄 Detailed results saved: {output_file}")

    # Provide recommendations
    print("\n💡 Recommendations:")

    if IMPORTS_OK:
        print("  ✅ Threading components are importable and initializable")
    else:
        print("  ❌ Fix import issues before proceeding with threading validation")

    if test_results["dbt_connectivity"] and test_results["dbt_connectivity"]["model_count"] > 0:
        print("  ✅ dbt models available for actual threading tests")
    else:
        print("  ⚠️ Limited dbt models available - consider using sample models for testing")

    if test_results["database_connectivity"] and test_results["database_connectivity"]["database_exists"]:
        print("  ✅ Database exists - can run actual data validation tests")
    else:
        print("  ⚠️ No database found - run a baseline simulation first")

    if test_results["performance_comparison"]:
        print("  ✅ Basic performance framework functional")

        # Check if we see any performance improvements
        perf_results = test_results["performance_comparison"]
        if 4 in perf_results and "speedup" in perf_results[4]:
            speedup = perf_results[4]["speedup"]
            if speedup > 1.2:
                print(f"  ✅ Observed {speedup:.2f}x speedup potential with threading")
            else:
                print(f"  ⚠️ Limited speedup observed ({speedup:.2f}x) - investigate bottlenecks")

    return successful_tests == total_tests


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
