#!/usr/bin/env python3
"""
CI/CD Integration Utilities for Event Generation Benchmarking

Provides utilities for integrating the benchmarking framework with
CI/CD pipelines including GitHub Actions, automated performance regression
detection, and result comparison across builds.

This module provides:
- Performance regression detection
- Build-to-build performance comparison
- Automated benchmark scheduling
- Performance alert generation
- Integration with CI/CD systems

Usage:
    python scripts/benchmark_ci_integration.py --mode regression-check
    python scripts/benchmark_ci_integration.py --mode baseline-update
    python scripts/benchmark_ci_integration.py --mode performance-gate
"""

import os
import sys
import json
import time
import logging
import argparse
import subprocess
from pathlib import Path
from datetime import datetime, timedelta
from dataclasses import dataclass, asdict
from typing import List, Dict, Any, Optional, Tuple
import tempfile

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from scripts.benchmark_event_generation import EventGenerationBenchmark, BenchmarkScenario


@dataclass
class PerformanceBaseline:
    """Performance baseline for regression detection."""
    scenario_name: str
    mode: str
    baseline_execution_time: float
    baseline_events_per_second: float
    baseline_memory_mb: float
    baseline_cpu_percent: float

    # Regression thresholds (percentage degradation)
    time_regression_threshold: float = 0.15  # 15% slower
    throughput_regression_threshold: float = 0.10  # 10% fewer events/sec
    memory_regression_threshold: float = 0.20  # 20% more memory

    timestamp: datetime = None
    git_commit: Optional[str] = None
    build_number: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now()


@dataclass
class RegressionResult:
    """Result of performance regression analysis."""
    scenario_name: str
    mode: str

    # Performance metrics
    current_execution_time: float
    baseline_execution_time: float
    time_change_percent: float

    current_throughput: float
    baseline_throughput: float
    throughput_change_percent: float

    current_memory: float
    baseline_memory: float
    memory_change_percent: float

    # Regression flags
    time_regression: bool = False
    throughput_regression: bool = False
    memory_regression: bool = False

    @property
    def has_regression(self) -> bool:
        """True if any regression detected."""
        return self.time_regression or self.throughput_regression or self.memory_regression

    @property
    def regression_severity(self) -> str:
        """Severity of regression (none, minor, major, critical)."""
        if not self.has_regression:
            return 'none'

        # Determine worst regression
        max_degradation = max(
            abs(self.time_change_percent) if self.time_regression else 0,
            abs(self.throughput_change_percent) if self.throughput_regression else 0,
            abs(self.memory_change_percent) if self.memory_regression else 0
        )

        if max_degradation >= 30:
            return 'critical'
        elif max_degradation >= 20:
            return 'major'
        elif max_degradation >= 10:
            return 'minor'
        else:
            return 'none'


