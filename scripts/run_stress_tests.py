#!/usr/bin/env python3
"""
Unified stress testing runner for PlanWise Navigator.

Story S063-09: Large Dataset Stress Testing
Provides a single entry point for all stress testing capabilities:
- Data generation
- Basic stress testing
- Performance benchmarking
- Multi-year scalability testing
- CI/CD automation
"""

import argparse
import logging
import subprocess
import sys
from pathlib import Path
from typing import List

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def run_command(cmd: List[str], description: str) -> int:
    """Run a command and return exit code"""
    logger.info(f"Running {description}...")
    logger.info(f"Command: {' '.join(cmd)}")

    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except Exception as e:
        logger.error(f"Failed to run {description}: {e}")
        return 1

def generate_test_data(
    sizes: List[int],
    output_dir: Path,
    formats: List[str] = ["parquet"]
) -> int:
    """Generate test datasets"""
    cmd = [
        sys.executable,
        "tests/stress/large_dataset_generator.py",
        "--sizes"
    ] + [str(s) for s in sizes] + [
        "--output-dir", str(output_dir),
        "--formats"
    ] + formats

    return run_command(cmd, f"Test data generation for sizes {sizes}")

def run_stress_tests(
    dataset_sizes: List[int],
    optimization_levels: List[str],
    test_data_dir: Path,
    results_dir: Path,
    max_years: int = 3,
    timeout_minutes: int = 60,
    quick_test: bool = False
) -> int:
    """Run comprehensive stress tests"""
    cmd = [
        sys.executable,
        "tests/stress/stress_test_framework.py",
        "--test-data-dir", str(test_data_dir),
        "--results-dir", str(results_dir),
        "--dataset-sizes"
    ] + [str(s) for s in dataset_sizes] + [
        "--optimization-levels"
    ] + optimization_levels + [
        "--max-years", str(max_years),
        "--timeout-minutes", str(timeout_minutes)
    ]

    if quick_test:
        cmd.append("--quick-test")

    return run_command(cmd, "Comprehensive stress testing")

def run_performance_benchmark(
    dataset_sizes: List[int],
    test_data_dir: Path,
    results_dir: Path,
    simulation_years: List[int] = [2025, 2026],
    runs_per_config: int = 3,
    timeout_minutes: int = 60,
    quick_benchmark: bool = False
) -> int:
    """Run performance benchmarking"""
    cmd = [
        sys.executable,
        "tests/stress/performance_benchmark.py",
        "--test-data-dir", str(test_data_dir),
        "--results-dir", str(results_dir),
        "--dataset-sizes"
    ] + [str(s) for s in dataset_sizes] + [
        "--simulation-years"
    ] + [str(y) for y in simulation_years] + [
        "--runs-per-config", str(runs_per_config),
        "--timeout-minutes", str(timeout_minutes)
    ]

    if quick_benchmark:
        cmd.append("--quick-benchmark")

    return run_command(cmd, "Performance benchmarking")

def run_multi_year_scalability(
    dataset_sizes: List[int],
    test_data_dir: Path,
    results_dir: Path,
    max_years: int = 10,
    optimization_levels: List[str] = ["medium", "high"],
    single_test: bool = False
) -> int:
    """Run multi-year scalability testing"""
    cmd = [
        sys.executable,
        "tests/stress/multi_year_scalability.py",
        "--test-data-dir", str(test_data_dir),
        "--results-dir", str(results_dir),
        "--dataset-sizes"
    ] + [str(s) for s in dataset_sizes] + [
        "--max-years", str(max_years),
        "--optimization-levels"
    ] + optimization_levels

    if single_test:
        cmd.append("--single-test")

    return run_command(cmd, "Multi-year scalability testing")

def run_ci_tests(
    test_level: str = "standard",
    timeout_minutes: int = 30,
    base_dir: Path = Path.cwd(),
    no_regression_detection: bool = False
) -> int:
    """Run CI-optimized stress tests"""
    cmd = [
        sys.executable,
        "tests/stress/ci_stress_runner.py",
        "--test-level", test_level,
        "--timeout-minutes", str(timeout_minutes),
        "--base-dir", str(base_dir)
    ]

    if no_regression_detection:
        cmd.append("--no-regression-detection")

    return run_command(cmd, f"CI stress testing ({test_level} level)")

