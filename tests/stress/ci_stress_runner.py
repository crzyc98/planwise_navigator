#!/usr/bin/env python3
"""
CI/CD-compatible stress testing runner for PlanWise Navigator.

Story S063-09: Large Dataset Stress Testing
- Automated stress testing designed for CI/CD pipelines
- Appropriate scope and timeouts for CI environments
- Performance regression detection and alerting
- Baseline performance tracking and comparison
"""

import json
import logging
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .large_dataset_generator import LargeDatasetGenerator
from .stress_test_framework import StressTestSuite, StressTestResult, OPTIMIZATION_LEVELS

# Configure logging for CI environments
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('ci_stress_test.log', mode='w')
    ]
)
logger = logging.getLogger(__name__)

class CIStressTestRunner:
    """CI/CD-optimized stress testing runner with regression detection"""

    def __init__(self, base_dir: Path = None):
        if base_dir is None:
            base_dir = Path.cwd()

        self.base_dir = base_dir
        self.test_data_dir = base_dir / "data" / "ci_stress_test"
        self.results_dir = base_dir / "test_results" / "ci_stress_tests"
        self.baseline_dir = base_dir / "test_baselines" / "stress_tests"

        # Create directories
        self.test_data_dir.mkdir(parents=True, exist_ok=True)
        self.results_dir.mkdir(parents=True, exist_ok=True)
        self.baseline_dir.mkdir(parents=True, exist_ok=True)

    def run_ci_stress_tests(
        self,
        test_level: str = "quick",
        timeout_minutes: int = 30,
        enable_regression_detection: bool = True
    ) -> Dict[str, Any]:
        """
        Run CI-appropriate stress tests

        Args:
            test_level: "quick", "standard", or "comprehensive"
            timeout_minutes: Overall timeout for all tests
            enable_regression_detection: Enable performance regression detection

        Returns:
            Test results with pass/fail status and metrics
        """
        logger.info(f"\n{'='*60}")
        logger.info(f"CI STRESS TEST RUNNER")
        logger.info(f"{'='*60}")
        logger.info(f"Test level: {test_level}")
        logger.info(f"Timeout: {timeout_minutes} minutes")
        logger.info(f"Regression detection: {'enabled' if enable_regression_detection else 'disabled'}")
        logger.info(f"Base directory: {self.base_dir}")

        start_time = time.time()

        # Configure test parameters based on level
        test_config = self._get_test_config(test_level)

        # Ensure test data exists
        self._ensure_test_data(test_config["dataset_sizes"])

        # Run stress tests
        logger.info(f"\nRunning {test_level} stress tests...")
        suite = StressTestSuite(self.test_data_dir, self.results_dir)

        test_results = suite.run_comprehensive_stress_tests(
            dataset_sizes=test_config["dataset_sizes"],
            optimization_levels=test_config["optimization_levels"],
            max_simulation_years=test_config["max_years"],
            timeout_minutes=test_config["timeout_per_test"]
        )

        # Analyze results
        analysis = self._analyze_test_results(test_results, test_config)

        # Performance regression detection
        regression_results = None
        if enable_regression_detection:
            regression_results = self._check_performance_regression(test_results, test_config)
            analysis["regression_analysis"] = regression_results

        # Calculate overall CI result
        ci_result = self._determine_ci_result(analysis, regression_results)

        # Generate CI report
        total_duration = time.time() - start_time
        ci_report = self._generate_ci_report(
            test_level=test_level,
            test_config=test_config,
            test_results=test_results,
            analysis=analysis,
            ci_result=ci_result,
            duration_seconds=total_duration
        )

        # Log final result
        self._log_ci_summary(ci_result, total_duration, test_level)

        return ci_report

    def _get_test_config(self, test_level: str) -> Dict[str, Any]:
        """Get test configuration based on test level"""

        configurations = {
            "quick": {
                "dataset_sizes": [1000, 10000],
                "optimization_levels": ["medium"],
                "max_years": 2,
                "timeout_per_test": 10,
                "description": "Quick validation for pull request CI"
            },
            "standard": {
                "dataset_sizes": [10000, 50000],
                "optimization_levels": ["medium", "high"],
                "max_years": 3,
                "timeout_per_test": 20,
                "description": "Standard CI testing for merge validation"
            },
            "comprehensive": {
                "dataset_sizes": [10000, 50000, 100000],
                "optimization_levels": ["low", "medium", "high"],
                "max_years": 5,
                "timeout_per_test": 30,
                "description": "Comprehensive testing for releases and nightly builds"
            }
        }

        if test_level not in configurations:
            logger.warning(f"Unknown test level '{test_level}', defaulting to 'standard'")
            test_level = "standard"

        return configurations[test_level]

    def _ensure_test_data(self, dataset_sizes: List[int]):
        """Ensure required test datasets exist"""
        logger.info("Checking test data availability...")

        missing_datasets = []

        for size in dataset_sizes:
            parquet_path = self.test_data_dir / f"stress_test_{size:06d}_employees.parquet"
            csv_path = self.test_data_dir / f"stress_test_{size:06d}_employees.csv"

            if not parquet_path.exists() and not csv_path.exists():
                missing_datasets.append(size)

        if missing_datasets:
            logger.info(f"Generating missing test datasets: {missing_datasets}")

            for size in missing_datasets:
                logger.info(f"Generating {size:,} employee dataset...")

                generator = LargeDatasetGenerator(size, memory_efficient=True)
                df = generator.generate_dataset(
                    batch_size=min(5000, size // 5),  # Smaller batches for CI
                    include_terminated=True,
                    termination_rate=0.08
                )

                # Save in parquet format for efficiency
                output_path = self.test_data_dir / f"stress_test_{size:06d}_employees.parquet"
                df.to_parquet(output_path, index=False, compression="snappy")

                logger.info(f"Generated dataset: {output_path}")

        else:
            logger.info("All required test datasets are available")

    def _analyze_test_results(
        self,
        test_results: List[StressTestResult],
        test_config: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Analyze test results for CI decision making"""

        total_tests = len(test_results)
        passed_tests = sum(1 for r in test_results if r.success)
        failed_tests = total_tests - passed_tests

        memory_exceeded_tests = sum(1 for r in test_results if r.memory_exceeded_limit)

        # Calculate performance statistics
        successful_results = [r for r in test_results if r.success]

        if successful_results:
            avg_duration = sum(r.test_duration for r in successful_results) / len(successful_results)
            avg_peak_memory = sum(r.peak_memory_mb for r in successful_results) / len(successful_results)
            avg_processing_rate = sum(r.processing_rate_records_per_sec for r in successful_results if r.processing_rate_records_per_sec > 0) / len([r for r in successful_results if r.processing_rate_records_per_sec > 0])
        else:
            avg_duration = 0
            avg_peak_memory = 0
            avg_processing_rate = 0

        # Analyze by optimization level
        by_opt_level = {}
        for result in test_results:
            level = result.optimization_level
            if level not in by_opt_level:
                by_opt_level[level] = {"total": 0, "passed": 0, "memory_exceeded": 0}

            by_opt_level[level]["total"] += 1
            if result.success:
                by_opt_level[level]["passed"] += 1
            if result.memory_exceeded_limit:
                by_opt_level[level]["memory_exceeded"] += 1

        # Calculate success rates by optimization level
        for level_stats in by_opt_level.values():
            level_stats["success_rate"] = level_stats["passed"] / level_stats["total"] if level_stats["total"] > 0 else 0
            level_stats["memory_compliance_rate"] = (level_stats["total"] - level_stats["memory_exceeded"]) / level_stats["total"] if level_stats["total"] > 0 else 0

        return {
            "summary": {
                "total_tests": total_tests,
                "passed_tests": passed_tests,
                "failed_tests": failed_tests,
                "success_rate": passed_tests / total_tests if total_tests > 0 else 0,
                "memory_exceeded_tests": memory_exceeded_tests,
                "memory_compliance_rate": (total_tests - memory_exceeded_tests) / total_tests if total_tests > 0 else 0
            },
            "performance": {
                "avg_duration_seconds": avg_duration,
                "avg_peak_memory_mb": avg_peak_memory,
                "avg_processing_rate_records_per_sec": avg_processing_rate
            },
            "by_optimization_level": by_opt_level,
            "test_config": test_config
        }

    def _check_performance_regression(
        self,
        test_results: List[StressTestResult],
        test_config: Dict[str, Any]
    ) -> Optional[Dict[str, Any]]:
        """Check for performance regression against baseline"""

        # Try to load baseline performance data
        baseline_path = self.baseline_dir / "performance_baseline.json"

        if not baseline_path.exists():
            logger.info("No performance baseline found - establishing new baseline")
            self._establish_performance_baseline(test_results, test_config)
            return {
                "baseline_status": "established",
                "regression_detected": False,
                "message": "New performance baseline established"
            }

        try:
            with open(baseline_path, 'r') as f:
                baseline = json.load(f)
        except Exception as e:
            logger.warning(f"Failed to load performance baseline: {e}")
            return None

        # Compare current results to baseline
        regression_analysis = {
            "baseline_status": "loaded",
            "regression_detected": False,
            "regressions": [],
            "improvements": [],
            "baseline_date": baseline.get("date", "unknown"),
            "comparison_date": datetime.now().isoformat()
        }

        # Performance regression thresholds
        REGRESSION_THRESHOLD = 0.20  # 20% performance degradation
        MEMORY_THRESHOLD = 0.15      # 15% memory increase
        SUCCESS_RATE_THRESHOLD = 0.05 # 5% success rate drop

        # Compare key metrics
        current_metrics = self._extract_baseline_metrics(test_results)
        baseline_metrics = baseline.get("metrics", {})

        for metric_name, current_value in current_metrics.items():
            if metric_name in baseline_metrics:
                baseline_value = baseline_metrics[metric_name]

                if baseline_value > 0:  # Avoid division by zero
                    change_pct = (current_value - baseline_value) / baseline_value

                    # Check for regressions
                    is_regression = False

                    if metric_name == "avg_duration_seconds" and change_pct > REGRESSION_THRESHOLD:
                        is_regression = True
                    elif metric_name == "avg_peak_memory_mb" and change_pct > MEMORY_THRESHOLD:
                        is_regression = True
                    elif metric_name == "success_rate" and change_pct < -SUCCESS_RATE_THRESHOLD:
                        is_regression = True
                    elif metric_name == "memory_compliance_rate" and change_pct < -SUCCESS_RATE_THRESHOLD:
                        is_regression = True

                    if is_regression:
                        regression_analysis["regression_detected"] = True
                        regression_analysis["regressions"].append({
                            "metric": metric_name,
                            "baseline_value": baseline_value,
                            "current_value": current_value,
                            "change_percent": change_pct * 100,
                            "severity": "high" if abs(change_pct) > 0.3 else "medium"
                        })

                    # Check for improvements (positive changes)
                    elif ((metric_name in ["avg_processing_rate_records_per_sec", "success_rate", "memory_compliance_rate"] and change_pct > 0.1) or
                          (metric_name in ["avg_duration_seconds", "avg_peak_memory_mb"] and change_pct < -0.1)):
                        regression_analysis["improvements"].append({
                            "metric": metric_name,
                            "baseline_value": baseline_value,
                            "current_value": current_value,
                            "improvement_percent": abs(change_pct) * 100
                        })

        return regression_analysis

    def _extract_baseline_metrics(self, test_results: List[StressTestResult]) -> Dict[str, float]:
        """Extract key metrics for baseline comparison"""
        successful_results = [r for r in test_results if r.success]

        if not successful_results:
            return {}

        total_tests = len(test_results)
        memory_exceeded = sum(1 for r in test_results if r.memory_exceeded_limit)

        return {
            "avg_duration_seconds": sum(r.test_duration for r in successful_results) / len(successful_results),
            "avg_peak_memory_mb": sum(r.peak_memory_mb for r in successful_results) / len(successful_results),
            "avg_processing_rate_records_per_sec": sum(r.processing_rate_records_per_sec for r in successful_results if r.processing_rate_records_per_sec > 0) / len([r for r in successful_results if r.processing_rate_records_per_sec > 0]) if any(r.processing_rate_records_per_sec > 0 for r in successful_results) else 0,
            "success_rate": len(successful_results) / total_tests if total_tests > 0 else 0,
            "memory_compliance_rate": (total_tests - memory_exceeded) / total_tests if total_tests > 0 else 0
        }

    def _establish_performance_baseline(
        self,
        test_results: List[StressTestResult],
        test_config: Dict[str, Any]
    ):
        """Establish new performance baseline"""

        baseline_data = {
            "date": datetime.now().isoformat(),
            "test_config": test_config,
            "metrics": self._extract_baseline_metrics(test_results),
            "test_results_count": len(test_results),
            "git_commit": os.environ.get("GITHUB_SHA", os.environ.get("GIT_COMMIT", "unknown")),
            "ci_environment": {
                "runner": os.environ.get("RUNNER_NAME", "unknown"),
                "os": os.environ.get("RUNNER_OS", "unknown"),
                "github_workflow": os.environ.get("GITHUB_WORKFLOW", "unknown")
            }
        }

        baseline_path = self.baseline_dir / "performance_baseline.json"

        with open(baseline_path, 'w') as f:
            json.dump(baseline_data, f, indent=2)

        logger.info(f"Performance baseline established: {baseline_path}")

    def _determine_ci_result(
        self,
        analysis: Dict[str, Any],
        regression_results: Optional[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Determine overall CI pass/fail result"""

        # CI failure conditions
        failure_reasons = []
        warnings = []

        # Success rate threshold
        success_rate = analysis["summary"]["success_rate"]
        if success_rate < 0.95:  # Less than 95% success rate
            failure_reasons.append(f"Success rate too low: {success_rate:.1%} < 95%")

        # Memory compliance threshold
        memory_compliance = analysis["summary"]["memory_compliance_rate"]
        if memory_compliance < 0.95:  # More than 5% memory limit violations
            failure_reasons.append(f"Memory compliance too low: {memory_compliance:.1%} < 95%")

        # Performance regression check
        if regression_results and regression_results.get("regression_detected", False):
            high_severity_regressions = [r for r in regression_results.get("regressions", []) if r.get("severity") == "high"]
            if high_severity_regressions:
                failure_reasons.append(f"High severity performance regression detected: {len(high_severity_regressions)} metrics")
            else:
                warnings.append(f"Performance regression detected: {len(regression_results.get('regressions', []))} metrics")

        # Determine overall result
        if failure_reasons:
            result_status = "FAIL"
            result_message = f"CI stress tests failed: {'; '.join(failure_reasons)}"
        else:
            result_status = "PASS"
            result_message = "All CI stress tests passed successfully"

            if warnings:
                result_message += f" (warnings: {'; '.join(warnings)})"

        return {
            "status": result_status,
            "message": result_message,
            "failure_reasons": failure_reasons,
            "warnings": warnings,
            "exit_code": 1 if failure_reasons else 0
        }

    def _generate_ci_report(
        self,
        test_level: str,
        test_config: Dict[str, Any],
        test_results: List[StressTestResult],
        analysis: Dict[str, Any],
        ci_result: Dict[str, Any],
        duration_seconds: float
    ) -> Dict[str, Any]:
        """Generate comprehensive CI report"""

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        report = {
            "metadata": {
                "timestamp": datetime.now().isoformat(),
                "test_level": test_level,
                "duration_seconds": duration_seconds,
                "duration_minutes": duration_seconds / 60,
                "git_commit": os.environ.get("GITHUB_SHA", os.environ.get("GIT_COMMIT", "unknown")),
                "ci_environment": {
                    "github_workflow": os.environ.get("GITHUB_WORKFLOW"),
                    "github_run_id": os.environ.get("GITHUB_RUN_ID"),
                    "runner_os": os.environ.get("RUNNER_OS"),
                    "runner_name": os.environ.get("RUNNER_NAME")
                }
            },
            "test_config": test_config,
            "ci_result": ci_result,
            "analysis": analysis,
            "test_results": [r.to_dict() for r in test_results]
        }

        # Save CI report
        report_path = self.results_dir / f"ci_stress_test_report_{timestamp}.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        # Save CI summary for easy parsing
        ci_summary = {
            "status": ci_result["status"],
            "message": ci_result["message"],
            "test_level": test_level,
            "total_tests": analysis["summary"]["total_tests"],
            "passed_tests": analysis["summary"]["passed_tests"],
            "success_rate": analysis["summary"]["success_rate"],
            "duration_minutes": duration_seconds / 60,
            "timestamp": datetime.now().isoformat()
        }

        summary_path = self.results_dir / f"ci_summary_{timestamp}.json"
        with open(summary_path, 'w') as f:
            json.dump(ci_summary, f, indent=2)

        logger.info(f"CI report saved: {report_path}")
        logger.info(f"CI summary saved: {summary_path}")

        return report

    def _log_ci_summary(self, ci_result: Dict[str, Any], duration_seconds: float, test_level: str):
        """Log final CI summary"""

        status_icon = "✅" if ci_result["status"] == "PASS" else "❌"

        logger.info(f"\n{'='*60}")
        logger.info(f"CI STRESS TEST SUMMARY")
        logger.info(f"{'='*60}")
        logger.info(f"{status_icon} Status: {ci_result['status']}")
        logger.info(f"Message: {ci_result['message']}")
        logger.info(f"Test level: {test_level}")
        logger.info(f"Duration: {duration_seconds:.1f} seconds ({duration_seconds/60:.1f} minutes)")

        if ci_result["warnings"]:
            logger.info(f"Warnings: {len(ci_result['warnings'])}")
            for warning in ci_result["warnings"]:
                logger.info(f"  ⚠️ {warning}")

        if ci_result["failure_reasons"]:
            logger.info(f"Failure reasons: {len(ci_result['failure_reasons'])}")
            for reason in ci_result["failure_reasons"]:
                logger.error(f"  ❌ {reason}")

        logger.info(f"Exit code: {ci_result['exit_code']}")

def main():
    """CLI entry point for CI stress testing"""
    import argparse

    parser = argparse.ArgumentParser(
        description="PlanWise Navigator CI/CD Stress Test Runner",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        "--test-level",
        choices=["quick", "standard", "comprehensive"],
        default="standard",
        help="Test level for CI environment"
    )

    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=30,
        help="Overall timeout for all tests"
    )

    parser.add_argument(
        "--no-regression-detection",
        action="store_true",
        help="Disable performance regression detection"
    )

    parser.add_argument(
        "--base-dir",
        type=Path,
        default=Path.cwd(),
        help="Base directory for test execution"
    )

    parser.add_argument(
        "--establish-baseline",
        action="store_true",
        help="Force establishment of new performance baseline"
    )

    args = parser.parse_args()

    logger.info(f"PlanWise Navigator CI Stress Test Runner")
    logger.info(f"Story S063-09: Automated CI/CD Stress Testing")

    # Initialize runner
    runner = CIStressTestRunner(base_dir=args.base_dir)

    # Force baseline establishment if requested
    if args.establish_baseline:
        baseline_path = runner.baseline_dir / "performance_baseline.json"
        if baseline_path.exists():
            backup_path = runner.baseline_dir / f"performance_baseline_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
            baseline_path.rename(backup_path)
            logger.info(f"Existing baseline backed up to: {backup_path}")

    try:
        # Run CI stress tests
        ci_report = runner.run_ci_stress_tests(
            test_level=args.test_level,
            timeout_minutes=args.timeout_minutes,
            enable_regression_detection=not args.no_regression_detection
        )

        # Exit with appropriate code for CI
        exit_code = ci_report["ci_result"]["exit_code"]
        sys.exit(exit_code)

    except KeyboardInterrupt:
        logger.info("CI stress testing interrupted by user")
        sys.exit(130)  # Standard exit code for SIGINT

    except Exception as e:
        logger.error(f"CI stress testing failed with exception: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
