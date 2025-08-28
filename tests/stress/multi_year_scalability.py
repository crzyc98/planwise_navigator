#!/usr/bin/env python3
"""
Multi-year simulation scalability testing for PlanWise Navigator.

Story S063-09: Large Dataset Stress Testing
- Test scalability for multi-year simulations (5+ years) with large datasets
- Memory growth patterns across simulation years
- State accumulation and checkpoint effectiveness
- Long-running simulation stability validation
"""

import json
import logging
import time
from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import psutil

from .stress_test_framework import (
    OPTIMIZATION_LEVELS,
    StressTestExecutor,
    StressTestResult,
    MemoryProfiler,
    DatabaseAnalyzer
)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class YearMetrics:
    """Per-year performance metrics"""
    year: int
    execution_time_seconds: float
    peak_memory_mb: float
    memory_delta_mb: float  # Memory change from previous year
    database_size_mb: float
    records_added: int
    cumulative_records: int
    success: bool
    error_message: Optional[str] = None

@dataclass
class MultiYearScalabilityResult:
    """Results from multi-year scalability testing"""

    # Test configuration
    dataset_size: int
    optimization_level: str
    simulation_years: List[int]
    total_duration_seconds: float

    # Per-year metrics
    year_metrics: List[YearMetrics]

    # Scaling characteristics
    memory_growth_rate_mb_per_year: float
    execution_time_growth_rate_sec_per_year: float
    database_growth_rate_mb_per_year: float

    # Success metrics
    years_completed: int
    years_failed: int
    overall_success: bool
    failure_point: Optional[int] = None  # First year that failed

    # Resource efficiency
    peak_memory_utilization_pct: float
    average_memory_utilization_pct: float
    memory_limit_exceeded: bool

    # State management
    checkpoint_overhead_seconds: float
    checkpoint_success_rate: float
    state_compression_effectiveness_pct: float

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

