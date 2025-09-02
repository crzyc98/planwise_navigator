#!/usr/bin/env python3
"""
Epic E067 Threading Test Suite Runner

This script orchestrates comprehensive testing of the multi-threading implementation
for Epic E067. It runs tests in specific order and provides detailed reporting.

Test Categories:
1. Unit Tests: Individual component validation
2. Integration Tests: End-to-end workflow testing
3. Performance Tests: Benchmarking and target validation
4. Determinism Tests: Result consistency validation
5. Resource Tests: Memory and CPU usage validation
6. Stress Tests: High-load and error condition testing

Usage:
    python scripts/run_e067_threading_tests.py [options]

Options:
    --category <category>    Run specific test category
    --quick                  Run only fast tests (skip performance/stress)
    --performance           Run performance benchmarks
    --stress                Run stress tests
    --report                Generate detailed HTML report
    --parallel              Run tests in parallel (when safe)
    --verbose               Enable verbose output
"""

import argparse
import sys
import os
import subprocess
import json
import time
from pathlib import Path
from typing import Dict, List, Optional, Any
from dataclasses import dataclass
import psutil

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@dataclass
class TestSuiteResult:
    """Container for test suite execution results."""
    category: str
    passed: int
    failed: int
    skipped: int
    errors: int
    warnings: int
    execution_time: float
    memory_peak_mb: float
    details: Dict[str, Any]