def main():
    """Main entry point for stress testing"""
    parser = argparse.ArgumentParser(
        description="PlanWise Navigator Comprehensive Stress Testing Suite",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    # Test mode selection
    parser.add_argument(
        "mode",
        choices=["generate-data", "stress-test", "benchmark", "scalability", "ci", "full-suite"],
        help="Testing mode to run"
    )

    # Common options
    parser.add_argument(
        "--dataset-sizes",
        type=int,
        nargs="+",
        default=[10000, 50000, 100000],
        help="Dataset sizes to test (number of employees)"
    )

    parser.add_argument(
        "--test-data-dir",
        type=Path,
        default=Path("data/stress_test"),
        help="Directory for test datasets"
    )

    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("test_results/stress_tests"),
        help="Directory for test results"
    )

    parser.add_argument(
        "--optimization-levels",
        choices=["low", "medium", "high"],
        nargs="+",
        default=["medium", "high"],
        help="Optimization levels to test"
    )

    # Data generation options
    parser.add_argument(
        "--formats",
        choices=["parquet", "csv"],
        nargs="+",
        default=["parquet"],
        help="Output formats for generated data"
    )

    # Testing options
    parser.add_argument(
        "--max-years",
        type=int,
        default=3,
        help="Maximum simulation years for stress testing"
    )

    parser.add_argument(
        "--timeout-minutes",
        type=int,
        default=60,
        help="Timeout per test in minutes"
    )

    parser.add_argument(
        "--quick-test",
        action="store_true",
        help="Run quick test with reduced scope"
    )

    # Benchmarking options
    parser.add_argument(
        "--simulation-years",
        type=int,
        nargs="+",
        default=[2025, 2026],
        help="Simulation years for benchmarking"
    )

    parser.add_argument(
        "--runs-per-config",
        type=int,
        default=3,
        help="Number of runs per configuration for benchmarking"
    )

    # Scalability options
    parser.add_argument(
        "--scalability-max-years",
        type=int,
        default=10,
        help="Maximum years for scalability testing"
    )

    parser.add_argument(
        "--single-scalability-test",
        action="store_true",
        help="Run single scalability test instead of comprehensive"
    )

    # CI options
    parser.add_argument(
        "--ci-test-level",
        choices=["quick", "standard", "comprehensive"],
        default="standard",
        help="CI test level"
    )

    parser.add_argument(
        "--no-regression-detection",
        action="store_true",
        help="Disable performance regression detection"
    )

    # Full suite options
    parser.add_argument(
        "--skip-data-generation",
        action="store_true",
        help="Skip data generation in full suite mode"
    )

    args = parser.parse_args()

    logger.info(f"PlanWise Navigator Stress Testing Suite")
    logger.info(f"Story S063-09: Large Dataset Stress Testing")
    logger.info(f"Mode: {args.mode}")

    # Ensure directories exist
    args.test_data_dir.mkdir(parents=True, exist_ok=True)
    args.results_dir.mkdir(parents=True, exist_ok=True)

    exit_code = 0

    try:
        if args.mode == "generate-data":
            exit_code = generate_test_data(
                sizes=args.dataset_sizes,
                output_dir=args.test_data_dir,
                formats=args.formats
            )

        elif args.mode == "stress-test":
            exit_code = run_stress_tests(
                dataset_sizes=args.dataset_sizes,
                optimization_levels=args.optimization_levels,
                test_data_dir=args.test_data_dir,
                results_dir=args.results_dir,
                max_years=args.max_years,
                timeout_minutes=args.timeout_minutes,
                quick_test=args.quick_test
            )

        elif args.mode == "benchmark":
            exit_code = run_performance_benchmark(
                dataset_sizes=args.dataset_sizes,
                test_data_dir=args.test_data_dir,
                results_dir=args.results_dir / "performance_benchmarks",
                simulation_years=args.simulation_years,
                runs_per_config=args.runs_per_config,
                timeout_minutes=args.timeout_minutes,
                quick_benchmark=args.quick_test
            )

        elif args.mode == "scalability":
            exit_code = run_multi_year_scalability(
                dataset_sizes=args.dataset_sizes,
                test_data_dir=args.test_data_dir,
                results_dir=args.results_dir / "multi_year_scalability",
                max_years=args.scalability_max_years,
                optimization_levels=args.optimization_levels,
                single_test=args.single_scalability_test
            )

        elif args.mode == "ci":
            exit_code = run_ci_tests(
                test_level=args.ci_test_level,
                timeout_minutes=args.timeout_minutes,
                base_dir=Path.cwd(),
                no_regression_detection=args.no_regression_detection
            )

        elif args.mode == "full-suite":
            logger.info("Running full stress testing suite...")

            # 1. Generate test data (unless skipped)
            if not args.skip_data_generation:
                logger.info("\n" + "="*60)
                logger.info("STEP 1: GENERATING TEST DATA")
                logger.info("="*60)

                exit_code = generate_test_data(
                    sizes=args.dataset_sizes,
                    output_dir=args.test_data_dir,
                    formats=args.formats
                )

                if exit_code != 0:
                    logger.error("Test data generation failed")
                    return exit_code
            else:
                logger.info("Skipping test data generation")

            # 2. Run stress tests
            logger.info("\n" + "="*60)
            logger.info("STEP 2: COMPREHENSIVE STRESS TESTING")
            logger.info("="*60)

            exit_code = run_stress_tests(
                dataset_sizes=args.dataset_sizes,
                optimization_levels=args.optimization_levels,
                test_data_dir=args.test_data_dir,
                results_dir=args.results_dir,
                max_years=args.max_years,
                timeout_minutes=args.timeout_minutes,
                quick_test=args.quick_test
            )

            if exit_code != 0:
                logger.warning("Stress testing had issues, but continuing with suite")

            # 3. Run performance benchmarks
            logger.info("\n" + "="*60)
            logger.info("STEP 3: PERFORMANCE BENCHMARKING")
            logger.info("="*60)

            benchmark_exit = run_performance_benchmark(
                dataset_sizes=args.dataset_sizes[:2],  # Limit for time
                test_data_dir=args.test_data_dir,
                results_dir=args.results_dir / "performance_benchmarks",
                simulation_years=args.simulation_years,
                runs_per_config=min(args.runs_per_config, 2),  # Limit for time
                timeout_minutes=args.timeout_minutes,
                quick_benchmark=args.quick_test
            )

            if benchmark_exit != 0:
                logger.warning("Performance benchmarking had issues, but continuing")
                exit_code = max(exit_code, benchmark_exit)

            # 4. Run scalability testing (limited scope)
            logger.info("\n" + "="*60)
            logger.info("STEP 4: SCALABILITY TESTING")
            logger.info("="*60)

            scalability_exit = run_multi_year_scalability(
                dataset_sizes=args.dataset_sizes[:2],  # Limit for time
                test_data_dir=args.test_data_dir,
                results_dir=args.results_dir / "multi_year_scalability",
                max_years=min(args.scalability_max_years, 5),  # Limit for time
                optimization_levels=args.optimization_levels[:2],  # Limit for time
                single_test=False
            )

            if scalability_exit != 0:
                logger.warning("Scalability testing had issues")
                exit_code = max(exit_code, scalability_exit)

            logger.info("\n" + "="*60)
            logger.info("FULL SUITE COMPLETED")
            logger.info("="*60)
            logger.info(f"Overall exit code: {exit_code}")
            logger.info(f"Results directory: {args.results_dir}")

        # Final status
        if exit_code == 0:
            logger.info("✅ All stress tests completed successfully")
        else:
            logger.error("❌ Some stress tests failed or had issues")

    except KeyboardInterrupt:
        logger.info("Stress testing interrupted by user")
        exit_code = 130

    except Exception as e:
        logger.error(f"Stress testing failed with exception: {e}")
        exit_code = 1

    return exit_code

if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
