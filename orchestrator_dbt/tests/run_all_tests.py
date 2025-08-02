#!/usr/bin/env python3
"""
Test runner for all orchestrator_dbt tests.

This script runs all test suites for the migrated event generation system,
providing comprehensive validation of Story S031-03 implementation.

Usage:
    # Run all tests
    python orchestrator_dbt/tests/run_all_tests.py

    # Run with verbose output
    python orchestrator_dbt/tests/run_all_tests.py --verbose

    # Run specific test suite
    python orchestrator_dbt/tests/run_all_tests.py --suite event_generation

    # Generate coverage report
    python orchestrator_dbt/tests/run_all_tests.py --coverage

Integration with CI/CD:
- Returns exit code 0 for success, 1 for failure
- Provides detailed output for debugging test failures
- Supports coverage reporting for code quality metrics
- Validates all migrated components maintain MVP functionality
"""

import argparse
import sys
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List

# Add parent directory for imports
sys.path.insert(0, str(Path(__file__).parent.parent.parent))


def run_event_generation_tests(verbose: bool = False) -> Dict[str, Any]:
    """Run event generation component tests."""
    print("🧪 Running Event Generation Component Tests")
    print("-" * 60)

    try:
        from orchestrator_dbt.tests.test_event_generation_components import run_comprehensive_test_suite

        start_time = time.time()
        success = run_comprehensive_test_suite()
        execution_time = time.time() - start_time

        result = {
            'suite_name': 'Event Generation Components',
            'success': success,
            'execution_time': execution_time,
            'test_count': 'Multiple test classes',
            'errors': [] if success else ['Some tests failed - see output above']
        }

        return result

    except Exception as e:
        return {
            'suite_name': 'Event Generation Components',
            'success': False,
            'execution_time': 0,
            'test_count': 0,
            'errors': [f"Test suite failed to run: {str(e)}"]
        }


def run_validation_tests(verbose: bool = False) -> Dict[str, Any]:
    """Run validation suite tests."""
    print("\n🧪 Running Validation Suite Tests")
    print("-" * 60)

    try:
        from orchestrator_dbt.validation.test_validation_suite import run_test_suite

        start_time = time.time()
        success = run_test_suite()
        execution_time = time.time() - start_time

        result = {
            'suite_name': 'Validation Suite',
            'success': success,
            'execution_time': execution_time,
            'test_count': 'Multiple validation test classes',
            'errors': [] if success else ['Some validation tests failed - see output above']
        }

        return result

    except Exception as e:
        return {
            'suite_name': 'Validation Suite',
            'success': False,
            'execution_time': 0,
            'test_count': 0,
            'errors': [f"Validation test suite failed to run: {str(e)}"]
        }


def run_benchmark_tests(verbose: bool = False) -> Dict[str, Any]:
    """Run benchmark suite tests."""
    print("\n🧪 Running Benchmark Suite Tests")
    print("-" * 60)

    try:
        from orchestrator_dbt.benchmarking.test_benchmark import run_test_suite

        start_time = time.time()
        success = run_test_suite()
        execution_time = time.time() - start_time

        result = {
            'suite_name': 'Benchmark Suite',
            'success': success,
            'execution_time': execution_time,
            'test_count': 'Multiple benchmark test classes',
            'errors': [] if success else ['Some benchmark tests failed - see output above']
        }

        return result

    except Exception as e:
        return {
            'suite_name': 'Benchmark Suite',
            'success': False,
            'execution_time': 0,
            'test_count': 0,
            'errors': [f"Benchmark test suite failed to run: {str(e)}"]
        }


def run_coverage_analysis(verbose: bool = False) -> Dict[str, Any]:
    """Run coverage analysis on all test suites."""
    print("\n📊 Running Coverage Analysis")
    print("-" * 60)

    try:
        # Check if coverage is available
        result = subprocess.run(['python', '-m', 'coverage', '--version'],
                              capture_output=True, text=True)

        if result.returncode != 0:
            return {
                'suite_name': 'Coverage Analysis',
                'success': False,
                'execution_time': 0,
                'test_count': 0,
                'errors': ['Coverage.py not installed. Run: pip install coverage']
            }

        # Run coverage on test files
        test_files = [
            'orchestrator_dbt/tests/test_event_generation_components.py',
            'orchestrator_dbt/validation/test_validation_suite.py',
            'orchestrator_dbt/benchmarking/test_benchmark.py'
        ]

        coverage_results = []
        start_time = time.time()

        for test_file in test_files:
            print(f"Running coverage for {test_file}...")

            # Run coverage
            cmd = ['python', '-m', 'coverage', 'run', '--append', test_file]
            result = subprocess.run(cmd, capture_output=True, text=True)

            if result.returncode == 0:
                coverage_results.append(f"✅ {test_file}")
            else:
                coverage_results.append(f"❌ {test_file}: {result.stderr.strip()}")

        # Generate coverage report
        print("Generating coverage report...")
        report_result = subprocess.run(
            ['python', '-m', 'coverage', 'report', '--show-missing'],
            capture_output=True, text=True
        )

        execution_time = time.time() - start_time

        if report_result.returncode == 0:
            print(report_result.stdout)

            return {
                'suite_name': 'Coverage Analysis',
                'success': True,
                'execution_time': execution_time,
                'test_count': len(test_files),
                'errors': [],
                'coverage_results': coverage_results,
                'coverage_report': report_result.stdout
            }
        else:
            return {
                'suite_name': 'Coverage Analysis',
                'success': False,
                'execution_time': execution_time,
                'test_count': len(test_files),
                'errors': [f"Coverage report failed: {report_result.stderr}"],
                'coverage_results': coverage_results
            }

    except Exception as e:
        return {
            'suite_name': 'Coverage Analysis',
            'success': False,
            'execution_time': 0,
            'test_count': 0,
            'errors': [f"Coverage analysis failed: {str(e)}"]
        }