class E067ThreadingTestRunner:
    """Orchestrates execution of Epic E067 threading tests."""

    def __init__(self):
        self.project_root = Path(__file__).parent.parent
        self.test_results: Dict[str, TestSuiteResult] = {}
        self.start_time = time.time()
        self.initial_memory = psutil.Process().memory_info().rss / (1024 * 1024)

    def run_test_category(self, category: str, **kwargs) -> TestSuiteResult:
        """Run a specific test category."""

        category_configs = {
            "unit": {
                "files": ["tests/test_e067_threading_comprehensive.py"],
                "markers": "unit and threading",
                "description": "Unit tests for threading components"
            },
            "integration": {
                "files": ["tests/integration/test_e067_threading_determinism.py"],
                "markers": "integration and threading",
                "description": "Integration tests for end-to-end workflows"
            },
            "performance": {
                "files": ["tests/performance/test_e067_threading_benchmarks.py"],
                "markers": "performance and threading",
                "description": "Performance benchmarking tests"
            },
            "determinism": {
                "files": ["tests/integration/test_e067_threading_determinism.py"],
                "markers": "determinism and threading",
                "description": "Determinism validation tests"
            },
            "resource": {
                "files": ["tests/test_e067_resource_validation.py"],
                "markers": "resource and threading",
                "description": "Resource usage validation tests"
            },
            "stress": {
                "files": ["tests/stress/test_e067_threading_stress.py"],
                "markers": "stress and threading",
                "description": "Stress and error condition tests"
            },
            "comprehensive": {
                "files": ["tests/test_e067_threading_comprehensive.py"],
                "markers": "threading",
                "description": "Comprehensive threading functionality tests"
            }
        }

        if category not in category_configs:
            raise ValueError(f"Unknown test category: {category}")

        config = category_configs[category]

        print(f"\n{'='*60}")
        print(f"Running {category.upper()} tests")
        print(f"Description: {config['description']}")
        print(f"Files: {', '.join(config['files'])}")
        print(f"{'='*60}")

        start_time = time.time()
        start_memory = psutil.Process().memory_info().rss / (1024 * 1024)

        # Build pytest command
        cmd = [
            sys.executable, "-m", "pytest",
            "--tb=short",
            "-v",
            f"--maxfail={kwargs.get('maxfail', 10)}",
        ]

        # Add markers
        if config.get("markers"):
            cmd.extend(["-m", config["markers"]])

        # Add specific files
        for test_file in config["files"]:
            test_path = self.project_root / test_file
            if test_path.exists():
                cmd.append(str(test_path))

        # Add additional options
        if kwargs.get("verbose", False):
            cmd.append("--verbose")

        if kwargs.get("capture", True):
            cmd.append("--capture=no")

        if category in ["stress", "performance"] and not kwargs.get("include_slow", False):
            cmd.extend(["-m", "not slow"])

        # Generate JSON report
        report_path = self.project_root / f"test_reports/e067_{category}_results.json"
        report_path.parent.mkdir(exist_ok=True)
        cmd.extend(["--json-report", f"--json-report-file={report_path}"])

        # Execute tests
        print(f"Executing: {' '.join(cmd)}")
        try:
            result = subprocess.run(
                cmd,
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=kwargs.get('timeout', 600)  # 10 minute default timeout
            )

            execution_time = time.time() - start_time
            peak_memory = psutil.Process().memory_info().rss / (1024 * 1024)
            memory_growth = peak_memory - start_memory

            # Parse results
            test_result = self._parse_test_results(result, report_path, execution_time, memory_growth)
            test_result.category = category

            # Display summary
            self._display_category_summary(test_result)

            return test_result

        except subprocess.TimeoutExpired:
            print(f"❌ {category} tests timed out after {kwargs.get('timeout', 600)} seconds")
            return TestSuiteResult(
                category=category,
                passed=0, failed=0, skipped=0, errors=1, warnings=0,
                execution_time=kwargs.get('timeout', 600),
                memory_peak_mb=0,
                details={"error": "Test execution timed out"}
            )
        except Exception as e:
            print(f"❌ Error running {category} tests: {e}")
            return TestSuiteResult(
                category=category,
                passed=0, failed=0, skipped=0, errors=1, warnings=0,
                execution_time=time.time() - start_time,
                memory_peak_mb=0,
                details={"error": str(e)}
            )

    def _parse_test_results(self, process_result, report_path: Path, execution_time: float, memory_growth: float) -> TestSuiteResult:
        """Parse test execution results."""

        # Default result structure
        result = TestSuiteResult(
            category="unknown",
            passed=0, failed=0, skipped=0, errors=0, warnings=0,
            execution_time=execution_time,
            memory_peak_mb=memory_growth,
            details={}
        )

        # Parse pytest output for basic counts
        output_lines = process_result.stdout.split('\n')
        for line in output_lines:
            if "passed" in line and ("failed" in line or "error" in line or "skipped" in line):
                # Parse summary line like "5 passed, 1 failed, 2 skipped in 10.2s"
                parts = line.split()
                for i, part in enumerate(parts):
                    if part == "passed" and i > 0:
                        result.passed = int(parts[i-1])
                    elif part == "failed" and i > 0:
                        result.failed = int(parts[i-1])
                    elif part == "skipped" and i > 0:
                        result.skipped = int(parts[i-1])
                    elif part == "error" and i > 0:
                        result.errors = int(parts[i-1])
                break

        # Try to load JSON report if available
        if report_path.exists():
            try:
                with open(report_path, 'r') as f:
                    json_data = json.load(f)
                    result.details = json_data

                    # Extract more detailed metrics from JSON report
                    if 'summary' in json_data:
                        summary = json_data['summary']
                        result.passed = summary.get('passed', result.passed)
                        result.failed = summary.get('failed', result.failed)
                        result.skipped = summary.get('skipped', result.skipped)
                        result.errors = summary.get('error', result.errors)

            except (json.JSONDecodeError, FileNotFoundError):
                pass  # Use parsed values from stdout

        # Store process details
        result.details.update({
            "return_code": process_result.returncode,
            "stdout_lines": len(output_lines),
            "stderr_lines": len(process_result.stderr.split('\n')) if process_result.stderr else 0
        })

        return result

    def _display_category_summary(self, result: TestSuiteResult):
        """Display summary for a test category."""

        total_tests = result.passed + result.failed + result.skipped + result.errors

        if result.failed > 0 or result.errors > 0:
            status_icon = "❌"
            status = "FAILED"
        elif total_tests == 0:
            status_icon = "⚠️"
            status = "NO TESTS"
        else:
            status_icon = "✅"
            status = "PASSED"

        print(f"\n{status_icon} {result.category.upper()} TESTS {status}")
        print(f"   Passed: {result.passed}")
        print(f"   Failed: {result.failed}")
        print(f"   Skipped: {result.skipped}")
        print(f"   Errors: {result.errors}")
        print(f"   Time: {result.execution_time:.1f}s")
        print(f"   Memory: {result.memory_peak_mb:+.1f}MB")

        if result.failed > 0 or result.errors > 0:
            print(f"   ⚠️  {result.category.title()} tests had failures!")

    def run_all_categories(self, **kwargs) -> Dict[str, TestSuiteResult]:
        """Run all test categories in appropriate order."""

        # Define execution order (dependencies and logical flow)
        if kwargs.get('quick', False):
            categories = ["unit", "integration", "resource"]
        else:
            categories = ["unit", "integration", "determinism", "resource", "performance", "stress"]

        print(f"\n🚀 Starting Epic E067 Threading Test Suite")
        print(f"Categories to run: {', '.join(categories)}")
        print(f"System: {psutil.cpu_count()} cores, {psutil.virtual_memory().total // (1024**3)}GB RAM")

        results = {}

        for category in categories:
            try:
                result = self.run_test_category(category, **kwargs)
                results[category] = result
                self.test_results[category] = result

                # Stop on critical failures for unit/integration tests
                if category in ["unit", "integration"] and (result.failed > 0 or result.errors > 0):
                    if not kwargs.get('continue_on_failure', False):
                        print(f"\n🛑 Stopping execution due to {category} test failures")
                        break

            except KeyboardInterrupt:
                print(f"\n🛑 Test execution interrupted by user")
                break
            except Exception as e:
                print(f"\n❌ Unexpected error in {category} tests: {e}")
                results[category] = TestSuiteResult(
                    category=category, passed=0, failed=0, skipped=0, errors=1, warnings=0,
                    execution_time=0, memory_peak_mb=0, details={"error": str(e)}
                )

        return results

    def generate_summary_report(self, results: Dict[str, TestSuiteResult]) -> str:
        """Generate comprehensive summary report."""

        total_execution_time = time.time() - self.start_time

        report = f"""
Epic E067 Multi-Threading Test Suite - Summary Report
{'='*60}

Execution Summary:
• Total Time: {total_execution_time:.1f} seconds
• Categories Run: {len(results)}
• System: {psutil.cpu_count()} cores, {psutil.virtual_memory().total // (1024**3)}GB RAM

Test Results by Category:
"""

        total_passed = total_failed = total_skipped = total_errors = 0

        for category, result in results.items():
            total_passed += result.passed
            total_failed += result.failed
            total_skipped += result.skipped
            total_errors += result.errors

            status = "✅ PASS" if result.failed == 0 and result.errors == 0 else "❌ FAIL"

            report += f"""
{category.upper()}: {status}
• Passed: {result.passed}, Failed: {result.failed}, Skipped: {result.skipped}, Errors: {result.errors}
• Time: {result.execution_time:.1f}s, Memory: {result.memory_peak_mb:+.1f}MB
"""

        # Overall summary
        overall_status = "PASSED" if total_failed == 0 and total_errors == 0 else "FAILED"

        report += f"""
{'='*60}
OVERALL RESULT: {overall_status}
• Total Tests: {total_passed + total_failed + total_skipped + total_errors}
• Passed: {total_passed}
• Failed: {total_failed}
• Skipped: {total_skipped}
• Errors: {total_errors}

Performance Target Validation:
"""

        # Add performance target analysis if available
        if "performance" in results:
            perf_result = results["performance"]
            if perf_result.passed > 0:
                report += "• ✅ Performance benchmarks completed\n"
            else:
                report += "• ❌ Performance benchmarks failed\n"
        else:
            report += "• ⚠️ Performance benchmarks not run\n"

        if "resource" in results:
            resource_result = results["resource"]
            if resource_result.passed > 0:
                report += "• ✅ Resource validation passed\n"
            else:
                report += "• ❌ Resource validation failed\n"
        else:
            report += "• ⚠️ Resource validation not run\n"

        if "determinism" in results:
            det_result = results["determinism"]
            if det_result.passed > 0:
                report += "• ✅ Determinism validation passed\n"
            else:
                report += "• ❌ Determinism validation failed\n"
        else:
            report += "• ⚠️ Determinism validation not run\n"

        report += f"\nGenerated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"

        return report

    def save_report(self, results: Dict[str, TestSuiteResult], filepath: Optional[Path] = None):
        """Save detailed report to file."""

        if filepath is None:
            filepath = self.project_root / "test_reports" / f"e067_threading_summary_{int(time.time())}.txt"

        filepath.parent.mkdir(exist_ok=True)

        report_content = self.generate_summary_report(results)

        with open(filepath, 'w') as f:
            f.write(report_content)

        print(f"📊 Detailed report saved to: {filepath}")
        return filepath