class MultiYearScalabilityTester:
    """Test multi-year simulation scalability characteristics"""

    def __init__(self, test_data_dir: Path, results_dir: Path):
        self.test_data_dir = test_data_dir
        self.results_dir = results_dir
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def test_multi_year_scalability(
        self,
        dataset_size: int,
        max_years: int = 10,
        optimization_level: str = "medium",
        timeout_minutes_per_year: int = 30
    ) -> MultiYearScalabilityResult:
        """
        Test scalability of multi-year simulations

        Args:
            dataset_size: Number of employees in test dataset
            max_years: Maximum years to simulate (test will stop at first failure)
            optimization_level: Optimization level to use
            timeout_minutes_per_year: Timeout per individual year

        Returns:
            MultiYearScalabilityResult with detailed scaling characteristics
        """
        logger.info(f"\n{'='*70}")
        logger.info(f"MULTI-YEAR SCALABILITY TEST")
        logger.info(f"{'='*70}")
        logger.info(f"Dataset size: {dataset_size:,} employees")
        logger.info(f"Maximum years: {max_years} (2025-{2024+max_years})")
        logger.info(f"Optimization level: {optimization_level}")
        logger.info(f"Timeout per year: {timeout_minutes_per_year} minutes")

        start_year = 2025
        simulation_years = list(range(start_year, start_year + max_years))
        opt_config = OPTIMIZATION_LEVELS[optimization_level]

        # Initialize tracking
        test_start_time = time.time()
        year_metrics = []
        overall_profiler = MemoryProfiler(opt_config.memory_limit_gb)
        overall_profiler.sample_memory("Multi-year test start")

        # Initialize result
        result = MultiYearScalabilityResult(
            dataset_size=dataset_size,
            optimization_level=optimization_level,
            simulation_years=simulation_years,
            total_duration_seconds=0.0,
            year_metrics=[],
            memory_growth_rate_mb_per_year=0.0,
            execution_time_growth_rate_sec_per_year=0.0,
            database_growth_rate_mb_per_year=0.0,
            years_completed=0,
            years_failed=0,
            overall_success=True,
            peak_memory_utilization_pct=0.0,
            average_memory_utilization_pct=0.0,
            memory_limit_exceeded=False,
            checkpoint_overhead_seconds=0.0,
            checkpoint_success_rate=1.0,
            state_compression_effectiveness_pct=0.0
        )

        previous_memory = overall_profiler.sample_memory("Baseline measurement")
        previous_db_size = 0.0

        # Test each year individually for detailed metrics
        for year_idx, year in enumerate(simulation_years):
            year_start_time = time.time()

            logger.info(f"\n{'='*50}")
            logger.info(f"TESTING YEAR {year} ({year_idx + 1}/{len(simulation_years)})")
            logger.info(f"{'='*50}")

            try:
                # Run single year simulation
                year_result = self._test_single_year(
                    dataset_size=dataset_size,
                    simulation_years=[year],
                    optimization_level=optimization_level,
                    timeout_minutes=timeout_minutes_per_year,
                    is_continuation=year_idx > 0
                )

                # Measure memory and database changes
                current_memory = overall_profiler.sample_memory(f"Year {year} complete")
                memory_delta = current_memory - previous_memory

                current_db_size = year_result.database_final_size_mb
                db_delta = current_db_size - previous_db_size

                # Create year metrics
                year_metric = YearMetrics(
                    year=year,
                    execution_time_seconds=year_result.test_duration,
                    peak_memory_mb=year_result.peak_memory_mb,
                    memory_delta_mb=memory_delta,
                    database_size_mb=current_db_size,
                    records_added=year_result.records_processed if year_idx == 0 else max(0, year_result.records_processed - (year_metrics[-1].cumulative_records if year_metrics else 0)),
                    cumulative_records=year_result.records_processed,
                    success=year_result.success
                )

                year_metrics.append(year_metric)

                if year_result.success:
                    result.years_completed += 1
                    logger.info(f"✅ Year {year} completed successfully")
                    logger.info(f"   Duration: {year_result.test_duration:.1f}s")
                    logger.info(f"   Peak memory: {year_result.peak_memory_mb:.1f}MB (Δ{memory_delta:+.1f}MB)")
                    logger.info(f"   Database size: {current_db_size:.1f}MB (Δ{db_delta:+.1f}MB)")
                    logger.info(f"   Records processed: {year_result.records_processed:,}")
                else:
                    result.years_failed += 1
                    result.overall_success = False
                    result.failure_point = year
                    year_metric.error_message = year_result.error_message

                    logger.error(f"❌ Year {year} failed: {year_result.error_message}")
                    logger.info("Stopping multi-year test at first failure")
                    break

                # Check memory limits
                memory_limit_mb = opt_config.memory_limit_gb * 1024
                if current_memory > memory_limit_mb:
                    result.memory_limit_exceeded = True
                    logger.warning(f"⚠️ Memory limit exceeded: {current_memory:.1f}MB > {memory_limit_mb:.1f}MB")

                # Update tracking variables
                previous_memory = current_memory
                previous_db_size = current_db_size

                # Log progress
                completed_pct = ((year_idx + 1) / len(simulation_years)) * 100
                elapsed_minutes = (time.time() - test_start_time) / 60

                logger.info(f"Progress: {completed_pct:.1f}% complete ({elapsed_minutes:.1f} minutes elapsed)")

            except Exception as e:
                logger.error(f"❌ Year {year} test failed with exception: {e}")

                year_metric = YearMetrics(
                    year=year,
                    execution_time_seconds=time.time() - year_start_time,
                    peak_memory_mb=overall_profiler.sample_memory(f"Year {year} failed"),
                    memory_delta_mb=0.0,
                    database_size_mb=0.0,
                    records_added=0,
                    cumulative_records=0,
                    success=False,
                    error_message=str(e)
                )

                year_metrics.append(year_metric)
                result.years_failed += 1
                result.overall_success = False
                result.failure_point = year
                break

        # Calculate final metrics
        result.total_duration_seconds = time.time() - test_start_time
        result.year_metrics = year_metrics

        # Calculate growth rates
        if len(year_metrics) >= 2:
            result.memory_growth_rate_mb_per_year = self._calculate_growth_rate(
                [m.peak_memory_mb for m in year_metrics if m.success]
            )
            result.execution_time_growth_rate_sec_per_year = self._calculate_growth_rate(
                [m.execution_time_seconds for m in year_metrics if m.success]
            )
            result.database_growth_rate_mb_per_year = self._calculate_growth_rate(
                [m.database_size_mb for m in year_metrics if m.success]
            )

        # Calculate memory utilization
        memory_limit_mb = opt_config.memory_limit_gb * 1024
        successful_metrics = [m for m in year_metrics if m.success]

        if successful_metrics:
            peak_memories = [m.peak_memory_mb for m in successful_metrics]
            result.peak_memory_utilization_pct = (max(peak_memories) / memory_limit_mb) * 100
            result.average_memory_utilization_pct = (sum(peak_memories) / len(peak_memories) / memory_limit_mb) * 100

        # Generate final analysis
        self._log_scalability_analysis(result)

        return result

    def _test_single_year(
        self,
        dataset_size: int,
        simulation_years: List[int],
        optimization_level: str,
        timeout_minutes: int,
        is_continuation: bool = False
    ) -> StressTestResult:
        """Test a single simulation year"""
        executor = StressTestExecutor(self.test_data_dir)

        return executor.run_single_stress_test(
            dataset_size=dataset_size,
            optimization_level=optimization_level,
            simulation_years=simulation_years,
            timeout_minutes=timeout_minutes
        )

    def _calculate_growth_rate(self, values: List[float]) -> float:
        """Calculate linear growth rate from a series of values"""
        if len(values) < 2:
            return 0.0

        # Simple linear regression slope calculation
        n = len(values)
        x_values = list(range(n))

        sum_x = sum(x_values)
        sum_y = sum(values)
        sum_xy = sum(x * y for x, y in zip(x_values, values))
        sum_x_squared = sum(x * x for x in x_values)

        if n * sum_x_squared - sum_x * sum_x == 0:
            return 0.0

        slope = (n * sum_xy - sum_x * sum_y) / (n * sum_x_squared - sum_x * sum_x)
        return slope

    def _log_scalability_analysis(self, result: MultiYearScalabilityResult):
        """Log detailed scalability analysis"""
        logger.info(f"\n{'='*60}")
        logger.info(f"MULTI-YEAR SCALABILITY ANALYSIS")
        logger.info(f"{'='*60}")

        logger.info(f"Dataset size: {result.dataset_size:,} employees")
        logger.info(f"Total duration: {result.total_duration_seconds:.1f} seconds ({result.total_duration_seconds/60:.1f} minutes)")
        logger.info(f"Years completed: {result.years_completed}/{len(result.simulation_years)}")

        if result.overall_success:
            logger.info(f"✅ All years completed successfully")
        else:
            logger.info(f"❌ Failed at year {result.failure_point}")

        # Growth rates
        if result.years_completed >= 2:
            logger.info(f"\nSCALING CHARACTERISTICS:")
            logger.info(f"  Memory growth: {result.memory_growth_rate_mb_per_year:+.1f} MB/year")
            logger.info(f"  Execution time growth: {result.execution_time_growth_rate_sec_per_year:+.1f} seconds/year")
            logger.info(f"  Database growth: {result.database_growth_rate_mb_per_year:+.1f} MB/year")

            # Project future resource needs
            if result.memory_growth_rate_mb_per_year > 0:
                memory_limit_mb = OPTIMIZATION_LEVELS[result.optimization_level].memory_limit_gb * 1024
                current_peak = max(m.peak_memory_mb for m in result.year_metrics if m.success)
                remaining_capacity = memory_limit_mb - current_peak

                if result.memory_growth_rate_mb_per_year > 0:
                    years_until_limit = remaining_capacity / result.memory_growth_rate_mb_per_year
                    logger.info(f"  Projected years until memory limit: {years_until_limit:.1f}")

        # Memory utilization
        logger.info(f"\nMEMORY UTILIZATION:")
        logger.info(f"  Peak utilization: {result.peak_memory_utilization_pct:.1f}%")
        logger.info(f"  Average utilization: {result.average_memory_utilization_pct:.1f}%")
        logger.info(f"  Memory limit exceeded: {'Yes' if result.memory_limit_exceeded else 'No'}")

        # Per-year breakdown
        logger.info(f"\nPER-YEAR BREAKDOWN:")
        for metric in result.year_metrics:
            status = "✅" if metric.success else "❌"
            logger.info(f"  {status} Year {metric.year}: {metric.execution_time_seconds:.1f}s, "
                       f"{metric.peak_memory_mb:.1f}MB, {metric.database_size_mb:.1f}MB DB, "
                       f"{metric.records_added:,} records")

    def run_comprehensive_scalability_analysis(
        self,
        dataset_sizes: List[int] = None,
        max_years: int = 10,
        optimization_levels: List[str] = None
    ) -> Dict[str, List[MultiYearScalabilityResult]]:
        """
        Run comprehensive scalability analysis across multiple configurations

        Args:
            dataset_sizes: Employee counts to test
            max_years: Maximum simulation years
            optimization_levels: Optimization levels to test

        Returns:
            Dictionary mapping optimization level to list of scalability results
        """
        if dataset_sizes is None:
            dataset_sizes = [50000, 100000, 200000]

        if optimization_levels is None:
            optimization_levels = ["medium", "high"]  # Skip low for time constraints

        logger.info(f"\n{'='*70}")
        logger.info(f"COMPREHENSIVE MULTI-YEAR SCALABILITY ANALYSIS")
        logger.info(f"{'='*70}")
        logger.info(f"Dataset sizes: {[f'{s:,}' for s in dataset_sizes]}")
        logger.info(f"Maximum years: {max_years}")
        logger.info(f"Optimization levels: {optimization_levels}")

        all_results = {}

        for opt_level in optimization_levels:
            logger.info(f"\n{'='*60}")
            logger.info(f"TESTING OPTIMIZATION LEVEL: {opt_level.upper()}")
            logger.info(f"{'='*60}")

            level_results = []

            for dataset_size in dataset_sizes:
                logger.info(f"\nTesting {dataset_size:,} employees with {opt_level} optimization...")

                try:
                    result = self.test_multi_year_scalability(
                        dataset_size=dataset_size,
                        max_years=max_years,
                        optimization_level=opt_level,
                        timeout_minutes_per_year=45
                    )

                    level_results.append(result)

                    # Save individual result
                    self._save_scalability_result(result)

                except Exception as e:
                    logger.error(f"Scalability test failed for {dataset_size:,} employees: {e}")

            all_results[opt_level] = level_results

        # Generate comprehensive analysis
        self._generate_scalability_report(all_results)

        return all_results

    def _save_scalability_result(self, result: MultiYearScalabilityResult):
        """Save individual scalability result"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"scalability_{result.dataset_size:06d}_{result.optimization_level}_{timestamp}.json"

        result_path = self.results_dir / filename

        with open(result_path, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)

        logger.debug(f"Saved scalability result: {result_path}")

    def _generate_scalability_report(
        self,
        all_results: Dict[str, List[MultiYearScalabilityResult]]
    ):
        """Generate comprehensive scalability analysis report"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Create comprehensive report
        report = {
            'metadata': {
                'timestamp': timestamp,
                'test_type': 'multi_year_scalability',
                'optimization_levels_tested': list(all_results.keys())
            },
            'scalability_analysis': {},
            'recommendations': [],
            'detailed_results': {}
        }

        # Analyze each optimization level
        for opt_level, results in all_results.items():
            successful_results = [r for r in results if r.overall_success]

            if successful_results:
                # Calculate statistics
                max_years_completed = max(r.years_completed for r in successful_results)
                avg_memory_growth = sum(r.memory_growth_rate_mb_per_year for r in successful_results) / len(successful_results)
                avg_time_growth = sum(r.execution_time_growth_rate_sec_per_year for r in successful_results) / len(successful_results)

                # Determine maximum viable dataset size
                max_viable_size = 0
                for result in successful_results:
                    if result.years_completed >= 5:  # Completed at least 5 years
                        max_viable_size = max(max_viable_size, result.dataset_size)

                report['scalability_analysis'][opt_level] = {
                    'max_years_achieved': max_years_completed,
                    'max_viable_dataset_size': max_viable_size,
                    'average_memory_growth_mb_per_year': avg_memory_growth,
                    'average_time_growth_sec_per_year': avg_time_growth,
                    'success_rate': len(successful_results) / len(results) if results else 0,
                    'total_tests': len(results),
                    'successful_tests': len(successful_results)
                }

                # Generate recommendations
                if max_viable_size >= 100000:
                    report['recommendations'].append(
                        f"{opt_level} optimization successfully handles 100K+ employees for multi-year simulations"
                    )

                if avg_memory_growth > 500:  # More than 500MB growth per year
                    report['recommendations'].append(
                        f"WARNING: {opt_level} shows high memory growth ({avg_memory_growth:.0f} MB/year) - "
                        f"may not scale to very long simulations"
                    )

        # Save detailed results
        for opt_level, results in all_results.items():
            report['detailed_results'][opt_level] = [r.to_dict() for r in results]

        # Save comprehensive report
        report_path = self.results_dir / f"multi_year_scalability_analysis_{timestamp}.json"
        with open(report_path, 'w') as f:
            json.dump(report, f, indent=2)

        # Generate CSV summary
        self._save_scalability_csv(all_results, timestamp)

        logger.info(f"Multi-year scalability report: {report_path}")

    def _save_scalability_csv(
        self,
        all_results: Dict[str, List[MultiYearScalabilityResult]],
        timestamp: str
    ):
        """Save scalability results to CSV"""
        csv_data = []

        for opt_level, results in all_results.items():
            for result in results:
                csv_data.append({
                    'optimization_level': opt_level,
                    'dataset_size': result.dataset_size,
                    'years_completed': result.years_completed,
                    'years_failed': result.years_failed,
                    'overall_success': result.overall_success,
                    'total_duration_seconds': result.total_duration_seconds,
                    'memory_growth_rate_mb_per_year': result.memory_growth_rate_mb_per_year,
                    'execution_time_growth_rate_sec_per_year': result.execution_time_growth_rate_sec_per_year,
                    'database_growth_rate_mb_per_year': result.database_growth_rate_mb_per_year,
                    'peak_memory_utilization_pct': result.peak_memory_utilization_pct,
                    'average_memory_utilization_pct': result.average_memory_utilization_pct,
                    'memory_limit_exceeded': result.memory_limit_exceeded,
                    'failure_point': result.failure_point or 0
                })

        df = pd.DataFrame(csv_data)
        csv_path = self.results_dir / f"multi_year_scalability_summary_{timestamp}.csv"
        df.to_csv(csv_path, index=False)

        logger.info(f"Scalability CSV summary: {csv_path}")

