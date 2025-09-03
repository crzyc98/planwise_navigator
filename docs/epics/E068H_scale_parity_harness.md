# Epic E068H: Scale & Parity Harness + CI + Rollback

## Goal
Prove linear scale, enforce determinism in CI, and document a fast rollback path.

## Scope
- **In**: Scale matrix jobs; parity runner (old vs new on 1k×2yrs slice); CI gates; rollback instructions & feature flag.
- **Out**: Functional changes.

## Deliverables
- Scale matrix: 5k/20k/50k employees × years=5 × shards=1/4/8; capture wall-clock, peak RSS, artifacts.
- Parity job runs legacy vs new pipeline, asserts equality on SimulationEvent + employee_state_by_year.
- Rollback plan:
  - Keep legacy writers behind feature_flag_legacy_events=true for two releases.
  - Rollback = checkout pre-E068 tag + set flag + re-run.

## Acceptance Criteria
- Time grows ~linearly; peak RSS within SLO (≤ 40 GB).
- CI parity must pass before merge to main.
- Rollback validated once on staging.

## Implementation Details

### Scale Testing Framework
```python
# scripts/scale_testing_framework.py
import subprocess
import time
import psutil
import json
from pathlib import Path
from typing import Dict, List, Any, Tuple
from dataclasses import dataclass, asdict
import logging
from concurrent.futures import ThreadPoolExecutor
import matplotlib.pyplot as plt
import pandas as pd

@dataclass
class ScaleTestConfig:
    """Configuration for scale testing."""
    employee_counts: List[int]
    year_counts: List[int]
    shard_counts: List[int]
    optimization_mode: str  # 'baseline', 'optimized', 'polars'
    iterations: int = 3
    output_dir: Path = Path("scale_test_results")

@dataclass
class ScaleTestResult:
    """Results from a single scale test run."""
    employee_count: int
    year_count: int
    shard_count: int
    optimization_mode: str
    iteration: int

    # Performance metrics
    wall_clock_time: float
    peak_memory_gb: float
    avg_cpu_percent: float
    total_events_generated: int

    # Derived metrics
    events_per_second: float
    memory_per_employee: float
    time_per_year: float

    # Success indicators
    completed_successfully: bool
    error_message: str = ""

class ScaleTestRunner:
    """Execute scale tests across different configurations."""

    def __init__(self, config: ScaleTestConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)
        self.results: List[ScaleTestResult] = []

        # Ensure output directory exists
        self.config.output_dir.mkdir(parents=True, exist_ok=True)

    def run_single_test(
        self,
        employee_count: int,
        year_count: int,
        shard_count: int,
        iteration: int
    ) -> ScaleTestResult:
        """Run a single scale test configuration."""

        self.logger.info(f"Running test: {employee_count} employees × {year_count} years × {shard_count} shards (iteration {iteration})")

        start_time = time.time()
        peak_memory = 0.0
        cpu_samples = []

        try:
            # Start monitoring
            monitor_thread = ThreadPoolExecutor(max_workers=1)
            monitoring_future = monitor_thread.submit(
                self._monitor_resources,
                cpu_samples
            )

            # Configure test environment
            test_vars = {
                'simulation_year': 2025,
                'start_year': 2025,
                'end_year': 2025 + year_count - 1,
                'dev_employee_limit': employee_count,
                'optimization_mode': self.config.optimization_mode,
                'event_shards': shard_count if shard_count > 1 else None
            }

            # Execute simulation based on optimization mode
            if self.config.optimization_mode == 'polars':
                success, events_count = self._run_polars_simulation(test_vars)
            else:
                success, events_count = self._run_dbt_simulation(test_vars)

            # Stop monitoring
            monitoring_future.cancel()
            monitor_thread.shutdown(wait=False)

            wall_clock_time = time.time() - start_time
            peak_memory = max(cpu_samples, key=lambda x: x[1])[1] if cpu_samples else 0
            avg_cpu = sum(x[0] for x in cpu_samples) / len(cpu_samples) if cpu_samples else 0

            # Create result record
            result = ScaleTestResult(
                employee_count=employee_count,
                year_count=year_count,
                shard_count=shard_count,
                optimization_mode=self.config.optimization_mode,
                iteration=iteration,
                wall_clock_time=wall_clock_time,
                peak_memory_gb=peak_memory / (1024**3),
                avg_cpu_percent=avg_cpu,
                total_events_generated=events_count,
                events_per_second=events_count / wall_clock_time if wall_clock_time > 0 else 0,
                memory_per_employee=peak_memory / (1024**3) / employee_count if employee_count > 0 else 0,
                time_per_year=wall_clock_time / year_count if year_count > 0 else 0,
                completed_successfully=success
            )

            self.logger.info(f"Test completed: {wall_clock_time:.1f}s, {peak_memory/(1024**3):.1f}GB peak, {events_count} events")
            return result

        except Exception as e:
            self.logger.error(f"Test failed: {e}")
            return ScaleTestResult(
                employee_count=employee_count,
                year_count=year_count,
                shard_count=shard_count,
                optimization_mode=self.config.optimization_mode,
                iteration=iteration,
                wall_clock_time=time.time() - start_time,
                peak_memory_gb=0,
                avg_cpu_percent=0,
                total_events_generated=0,
                events_per_second=0,
                memory_per_employee=0,
                time_per_year=0,
                completed_successfully=False,
                error_message=str(e)
            )

    def _monitor_resources(self, cpu_samples: List[Tuple[float, int]]) -> None:
        """Monitor CPU and memory usage during test."""
        while True:
            try:
                cpu_percent = psutil.cpu_percent(interval=1)
                memory_bytes = psutil.virtual_memory().used
                cpu_samples.append((cpu_percent, memory_bytes))
                time.sleep(2)
            except:
                break

    def _run_dbt_simulation(self, test_vars: Dict) -> Tuple[bool, int]:
        """Run dbt-based simulation."""

        # Build dbt command
        cmd = [
            "python", "-m", "navigator_orchestrator", "run",
            "--years", str(test_vars['start_year']), str(test_vars['end_year']),
            "--optimization", test_vars.get('optimization_mode', 'medium')
        ]

        if test_vars.get('event_shards'):
            cmd.extend(["--shards", str(test_vars['event_shards'])])

        # Set environment variables for employee limit
        env = os.environ.copy()
        env['DBT_DEV_EMPLOYEE_LIMIT'] = str(test_vars['dev_employee_limit'])

        # Execute simulation
        result = subprocess.run(cmd, capture_output=True, text=True, env=env)

        success = result.returncode == 0

        # Count events from database
        events_count = 0
        if success:
            try:
                import duckdb
                conn = duckdb.connect("dbt/simulation.duckdb")
                query = "SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year BETWEEN ? AND ?"
                events_count = conn.execute(query, [test_vars['start_year'], test_vars['end_year']]).fetchone()[0]
                conn.close()
            except Exception as e:
                self.logger.warning(f"Could not count events: {e}")

        return success, events_count

    def _run_polars_simulation(self, test_vars: Dict) -> Tuple[bool, int]:
        """Run Polars-based simulation."""

        output_path = Path("/tmp/scale_test_polars")

        cmd = [
            "python", "navigator_orchestrator/polars_event_factory.py",
            "--start", str(test_vars['start_year']),
            "--end", str(test_vars['end_year']),
            "--out", str(output_path)
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        success = result.returncode == 0

        # Count events from summary
        events_count = 0
        if success:
            try:
                summary_file = output_path / "generation_summary.json"
                if summary_file.exists():
                    with open(summary_file) as f:
                        summary = json.load(f)
                        events_count = summary.get('total_events', 0)
            except Exception as e:
                self.logger.warning(f"Could not read event count: {e}")

        return success, events_count

    def run_scale_matrix(self) -> None:
        """Run the full scale testing matrix."""

        total_tests = (len(self.config.employee_counts) *
                      len(self.config.year_counts) *
                      len(self.config.shard_counts) *
                      self.config.iterations)

        self.logger.info(f"Starting scale matrix: {total_tests} total tests")

        test_num = 0
        for employee_count in self.config.employee_counts:
            for year_count in self.config.year_counts:
                for shard_count in self.config.shard_counts:
                    for iteration in range(self.config.iterations):
                        test_num += 1

                        self.logger.info(f"Test {test_num}/{total_tests}")

                        result = self.run_single_test(
                            employee_count, year_count, shard_count, iteration
                        )

                        self.results.append(result)

                        # Save intermediate results
                        self.save_results()

        self.logger.info("Scale matrix completed!")
        self.generate_report()

    def save_results(self) -> None:
        """Save results to JSON file."""
        results_file = self.config.output_dir / f"scale_results_{self.config.optimization_mode}.json"

        with open(results_file, 'w') as f:
            json.dump([asdict(r) for r in self.results], f, indent=2)

    def generate_report(self) -> None:
        """Generate scale testing report with visualizations."""

        df = pd.DataFrame([asdict(r) for r in self.results])

        # Calculate aggregate statistics
        summary_stats = df.groupby(['employee_count', 'year_count', 'shard_count']).agg({
            'wall_clock_time': ['mean', 'std', 'min', 'max'],
            'peak_memory_gb': ['mean', 'std', 'min', 'max'],
            'events_per_second': ['mean', 'std'],
            'completed_successfully': 'all'
        }).round(2)

        # Generate visualizations
        self._plot_scaling_characteristics(df)
        self._plot_memory_usage(df)
        self._plot_throughput(df)

        # Write report
        report_path = self.config.output_dir / f"scale_report_{self.config.optimization_mode}.md"

        with open(report_path, 'w') as f:
            f.write(f"# Scale Testing Report - {self.config.optimization_mode.title()} Mode\n\n")
            f.write(f"Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}\n\n")

            f.write("## Summary Statistics\n\n")
            f.write(summary_stats.to_markdown())
            f.write("\n\n")

            # Linear scaling analysis
            f.write("## Linear Scaling Analysis\n\n")
            scaling_analysis = self._analyze_linear_scaling(df)
            f.write(scaling_analysis)

            # Memory efficiency analysis
            f.write("## Memory Efficiency\n\n")
            memory_analysis = self._analyze_memory_efficiency(df)
            f.write(memory_analysis)

            # Performance recommendations
            f.write("## Recommendations\n\n")
            recommendations = self._generate_recommendations(df)
            f.write(recommendations)

        self.logger.info(f"Scale testing report generated: {report_path}")

    def _plot_scaling_characteristics(self, df: pd.DataFrame) -> None:
        """Plot scaling characteristics."""
        fig, axes = plt.subplots(2, 2, figsize=(15, 10))

        # Time vs employee count
        for year_count in df['year_count'].unique():
            subset = df[df['year_count'] == year_count].groupby('employee_count')['wall_clock_time'].mean()
            axes[0,0].plot(subset.index, subset.values, marker='o', label=f'{year_count} years')
        axes[0,0].set_xlabel('Employee Count')
        axes[0,0].set_ylabel('Wall Clock Time (s)')
        axes[0,0].set_title('Scaling: Time vs Employee Count')
        axes[0,0].legend()
        axes[0,0].grid(True)

        # Memory vs employee count
        for year_count in df['year_count'].unique():
            subset = df[df['year_count'] == year_count].groupby('employee_count')['peak_memory_gb'].mean()
            axes[0,1].plot(subset.index, subset.values, marker='s', label=f'{year_count} years')
        axes[0,1].set_xlabel('Employee Count')
        axes[0,1].set_ylabel('Peak Memory (GB)')
        axes[0,1].set_title('Scaling: Memory vs Employee Count')
        axes[0,1].legend()
        axes[0,1].grid(True)

        # Events per second
        throughput = df.groupby('employee_count')['events_per_second'].mean()
        axes[1,0].plot(throughput.index, throughput.values, marker='^', color='green')
        axes[1,0].set_xlabel('Employee Count')
        axes[1,0].set_ylabel('Events/Second')
        axes[1,0].set_title('Throughput Scaling')
        axes[1,0].grid(True)

        # Time per year scaling
        time_per_year = df.groupby('year_count')['time_per_year'].mean()
        axes[1,1].plot(time_per_year.index, time_per_year.values, marker='d', color='red')
        axes[1,1].set_xlabel('Year Count')
        axes[1,1].set_ylabel('Time per Year (s)')
        axes[1,1].set_title('Multi-Year Efficiency')
        axes[1,1].grid(True)

        plt.tight_layout()
        plt.savefig(self.config.output_dir / f"scaling_characteristics_{self.config.optimization_mode}.png", dpi=300)
        plt.close()

    def _analyze_linear_scaling(self, df: pd.DataFrame) -> str:
        """Analyze linear scaling properties."""

        # Check if time scales linearly with employee count
        from scipy.stats import linregress

        analysis = "Linear scaling analysis:\n\n"

        for year_count in sorted(df['year_count'].unique()):
            subset = df[df['year_count'] == year_count].groupby('employee_count')['wall_clock_time'].mean()

            if len(subset) >= 3:  # Need at least 3 points for regression
                slope, intercept, r_value, p_value, std_err = linregress(subset.index, subset.values)

                analysis += f"**{year_count} years:**\n"
                analysis += f"- R² = {r_value**2:.3f} (closer to 1.0 = more linear)\n"
                analysis += f"- Slope = {slope:.4f} seconds per employee\n"
                analysis += f"- P-value = {p_value:.4f} (< 0.05 = statistically significant)\n"

                if r_value**2 > 0.95:
                    analysis += "- ✅ Excellent linear scaling\n"
                elif r_value**2 > 0.90:
                    analysis += "- ✅ Good linear scaling\n"
                elif r_value**2 > 0.80:
                    analysis += "- ⚠️ Acceptable scaling with some non-linearity\n"
                else:
                    analysis += "- ❌ Poor linear scaling - investigate bottlenecks\n"

                analysis += "\n"

        return analysis

def main():
    """CLI entry point for scale testing."""
    import argparse

    parser = argparse.ArgumentParser(description="Scale testing framework")
    parser.add_argument('--mode', choices=['baseline', 'optimized', 'polars'],
                        default='optimized', help='Optimization mode to test')
    parser.add_argument('--employees', nargs='+', type=int, default=[1000, 5000, 20000],
                        help='Employee counts to test')
    parser.add_argument('--years', nargs='+', type=int, default=[1, 2, 5],
                        help='Year counts to test')
    parser.add_argument('--shards', nargs='+', type=int, default=[1, 4, 8],
                        help='Shard counts to test')
    parser.add_argument('--iterations', type=int, default=3,
                        help='Number of iterations per configuration')
    parser.add_argument('--output', type=Path, default=Path('scale_test_results'),
                        help='Output directory')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(level=logging.INFO)

    # Create and run scale test
    config = ScaleTestConfig(
        employee_counts=args.employees,
        year_counts=args.years,
        shard_counts=args.shards,
        optimization_mode=args.mode,
        iterations=args.iterations,
        output_dir=args.output
    )

    runner = ScaleTestRunner(config)
    runner.run_scale_matrix()

if __name__ == "__main__":
    main()
```

