#!/usr/bin/env python3
"""
Comprehensive stress testing framework for PlanWise Navigator single-threaded performance.

Story S063-09: Large Dataset Stress Testing
- Memory usage validation under maximum load
- Performance benchmarking across optimization levels
- Scalability testing for multi-year simulations with large workforces
- Automated stress testing for CI/CD integration
"""

import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import tempfile
import shutil

import psutil
import pandas as pd
import duckdb

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

@dataclass
class OptimizationLevel:
    """Single-threaded optimization level configuration"""
    name: str
    memory_limit_gb: float
    batch_size: int
    max_workers: int = 1  # Always single-threaded
    enable_compression: bool = True
    description: str = ""

# Optimization levels aligned with Epic E063
OPTIMIZATION_LEVELS = {
    "low": OptimizationLevel(
        name="low",
        memory_limit_gb=2.0,
        batch_size=250,
        description="Ultra-stable for 4GB RAM systems"
    ),
    "medium": OptimizationLevel(
        name="medium",
        memory_limit_gb=4.0,
        batch_size=500,
        description="Balanced performance for standard work laptops"
    ),
    "high": OptimizationLevel(
        name="high",
        memory_limit_gb=6.0,
        batch_size=1000,
        description="Faster execution for high-spec workstations"
    )
}