class CIBenchmarkOrchestrator:
    """Orchestrator for CI/CD benchmark integration."""

    def __init__(self, baseline_dir: Path = None, output_dir: Path = None):
        """Initialize CI benchmark orchestrator."""
        self.baseline_dir = baseline_dir or Path("benchmark_baselines")
        self.output_dir = output_dir or Path("benchmark_results")
        self.baseline_dir.mkdir(parents=True, exist_ok=True)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.logger = self._setup_logging()

        # Git information
        self.git_commit = self._get_git_commit()
        self.build_number = os.environ.get('BUILD_NUMBER') or os.environ.get('GITHUB_RUN_NUMBER')

    def _setup_logging(self) -> logging.Logger:
        """Setup logging for CI integration."""
        logger = logging.getLogger('ci_benchmark')

        if not logger.handlers:
            handler = logging.StreamHandler()
            formatter = logging.Formatter(
                '%(asctime)s - CI-BENCHMARK - %(levelname)s - %(message)s'
            )
            handler.setFormatter(formatter)
            logger.addHandler(handler)
            logger.setLevel(logging.INFO)

        return logger

    def _get_git_commit(self) -> Optional[str]:
        """Get current git commit hash."""
        try:
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                capture_output=True,
                text=True,
                check=True
            )
            return result.stdout.strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            return None

    def run_regression_check(self,
                           scenarios: List[str] = None,
                           modes: List[str] = None,
                           fail_on_regression: bool = True) -> Dict[str, Any]:
        """
        Run performance regression check against baseline.

        Args:
            scenarios: Scenarios to test (default: quick benchmarks)
            modes: Modes to test (default: both)
            fail_on_regression: Whether to fail CI on regression

        Returns:
            Regression analysis results
        """
        scenarios = scenarios or ['quick', '1kx3']  # Fast scenarios for CI
        modes = modes or ['sql', 'polars']

        self.logger.info("Starting performance regression check...")
        self.logger.info(f"Git commit: {self.git_commit}")
        self.logger.info(f"Build number: {self.build_number}")

        # Run current benchmarks
        benchmark = EventGenerationBenchmark(
            output_dir=self.output_dir / "current",
            random_seed=12345
        )

        current_results = benchmark.run_benchmark_suite(
            scenarios=scenarios,
            modes=modes,
            runs_per_scenario=3,  # Quick runs for CI
            validate_results=True
        )

        # Load baselines
        baselines = self._load_baselines()

        # Perform regression analysis
        regression_analysis = self._analyze_regressions(
            current_results=current_results,
            baselines=baselines
        )

        # Generate CI-specific reports
        self._generate_ci_report(regression_analysis)

        # Check if we should fail CI
        has_critical_regression = any(
            result.regression_severity in ['critical', 'major']
            for result in regression_analysis.get('regressions', [])
        )

        if fail_on_regression and has_critical_regression:
            self.logger.error("Critical performance regression detected - failing CI")
            return {
                'status': 'FAILED',
                'reason': 'Critical performance regression',
                'analysis': regression_analysis
            }
        else:
            return {
                'status': 'PASSED',
                'analysis': regression_analysis
            }

    def update_performance_baseline(self,
                                  scenarios: List[str] = None,
                                  modes: List[str] = None) -> Dict[str, Any]:
        """
        Update performance baseline with current results.

        Should be run on main branch after performance improvements
        or when establishing new baselines.
        """
        scenarios = scenarios or ['quick', '1kx3', '5kx5']
        modes = modes or ['sql', 'polars']

        self.logger.info("Updating performance baseline...")

        # Run comprehensive benchmarks
        benchmark = EventGenerationBenchmark(
            output_dir=self.output_dir / "baseline_update",
            random_seed=12345
        )

        results = benchmark.run_benchmark_suite(
            scenarios=scenarios,
            modes=modes,
            runs_per_scenario=5,  # More runs for stable baseline
            validate_results=True
        )

        # Create new baselines
        new_baselines = self._create_baselines_from_results(results)

        # Save baselines
        self._save_baselines(new_baselines)

        self.logger.info(f"Updated {len(new_baselines)} performance baselines")

        return {
            'status': 'SUCCESS',
            'baselines_updated': len(new_baselines),
            'git_commit': self.git_commit,
            'build_number': self.build_number
        }

    def run_performance_gate(self,
                           target_scenario: str = '5kx5',
                           target_time: float = 60.0,
                           mode: str = 'polars') -> Dict[str, Any]:
        """
        Run performance gate check for specific targets.

        Used to ensure performance requirements are met before release.
        """
        self.logger.info(f"Running performance gate check for {target_scenario}")
        self.logger.info(f"Target: {target_time}s for {mode} mode")

        # Run target benchmark
        benchmark = EventGenerationBenchmark(
            output_dir=self.output_dir / "performance_gate",
            random_seed=12345
        )

        results = benchmark.run_benchmark_suite(
            scenarios=[target_scenario],
            modes=[mode],
            runs_per_scenario=3,
            validate_results=True
        )

        # Check if target was met
        scenario_results = results.get('scenarios_tested', {}).get(target_scenario, {})
        mode_results = scenario_results.get('results_by_mode', {}).get(mode, {})

        if mode_results:
            actual_time = mode_results.get('avg_execution_time', float('inf'))
            target_met = actual_time <= target_time

            gate_result = {
                'status': 'PASSED' if target_met else 'FAILED',
                'target_scenario': target_scenario,
                'target_time': target_time,
                'actual_time': actual_time,
                'mode': mode,
                'margin': target_time - actual_time,
                'margin_percent': ((target_time - actual_time) / target_time) * 100
            }

            if target_met:
                self.logger.info(f"✅ Performance gate PASSED: {actual_time:.1f}s <= {target_time}s")
            else:
                self.logger.error(f"❌ Performance gate FAILED: {actual_time:.1f}s > {target_time}s")

            return gate_result
        else:
            return {
                'status': 'ERROR',
                'reason': 'No results available for analysis'
            }

    def _load_baselines(self) -> Dict[str, PerformanceBaseline]:
        """Load performance baselines from disk."""
        baselines = {}

        baseline_files = list(self.baseline_dir.glob("*.json"))
        for baseline_file in baseline_files:
            try:
                with open(baseline_file, 'r') as f:
                    data = json.load(f)

                    # Convert to PerformanceBaseline objects
                    baseline_key = f"{data['scenario_name']}_{data['mode']}"

                    # Handle datetime deserialization
                    timestamp_str = data.get('timestamp')
                    timestamp = None
                    if timestamp_str:
                        try:
                            timestamp = datetime.fromisoformat(timestamp_str)
                        except ValueError:
                            timestamp = datetime.now()

                    baselines[baseline_key] = PerformanceBaseline(
                        scenario_name=data['scenario_name'],
                        mode=data['mode'],
                        baseline_execution_time=data['baseline_execution_time'],
                        baseline_events_per_second=data['baseline_events_per_second'],
                        baseline_memory_mb=data['baseline_memory_mb'],
                        baseline_cpu_percent=data['baseline_cpu_percent'],
                        timestamp=timestamp,
                        git_commit=data.get('git_commit'),
                        build_number=data.get('build_number')
                    )
            except Exception as e:
                self.logger.warning(f"Could not load baseline {baseline_file}: {e}")

        self.logger.info(f"Loaded {len(baselines)} performance baselines")
        return baselines

    def _save_baselines(self, baselines: List[PerformanceBaseline]):
        """Save performance baselines to disk."""
        for baseline in baselines:
            baseline_file = self.baseline_dir / f"{baseline.scenario_name}_{baseline.mode}_baseline.json"

            # Convert to JSON-serializable format
            data = asdict(baseline)
            if baseline.timestamp:
                data['timestamp'] = baseline.timestamp.isoformat()

            with open(baseline_file, 'w') as f:
                json.dump(data, f, indent=2, default=str)

        self.logger.info(f"Saved {len(baselines)} performance baselines")

    def _create_baselines_from_results(self, results: Dict[str, Any]) -> List[PerformanceBaseline]:
        """Create baseline objects from benchmark results."""
        baselines = []

        scenarios_tested = results.get('scenarios_tested', {})
        for scenario_name, scenario_data in scenarios_tested.items():
            for mode, mode_results in scenario_data.get('results_by_mode', {}).items():
                baseline = PerformanceBaseline(
                    scenario_name=scenario_name,
                    mode=mode,
                    baseline_execution_time=mode_results.get('avg_execution_time', 0.0),
                    baseline_events_per_second=mode_results.get('avg_events_per_second', 0.0),
                    baseline_memory_mb=mode_results.get('avg_peak_memory_mb', 0.0),
                    baseline_cpu_percent=mode_results.get('avg_cpu_percent', 0.0),
                    timestamp=datetime.now(),
                    git_commit=self.git_commit,
                    build_number=self.build_number
                )
                baselines.append(baseline)

        return baselines

    def _analyze_regressions(self,
                           current_results: Dict[str, Any],
                           baselines: Dict[str, PerformanceBaseline]) -> Dict[str, Any]:
        """Analyze performance regressions against baselines."""
        regressions = []

        scenarios_tested = current_results.get('scenarios_tested', {})
        for scenario_name, scenario_data in scenarios_tested.items():
            for mode, mode_results in scenario_data.get('results_by_mode', {}).items():
                baseline_key = f"{scenario_name}_{mode}"
                baseline = baselines.get(baseline_key)

                if not baseline:
                    self.logger.warning(f"No baseline found for {baseline_key}")
                    continue

                # Calculate performance changes
                current_time = mode_results.get('avg_execution_time', 0.0)
                current_throughput = mode_results.get('avg_events_per_second', 0.0)
                current_memory = mode_results.get('avg_peak_memory_mb', 0.0)

                # Calculate percentage changes
                time_change = ((current_time - baseline.baseline_execution_time) /
                              baseline.baseline_execution_time * 100) if baseline.baseline_execution_time > 0 else 0

                throughput_change = ((current_throughput - baseline.baseline_events_per_second) /
                                   baseline.baseline_events_per_second * 100) if baseline.baseline_events_per_second > 0 else 0

                memory_change = ((current_memory - baseline.baseline_memory_mb) /
                               baseline.baseline_memory_mb * 100) if baseline.baseline_memory_mb > 0 else 0

                # Detect regressions
                regression_result = RegressionResult(
                    scenario_name=scenario_name,
                    mode=mode,
                    current_execution_time=current_time,
                    baseline_execution_time=baseline.baseline_execution_time,
                    time_change_percent=time_change,
                    current_throughput=current_throughput,
                    baseline_throughput=baseline.baseline_events_per_second,
                    throughput_change_percent=throughput_change,
                    current_memory=current_memory,
                    baseline_memory=baseline.baseline_memory_mb,
                    memory_change_percent=memory_change,
                    time_regression=time_change > baseline.time_regression_threshold * 100,
                    throughput_regression=throughput_change < -baseline.throughput_regression_threshold * 100,
                    memory_regression=memory_change > baseline.memory_regression_threshold * 100
                )

                regressions.append(regression_result)

        # Summarize regression analysis
        total_regressions = sum(1 for r in regressions if r.has_regression)
        critical_regressions = sum(1 for r in regressions if r.regression_severity == 'critical')
        major_regressions = sum(1 for r in regressions if r.regression_severity == 'major')

        return {
            'total_comparisons': len(regressions),
            'total_regressions': total_regressions,
            'critical_regressions': critical_regressions,
            'major_regressions': major_regressions,
            'regressions': regressions,
            'git_commit': self.git_commit,
            'build_number': self.build_number,
            'timestamp': datetime.now().isoformat()
        }

    def _generate_ci_report(self, regression_analysis: Dict[str, Any]):
        """Generate CI-specific report for build systems."""
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

        # JSON report for machine consumption
        json_report = self.output_dir / f"ci_report_{timestamp}.json"
        with open(json_report, 'w') as f:
            # Convert RegressionResult objects to dict for JSON serialization
            serializable_analysis = dict(regression_analysis)
            serializable_analysis['regressions'] = [
                asdict(r) for r in regression_analysis.get('regressions', [])
            ]
            json.dump(serializable_analysis, f, indent=2, default=str)

        # Human-readable summary
        summary_report = self.output_dir / f"ci_summary_{timestamp}.txt"
        with open(summary_report, 'w') as f:
            f.write("PERFORMANCE REGRESSION ANALYSIS\n")
            f.write("="*50 + "\n\n")
            f.write(f"Timestamp: {regression_analysis.get('timestamp', 'Unknown')}\n")
            f.write(f"Git commit: {regression_analysis.get('git_commit', 'Unknown')}\n")
            f.write(f"Build number: {regression_analysis.get('build_number', 'Unknown')}\n\n")

            f.write(f"Total comparisons: {regression_analysis.get('total_comparisons', 0)}\n")
            f.write(f"Total regressions: {regression_analysis.get('total_regressions', 0)}\n")
            f.write(f"Critical regressions: {regression_analysis.get('critical_regressions', 0)}\n")
            f.write(f"Major regressions: {regression_analysis.get('major_regressions', 0)}\n\n")

            # Detail regressions
            regressions = regression_analysis.get('regressions', [])
            for regression in regressions:
                if regression.has_regression:
                    f.write(f"REGRESSION: {regression.scenario_name} ({regression.mode})\n")
                    f.write(f"  Severity: {regression.regression_severity.upper()}\n")
                    f.write(f"  Time change: {regression.time_change_percent:+.1f}%\n")
                    f.write(f"  Throughput change: {regression.throughput_change_percent:+.1f}%\n")
                    f.write(f"  Memory change: {regression.memory_change_percent:+.1f}%\n\n")

        self.logger.info(f"CI reports generated: {json_report}, {summary_report}")