### Parity Testing Framework
```python
# scripts/parity_testing_framework.py
import subprocess
import json
import hashlib
from pathlib import Path
from typing import Dict, List, Any, Tuple
import pandas as pd
import logging

class ParityTester:
    """Test parity between legacy and optimized implementations."""

    def __init__(self, test_config: Dict[str, Any]):
        self.config = test_config
        self.logger = logging.getLogger(__name__)

    def run_parity_test(self) -> bool:
        """Run comprehensive parity test between implementations."""

        self.logger.info("Starting parity test...")

        # Run legacy implementation
        self.logger.info("Running legacy implementation...")
        legacy_results = self._run_legacy_simulation()

        # Run optimized implementation
        self.logger.info("Running optimized implementation...")
        optimized_results = self._run_optimized_simulation()

        # Compare results
        parity_passed = self._compare_results(legacy_results, optimized_results)

        # Generate report
        self._generate_parity_report(legacy_results, optimized_results, parity_passed)

        return parity_passed

    def _run_legacy_simulation(self) -> Dict[str, Any]:
        """Run simulation with legacy implementation."""

        # Set legacy mode flag
        env = os.environ.copy()
        env['FEATURE_FLAG_LEGACY_EVENTS'] = 'true'
        env['DBT_DEV_EMPLOYEE_LIMIT'] = str(self.config['employee_limit'])

        cmd = [
            "python", "-m", "navigator_orchestrator", "run",
            "--years", str(self.config['start_year']), str(self.config['end_year']),
            "--optimization", "legacy"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, env=env)

        if result.returncode != 0:
            raise RuntimeError(f"Legacy simulation failed: {result.stderr}")

        return self._extract_simulation_results('legacy')

    def _run_optimized_simulation(self) -> Dict[str, Any]:
        """Run simulation with optimized implementation."""

        # Clear legacy flag
        env = os.environ.copy()
        env.pop('FEATURE_FLAG_LEGACY_EVENTS', None)
        env['DBT_DEV_EMPLOYEE_LIMIT'] = str(self.config['employee_limit'])

        cmd = [
            "python", "-m", "navigator_orchestrator", "run",
            "--years", str(self.config['start_year']), str(self.config['end_year']),
            "--optimization", "high"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True, env=env)

        if result.returncode != 0:
            raise RuntimeError(f"Optimized simulation failed: {result.stderr}")

        return self._extract_simulation_results('optimized')

    def _extract_simulation_results(self, mode: str) -> Dict[str, Any]:
        """Extract simulation results from database."""

        import duckdb

        conn = duckdb.connect("dbt/simulation.duckdb")

        # Extract events
        events_query = """
        SELECT
          employee_id,
          event_type,
          event_date,
          simulation_year,
          hash(event_payload) as payload_hash
        FROM fct_yearly_events
        WHERE simulation_year BETWEEN ? AND ?
        ORDER BY employee_id, simulation_year, event_type, event_date
        """

        events = conn.execute(events_query, [
            self.config['start_year'],
            self.config['end_year']
        ]).fetchall()

        # Extract employee state
        state_query = """
        SELECT
          employee_id,
          simulation_year,
          is_active,
          hire_date,
          current_level,
          current_salary,
          is_enrolled,
          deferral_rate,
          account_balance
        FROM fct_workforce_snapshot
        WHERE simulation_year BETWEEN ? AND ?
        ORDER BY employee_id, simulation_year
        """

        state = conn.execute(state_query, [
            self.config['start_year'],
            self.config['end_year']
        ]).fetchall()

        conn.close()

        # Compute hashes for comparison
        events_hash = hashlib.sha256(str(events).encode()).hexdigest()
        state_hash = hashlib.sha256(str(state).encode()).hexdigest()

        return {
            'mode': mode,
            'events': events,
            'events_hash': events_hash,
            'events_count': len(events),
            'state': state,
            'state_hash': state_hash,
            'state_count': len(state)
        }

    def _compare_results(self, legacy: Dict, optimized: Dict) -> bool:
        """Compare legacy and optimized results for parity."""

        self.logger.info("Comparing simulation results...")

        parity_checks = []

        # Event count parity
        events_count_match = legacy['events_count'] == optimized['events_count']
        parity_checks.append(('event_count', events_count_match))
        self.logger.info(f"Event count - Legacy: {legacy['events_count']}, Optimized: {optimized['events_count']} {'✅' if events_count_match else '❌'}")

        # Event hash parity
        events_hash_match = legacy['events_hash'] == optimized['events_hash']
        parity_checks.append(('event_hash', events_hash_match))
        self.logger.info(f"Event hash match: {'✅' if events_hash_match else '❌'}")

        # State count parity
        state_count_match = legacy['state_count'] == optimized['state_count']
        parity_checks.append(('state_count', state_count_match))
        self.logger.info(f"State count - Legacy: {legacy['state_count']}, Optimized: {optimized['state_count']} {'✅' if state_count_match else '❌'}")

        # State hash parity
        state_hash_match = legacy['state_hash'] == optimized['state_hash']
        parity_checks.append(('state_hash', state_hash_match))
        self.logger.info(f"State hash match: {'✅' if state_hash_match else '❌'}")

        # Detailed comparison if hashes don't match
        if not events_hash_match:
            self._detailed_event_comparison(legacy['events'], optimized['events'])

        if not state_hash_match:
            self._detailed_state_comparison(legacy['state'], optimized['state'])

        all_passed = all(result for _, result in parity_checks)
        return all_passed

    def _detailed_event_comparison(self, legacy_events: List, optimized_events: List) -> None:
        """Perform detailed event-by-event comparison."""

        self.logger.warning("Events don't match - performing detailed comparison...")

        # Convert to dataframes for easier comparison
        legacy_df = pd.DataFrame(legacy_events, columns=['employee_id', 'event_type', 'event_date', 'simulation_year', 'payload_hash'])
        optimized_df = pd.DataFrame(optimized_events, columns=['employee_id', 'event_type', 'event_date', 'simulation_year', 'payload_hash'])

        # Find differences
        legacy_set = set(legacy_df.itertuples(index=False))
        optimized_set = set(optimized_df.itertuples(index=False))

        only_in_legacy = legacy_set - optimized_set
        only_in_optimized = optimized_set - legacy_set

        self.logger.warning(f"Events only in legacy: {len(only_in_legacy)}")
        for event in list(only_in_legacy)[:10]:  # Show first 10
            self.logger.warning(f"  {event}")

        self.logger.warning(f"Events only in optimized: {len(only_in_optimized)}")
        for event in list(only_in_optimized)[:10]:  # Show first 10
            self.logger.warning(f"  {event}")

def main():
    """CLI entry point for parity testing."""
    import argparse

    parser = argparse.ArgumentParser(description="Parity testing framework")
    parser.add_argument('--employees', type=int, default=1000, help='Employee limit for test')
    parser.add_argument('--start-year', type=int, default=2025, help='Start year')
    parser.add_argument('--end-year', type=int, default=2026, help='End year')
    parser.add_argument('--seed', type=int, default=12345, help='Random seed')

    args = parser.parse_args()

    # Setup logging
    logging.basicConfig(level=logging.INFO)

    # Run parity test
    config = {
        'employee_limit': args.employees,
        'start_year': args.start_year,
        'end_year': args.end_year,
        'random_seed': args.seed
    }

    tester = ParityTester(config)
    parity_passed = tester.run_parity_test()

    if parity_passed:
        print("✅ Parity test PASSED - optimized implementation matches legacy")
        exit(0)
    else:
        print("❌ Parity test FAILED - optimized implementation differs from legacy")
        exit(1)

if __name__ == "__main__":
    main()
```