@dataclass
class StressTestResult:
    """Results from a single stress test run"""
    # Test configuration
    dataset_size: int
    optimization_level: str
    simulation_years: List[int]
    test_duration: float

    # Performance metrics
    peak_memory_mb: float
    average_memory_mb: float
    memory_exceeded_limit: bool

    # Success metrics
    success: bool
    completed_years: List[int]
    failed_years: List[int]
    error_message: Optional[str] = None

    # Detailed performance data
    per_year_metrics: Dict[int, Dict[str, Any]] = None
    database_final_size_mb: float = 0.0
    records_processed: int = 0
    processing_rate_records_per_sec: float = 0.0

    # System information
    cpu_count: int = 0
    total_system_memory_gb: float = 0.0
    platform_info: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization"""
        return asdict(self)

class MemoryProfiler:
    """Real-time memory monitoring for stress testing"""

    def __init__(self, memory_limit_gb: float):
        self.memory_limit_gb = memory_limit_gb
        self.memory_limit_mb = memory_limit_gb * 1024
        self.process = psutil.Process()

        self.start_time = time.time()
        self.start_memory = self._get_memory_mb()
        self.peak_memory = self.start_memory
        self.memory_samples = []

    def _get_memory_mb(self) -> float:
        """Get current memory usage in MB"""
        return self.process.memory_info().rss / 1024 / 1024

    def sample_memory(self, stage: str = "") -> float:
        """Sample memory usage and check against limits"""
        current_memory = self._get_memory_mb()
        elapsed_time = time.time() - self.start_time

        self.peak_memory = max(self.peak_memory, current_memory)
        self.memory_samples.append({
            'time': elapsed_time,
            'memory_mb': current_memory,
            'stage': stage
        })

        if stage:
            exceeded = current_memory > self.memory_limit_mb
            status = "⚠️ EXCEEDED" if exceeded else "✅"
            logger.info(f"{status} {stage}: {current_memory:.1f} MB "
                       f"(limit: {self.memory_limit_mb:.1f} MB, peak: {self.peak_memory:.1f} MB)")

        return current_memory

    def get_summary(self) -> Dict[str, Any]:
        """Get memory usage summary"""
        if not self.memory_samples:
            return {}

        memory_values = [s['memory_mb'] for s in self.memory_samples]

        return {
            'start_memory_mb': self.start_memory,
            'peak_memory_mb': self.peak_memory,
            'average_memory_mb': sum(memory_values) / len(memory_values),
            'memory_limit_mb': self.memory_limit_mb,
            'exceeded_limit': self.peak_memory > self.memory_limit_mb,
            'samples_count': len(self.memory_samples),
            'total_duration': time.time() - self.start_time
        }

class DatabaseAnalyzer:
    """Analyze database state and performance characteristics"""

    def __init__(self, db_path: Path):
        self.db_path = db_path

    def get_database_size_mb(self) -> float:
        """Get database file size in MB"""
        if self.db_path.exists():
            return self.db_path.stat().st_size / 1024 / 1024
        return 0.0

    def analyze_data_distribution(self) -> Dict[str, Any]:
        """Analyze data distribution and table sizes"""
        if not self.db_path.exists():
            return {}

        try:
            conn = duckdb.connect(str(self.db_path))

            analysis = {}

            # Table sizes
            tables_info = conn.execute("""
                SELECT
                    table_name,
                    estimated_size
                FROM duckdb_tables()
                WHERE schema_name != 'information_schema'
                ORDER BY estimated_size DESC
            """).fetchall()

            analysis['table_sizes'] = [
                {'table_name': name, 'estimated_size': size}
                for name, size in tables_info
            ]

            # Key tables record counts
            key_tables = ['fct_yearly_events', 'fct_workforce_snapshot', 'int_baseline_workforce']
            record_counts = {}

            for table in key_tables:
                try:
                    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    record_counts[table] = count
                except:
                    record_counts[table] = 0

            analysis['record_counts'] = record_counts

            # Simulation years covered
            try:
                years = conn.execute(
                    "SELECT DISTINCT simulation_year FROM fct_yearly_events ORDER BY simulation_year"
                ).fetchall()
                analysis['simulation_years'] = [y[0] for y in years]
            except:
                analysis['simulation_years'] = []

            conn.close()
            return analysis

        except Exception as e:
            logger.warning(f"Database analysis failed: {e}")
            return {}

class StressTestExecutor:
    """Execute stress tests with comprehensive monitoring"""

    def __init__(self, test_data_dir: Path):
        self.test_data_dir = test_data_dir

    def run_single_stress_test(
        self,
        dataset_size: int,
        optimization_level: str,
        simulation_years: List[int],
        timeout_minutes: int = 60
    ) -> StressTestResult:
        """
        Run a single stress test configuration

        Args:
            dataset_size: Number of employees in test dataset
            optimization_level: Optimization level (low/medium/high)
            simulation_years: Years to simulate
            timeout_minutes: Maximum execution time before timeout

        Returns:
            StressTestResult with comprehensive metrics
        """
        opt_config = OPTIMIZATION_LEVELS[optimization_level]
        start_time = time.time()

        logger.info(f"\n{'='*60}")
        logger.info(f"STRESS TEST: {dataset_size:,} employees | {optimization_level.upper()} optimization")
        logger.info(f"Years: {simulation_years} | Memory limit: {opt_config.memory_limit_gb}GB")
        logger.info(f"{'='*60}")

        # Initialize memory profiler
        profiler = MemoryProfiler(opt_config.memory_limit_gb)
        profiler.sample_memory("Test start")

        # Setup test environment
        test_db_path, census_path = self._setup_test_environment(dataset_size, profiler)

        # Initialize result
        result = StressTestResult(
            dataset_size=dataset_size,
            optimization_level=optimization_level,
            simulation_years=simulation_years,
            test_duration=0.0,
            peak_memory_mb=0.0,
            average_memory_mb=0.0,
            memory_exceeded_limit=False,
            success=False,
            completed_years=[],
            failed_years=[],
            per_year_metrics={},
            cpu_count=psutil.cpu_count(),
            total_system_memory_gb=psutil.virtual_memory().total / 1024**3,
            platform_info=f"{os.name} {psutil.cpu_count()} cores"
        )

        try:
            # Run simulation with timeout
            result = self._execute_simulation(
                test_db_path, census_path, opt_config,
                simulation_years, profiler, result, timeout_minutes
            )

        except Exception as e:
            logger.error(f"Simulation execution failed: {e}")
            result.error_message = str(e)
            result.failed_years = simulation_years

        finally:
            # Final analysis
            result.test_duration = time.time() - start_time
            memory_summary = profiler.get_summary()

            result.peak_memory_mb = memory_summary.get('peak_memory_mb', 0.0)
            result.average_memory_mb = memory_summary.get('average_memory_mb', 0.0)
            result.memory_exceeded_limit = memory_summary.get('exceeded_limit', False)

            # Database analysis
            db_analyzer = DatabaseAnalyzer(test_db_path)
            result.database_final_size_mb = db_analyzer.get_database_size_mb()

            data_analysis = db_analyzer.analyze_data_distribution()
            if 'record_counts' in data_analysis:
                result.records_processed = sum(data_analysis['record_counts'].values())
                if result.test_duration > 0:
                    result.processing_rate_records_per_sec = result.records_processed / result.test_duration

            # Cleanup test environment
            self._cleanup_test_environment(test_db_path, census_path)

        return result

    def _setup_test_environment(self, dataset_size: int, profiler: MemoryProfiler) -> Tuple[Path, Path]:
        """Setup isolated test environment"""
        profiler.sample_memory("Environment setup start")

        # Create temporary database
        test_db_path = Path(f"temp_stress_test_{dataset_size}_{int(time.time())}.duckdb")

        # Find test dataset
        census_path = self.test_data_dir / f"stress_test_{dataset_size:06d}_employees.parquet"

        if not census_path.exists():
            # Try CSV fallback
            census_path = self.test_data_dir / f"stress_test_{dataset_size:06d}_employees.csv"

        if not census_path.exists():
            raise FileNotFoundError(f"Test dataset not found: {census_path}")

        logger.info(f"Using test dataset: {census_path}")
        logger.info(f"Test database: {test_db_path}")

        # Copy census data to expected location for simulation
        expected_census_path = Path("data/census_preprocessed.parquet")
        expected_census_path.parent.mkdir(parents=True, exist_ok=True)

        if census_path.suffix == '.parquet':
            shutil.copy2(census_path, expected_census_path)
        else:
            # Convert CSV to parquet
            df = pd.read_csv(census_path)
            df.to_parquet(expected_census_path, index=False)

        profiler.sample_memory("Environment setup complete")
        return test_db_path, expected_census_path

    def _execute_simulation(
        self,
        test_db_path: Path,
        census_path: Path,
        opt_config: OptimizationLevel,
        simulation_years: List[int],
        profiler: MemoryProfiler,
        result: StressTestResult,
        timeout_minutes: int
    ) -> StressTestResult:
        """Execute the simulation with monitoring"""

        # Set environment variables for single-threaded execution
        env = os.environ.copy()
        env.update({
            'DATABASE_PATH': str(test_db_path),
            'DBT_THREADS': '1',
            'PW_OPT_LEVEL': opt_config.name,
            'PW_MEMORY_LIMIT_GB': str(opt_config.memory_limit_gb),
            'PW_BATCH_SIZE': str(opt_config.batch_size),
        })

        profiler.sample_memory("Simulation start")

        completed_years = []
        failed_years = []
        per_year_metrics = {}

        min_year = min(simulation_years)
        max_year = max(simulation_years)

        try:
            # Construct simulation command
            cmd = [
                'python', 'navigator_orchestrator run',
                '--years', str(min_year), str(max_year),
                '--threads', '1',
                '--optimization', opt_config.name,
            ]

            if opt_config.enable_compression:
                cmd.append('--enable-compression')

            logger.info(f"Executing: {' '.join(cmd)}")

            # Run simulation with timeout
            process = subprocess.Popen(
                cmd,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                universal_newlines=True,
                bufsize=1
            )

            # Monitor execution with timeout
            timeout_seconds = timeout_minutes * 60
            start_time = time.time()

            while True:
                elapsed = time.time() - start_time

                if process.poll() is not None:
                    # Process completed
                    break

                if elapsed > timeout_seconds:
                    # Timeout reached
                    logger.warning(f"Simulation timeout ({timeout_minutes} minutes) - terminating")
                    process.terminate()
                    result.error_message = f"Timeout after {timeout_minutes} minutes"
                    break

                # Sample memory every 30 seconds
                if int(elapsed) % 30 == 0:
                    profiler.sample_memory(f"Running ({elapsed:.0f}s)")

                time.sleep(5)  # Check every 5 seconds

            # Get final output
            stdout, _ = process.communicate()
            return_code = process.returncode

            profiler.sample_memory("Simulation complete")

            if return_code == 0:
                result.success = True
                result.completed_years = simulation_years.copy()
                logger.info("✅ Simulation completed successfully")
            else:
                result.success = False
                result.failed_years = simulation_years.copy()
                result.error_message = f"Simulation failed with return code {return_code}"
                logger.error(f"❌ Simulation failed: {result.error_message}")

            # Parse output for detailed metrics if available
            if stdout:
                result.per_year_metrics = self._parse_simulation_output(stdout)

        except subprocess.TimeoutExpired:
            result.error_message = f"Simulation timeout after {timeout_minutes} minutes"
            result.failed_years = simulation_years.copy()
            logger.error(f"❌ {result.error_message}")

        except Exception as e:
            result.error_message = f"Simulation error: {str(e)}"
            result.failed_years = simulation_years.copy()
            logger.error(f"❌ {result.error_message}")

        return result

    def _parse_simulation_output(self, output: str) -> Dict[int, Dict[str, Any]]:
        """Parse simulation output for per-year metrics"""
        per_year_metrics = {}

        # Look for year completion patterns
        lines = output.split('\n')
        for line in lines:
            if 'Year' in line and 'completed' in line:
                # Try to extract year and timing info
                # This is a simple parser - could be enhanced based on actual output format
                try:
                    if 'Year 2025' in line:
                        per_year_metrics[2025] = {'status': 'completed'}
                    elif 'Year 2026' in line:
                        per_year_metrics[2026] = {'status': 'completed'}
                    # Add more years as needed
                except:
                    pass

        return per_year_metrics

    def _cleanup_test_environment(self, test_db_path: Path, census_path: Path):
        """Clean up test environment"""
        try:
            if test_db_path.exists():
                test_db_path.unlink()

            # Remove temporary census data
            expected_census_path = Path("data/census_preprocessed.parquet")
            if expected_census_path.exists():
                expected_census_path.unlink()

        except Exception as e:
            logger.warning(f"Cleanup warning: {e}")

class StressTestSuite:
    """Comprehensive stress testing suite for PlanWise Navigator"""

    def __init__(self, test_data_dir: Path, results_dir: Path):
        self.test_data_dir = test_data_dir
        self.results_dir = results_dir
        self.executor = StressTestExecutor(test_data_dir)

        # Ensure results directory exists
        self.results_dir.mkdir(parents=True, exist_ok=True)

    def run_comprehensive_stress_tests(
        self,
        dataset_sizes: List[int] = None,
        optimization_levels: List[str] = None,
        max_simulation_years: int = 3,
        timeout_minutes: int = 60
    ) -> List[StressTestResult]:
        """
        Run comprehensive stress testing across multiple configurations

        Args:
            dataset_sizes: Employee counts to test (default: [1000, 10000, 50000, 100000])
            optimization_levels: Levels to test (default: all levels)
            max_simulation_years: Maximum years to simulate
            timeout_minutes: Timeout per test

        Returns:
            List of all test results
        """
        if dataset_sizes is None:
            dataset_sizes = [1000, 10000, 50000, 100000]

        if optimization_levels is None:
            optimization_levels = list(OPTIMIZATION_LEVELS.keys())

        simulation_years = list(range(2025, 2025 + max_simulation_years))

        logger.info(f"\n{'='*70}")
        logger.info(f"COMPREHENSIVE STRESS TEST SUITE")
        logger.info(f"{'='*70}")
        logger.info(f"Dataset sizes: {[f'{s:,}' for s in dataset_sizes]}")
        logger.info(f"Optimization levels: {optimization_levels}")
        logger.info(f"Simulation years: {simulation_years}")
        logger.info(f"Total test combinations: {len(dataset_sizes) * len(optimization_levels)}")
        logger.info(f"Estimated duration: {len(dataset_sizes) * len(optimization_levels) * timeout_minutes} minutes (max)")

        all_results = []
        test_count = 0
        total_tests = len(dataset_sizes) * len(optimization_levels)

        suite_start_time = time.time()

        for dataset_size in dataset_sizes:
            for opt_level in optimization_levels:
                test_count += 1

                logger.info(f"\n{'='*50}")
                logger.info(f"TEST {test_count}/{total_tests}: {dataset_size:,} employees, {opt_level} optimization")
                logger.info(f"{'='*50}")

                try:
                    result = self.executor.run_single_stress_test(
                        dataset_size=dataset_size,
                        optimization_level=opt_level,
                        simulation_years=simulation_years,
                        timeout_minutes=timeout_minutes
                    )

                    all_results.append(result)

                    # Log test summary
                    status = "✅ PASS" if result.success else "❌ FAIL"
                    memory_status = "⚠️ EXCEEDED" if result.memory_exceeded_limit else "✅ OK"

                    logger.info(f"{status} Test completed in {result.test_duration:.1f}s")
                    logger.info(f"{memory_status} Peak memory: {result.peak_memory_mb:.1f} MB "
                               f"(limit: {OPTIMIZATION_LEVELS[opt_level].memory_limit_gb * 1024:.1f} MB)")

                    if result.error_message:
                        logger.info(f"Error: {result.error_message}")

                    # Save individual result
                    self._save_individual_result(result, test_count)

                except Exception as e:
                    logger.error(f"❌ Test execution failed: {e}")

                    # Create failure result
                    failure_result = StressTestResult(
                        dataset_size=dataset_size,
                        optimization_level=opt_level,
                        simulation_years=simulation_years,
                        test_duration=0.0,
                        peak_memory_mb=0.0,
                        average_memory_mb=0.0,
                        memory_exceeded_limit=False,
                        success=False,
                        completed_years=[],
                        failed_years=simulation_years,
                        error_message=str(e)
                    )

                    all_results.append(failure_result)
                    self._save_individual_result(failure_result, test_count)

        suite_duration = time.time() - suite_start_time

        # Generate comprehensive report
        self._generate_comprehensive_report(all_results, suite_duration)

        logger.info(f"\n{'='*70}")
        logger.info(f"STRESS TEST SUITE COMPLETED")
        logger.info(f"{'='*70}")
        logger.info(f"Total tests: {total_tests}")
        logger.info(f"Passed: {sum(1 for r in all_results if r.success)}")
        logger.info(f"Failed: {sum(1 for r in all_results if not r.success)}")
        logger.info(f"Suite duration: {suite_duration:.1f} seconds ({suite_duration/60:.1f} minutes)")
        logger.info(f"Results saved to: {self.results_dir}")

        return all_results

    def _save_individual_result(self, result: StressTestResult, test_number: int):
        """Save individual test result to JSON"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"stress_test_{test_number:02d}_{result.dataset_size:06d}_{result.optimization_level}_{timestamp}.json"

        result_path = self.results_dir / filename

        with open(result_path, 'w') as f:
            json.dump(result.to_dict(), f, indent=2)

        logger.debug(f"Saved result: {result_path}")

    def _generate_comprehensive_report(self, results: List[StressTestResult], suite_duration: float):
        """Generate comprehensive test report"""
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        # Summary statistics
        total_tests = len(results)
        passed_tests = sum(1 for r in results if r.success)
        failed_tests = total_tests - passed_tests

        memory_exceeded = sum(1 for r in results if r.memory_exceeded_limit)

        # Performance analysis
        successful_results = [r for r in results if r.success]

        if successful_results:
            avg_duration = sum(r.test_duration for r in successful_results) / len(successful_results)
            avg_peak_memory = sum(r.peak_memory_mb for r in successful_results) / len(successful_results)
            max_records_processed = max((r.records_processed for r in successful_results), default=0)
        else:
            avg_duration = 0
            avg_peak_memory = 0
            max_records_processed = 0

        # Create comprehensive report
        report = {
            'metadata': {
                'timestamp': timestamp,
                'suite_duration_seconds': suite_duration,
                'total_tests': total_tests,
                'test_data_directory': str(self.test_data_dir),
                'results_directory': str(self.results_dir)
            },
            'summary': {
                'passed_tests': passed_tests,
                'failed_tests': failed_tests,
                'success_rate': passed_tests / total_tests if total_tests > 0 else 0,
                'memory_exceeded_count': memory_exceeded,
                'memory_compliance_rate': (total_tests - memory_exceeded) / total_tests if total_tests > 0 else 0
            },
            'performance_metrics': {
                'average_test_duration_seconds': avg_duration,
                'average_peak_memory_mb': avg_peak_memory,
                'max_records_processed': max_records_processed,
                'max_processing_rate': max((r.processing_rate_records_per_sec for r in successful_results), default=0)
            },
            'detailed_results': [r.to_dict() for r in results],
            'analysis': self._analyze_results(results)
        }

        # Save JSON report
        json_report_path = self.results_dir / f"comprehensive_stress_test_report_{timestamp}.json"
        with open(json_report_path, 'w') as f:
            json.dump(report, f, indent=2)

        # Save CSV summary
        csv_report_path = self.results_dir / f"stress_test_summary_{timestamp}.csv"
        self._save_csv_summary(results, csv_report_path)

        logger.info(f"Comprehensive report saved: {json_report_path}")
        logger.info(f"CSV summary saved: {csv_report_path}")

    def _analyze_results(self, results: List[StressTestResult]) -> Dict[str, Any]:
        """Analyze results for patterns and recommendations"""
        analysis = {
            'scaling_analysis': {},
            'memory_analysis': {},
            'optimization_level_analysis': {},
            'recommendations': []
        }

        # Group by dataset size
        by_size = {}
        for result in results:
            size = result.dataset_size
            if size not in by_size:
                by_size[size] = []
            by_size[size].append(result)

        # Scaling analysis
        for size, size_results in by_size.items():
            successful = [r for r in size_results if r.success]
            if successful:
                analysis['scaling_analysis'][size] = {
                    'success_rate': len(successful) / len(size_results),
                    'average_duration': sum(r.test_duration for r in successful) / len(successful),
                    'average_peak_memory': sum(r.peak_memory_mb for r in successful) / len(successful),
                    'memory_exceeded_rate': sum(1 for r in size_results if r.memory_exceeded_limit) / len(size_results)
                }

        # Memory analysis by optimization level
        by_opt_level = {}
        for result in results:
            level = result.optimization_level
            if level not in by_opt_level:
                by_opt_level[level] = []
            by_opt_level[level].append(result)

        for level, level_results in by_opt_level.items():
            successful = [r for r in level_results if r.success]
            if successful:
                analysis['optimization_level_analysis'][level] = {
                    'success_rate': len(successful) / len(level_results),
                    'average_peak_memory': sum(r.peak_memory_mb for r in successful) / len(successful),
                    'memory_limit_mb': OPTIMIZATION_LEVELS[level].memory_limit_gb * 1024,
                    'memory_utilization': (sum(r.peak_memory_mb for r in successful) / len(successful)) / (OPTIMIZATION_LEVELS[level].memory_limit_gb * 1024)
                }

        # Generate recommendations
        failed_results = [r for r in results if not r.success]
        memory_exceeded_results = [r for r in results if r.memory_exceeded_limit]

        if failed_results:
            analysis['recommendations'].append(
                f"Failed tests detected: Consider using lower optimization levels for dataset sizes that failed"
            )

        if memory_exceeded_results:
            analysis['recommendations'].append(
                f"Memory limit exceeded in {len(memory_exceeded_results)} tests: Review memory limits and batch sizes"
            )

        # Dataset size recommendations
        largest_successful_size = 0
        for result in results:
            if result.success and result.dataset_size > largest_successful_size:
                largest_successful_size = result.dataset_size

        if largest_successful_size > 0:
            analysis['recommendations'].append(
                f"Validated up to {largest_successful_size:,} employees successfully"
            )

        return analysis

    def _save_csv_summary(self, results: List[StressTestResult], csv_path: Path):
        """Save summary results to CSV"""
        summary_data = []

        for result in results:
            summary_data.append({
                'dataset_size': result.dataset_size,
                'optimization_level': result.optimization_level,
                'success': result.success,
                'test_duration_seconds': result.test_duration,
                'peak_memory_mb': result.peak_memory_mb,
                'average_memory_mb': result.average_memory_mb,
                'memory_exceeded_limit': result.memory_exceeded_limit,
                'records_processed': result.records_processed,
                'processing_rate_records_per_sec': result.processing_rate_records_per_sec,
                'database_final_size_mb': result.database_final_size_mb,
                'completed_years': len(result.completed_years),
                'failed_years': len(result.failed_years),
                'error_message': result.error_message or ''
            })

        df = pd.DataFrame(summary_data)
        df.to_csv(csv_path, index=False)

