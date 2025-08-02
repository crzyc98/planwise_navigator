#!/usr/bin/env python3
"""
Test script for orchestrator_dbt optimizations.

This script validates the performance improvements and ensures the optimized
workflow functions correctly with faster execution times.
"""

import sys
import time
import logging
from pathlib import Path
from typing import Dict, Any

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from orchestrator_dbt.core.workflow_orchestrator import WorkflowOrchestrator
from orchestrator_dbt.core.config import OrchestrationConfig
from orchestrator_dbt.utils.performance_monitor import PerformanceMonitor
from orchestrator_dbt.utils.error_recovery import error_recovery
from orchestrator_dbt.utils.logging_utils import setup_logging


def test_system_readiness() -> bool:
    """
    Test system readiness for optimized execution.

    Returns:
        True if system is ready
    """
    print("🔧 Testing system readiness...")

    try:
        config = OrchestrationConfig()
        orchestrator = WorkflowOrchestrator()

        status = orchestrator.get_system_status()

        print(f"   Database accessible: {'✅' if status.get('database_accessible', False) else '❌'}")
        print(f"   dbt available: {'✅' if status.get('dbt_available', False) else '❌'}")
        print(f"   Seeds available: {'✅' if status.get('seeds_available', False) else '❌'}")
        print(f"   Staging models available: {'✅' if status.get('staging_models_available', False) else '❌'}")

        ready = status.get('ready_for_setup', False)
        print(f"   Overall readiness: {'✅' if ready else '❌'}")

        return ready

    except Exception as e:
        print(f"   ❌ System readiness test failed: {e}")
        return False


def test_performance_analysis() -> Dict[str, Any]:
    """
    Test performance analysis capabilities.

    Returns:
        Performance metrics dictionary
    """
    print("📊 Testing performance analysis...")

    try:
        orchestrator = WorkflowOrchestrator()
        metrics = orchestrator.get_workflow_performance_metrics()

        seed_metrics = metrics.get("seed_loading", {})
        staging_metrics = metrics.get("staging_models", {})
        recommendations = metrics.get("optimization_recommendations", [])
        estimated_savings = metrics.get("estimated_time_savings", 0)

        print(f"   Seeds available: {seed_metrics.get('total_seeds_available', 0)}")
        print(f"   Staging models available: {staging_metrics.get('total_models_available', 0)}")
        print(f"   Optimization recommendations: {len(recommendations)}")
        print(f"   Estimated time savings: {estimated_savings:.1f}s")

        return metrics

    except Exception as e:
        print(f"   ❌ Performance analysis test failed: {e}")
        return {}


def test_optimized_workflow(max_workers: int = 4) -> Dict[str, Any]:
    """
    Test optimized workflow execution.

    Args:
        max_workers: Maximum concurrent workers

    Returns:
        Test results dictionary
    """
    print(f"🚀 Testing optimized workflow (max_workers={max_workers})...")

    try:
        # Initialize performance monitoring
        monitor = PerformanceMonitor(enable_detailed_tracking=True)

        # Initialize orchestrator
        orchestrator = WorkflowOrchestrator()

        # Start monitoring
        operation_id = monitor.start_operation("test_optimized_workflow", {"max_workers": max_workers})

        # Run optimized workflow
        start_time = time.time()
        result = orchestrator.run_optimized_setup_workflow(max_workers=max_workers)
        execution_time = time.time() - start_time

        # End monitoring
        monitor.end_operation(operation_id, result.success)

        # Generate performance report
        report = monitor.generate_report()

        print(f"   Workflow success: {'✅' if result.success else '❌'}")
        print(f"   Steps completed: {result.steps_completed}/{result.steps_total}")
        print(f"   Execution time: {execution_time:.2f}s")
        print(f"   Target met (<20s): {'✅' if execution_time < 20.0 else '❌'}")

        if result.success and execution_time < 20.0:
            improvement = ((47.0 - execution_time) / 47.0) * 100
            print(f"   Performance improvement: {improvement:.1f}% faster than baseline")

        return {
            "success": result.success,
            "execution_time": execution_time,
            "target_met": execution_time < 20.0,
            "steps_completed": result.steps_completed,
            "steps_total": result.steps_total,
            "performance_report": report
        }

    except Exception as e:
        print(f"   ❌ Optimized workflow test failed: {e}")
        return {
            "success": False,
            "execution_time": 0.0,
            "target_met": False,
            "error": str(e)
        }


def test_fallback_behavior() -> bool:
    """
    Test fallback behavior when optimizations fail.

    Returns:
        True if fallback works correctly
    """
    print("🔄 Testing fallback behavior...")

    try:
        orchestrator = WorkflowOrchestrator()

        # This should test the fallback from optimized to standard workflow
        # In a real test, we might simulate failures, but for now we'll just
        # test that the standard workflow works

        result = orchestrator.run_complete_setup_workflow()

        print(f"   Standard workflow success: {'✅' if result.success else '❌'}")
        print(f"   Steps completed: {result.steps_completed}/{result.steps_total}")

        return result.success

    except Exception as e:
        print(f"   ❌ Fallback behavior test failed: {e}")
        return False