### CI/CD Integration
```yaml
# .github/workflows/scale_parity_tests.yml
name: Scale and Parity Testing

on:
  pull_request:
    paths:
      - 'dbt/models/events/**'
      - 'dbt/models/state/**'
      - 'navigator_orchestrator/**'
      - 'scripts/scale_testing_framework.py'
      - 'scripts/parity_testing_framework.py'

jobs:
  parity-test:
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
    - uses: actions/checkout@v3

    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install dbt-duckdb duckdb polars pandas scipy matplotlib

    - name: Setup test environment
      run: |
        cd dbt
        dbt deps
        dbt seed --select census_data comp_levers --threads 1

    - name: Run parity test
      run: |
        python scripts/parity_testing_framework.py \
          --employees 1000 \
          --start-year 2025 \
          --end-year 2026 \
          --seed 42
      env:
        DBT_PROFILES_DIR: ${{ github.workspace }}/dbt

    - name: Upload parity results
      if: always()
      uses: actions/upload-artifact@v3
      with:
        name: parity-test-results
        path: parity_test_results/

  scale-test:
    runs-on: ubuntu-latest-16-cores  # Use high-spec runner
    timeout-minutes: 120
    if: contains(github.event.pull_request.labels.*.name, 'scale-test')

    strategy:
      matrix:
        mode: [baseline, optimized]

    steps:
    - uses: actions/checkout@v3

    - name: Setup Python
      uses: actions/setup-python@v4
      with:
        python-version: '3.11'

    - name: Install dependencies
      run: |
        pip install -r requirements.txt
        pip install dbt-duckdb duckdb polars pandas scipy matplotlib

    - name: Setup test environment
      run: |
        cd dbt
        dbt deps
        dbt seed --threads 4

    - name: Run scale test
      run: |
        python scripts/scale_testing_framework.py \
          --mode ${{ matrix.mode }} \
          --employees 1000 5000 \
          --years 1 3 \
          --shards 1 4 \
          --iterations 2 \
          --output scale_test_results_${{ matrix.mode }}

    - name: Upload scale results
      uses: actions/upload-artifact@v3
      with:
        name: scale-test-results-${{ matrix.mode }}
        path: scale_test_results_${{ matrix.mode }}/

  compare-scale-results:
    runs-on: ubuntu-latest
    needs: [scale-test]
    if: contains(github.event.pull_request.labels.*.name, 'scale-test')

    steps:
    - uses: actions/checkout@v3

    - name: Download scale results
      uses: actions/download-artifact@v3
      with:
        path: scale_results/

    - name: Compare performance
      run: |
        python scripts/compare_scale_results.py \
          --baseline scale_results/scale-test-results-baseline/ \
          --optimized scale_results/scale-test-results-optimized/ \
          --output performance_comparison.md

    - name: Comment PR with results
      uses: actions/github-script@v6
      with:
        script: |
          const fs = require('fs');
          const report = fs.readFileSync('performance_comparison.md', 'utf8');

          github.rest.issues.createComment({
            issue_number: context.issue.number,
            owner: context.repo.owner,
            repo: context.repo.repo,
            body: `## Scale Test Results\n\n${report}`
          });