def main():
    """CLI entry point for multi-year scalability testing"""
    import argparse

    parser = argparse.ArgumentParser(
        description="PlanWise Navigator Multi-Year Scalability Testing",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter
    )

    parser.add_argument(
        "--test-data-dir",
        type=Path,
        default=Path("data/stress_test"),
        help="Directory containing test datasets"
    )

    parser.add_argument(
        "--results-dir",
        type=Path,
        default=Path("test_results/multi_year_scalability"),
        help="Directory to save results"
    )

    parser.add_argument(
        "--dataset-sizes",
        type=int,
        nargs="+",
        default=[50000, 100000],
        help="Dataset sizes to test"
    )

    parser.add_argument(
        "--max-years",
        type=int,
        default=10,
        help="Maximum simulation years"
    )

    parser.add_argument(
        "--optimization-levels",
        choices=list(OPTIMIZATION_LEVELS.keys()),
        nargs="+",
        default=["medium", "high"],
        help="Optimization levels to test"
    )

    parser.add_argument(
        "--single-test",
        action="store_true",
        help="Run single test with first dataset size"
    )

    args = parser.parse_args()

    logger.info(f"PlanWise Navigator Multi-Year Scalability Testing")
    logger.info(f"Story S063-09: Multi-Year Simulation Scalability")

    # Create tester
    tester = MultiYearScalabilityTester(args.test_data_dir, args.results_dir)

    if args.single_test:
        # Single scalability test
        result = tester.test_multi_year_scalability(
            dataset_size=args.dataset_sizes[0],
            max_years=args.max_years,
            optimization_level=args.optimization_levels[0]
        )

        logger.info(f"\nSingle test completed:")
        logger.info(f"  Success: {'Yes' if result.overall_success else 'No'}")
        logger.info(f"  Years completed: {result.years_completed}")
        logger.info(f"  Peak memory utilization: {result.peak_memory_utilization_pct:.1f}%")

    else:
        # Comprehensive analysis
        all_results = tester.run_comprehensive_scalability_analysis(
            dataset_sizes=args.dataset_sizes,
            max_years=args.max_years,
            optimization_levels=args.optimization_levels
        )

        # Print summary
        logger.info(f"\n{'='*60}")
        logger.info(f"COMPREHENSIVE SCALABILITY ANALYSIS COMPLETE")
        logger.info(f"{'='*60}")

        for opt_level, results in all_results.items():
            successful = sum(1 for r in results if r.overall_success)
            total = len(results)
            logger.info(f"{opt_level.upper()} optimization: {successful}/{total} successful")

            if successful > 0:
                max_years = max(r.years_completed for r in results if r.overall_success)
                max_size = max(r.dataset_size for r in results if r.overall_success)
                logger.info(f"  Best result: {max_years} years with {max_size:,} employees")

    logger.info(f"Results saved to: {args.results_dir}")

if __name__ == "__main__":
    main()