def main():
    """CLI entry point for stress testing suite"""
    import argparse

    parser = argparse.ArgumentParser(
        description="PlanWise Navigator Stress Testing Suite - Story S063-09",
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
        default=Path("test_results/stress_tests"),
        help="Directory to save test results"
    )

    parser.add_argument(
        "--dataset-sizes",
        type=int,
        nargs="+",
        default=[1000, 10000, 50000, 100000],
        help="Dataset sizes to test"
    )

    parser.add_argument(
        "--optimization-levels",
        choices=list(OPTIMIZATION_LEVELS.keys()),
        nargs="+",
        default=list(OPTIMIZATION_LEVELS.keys()),
        help="Optimization levels to test"
    )

    parser.add_argument(
        "--max-years",
        type=int,
        default=3,
        help="Maximum simulation years"
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
        help="Run quick test with smaller datasets"
    )

    args = parser.parse_args()

    if args.quick_test:
        args.dataset_sizes = [1000, 10000]
        args.max_years = 2
        args.timeout_minutes = 30

    logger.info(f"PlanWise Navigator Stress Testing Suite")
    logger.info(f"Story S063-09: Large Dataset Stress Testing")
    logger.info(f"Test data directory: {args.test_data_dir}")
    logger.info(f"Results directory: {args.results_dir}")

    # Create test suite
    suite = StressTestSuite(args.test_data_dir, args.results_dir)

    # Run comprehensive tests
    results = suite.run_comprehensive_stress_tests(
        dataset_sizes=args.dataset_sizes,
        optimization_levels=args.optimization_levels,
        max_simulation_years=args.max_years,
        timeout_minutes=args.timeout_minutes
    )

    # Print final summary
    passed = sum(1 for r in results if r.success)
    total = len(results)

    logger.info(f"\n{'='*60}")
    logger.info(f"FINAL RESULTS: {passed}/{total} tests passed ({passed/total:.1%} success rate)")
    logger.info(f"Results available in: {args.results_dir}")

if __name__ == "__main__":
    main()