```

### Rollback Plan Documentation
```bash
# scripts/rollback_plan.sh
#!/bin/bash

# E068 Optimization Rollback Plan
# Usage: ./scripts/rollback_plan.sh [validate|execute]

set -euo pipefail

ROLLBACK_TAG="pre-E068-optimization"
FEATURE_FLAG="FEATURE_FLAG_LEGACY_EVENTS=true"
BACKUP_DIR="rollback_backup_$(date +%Y%m%d_%H%M%S)"

validate_rollback() {
    echo "🔍 Validating rollback readiness..."

    # Check if rollback tag exists
    if ! git tag | grep -q "$ROLLBACK_TAG"; then
        echo "❌ Rollback tag '$ROLLBACK_TAG' not found"
        echo "   Create tag before E068 implementation: git tag $ROLLBACK_TAG <commit-hash>"
        exit 1
    fi

    # Check current branch
    current_branch=$(git rev-parse --abbrev-ref HEAD)
    if [[ "$current_branch" != "main" ]]; then
        echo "⚠️  Current branch: $current_branch (should be 'main' for production rollback)"
    fi

    # Check for uncommitted changes
    if ! git diff --quiet; then
        echo "⚠️  Uncommitted changes detected - will be lost during rollback"
        git status --short
        read -p "Continue? (y/N): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi

    # Test legacy mode functionality
    echo "🧪 Testing legacy mode..."
    export $FEATURE_FLAG

    # Run quick validation simulation
    cd dbt
    timeout 300 dbt run --select stg_census_data int_baseline_workforce --threads 1 --vars '{"simulation_year": 2025, "dev_employee_limit": 100}' || {
        echo "❌ Legacy mode test failed"
        exit 1
    }
    cd ..

    echo "✅ Rollback validation passed"
}

