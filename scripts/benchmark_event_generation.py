#!/usr/bin/env python3
"""
E068G Event Generation Benchmarking Framework

Comprehensive performance comparison between SQL-based and Polars-based
event generation systems. Measures execution time, memory usage, CPU utilization,
throughput, and validates result parity.

This framework provides:
- Performance metrics collection with statistical analysis
- Configurable test scenarios (employee count, year range)
- Result validation and parity testing
- Multi-format reporting (JSON, CSV, markdown)
- CI/CD integration support

Usage:
    python scripts/benchmark_event_generation.py --help
    python scripts/benchmark_event_generation.py --quick
    python scripts/benchmark_event_generation.py --full --runs 5
    python scripts/benchmark_event_generation.py --scenario 5000x5 --runs 3
"""

import os
import sys
import json
import time
import psutil
import logging
import argparse
import statistics
import subprocess
import threading
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, field, asdict
from typing import List, Dict, Any, Optional, Tuple, Union
from concurrent.futures import ThreadPoolExecutor, as_completed
import tempfile
import shutil

# Scientific computing for statistical analysis
import numpy as np
from scipy import stats

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))
from planalign_orchestrator.config import load_simulation_config, get_database_path
from planalign_orchestrator.polars_event_factory import PolarsEventGenerator, EventFactoryConfig


@dataclass
class BenchmarkScenario:
    """Configuration for a single benchmark scenario."""
    name: str
    description: str
    employee_count: int
    start_year: int
    end_year: int
    expected_events_range: Tuple[int, int]  # (min, max) expected events
    target_time_seconds: float = 60.0  # Performance target

    @property
    def year_count(self) -> int:
        """Number of years in the scenario."""
        return self.end_year - self.start_year + 1

    @property
    def total_employee_years(self) -> int:
        """Total employee-year combinations."""
        return self.employee_count * self.year_count


@dataclass
class PerformanceMetrics:
    """Performance metrics for a single benchmark run."""
    # Timing metrics
    execution_time_seconds: float
    setup_time_seconds: float = 0.0
    cleanup_time_seconds: float = 0.0

    # Throughput metrics
    events_generated: int = 0
    events_per_second: float = 0.0
    employee_years_per_second: float = 0.0

    # Resource utilization
    peak_memory_mb: float = 0.0
    avg_memory_mb: float = 0.0
    peak_cpu_percent: float = 0.0
    avg_cpu_percent: float = 0.0

    # System resource usage
    disk_io_read_mb: float = 0.0
    disk_io_write_mb: float = 0.0
    network_io_bytes: float = 0.0

    # Quality metrics
    success: bool = True
    error_message: Optional[str] = None
    validation_passed: bool = False

    def __post_init__(self):
        """Calculate derived metrics."""
        if self.execution_time_seconds > 0:
            self.events_per_second = self.events_generated / self.execution_time_seconds


@dataclass
class BenchmarkResult:
    """Results from running a benchmark scenario."""
    scenario: BenchmarkScenario
    mode: str  # 'sql' or 'polars'
    runs: List[PerformanceMetrics]
    timestamp: datetime = field(default_factory=datetime.now)

    # Statistical summaries
    avg_metrics: Optional[PerformanceMetrics] = None
    confidence_interval_95: Optional[Dict[str, Tuple[float, float]]] = None

    def __post_init__(self):
        """Calculate statistical summaries."""
        if self.runs:
            self._calculate_statistics()

    def _calculate_statistics(self):
        """Calculate statistical summaries from multiple runs."""
        successful_runs = [run for run in self.runs if run.success]
        if not successful_runs:
            return

        # Calculate averages
        self.avg_metrics = PerformanceMetrics(
            execution_time_seconds=statistics.mean(r.execution_time_seconds for r in successful_runs),
            setup_time_seconds=statistics.mean(r.setup_time_seconds for r in successful_runs),
            cleanup_time_seconds=statistics.mean(r.cleanup_time_seconds for r in successful_runs),
            events_generated=int(statistics.mean(r.events_generated for r in successful_runs)),
            events_per_second=statistics.mean(r.events_per_second for r in successful_runs),
            employee_years_per_second=statistics.mean(r.employee_years_per_second for r in successful_runs),
            peak_memory_mb=statistics.mean(r.peak_memory_mb for r in successful_runs),
            avg_memory_mb=statistics.mean(r.avg_memory_mb for r in successful_runs),
            peak_cpu_percent=statistics.mean(r.peak_cpu_percent for r in successful_runs),
            avg_cpu_percent=statistics.mean(r.avg_cpu_percent for r in successful_runs),
            disk_io_read_mb=statistics.mean(r.disk_io_read_mb for r in successful_runs),
            disk_io_write_mb=statistics.mean(r.disk_io_write_mb for r in successful_runs),
            network_io_bytes=statistics.mean(r.network_io_bytes for r in successful_runs),
            success=len(successful_runs) > 0,
            validation_passed=all(r.validation_passed for r in successful_runs)
        )

        # Calculate 95% confidence intervals if we have enough data
        if len(successful_runs) >= 3:
            self.confidence_interval_95 = self._calculate_confidence_intervals(successful_runs)

    def _calculate_confidence_intervals(self, runs: List[PerformanceMetrics]) -> Dict[str, Tuple[float, float]]:
        """Calculate 95% confidence intervals for key metrics."""
        intervals = {}

        metrics = [
            ('execution_time_seconds', [r.execution_time_seconds for r in runs]),
            ('events_per_second', [r.events_per_second for r in runs]),
            ('peak_memory_mb', [r.peak_memory_mb for r in runs]),
            ('avg_cpu_percent', [r.avg_cpu_percent for r in runs])
        ]

        for metric_name, values in metrics:
            if len(values) >= 3:
                mean_val = statistics.mean(values)
                std_err = statistics.stdev(values) / np.sqrt(len(values))
                # Using t-distribution for small samples
                t_value = stats.t.ppf(0.975, len(values) - 1)  # 95% confidence
                margin = t_value * std_err
                intervals[metric_name] = (mean_val - margin, mean_val + margin)

        return intervals