def main():
    """Main CLI entry point for CI integration."""
    parser = argparse.ArgumentParser(
        description="CI/CD Integration for Event Generation Benchmarking",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check for performance regressions
  python scripts/benchmark_ci_integration.py --mode regression-check

  # Update performance baseline (after improvements)
  python scripts/benchmark_ci_integration.py --mode baseline-update

  # Performance gate check for release
  python scripts/benchmark_ci_integration.py --mode performance-gate --scenario 5kx5 --target-time 60

  # Custom regression check
  python scripts/benchmark_ci_integration.py --mode regression-check --scenarios quick 1kx3 --modes polars
        """
    )

    # Mode selection
    parser.add_argument('--mode', required=True,
                       choices=['regression-check', 'baseline-update', 'performance-gate'],
                       help='CI integration mode')

    # Common options
    parser.add_argument('--scenarios', nargs='+',
                       choices=['quick', '1kx3', '5kx5', 'stress'],
                       help='Scenarios to test')
    parser.add_argument('--modes', nargs='+',
                       choices=['sql', 'polars'],
                       help='Generation modes to test')

    # Performance gate options
    parser.add_argument('--scenario', choices=['quick', '1kx3', '5kx5', 'stress'],
                       help='Single scenario for performance gate')
    parser.add_argument('--target-time', type=float, default=60.0,
                       help='Target time in seconds for performance gate')
    parser.add_argument('--mode-single', choices=['sql', 'polars'], default='polars',
                       help='Mode for performance gate check')

    # Configuration
    parser.add_argument('--baseline-dir', type=Path, default='benchmark_baselines',
                       help='Directory for performance baselines')
    parser.add_argument('--output-dir', type=Path, default='benchmark_results',
                       help='Directory for output results')

    # CI behavior
    parser.add_argument('--fail-on-regression', action='store_true', default=True,
                       help='Fail CI on performance regression (default: True)')
    parser.add_argument('--no-fail-on-regression', dest='fail_on_regression', action='store_false',
                       help='Do not fail CI on performance regression')

    # Logging
    parser.add_argument('--verbose', '-v', action='store_true',
                       help='Verbose logging')
    parser.add_argument('--quiet', '-q', action='store_true',
                       help='Quiet mode - minimal output')

    args = parser.parse_args()

    # Setup logging
    if args.quiet:
        logging.basicConfig(level=logging.WARNING)
    elif args.verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.INFO)

    # Initialize orchestrator
    orchestrator = CIBenchmarkOrchestrator(
        baseline_dir=args.baseline_dir,
        output_dir=args.output_dir
    )

    try:
        if args.mode == 'regression-check':
            result = orchestrator.run_regression_check(
                scenarios=args.scenarios,
                modes=args.modes,
                fail_on_regression=args.fail_on_regression
            )

            print(f"Status: {result['status']}")
            if result['status'] == 'FAILED':
                print(f"Reason: {result['reason']}")
                sys.exit(1)
            else:
                analysis = result['analysis']
                print(f"Total regressions: {analysis.get('total_regressions', 0)}")
                print(f"Critical regressions: {analysis.get('critical_regressions', 0)}")
                sys.exit(0)

        elif args.mode == 'baseline-update':
            result = orchestrator.update_performance_baseline(
                scenarios=args.scenarios,
                modes=args.modes
            )

            print(f"Status: {result['status']}")
            print(f"Baselines updated: {result['baselines_updated']}")
            sys.exit(0)

        elif args.mode == 'performance-gate':
            result = orchestrator.run_performance_gate(
                target_scenario=args.scenario or '5kx5',
                target_time=args.target_time,
                mode=args.mode_single
            )

            print(f"Status: {result['status']}")
            if result['status'] == 'PASSED':
                print(f"Target met: {result['actual_time']:.1f}s <= {result['target_time']}s")
                print(f"Margin: {result['margin']:.1f}s ({result['margin_percent']:.1f}%)")
                sys.exit(0)
            else:
                print(f"Target missed: {result.get('actual_time', 0):.1f}s > {result['target_time']}s")
                sys.exit(1)

    except KeyboardInterrupt:
        print("CI benchmark interrupted")
        sys.exit(130)
    except Exception as e:
        print(f"CI benchmark failed: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