execute_rollback() {
    echo "🚨 Executing E068 optimization rollback..."

    # Create backup of current state
    echo "📦 Creating backup..."
    mkdir -p "$BACKUP_DIR"

    # Backup database
    if [[ -f "dbt/simulation.duckdb" ]]; then
        cp "dbt/simulation.duckdb" "$BACKUP_DIR/"
        echo "   Database backed up"
    fi

    # Backup configuration
    cp -r "config/" "$BACKUP_DIR/"
    cp -r "dbt/models/" "$BACKUP_DIR/"
    echo "   Configuration backed up to $BACKUP_DIR"

    # Checkout rollback tag
    echo "⏪ Rolling back to $ROLLBACK_TAG..."
    git checkout "$ROLLBACK_TAG"

    # Set legacy mode environment
    echo "🏳️  Enabling legacy mode..."

    # Create environment file for persistent flag
    cat > .env.rollback << EOF
# E068 Rollback - Legacy Mode Active
$FEATURE_FLAG
DBT_OPTIMIZATION_MODE=legacy
ROLLBACK_ACTIVE=true
ROLLBACK_TIMESTAMP=$(date -Iseconds)
EOF

    # Update configuration to use legacy paths
    if [[ -f "config/simulation_config.yaml" ]]; then
        # Backup current config
        cp "config/simulation_config.yaml" "config/simulation_config.yaml.pre-rollback"

        # Restore legacy configuration
        sed -i 's/use_optimized_events: true/use_optimized_events: false/g' config/simulation_config.yaml
        sed -i 's/event_generation_mode: "optimized"/event_generation_mode: "legacy"/g' config/simulation_config.yaml
    fi

    # Rebuild with legacy models
    echo "🔨 Rebuilding with legacy implementation..."
    cd dbt

    # Clean optimized models
    dbt run --select models --full-refresh --threads 1

    cd ..

    # Verification test
    echo "✅ Running rollback verification..."
    export $FEATURE_FLAG
    python -m navigator_orchestrator run --years 2025 --optimization legacy --dry-run

    echo "🎯 Rollback completed successfully!"
    echo ""
    echo "Next steps:"
    echo "1. Verify application functionality"
    echo "2. Monitor performance (expect ~2× slower execution)"
    echo "3. Plan forward-fix deployment"
    echo "4. Restore from backup when ready: cp $BACKUP_DIR/* ./"
    echo ""
    echo "To restore optimization:"
    echo "  git checkout main"
    echo "  rm .env.rollback"
    echo "  source .env  # Re-enable optimized mode"
}