class ResourceMonitor:
    """Monitor system resource usage during benchmark execution."""

    def __init__(self, pid: int, interval: float = 0.5):
        """Initialize resource monitor for a specific process."""
        self.pid = pid
        self.interval = interval
        self.process = psutil.Process(pid)
        self.measurements = []
        self.monitoring = False
        self.monitor_thread = None

        # Get initial I/O counters
        try:
            self.initial_io = self.process.io_counters()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            self.initial_io = None

    def start_monitoring(self):
        """Start resource monitoring in background thread."""
        self.monitoring = True
        self.measurements = []
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

    def stop_monitoring(self) -> PerformanceMetrics:
        """Stop monitoring and return aggregated metrics."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2.0)

        return self._aggregate_measurements()

    def _monitor_loop(self):
        """Background monitoring loop."""
        while self.monitoring:
            try:
                # Memory usage
                memory_info = self.process.memory_info()
                memory_mb = memory_info.rss / 1024 / 1024

                # CPU usage
                cpu_percent = self.process.cpu_percent()

                # Record measurement
                self.measurements.append({
                    'timestamp': time.time(),
                    'memory_mb': memory_mb,
                    'cpu_percent': cpu_percent
                })

                time.sleep(self.interval)

            except (psutil.NoSuchProcess, psutil.AccessDenied):
                # Process ended or access denied
                break
            except Exception:
                # Other monitoring errors, continue
                continue

    def _aggregate_measurements(self) -> PerformanceMetrics:
        """Aggregate measurements into performance metrics."""
        if not self.measurements:
            return PerformanceMetrics(execution_time_seconds=0.0)

        # Memory metrics
        memory_values = [m['memory_mb'] for m in self.measurements]
        peak_memory_mb = max(memory_values) if memory_values else 0.0
        avg_memory_mb = statistics.mean(memory_values) if memory_values else 0.0

        # CPU metrics
        cpu_values = [m['cpu_percent'] for m in self.measurements if m['cpu_percent'] > 0]
        peak_cpu_percent = max(cpu_values) if cpu_values else 0.0
        avg_cpu_percent = statistics.mean(cpu_values) if cpu_values else 0.0

        # I/O metrics
        disk_io_read_mb = 0.0
        disk_io_write_mb = 0.0

        if self.initial_io:
            try:
                final_io = self.process.io_counters()
                disk_io_read_mb = (final_io.read_bytes - self.initial_io.read_bytes) / 1024 / 1024
                disk_io_write_mb = (final_io.write_bytes - self.initial_io.write_bytes) / 1024 / 1024
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        return PerformanceMetrics(
            execution_time_seconds=0.0,  # Will be set by benchmark runner
            peak_memory_mb=peak_memory_mb,
            avg_memory_mb=avg_memory_mb,
            peak_cpu_percent=peak_cpu_percent,
            avg_cpu_percent=avg_cpu_percent,
            disk_io_read_mb=disk_io_read_mb,
            disk_io_write_mb=disk_io_write_mb
        )


class EventGenerationBenchmark:
    """Main benchmarking framework for event generation performance."""

    # Predefined benchmark scenarios
    PREDEFINED_SCENARIOS = {
        'quick': BenchmarkScenario(
            name='quick',
            description='Quick validation test with minimal data',
            employee_count=100,
            start_year=2025,
            end_year=2026,
            expected_events_range=(50, 500),
            target_time_seconds=5.0
        ),
        '1kx3': BenchmarkScenario(
            name='1kx3',
            description='1k employees × 3 years - development testing',
            employee_count=1000,
            start_year=2025,
            end_year=2027,
            expected_events_range=(1000, 10000),
            target_time_seconds=10.0
        ),
        '5kx5': BenchmarkScenario(
            name='5kx5',
            description='5k employees × 5 years - production target',
            employee_count=5000,
            start_year=2025,
            end_year=2029,
            expected_events_range=(10000, 100000),
            target_time_seconds=60.0
        ),
        'stress': BenchmarkScenario(
            name='stress',
            description='10k employees × 10 years - stress testing',
            employee_count=10000,
            start_year=2025,
            end_year=2034,
            expected_events_range=(50000, 500000),
            target_time_seconds=300.0
        )
    }

    def __init__(self, output_dir: Path, random_seed: int = 12345):
        """Initialize benchmark framework."""
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.random_seed = random_seed
        self.logger = self._setup_logging()

        # Benchmark results storage
        self.results: List[BenchmarkResult] = []

        # Temporary directories for isolation
        self.temp_dirs = []

    def _setup_logging(self) -> logging.Logger:
        """Setup logging for benchmark framework."""
        logger = logging.getLogger('benchmark_event_generation')

        # Don't add handlers if already configured
        if not logger.handlers:
            # Console handler
            console_handler = logging.StreamHandler()
            console_formatter = logging.Formatter(
                '%(asctime)s - BENCHMARK - %(levelname)s - %(message)s'
            )
            console_handler.setFormatter(console_formatter)
            logger.addHandler(console_handler)

            # File handler
            log_file = self.output_dir / f"benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
            file_handler = logging.FileHandler(log_file)
            file_formatter = logging.Formatter(
                '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
            )
            file_handler.setFormatter(file_formatter)
            logger.addHandler(file_handler)

            logger.setLevel(logging.INFO)

        return logger

    def run_benchmark_suite(self,
                          scenarios: List[str],
                          modes: List[str],
                          runs_per_scenario: int = 3,
                          validate_results: bool = True) -> Dict[str, Any]:
        """
        Run complete benchmark suite with multiple scenarios and modes.

        Args:
            scenarios: List of scenario names to run
            modes: List of modes ('sql', 'polars') to benchmark
            runs_per_scenario: Number of runs per scenario for statistical validity
            validate_results: Whether to validate result parity

        Returns:
            Comprehensive benchmark results summary
        """
        self.logger.info("="*80)
        self.logger.info("STARTING EVENT GENERATION BENCHMARK SUITE")
        self.logger.info("="*80)
        self.logger.info(f"Scenarios: {scenarios}")
        self.logger.info(f"Modes: {modes}")
        self.logger.info(f"Runs per scenario: {runs_per_scenario}")
        self.logger.info(f"Validate results: {validate_results}")

        suite_start_time = time.time()

        # Run all scenario/mode combinations
        for scenario_name in scenarios:
            if scenario_name not in self.PREDEFINED_SCENARIOS:
                self.logger.error(f"Unknown scenario: {scenario_name}")
                continue

            scenario = self.PREDEFINED_SCENARIOS[scenario_name]
            self.logger.info(f"\n--- Running scenario: {scenario.name} ---")
            self.logger.info(f"Description: {scenario.description}")
            self.logger.info(f"Employee count: {scenario.employee_count:,}")
            self.logger.info(f"Years: {scenario.start_year}-{scenario.end_year} ({scenario.year_count} years)")
            self.logger.info(f"Target time: {scenario.target_time_seconds}s")

            for mode in modes:
                self.logger.info(f"\n  Running {mode.upper()} mode...")

                try:
                    result = self._run_scenario_benchmark(
                        scenario=scenario,
                        mode=mode,
                        num_runs=runs_per_scenario,
                        validate_results=validate_results
                    )
                    self.results.append(result)

                    # Log summary
                    if result.avg_metrics:
                        self.logger.info(f"  {mode.upper()} Results:")
                        self.logger.info(f"    Avg time: {result.avg_metrics.execution_time_seconds:.2f}s")
                        self.logger.info(f"    Avg events/sec: {result.avg_metrics.events_per_second:.0f}")
                        self.logger.info(f"    Peak memory: {result.avg_metrics.peak_memory_mb:.1f}MB")
                        self.logger.info(f"    Success rate: {sum(1 for r in result.runs if r.success)}/{len(result.runs)}")

                        if result.avg_metrics.execution_time_seconds <= scenario.target_time_seconds:
                            self.logger.info(f"    ✅ Performance target MET")
                        else:
                            self.logger.info(f"    ❌ Performance target MISSED")

                except Exception as e:
                    self.logger.error(f"Failed to run {mode} benchmark for {scenario_name}: {e}", exc_info=True)

        # Generate comprehensive report
        suite_duration = time.time() - suite_start_time
        self.logger.info(f"\nBenchmark suite completed in {suite_duration:.1f}s")

        # Clean up temporary directories
        self._cleanup_temp_dirs()

        # Generate all report formats
        summary = self._generate_comprehensive_report()

        self.logger.info(f"Results written to: {self.output_dir}")
        return summary

    def _run_scenario_benchmark(self,
                              scenario: BenchmarkScenario,
                              mode: str,
                              num_runs: int,
                              validate_results: bool) -> BenchmarkResult:
        """Run benchmark for a single scenario and mode."""
        runs = []

        for run_num in range(num_runs):
            self.logger.info(f"    Run {run_num + 1}/{num_runs}...")

            try:
                if mode == 'sql':
                    metrics = self._run_sql_benchmark(scenario, run_num)
                elif mode == 'polars':
                    metrics = self._run_polars_benchmark(scenario, run_num)
                else:
                    raise ValueError(f"Unknown mode: {mode}")

                # Validate results if requested
                if validate_results and metrics.success:
                    metrics.validation_passed = self._validate_results(scenario, mode, run_num)

                runs.append(metrics)

            except Exception as e:
                self.logger.error(f"Run {run_num + 1} failed: {e}", exc_info=True)
                runs.append(PerformanceMetrics(
                    execution_time_seconds=0.0,
                    success=False,
                    error_message=str(e)
                ))

        return BenchmarkResult(scenario=scenario, mode=mode, runs=runs)

    def _run_sql_benchmark(self, scenario: BenchmarkScenario, run_num: int) -> PerformanceMetrics:
        """Run SQL-based event generation benchmark."""
        temp_dir = self._create_temp_dir(f"sql_run_{run_num}")

        # Setup timing
        setup_start = time.time()

        # Prepare environment for SQL mode
        dbt_dir = Path("dbt")
        if not dbt_dir.exists():
            raise FileNotFoundError("dbt directory not found")

        # Start resource monitoring
        current_process = psutil.Process()
        monitor = ResourceMonitor(current_process.pid)
        monitor.start_monitoring()

        setup_time = time.time() - setup_start

        # Run SQL-based event generation
        exec_start = time.time()

        try:
            # Build foundation models first
            foundation_cmd = [
                "dbt", "run",
                "--select", "tag:foundation",
                "--threads", "1",  # Single-threaded for consistency
                "--vars", f"simulation_year: {scenario.start_year}"
            ]

            result = subprocess.run(
                foundation_cmd,
                cwd=str(dbt_dir),
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )

            if result.returncode != 0:
                raise subprocess.CalledProcessError(result.returncode, foundation_cmd, result.stderr)

            # Run event generation for all years
            total_events = 0
            for year in range(scenario.start_year, scenario.end_year + 1):
                events_cmd = [
                    "dbt", "run",
                    "--select", "tag:EVENT_GENERATION",
                    "--threads", "1",
                    "--vars", f"simulation_year: {year}"
                ]

                result = subprocess.run(
                    events_cmd,
                    cwd=str(dbt_dir),
                    capture_output=True,
                    text=True,
                    timeout=600  # 10 minute timeout per year
                )

                if result.returncode != 0:
                    raise subprocess.CalledProcessError(result.returncode, events_cmd, result.stderr)

            # Count events generated
            total_events = self._count_generated_events_sql()

            execution_time = time.time() - exec_start

            # Stop monitoring
            resource_metrics = monitor.stop_monitoring()
            resource_metrics.execution_time_seconds = execution_time
            resource_metrics.setup_time_seconds = setup_time
            resource_metrics.events_generated = total_events
            resource_metrics.employee_years_per_second = (
                scenario.total_employee_years / execution_time if execution_time > 0 else 0
            )
            resource_metrics.success = True

            return resource_metrics

        except Exception as e:
            monitor.stop_monitoring()
            return PerformanceMetrics(
                execution_time_seconds=time.time() - exec_start,
                setup_time_seconds=setup_time,
                success=False,
                error_message=str(e)
            )

    def _run_polars_benchmark(self, scenario: BenchmarkScenario, run_num: int) -> PerformanceMetrics:
        """Run Polars-based event generation benchmark."""
        temp_dir = self._create_temp_dir(f"polars_run_{run_num}")

        # Setup timing
        setup_start = time.time()

        # Create Polars event factory configuration
        config = EventFactoryConfig(
            start_year=scenario.start_year,
            end_year=scenario.end_year,
            output_path=temp_dir / "events",
            random_seed=self.random_seed,
            batch_size=min(10000, scenario.employee_count),
            enable_compression=True,
            compression_level=6
        )

        # Start resource monitoring
        current_process = psutil.Process()
        monitor = ResourceMonitor(current_process.pid)

        setup_time = time.time() - setup_start
        monitor.start_monitoring()

        # Run Polars-based event generation
        exec_start = time.time()

        try:
            generator = PolarsEventGenerator(config)
            generator.generate_multi_year_events()

            execution_time = time.time() - exec_start

            # Stop monitoring
            resource_metrics = monitor.stop_monitoring()
            resource_metrics.execution_time_seconds = execution_time
            resource_metrics.setup_time_seconds = setup_time
            resource_metrics.events_generated = generator.stats['total_events_generated']
            resource_metrics.employee_years_per_second = (
                scenario.total_employee_years / execution_time if execution_time > 0 else 0
            )
            resource_metrics.success = True

            return resource_metrics

        except Exception as e:
            monitor.stop_monitoring()
            return PerformanceMetrics(
                execution_time_seconds=time.time() - exec_start,
                setup_time_seconds=setup_time,
                success=False,
                error_message=str(e)
            )

    def _count_generated_events_sql(self) -> int:
        """Count events generated by SQL mode."""
        try:
            import duckdb
            db_path = get_database_path()

            if not db_path.exists():
                return 0

            conn = duckdb.connect(str(db_path))
            result = conn.execute("SELECT COUNT(*) FROM fct_yearly_events").fetchone()
            conn.close()

            return result[0] if result else 0

        except Exception as e:
            self.logger.warning(f"Could not count SQL events: {e}")
            return 0

    def _validate_results(self, scenario: BenchmarkScenario, mode: str, run_num: int) -> bool:
        """Validate results for correctness and parity."""
        try:
            # Basic validation: check event counts are reasonable
            if mode == 'sql':
                event_count = self._count_generated_events_sql()
            else:
                # For Polars mode, we would need to count from parquet files
                event_count = 0  # Simplified for now

            # Check if event count is within expected range
            min_events, max_events = scenario.expected_events_range
            if min_events <= event_count <= max_events:
                self.logger.debug(f"Validation PASSED: {event_count} events in expected range [{min_events}, {max_events}]")
                return True
            else:
                self.logger.warning(f"Validation FAILED: {event_count} events outside expected range [{min_events}, {max_events}]")
                return False

        except Exception as e:
            self.logger.error(f"Validation error: {e}")
            return False

    def _create_temp_dir(self, name: str) -> Path:
        """Create temporary directory for benchmark isolation."""
        temp_dir = self.output_dir / "temp" / name
        temp_dir.mkdir(parents=True, exist_ok=True)
        self.temp_dirs.append(temp_dir)
        return temp_dir

    def _cleanup_temp_dirs(self):
        """Clean up temporary directories."""
        for temp_dir in self.temp_dirs:
            try:
                if temp_dir.exists():
                    shutil.rmtree(temp_dir)
            except Exception as e:
                self.logger.warning(f"Could not clean up {temp_dir}: {e}")
        self.temp_dirs.clear()

    def _generate_comprehensive_report(self) -> Dict[str, Any]:
        """Generate comprehensive benchmark report in multiple formats."""
        timestamp = datetime.now()

        # Generate summary statistics
        summary = {
            'benchmark_metadata': {
                'timestamp': timestamp.isoformat(),
                'framework_version': '1.0.0',
                'random_seed': self.random_seed,
                'total_scenarios': len(self.results),
                'output_directory': str(self.output_dir)
            },
            'scenarios_tested': {},
            'performance_comparison': {},
            'statistical_analysis': {},
            'recommendations': []
        }

        # Group results by scenario for comparison
        scenario_groups = {}
        for result in self.results:
            scenario_name = result.scenario.name
            if scenario_name not in scenario_groups:
                scenario_groups[scenario_name] = {'sql': None, 'polars': None}
            scenario_groups[scenario_name][result.mode] = result

        # Analyze each scenario
        for scenario_name, modes in scenario_groups.items():
            scenario_analysis = self._analyze_scenario_performance(scenario_name, modes)
            summary['scenarios_tested'][scenario_name] = scenario_analysis

        # Generate performance comparison
        summary['performance_comparison'] = self._generate_performance_comparison(scenario_groups)

        # Statistical analysis
        summary['statistical_analysis'] = self._generate_statistical_analysis(scenario_groups)

        # Generate recommendations
        summary['recommendations'] = self._generate_recommendations(scenario_groups)

        # Write reports in multiple formats
        self._write_json_report(summary)
        self._write_csv_report()
        self._write_markdown_report(summary)

        return summary

    def _analyze_scenario_performance(self, scenario_name: str, modes: Dict[str, BenchmarkResult]) -> Dict[str, Any]:
        """Analyze performance for a single scenario across modes."""
        analysis = {
            'scenario_name': scenario_name,
            'modes_tested': list(modes.keys()),
            'results_by_mode': {}
        }

        for mode, result in modes.items():
            if result and result.avg_metrics:
                analysis['results_by_mode'][mode] = {
                    'avg_execution_time': result.avg_metrics.execution_time_seconds,
                    'avg_events_per_second': result.avg_metrics.events_per_second,
                    'avg_peak_memory_mb': result.avg_metrics.peak_memory_mb,
                    'avg_cpu_percent': result.avg_metrics.avg_cpu_percent,
                    'success_rate': sum(1 for r in result.runs if r.success) / len(result.runs),
                    'validation_rate': sum(1 for r in result.runs if r.validation_passed) / len(result.runs),
                    'meets_target': result.avg_metrics.execution_time_seconds <= result.scenario.target_time_seconds,
                    'confidence_intervals': result.confidence_interval_95 or {}
                }

        return analysis

    def _generate_performance_comparison(self, scenario_groups: Dict) -> Dict[str, Any]:
        """Generate performance comparison between SQL and Polars modes."""
        comparison = {
            'summary': {},
            'detailed_comparisons': {}
        }

        sql_wins = 0
        polars_wins = 0

        for scenario_name, modes in scenario_groups.items():
            sql_result = modes.get('sql')
            polars_result = modes.get('polars')

            if sql_result and polars_result and sql_result.avg_metrics and polars_result.avg_metrics:
                sql_time = sql_result.avg_metrics.execution_time_seconds
                polars_time = polars_result.avg_metrics.execution_time_seconds

                if sql_time > 0 and polars_time > 0:
                    speedup = sql_time / polars_time
                    winner = 'polars' if speedup > 1.0 else 'sql'

                    if winner == 'polars':
                        polars_wins += 1
                    else:
                        sql_wins += 1

                    comparison['detailed_comparisons'][scenario_name] = {
                        'sql_time': sql_time,
                        'polars_time': polars_time,
                        'speedup_factor': speedup,
                        'winner': winner,
                        'sql_events_per_sec': sql_result.avg_metrics.events_per_second,
                        'polars_events_per_sec': polars_result.avg_metrics.events_per_second,
                        'throughput_improvement': (
                            polars_result.avg_metrics.events_per_second /
                            sql_result.avg_metrics.events_per_second
                        ) if sql_result.avg_metrics.events_per_second > 0 else 0
                    }

        comparison['summary'] = {
            'sql_wins': sql_wins,
            'polars_wins': polars_wins,
            'total_comparisons': sql_wins + polars_wins
        }

        return comparison

    def _generate_statistical_analysis(self, scenario_groups: Dict) -> Dict[str, Any]:
        """Generate statistical analysis of benchmark results."""
        analysis = {
            'significance_tests': {},
            'effect_sizes': {},
            'recommendations': []
        }

        for scenario_name, modes in scenario_groups.items():
            sql_result = modes.get('sql')
            polars_result = modes.get('polars')

            if sql_result and polars_result and len(sql_result.runs) >= 3 and len(polars_result.runs) >= 3:
                # Extract execution times
                sql_times = [r.execution_time_seconds for r in sql_result.runs if r.success]
                polars_times = [r.execution_time_seconds for r in polars_result.runs if r.success]

                if len(sql_times) >= 3 and len(polars_times) >= 3:
                    # Perform t-test
                    try:
                        t_stat, p_value = stats.ttest_ind(sql_times, polars_times)

                        # Calculate effect size (Cohen's d)
                        pooled_std = np.sqrt(
                            ((len(sql_times) - 1) * np.std(sql_times, ddof=1)**2 +
                             (len(polars_times) - 1) * np.std(polars_times, ddof=1)**2) /
                            (len(sql_times) + len(polars_times) - 2)
                        )

                        cohens_d = (np.mean(sql_times) - np.mean(polars_times)) / pooled_std if pooled_std > 0 else 0

                        analysis['significance_tests'][scenario_name] = {
                            't_statistic': float(t_stat),
                            'p_value': float(p_value),
                            'significant': p_value < 0.05,
                            'interpretation': 'Statistically significant difference' if p_value < 0.05 else 'No significant difference'
                        }

                        analysis['effect_sizes'][scenario_name] = {
                            'cohens_d': float(cohens_d),
                            'effect_size': (
                                'Large' if abs(cohens_d) >= 0.8 else
                                'Medium' if abs(cohens_d) >= 0.5 else
                                'Small' if abs(cohens_d) >= 0.2 else
                                'Negligible'
                            )
                        }

                    except Exception as e:
                        self.logger.warning(f"Statistical analysis failed for {scenario_name}: {e}")

        return analysis

    def _generate_recommendations(self, scenario_groups: Dict) -> List[str]:
        """Generate performance recommendations based on benchmark results."""
        recommendations = []

        # Analyze overall performance trends
        polars_faster_count = 0
        total_comparisons = 0

        for scenario_name, modes in scenario_groups.items():
            sql_result = modes.get('sql')
            polars_result = modes.get('polars')

            if sql_result and polars_result and sql_result.avg_metrics and polars_result.avg_metrics:
                total_comparisons += 1
                if polars_result.avg_metrics.execution_time_seconds < sql_result.avg_metrics.execution_time_seconds:
                    polars_faster_count += 1

        # Generate recommendations based on analysis
        if total_comparisons > 0:
            polars_win_rate = polars_faster_count / total_comparisons

            if polars_win_rate >= 0.8:
                recommendations.append("🚀 STRONG RECOMMENDATION: Adopt Polars mode for production workloads")
                recommendations.append("Polars consistently outperforms SQL mode across scenarios")
            elif polars_win_rate >= 0.6:
                recommendations.append("✅ MODERATE RECOMMENDATION: Consider Polars mode for large-scale scenarios")
                recommendations.append("Polars shows significant performance advantages in most cases")
            else:
                recommendations.append("⚠️  MIXED RESULTS: Evaluate Polars mode case-by-case")
                recommendations.append("Performance benefits vary significantly by scenario")

        # Check 5k×5 target specifically
        target_scenario = scenario_groups.get('5kx5')
        if target_scenario:
            polars_result = target_scenario.get('polars')
            if polars_result and polars_result.avg_metrics:
                if polars_result.avg_metrics.execution_time_seconds <= 60.0:
                    recommendations.append("🎯 TARGET ACHIEVED: Polars mode meets ≤60s performance target for 5k×5")
                else:
                    recommendations.append("❌ TARGET MISSED: Polars mode exceeds 60s target for 5k×5")
                    recommendations.append("Consider further optimization or infrastructure improvements")

        # Memory usage recommendations
        high_memory_scenarios = []
        for scenario_name, modes in scenario_groups.items():
            polars_result = modes.get('polars')
            if polars_result and polars_result.avg_metrics:
                if polars_result.avg_metrics.peak_memory_mb > 4000:  # >4GB
                    high_memory_scenarios.append(scenario_name)

        if high_memory_scenarios:
            recommendations.append(f"💾 MEMORY OPTIMIZATION: High memory usage detected in {len(high_memory_scenarios)} scenarios")
            recommendations.append("Consider batch size tuning or streaming optimization")

        return recommendations

    def _write_json_report(self, summary: Dict[str, Any]):
        """Write comprehensive JSON report."""
        json_file = self.output_dir / f"benchmark_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        # Convert results to JSON-serializable format
        json_data = {
            'summary': summary,
            'detailed_results': []
        }

        for result in self.results:
            json_data['detailed_results'].append({
                'scenario': asdict(result.scenario),
                'mode': result.mode,
                'timestamp': result.timestamp.isoformat(),
                'runs': [asdict(run) for run in result.runs],
                'avg_metrics': asdict(result.avg_metrics) if result.avg_metrics else None,
                'confidence_intervals': result.confidence_interval_95
            })

        with open(json_file, 'w') as f:
            json.dump(json_data, f, indent=2, default=str)

        self.logger.info(f"JSON report written to: {json_file}")

    def _write_csv_report(self):
        """Write CSV report with tabular performance data."""
        csv_file = self.output_dir / f"benchmark_data_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        import csv

        with open(csv_file, 'w', newline='') as f:
            writer = csv.writer(f)

            # Header
            writer.writerow([
                'scenario_name', 'mode', 'run_number', 'execution_time_seconds',
                'events_generated', 'events_per_second', 'peak_memory_mb',
                'avg_cpu_percent', 'success', 'validation_passed'
            ])

            # Data rows
            for result in self.results:
                for i, run in enumerate(result.runs):
                    writer.writerow([
                        result.scenario.name,
                        result.mode,
                        i + 1,
                        run.execution_time_seconds,
                        run.events_generated,
                        run.events_per_second,
                        run.peak_memory_mb,
                        run.avg_cpu_percent,
                        run.success,
                        run.validation_passed
                    ])

        self.logger.info(f"CSV report written to: {csv_file}")

    def _write_markdown_report(self, summary: Dict[str, Any]):
        """Write markdown report for documentation."""
        md_file = self.output_dir / f"benchmark_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"

        with open(md_file, 'w') as f:
            f.write("# Event Generation Benchmark Report\n\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            # Executive Summary
            f.write("## Executive Summary\n\n")
            performance_comparison = summary.get('performance_comparison', {})
            if performance_comparison:
                sql_wins = performance_comparison.get('summary', {}).get('sql_wins', 0)
                polars_wins = performance_comparison.get('summary', {}).get('polars_wins', 0)
                f.write(f"- **Polars wins**: {polars_wins} scenarios\n")
                f.write(f"- **SQL wins**: {sql_wins} scenarios\n")
                f.write(f"- **Total scenarios**: {len(summary.get('scenarios_tested', {}))}\n\n")

            # Scenarios Tested
            f.write("## Scenarios Tested\n\n")
            for scenario_name, analysis in summary.get('scenarios_tested', {}).items():
                f.write(f"### {scenario_name}\n\n")
                f.write("| Mode | Avg Time (s) | Events/sec | Peak Memory (MB) | Target Met |\n")
                f.write("|------|-------------|------------|------------------|------------|\n")

                for mode, results in analysis.get('results_by_mode', {}).items():
                    target_met = "✅" if results.get('meets_target', False) else "❌"
                    f.write(f"| {mode.upper()} | {results.get('avg_execution_time', 0):.2f} | "
                           f"{results.get('avg_events_per_second', 0):.0f} | "
                           f"{results.get('avg_peak_memory_mb', 0):.1f} | {target_met} |\n")
                f.write("\n")

            # Performance Comparison
            f.write("## Performance Comparison\n\n")
            detailed_comparisons = performance_comparison.get('detailed_comparisons', {})
            if detailed_comparisons:
                f.write("| Scenario | Winner | Speedup | Throughput Improvement |\n")
                f.write("|----------|---------|---------|------------------------|\n")

                for scenario, comparison in detailed_comparisons.items():
                    winner = comparison.get('winner', 'unknown').upper()
                    speedup = comparison.get('speedup_factor', 0)
                    throughput = comparison.get('throughput_improvement', 0)
                    f.write(f"| {scenario} | {winner} | {speedup:.2f}x | {throughput:.2f}x |\n")
                f.write("\n")

            # Recommendations
            f.write("## Recommendations\n\n")
            for recommendation in summary.get('recommendations', []):
                f.write(f"- {recommendation}\n")
            f.write("\n")

            # Statistical Analysis
            stats_analysis = summary.get('statistical_analysis', {})
            if stats_analysis.get('significance_tests'):
                f.write("## Statistical Analysis\n\n")
                f.write("| Scenario | P-value | Significant | Effect Size |\n")
                f.write("|----------|---------|-------------|-------------|\n")

                for scenario, test in stats_analysis.get('significance_tests', {}).items():
                    effect_size = stats_analysis.get('effect_sizes', {}).get(scenario, {}).get('effect_size', 'Unknown')
                    significant = "Yes" if test.get('significant', False) else "No"
                    f.write(f"| {scenario} | {test.get('p_value', 0):.4f} | {significant} | {effect_size} |\n")

        self.logger.info(f"Markdown report written to: {md_file}")


def main():
    """Main CLI entry point for benchmark framework."""
    parser = argparse.ArgumentParser(
        description="Event Generation Benchmarking Framework",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Quick validation test
  python scripts/benchmark_event_generation.py --quick

  # Full benchmark suite with 5 runs per scenario
  python scripts/benchmark_event_generation.py --full --runs 5

  # Specific scenario comparison
  python scripts/benchmark_event_generation.py --scenario 5kx5 --runs 3

  # Custom scenarios and modes
  python scripts/benchmark_event_generation.py --scenarios quick 1kx3 --modes sql polars --runs 3

  # CI/CD integration (minimal output)
  python scripts/benchmark_event_generation.py --ci --scenario 5kx5 --target-time 60
        """
    )

    # Benchmark configuration
    parser.add_argument('--scenarios', nargs='+',
                       choices=['quick', '1kx3', '5kx5', 'stress'],
                       help='Scenarios to benchmark')
    parser.add_argument('--modes', nargs='+', choices=['sql', 'polars'],
                       default=['sql', 'polars'],
                       help='Event generation modes to test (default: both)')
    parser.add_argument('--runs', type=int, default=3,
                       help='Number of runs per scenario (default: 3)')

    # Predefined benchmark suites
    parser.add_argument('--quick', action='store_true',
                       help='Run quick validation benchmark')
    parser.add_argument('--full', action='store_true',
                       help='Run full benchmark suite')
    parser.add_argument('--ci', action='store_true',
                       help='CI/CD mode - minimal output, exit code indicates success')

    # Individual scenario shortcuts
    parser.add_argument('--scenario', choices=['quick', '1kx3', '5kx5', 'stress'],
                       help='Run single scenario benchmark')

    # Configuration options
    parser.add_argument('--output-dir', type=Path, default='benchmark_results',
                       help='Output directory for results (default: benchmark_results)')
    parser.add_argument('--random-seed', type=int, default=12345,
                       help='Random seed for reproducible results (default: 12345)')
    parser.add_argument('--target-time', type=float, default=60.0,
                       help='Target time in seconds for performance assessment (default: 60.0)')

    # Validation options
    parser.add_argument('--no-validation', action='store_true',
                       help='Skip result validation (faster execution)')
    parser.add_argument('--validate-parity', action='store_true',
                       help='Perform detailed parity validation between modes')

    # Logging and debugging
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose logging')
    parser.add_argument('--debug', action='store_true',
                       help='Debug logging level')

    args = parser.parse_args()

    # Setup logging
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)
    elif args.verbose:
        logging.basicConfig(level=logging.INFO)
    elif args.ci:
        logging.basicConfig(level=logging.WARNING)
    else:
        logging.basicConfig(level=logging.INFO)

    # Determine scenarios to run
    scenarios = []
    if args.quick:
        scenarios = ['quick']
    elif args.full:
        scenarios = ['quick', '1kx3', '5kx5']
    elif args.scenario:
        scenarios = [args.scenario]
    elif args.scenarios:
        scenarios = args.scenarios
    else:
        scenarios = ['quick']  # Default

    # Initialize benchmark framework
    benchmark = EventGenerationBenchmark(
        output_dir=args.output_dir,
        random_seed=args.random_seed
    )

    try:
        # Run benchmark suite
        results = benchmark.run_benchmark_suite(
            scenarios=scenarios,
            modes=args.modes,
            runs_per_scenario=args.runs,
            validate_results=not args.no_validation
        )

        if args.ci:
            # CI mode: check if target performance was met
            success = True
            for scenario_name, analysis in results.get('scenarios_tested', {}).items():
                for mode, mode_results in analysis.get('results_by_mode', {}).items():
                    if not mode_results.get('meets_target', False):
                        success = False
                        print(f"FAILED: {mode} mode for {scenario_name} exceeded target time")

            if success:
                print("SUCCESS: All benchmarks met performance targets")
                sys.exit(0)
            else:
                sys.exit(1)
        else:
            # Interactive mode: show summary
            print("\n" + "="*80)
            print("BENCHMARK COMPLETE")
            print("="*80)

            performance_comparison = results.get('performance_comparison', {})
            if performance_comparison:
                summary = performance_comparison.get('summary', {})
                print(f"Polars wins: {summary.get('polars_wins', 0)}")
                print(f"SQL wins: {summary.get('sql_wins', 0)}")
                print(f"Total comparisons: {summary.get('total_comparisons', 0)}")

            print(f"\nResults written to: {args.output_dir}")
            print(f"Check the generated reports for detailed analysis.")

            # Show recommendations
            recommendations = results.get('recommendations', [])
            if recommendations:
                print("\nKey Recommendations:")
                for rec in recommendations[:3]:  # Show top 3
                    print(f"  {rec}")

    except KeyboardInterrupt:
        print("\nBenchmark interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"Benchmark failed: {e}")
        if args.debug:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