def main():
    """Main entry point."""

    parser = argparse.ArgumentParser(
        description="Run Epic E067 Threading Test Suite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/run_e067_threading_tests.py --quick
  python scripts/run_e067_threading_tests.py --category unit
  python scripts/run_e067_threading_tests.py --performance --report
  python scripts/run_e067_threading_tests.py --stress --verbose
        """
    )

    parser.add_argument(
        "--category",
        choices=["unit", "integration", "performance", "determinism", "resource", "stress", "comprehensive"],
        help="Run specific test category only"
    )

    parser.add_argument(
        "--quick",
        action="store_true",
        help="Run only fast tests (skip performance and stress tests)"
    )

    parser.add_argument(
        "--performance",
        action="store_true",
        help="Include performance benchmarking tests"
    )

    parser.add_argument(
        "--stress",
        action="store_true",
        help="Include stress tests"
    )

    parser.add_argument(
        "--report",
        action="store_true",
        help="Generate detailed HTML/text report"
    )

    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose test output"
    )

    parser.add_argument(
        "--continue-on-failure",
        action="store_true",
        help="Continue running tests even if critical tests fail"
    )

    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="Timeout for each test category in seconds (default: 600)"
    )

    parser.add_argument(
        "--maxfail",
        type=int,
        default=10,
        help="Stop after this many failures per category (default: 10)"
    )

    args = parser.parse_args()

    # Create test runner
    runner = E067ThreadingTestRunner()

    try:
        if args.category:
            # Run single category
            result = runner.run_test_category(
                args.category,
                verbose=args.verbose,
                timeout=args.timeout,
                maxfail=args.maxfail,
                include_slow=args.performance or args.stress
            )
            results = {args.category: result}
        else:
            # Run all categories
            kwargs = {
                'quick': args.quick,
                'verbose': args.verbose,
                'timeout': args.timeout,
                'maxfail': args.maxfail,
                'continue_on_failure': args.continue_on_failure,
                'include_slow': args.performance or args.stress
            }
            results = runner.run_all_categories(**kwargs)

        # Display and save summary
        print(runner.generate_summary_report(results))

        if args.report:
            report_path = runner.save_report(results)
            print(f"Report saved to: {report_path}")

        # Exit with appropriate code
        total_failures = sum(r.failed + r.errors for r in results.values())
        sys.exit(0 if total_failures == 0 else 1)

    except KeyboardInterrupt:
        print("\n🛑 Test execution interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Unexpected error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