show_usage() {
    echo "Usage: $0 [validate|execute]"
    echo ""
    echo "Commands:"
    echo "  validate  - Check rollback readiness (safe, no changes)"
    echo "  execute   - Perform actual rollback (destructive)"
    echo ""
    echo "Environment:"
    echo "  Rollback tag: $ROLLBACK_TAG"
    echo "  Feature flag: $FEATURE_FLAG"
}

# Main execution
case "${1:-}" in
    validate)
        validate_rollback
        ;;
    execute)
        validate_rollback  # Always validate first
        echo ""
        echo "⚠️  This will rollback E068 optimizations and may result in data loss."
        read -p "Are you sure you want to proceed? Type 'ROLLBACK' to confirm: " confirmation
        if [[ "$confirmation" == "ROLLBACK" ]]; then
            execute_rollback
        else
            echo "Rollback cancelled"
            exit 1
        fi
        ;;
    *)
        show_usage
        exit 1
        ;;
esac
```

## Success Metrics
- Linear scaling: R² > 0.90 for time vs employee count relationships
- Memory efficiency: Peak RSS ≤ 40GB for 50k employee simulations
- CI integration: Parity tests pass automatically on all optimization PRs
- Rollback capability: <10 minute rollback time validated on staging environment
- Performance verification: Optimized mode delivers target 2× improvement vs baseline

## Dependencies
- GitHub Actions with high-spec runners (16 vCPU, 64GB RAM)
- Statistical analysis libraries (scipy, pandas, matplotlib)
- Git tagging strategy for rollback points
- Feature flag infrastructure for legacy mode toggle

## Risk Mitigation
- **CI resource usage**: Use labels to trigger expensive scale tests only when needed
- **Rollback complexity**: Automated rollback scripts with validation
- **False positive parity failures**: Detailed diff reporting for root cause analysis
- **Performance regression detection**: Automated alerts on significant degradation

---

**Epic**: E068H
**Parent Epic**: E068 - Database Query Optimization
**Status**: 🔴 NOT STARTED
**Priority**: High (Required for safe deployment)
**Estimated Effort**: 4 story points
**Target Performance**: Prove linear scaling and deployment safety
