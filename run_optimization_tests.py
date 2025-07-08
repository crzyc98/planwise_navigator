#!/usr/bin/env python3
"""
Comprehensive Test Runner for Optimization Testing Framework
============================================================

This script provides a convenient interface for running the complete optimization
testing suite with various configurations and reporting options.

Test Categories:
- Unit Tests: Individual component testing
- Integration Tests: Cross-component workflow testing
- Performance Tests: Speed and memory benchmarking
- Edge Case Tests: Boundary and stress testing
- Error Handling Tests: Failure mode validation
- End-to-End Tests: Complete user journey testing

Usage:
    python run_optimization_tests.py --all
    python run_optimization_tests.py --unit --integration
    python run_optimization_tests.py --performance --report
    python run_optimization_tests.py --quick
"""

import argparse
import subprocess
import sys
import time
import os
from pathlib import Path
from typing import List, Dict, Any
import json


class OptimizationTestRunner:
    """Comprehensive test runner for optimization features."""

    def __init__(self):
        self.test_dir = Path(__file__).parent / "tests"
        self.results = {}
        self.start_time = None

    def run_tests(self, test_categories: List[str], options: Dict[str, Any]) -> bool:
        """Run specified test categories with options."""

        self.start_time = time.time()
        print("🚀 Starting PlanWise Navigator Optimization Test Suite")
        print("=" * 80)

        all_passed = True

        for category in test_categories:
            print(f"\n📋 Running {category.upper()} tests...")

            success = self._run_test_category(category, options)
            self.results[category] = success

            if success:
                print(f"✅ {category.upper()} tests passed")
            else:
                print(f"❌ {category.upper()} tests failed")
                all_passed = False

        self._print_summary()

        if options.get('report'):
            self._generate_report()

        return all_passed

    def _run_test_category(self, category: str, options: Dict[str, Any]) -> bool:
        """Run a specific test category."""

        cmd = ["python", "-m", "pytest"]

        # Add test markers
        if category == "unit":
            cmd.extend(["-m", "unit"])
        elif category == "integration":
            cmd.extend(["-m", "integration"])
        elif category == "performance":
            cmd.extend(["-m", "performance"])
        elif category == "edge_case":
            cmd.extend(["-m", "edge_case"])
        elif category == "error_handling":
            cmd.extend(["-m", "error_handling"])
        elif category == "e2e":
            cmd.extend(["-m", "e2e"])
        elif category == "all":
            pass  # Run all tests

        # Add test files
        test_files = self._get_test_files(category)
        cmd.extend(test_files)

        # Add options
        if options.get('verbose'):
            cmd.append("-v")

        if options.get('show_capture'):
            cmd.append("-s")

        if options.get('fail_fast'):
            cmd.append("-x")

        if options.get('parallel'):
            cmd.extend(["-n", "auto"])

        # Add coverage if requested
        if options.get('coverage'):
            cmd.extend([
                "--cov=streamlit_dashboard",
                "--cov=orchestrator.optimization",
                "--cov-report=term-missing"
            ])

        # Run tests
        try:
            result = subprocess.run(cmd, cwd=self.test_dir.parent, capture_output=True, text=True)

            if options.get('verbose') or result.returncode != 0:
                print(result.stdout)
                if result.stderr:
                    print("STDERR:", result.stderr)

            return result.returncode == 0

        except Exception as e:
            print(f"Error running {category} tests: {e}")
            return False

    def _get_test_files(self, category: str) -> List[str]:
        """Get test files for a specific category."""

        test_files = []

        if category == "unit":
            test_files = [
                "tests/test_advanced_optimization_unit.py",
                "tests/test_optimization_schemas.py"
            ]
        elif category == "integration":
            test_files = [
                "tests/test_compensation_workflow_integration.py",
                "tests/test_compensation_tuning_integration.py"
            ]
        elif category == "performance":
            test_files = [
                "tests/test_optimization_performance.py"
            ]
        elif category == "edge_case":
            test_files = [
                "tests/test_optimization_edge_cases.py"
            ]
        elif category == "error_handling":
            test_files = [
                "tests/test_optimization_error_handling.py"
            ]
        elif category == "e2e":
            test_files = [
                "tests/test_end_to_end_optimization.py"
            ]
        elif category == "all":
            test_files = [
                "tests/test_advanced_optimization_unit.py",
                "tests/test_optimization_schemas.py",
                "tests/test_compensation_workflow_integration.py",
                "tests/test_compensation_tuning_integration.py",
                "tests/test_optimization_performance.py",
                "tests/test_optimization_edge_cases.py",
                "tests/test_optimization_error_handling.py",
                "tests/test_end_to_end_optimization.py"
            ]

        return test_files

    def _print_summary(self):
        """Print test execution summary."""

        total_time = time.time() - self.start_time

        print("\n" + "=" * 80)
        print("🏁 TEST EXECUTION SUMMARY")
        print("=" * 80)

        passed_count = sum(1 for success in self.results.values() if success)
        total_count = len(self.results)

        print(f"📊 Results: {passed_count}/{total_count} test categories passed")
        print(f"⏱️  Total execution time: {total_time:.2f} seconds")

        if passed_count == total_count:
            print("🎉 All test categories passed successfully!")
        else:
            print("⚠️  Some test categories failed. See details above.")

        print("\n📈 Category Breakdown:")
        for category, success in self.results.items():
            status = "✅ PASS" if success else "❌ FAIL"
            print(f"  {category.upper():<15} {status}")

        print("=" * 80)

    def _generate_report(self):
        """Generate detailed test report."""

        report_file = Path(__file__).parent / "test_report.json"

        report_data = {
            "timestamp": time.time(),
            "execution_time": time.time() - self.start_time,
            "results": self.results,
            "summary": {
                "total_categories": len(self.results),
                "passed_categories": sum(1 for success in self.results.values() if success),
                "overall_success": all(self.results.values())
            }
        }

        with open(report_file, 'w') as f:
            json.dump(report_data, f, indent=2)

        print(f"📄 Test report saved to: {report_file}")