def print_test_summary(results: List[Dict[str, Any]]) -> None:
    """Print comprehensive test summary."""
    print("\n" + "="*80)
    print("🎯 COMPREHENSIVE TEST SUITE SUMMARY - STORY S031-03")
    print("="*80)

    total_execution_time = sum(r['execution_time'] for r in results)
    successful_suites = sum(1 for r in results if r['success'])
    total_suites = len(results)

    print(f"\n📊 Overview:")
    print(f"   Total Test Suites: {total_suites}")
    print(f"   Successful Suites: {successful_suites}")
    print(f"   Failed Suites: {total_suites - successful_suites}")
    print(f"   Total Execution Time: {total_execution_time:.3f}s")
    print(f"   Success Rate: {(successful_suites / total_suites * 100):.1f}%")

    print(f"\n📋 Test Suite Results:")
    for result in results:
        status_icon = "✅" if result['success'] else "❌"
        suite_name = result['suite_name']
        exec_time = result['execution_time']

        print(f"   {status_icon} {suite_name}: {exec_time:.3f}s")

        if not result['success'] and result.get('errors'):
            for error in result['errors'][:3]:  # Show first 3 errors
                print(f"      ⚠️ {error}")

    # Story S031-03 specific validation
    print(f"\n🎯 Story S031-03 Validation:")

    event_gen_success = any(r['success'] and 'Event Generation' in r['suite_name'] for r in results)
    validation_success = any(r['success'] and 'Validation' in r['suite_name'] for r in results)
    benchmark_success = any(r['success'] and 'Benchmark' in r['suite_name'] for r in results)

    print(f"   {'✅' if event_gen_success else '❌'} Event Generation Migration: {'VALIDATED' if event_gen_success else 'FAILED'}")
    print(f"   {'✅' if validation_success else '❌'} Financial Precision & Audit Trails: {'VALIDATED' if validation_success else 'FAILED'}")
    print(f"   {'✅' if benchmark_success else '❌'} Performance Benchmarking: {'VALIDATED' if benchmark_success else 'FAILED'}")

    # Overall S031-03 status
    story_success = event_gen_success and validation_success and benchmark_success
    print(f"\n🎉 Story S031-03 Status: {'✅ COMPLETE' if story_success else '❌ ISSUES FOUND'}")

    if story_success:
        print(f"   • Migration from orchestrator_mvp to orchestrator_dbt validated")
        print(f"   • Financial precision maintained across all components")
        print(f"   • Performance improvements benchmarked and validated")
        print(f"   • Comprehensive audit trail validation successful")
    else:
        print(f"   • Review failed test suites above for resolution guidance")


def main():
    """Main test runner entry point."""
    parser = argparse.ArgumentParser(
        description='Run comprehensive test suite for Story S031-03 event generation migration',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                           # Run all test suites
  %(prog)s --verbose                 # Run with verbose output
  %(prog)s --suite event_generation  # Run specific suite
  %(prog)s --coverage               # Include coverage analysis
        """
    )

    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose test output'
    )

    parser.add_argument(
        '--suite',
        choices=['event_generation', 'validation', 'benchmark', 'all'],
        default='all',
        help='Specific test suite to run (default: all)'
    )

    parser.add_argument(
        '--coverage',
        action='store_true',
        help='Include coverage analysis in test run'
    )

    parser.add_argument(
        '--fail-fast',
        action='store_true',
        help='Stop on first test suite failure'
    )

    args = parser.parse_args()

    print("🚀 Starting Comprehensive Test Suite for Story S031-03")
    print("📅 Event Generation Performance Migration")
    print("🎯 Validating orchestrator_mvp → orchestrator_dbt migration")

    results = []

    try:
        # Run specified test suites
        if args.suite in ['event_generation', 'all']:
            result = run_event_generation_tests(args.verbose)
            results.append(result)

            if args.fail_fast and not result['success']:
                print(f"\n💥 Stopping due to --fail-fast: {result['suite_name']} failed")
                print_test_summary(results)
                sys.exit(1)

        if args.suite in ['validation', 'all']:
            result = run_validation_tests(args.verbose)
            results.append(result)

            if args.fail_fast and not result['success']:
                print(f"\n💥 Stopping due to --fail-fast: {result['suite_name']} failed")
                print_test_summary(results)
                sys.exit(1)

        if args.suite in ['benchmark', 'all']:
            result = run_benchmark_tests(args.verbose)
            results.append(result)

            if args.fail_fast and not result['success']:
                print(f"\n💥 Stopping due to --fail-fast: {result['suite_name']} failed")
                print_test_summary(results)
                sys.exit(1)

        # Run coverage analysis if requested
        if args.coverage:
            result = run_coverage_analysis(args.verbose)
            results.append(result)

        # Print comprehensive summary
        print_test_summary(results)

        # Determine exit code
        all_successful = all(result['success'] for result in results)

        if all_successful:
            print(f"\n🎉 All test suites passed! Story S031-03 migration validated successfully.")
            sys.exit(0)
        else:
            print(f"\n⚠️ Some test suites failed. Review results above for resolution guidance.")
            sys.exit(1)

    except KeyboardInterrupt:
        print(f"\n⏹️ Test run interrupted by user")
        if results:
            print_test_summary(results)
        sys.exit(130)

    except Exception as e:
        print(f"\n💥 Test runner failed with error: {str(e)}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