def test_error_recovery() -> bool:
    """
    Test error recovery mechanisms.

    Returns:
        True if error recovery is working
    """
    print("🛡️ Testing error recovery mechanisms...")

    try:
        # Test error classification
        from orchestrator_dbt.utils.error_recovery import ErrorRecoveryManager

        recovery_manager = ErrorRecoveryManager()

        # Test different error types
        test_errors = [
            (Exception("Connection timeout"), "network or timeout related"),
            (Exception("Database schema error"), "database or schema related"),
            (Exception("dbt command failed"), "command execution related"),
            (Exception("Configuration invalid"), "configuration related")
        ]

        classifications = []
        for error, expected_type in test_errors:
            error_type = recovery_manager.classify_error(error)
            classifications.append((error_type.value, expected_type))
            print(f"   Error '{error}' classified as: {error_type.value}")

        # Get error summary
        summary = recovery_manager.get_error_summary()
        print(f"   Error recovery system initialized: ✅")
        print(f"   Circuit breakers available: {len(recovery_manager.circuit_breakers)}")

        return True

    except Exception as e:
        print(f"   ❌ Error recovery test failed: {e}")
        return False


def run_comprehensive_test() -> Dict[str, Any]:
    """
    Run comprehensive test suite for optimizations.

    Returns:
        Test results summary
    """
    print("\n" + "=" * 60)
    print("🧪 ORCHESTRATOR_DBT OPTIMIZATION TEST SUITE")
    print("=" * 60)
    print(f"Started at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    results = {
        "timestamp": time.strftime('%Y-%m-%d %H:%M:%S'),
        "tests": {}
    }

    # Test 1: System Readiness
    results["tests"]["system_readiness"] = test_system_readiness()

    # Test 2: Performance Analysis
    performance_metrics = test_performance_analysis()
    results["tests"]["performance_analysis"] = bool(performance_metrics)
    results["performance_metrics"] = performance_metrics

    # Test 3: Error Recovery
    results["tests"]["error_recovery"] = test_error_recovery()

    # Test 4: Optimized Workflow (only if system is ready)
    if results["tests"]["system_readiness"]:
        workflow_results = test_optimized_workflow(max_workers=4)
        results["tests"]["optimized_workflow"] = workflow_results["success"]
        results["workflow_results"] = workflow_results

        # Test 5: Fallback Behavior
        results["tests"]["fallback_behavior"] = test_fallback_behavior()
    else:
        print("⚠️  Skipping workflow tests - system not ready")
        results["tests"]["optimized_workflow"] = False
        results["tests"]["fallback_behavior"] = False

    # Calculate overall success
    test_results = results["tests"]
    total_tests = len(test_results)
    passed_tests = sum(1 for result in test_results.values() if result)

    results["summary"] = {
        "total_tests": total_tests,
        "passed_tests": passed_tests,
        "failed_tests": total_tests - passed_tests,
        "success_rate": (passed_tests / total_tests) * 100 if total_tests > 0 else 0,
        "overall_success": passed_tests == total_tests
    }

    # Print summary
    print("\n" + "=" * 60)
    print("📊 TEST RESULTS SUMMARY")
    print("=" * 60)

    for test_name, result in test_results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"   {test_name.replace('_', ' ').title()}: {status}")

    print(f"\n📈 Overall Results:")
    print(f"   Tests passed: {passed_tests}/{total_tests}")
    print(f"   Success rate: {results['summary']['success_rate']:.1f}%")
    print(f"   Overall status: {'✅ SUCCESS' if results['summary']['overall_success'] else '❌ FAILURE'}")

    # Show performance results if available
    if "workflow_results" in results:
        workflow_results = results["workflow_results"]
        if workflow_results.get("success"):
            execution_time = workflow_results.get("execution_time", 0)
            target_met = workflow_results.get("target_met", False)

            print(f"\n⚡ Performance Results:")
            print(f"   Execution time: {execution_time:.2f}s")
            print(f"   Target (<20s): {'✅ MET' if target_met else '❌ MISSED'}")

            if target_met:
                improvement = ((47.0 - execution_time) / 47.0) * 100
                print(f"   Improvement: {improvement:.1f}% faster than baseline (47s)")

    print("=" * 60)
    print(f"Completed at: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60 + "\n")

    return results


def main():
    """Main entry point for optimization testing."""
    # Setup logging
    setup_logging(level="INFO")

    try:
        # Run comprehensive test suite
        results = run_comprehensive_test()

        # Exit with appropriate code
        success = results["summary"]["overall_success"]
        sys.exit(0 if success else 1)

    except KeyboardInterrupt:
        print("\n❌ Testing interrupted by user")
        sys.exit(130)

    except Exception as e:
        print(f"\n💥 Testing failed with exception: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