def main():
    """Main entry point for test runner."""

    parser = argparse.ArgumentParser(
        description="Run PlanWise Navigator optimization tests",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --all                    # Run all test categories
  %(prog)s --unit --integration     # Run unit and integration tests only
  %(prog)s --performance --report   # Run performance tests with report
  %(prog)s --quick                  # Quick test run (unit + integration)
  %(prog)s --e2e --verbose          # Run end-to-end tests with verbose output
        """
    )

    # Test category options
    parser.add_argument("--all", action="store_true", help="Run all test categories")
    parser.add_argument("--unit", action="store_true", help="Run unit tests")
    parser.add_argument("--integration", action="store_true", help="Run integration tests")
    parser.add_argument("--performance", action="store_true", help="Run performance tests")
    parser.add_argument("--edge-case", action="store_true", help="Run edge case tests")
    parser.add_argument("--error-handling", action="store_true", help="Run error handling tests")
    parser.add_argument("--e2e", action="store_true", help="Run end-to-end tests")
    parser.add_argument("--quick", action="store_true", help="Quick test run (unit + integration)")

    # Execution options
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--show-capture", "-s", action="store_true", help="Show print statements")
    parser.add_argument("--fail-fast", "-x", action="store_true", help="Stop on first failure")
    parser.add_argument("--parallel", "-n", action="store_true", help="Run tests in parallel")
    parser.add_argument("--coverage", action="store_true", help="Generate coverage report")
    parser.add_argument("--report", action="store_true", help="Generate detailed test report")

    args = parser.parse_args()

    # Determine test categories to run
    test_categories = []

    if args.all:
        test_categories = ["all"]
    elif args.quick:
        test_categories = ["unit", "integration"]
    else:
        if args.unit:
            test_categories.append("unit")
        if args.integration:
            test_categories.append("integration")
        if args.performance:
            test_categories.append("performance")
        if getattr(args, 'edge_case'):
            test_categories.append("edge_case")
        if getattr(args, 'error_handling'):
            test_categories.append("error_handling")
        if args.e2e:
            test_categories.append("e2e")

    # Default to quick tests if nothing specified
    if not test_categories:
        test_categories = ["unit", "integration"]
        print("No test categories specified, defaulting to --quick (unit + integration)")

    # Execution options
    options = {
        'verbose': args.verbose,
        'show_capture': args.show_capture,
        'fail_fast': args.fail_fast,
        'parallel': args.parallel,
        'coverage': args.coverage,
        'report': args.report
    }

    # Check if pytest is available
    try:
        subprocess.run(["python", "-m", "pytest", "--version"],
                      capture_output=True, check=True)
    except subprocess.CalledProcessError:
        print("❌ pytest is not installed. Please install with: pip install pytest")
        sys.exit(1)

    # Run tests
    runner = OptimizationTestRunner()
    success = runner.run_tests(test_categories, options)

    # Exit with appropriate code
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
