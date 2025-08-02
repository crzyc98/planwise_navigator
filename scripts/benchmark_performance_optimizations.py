#!/usr/bin/env python3
"""
Performance Optimization Benchmark Script.

This script validates the 82% performance improvement target by:
1. Running baseline performance tests
2. Running optimized performance tests
3. Comparing results and calculating improvement percentages
4. Generating comprehensive performance reports

Usage:
    python scripts/benchmark_performance_optimizations.py [--baseline-only] [--optimized-only] [--full-benchmark]
"""

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Dict, List, Any, Optional

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from orchestrator_mvp.core.optimized_multi_year_engine import create_optimized_multi_year_engine
from orchestrator_mvp.core.database_manager import clear_database, get_connection
from orchestrator_mvp.core.duckdb_optimizations import apply_duckdb_optimizations
from orchestrator_mvp.utils.dbt_batch_executor import create_optimized_dbt_executor


class PerformanceBenchmark:
    """Comprehensive performance benchmarking system."""

    def __init__(self, dbt_project_path: str, simulation_years: List[int]):
        self.dbt_project_path = Path(dbt_project_path)
        self.simulation_years = simulation_years
        self.benchmark_results = {
            "baseline": {},
            "optimized": {},
            "comparison": {},
            "system_info": {}
        }

        self._collect_system_info()

    def _collect_system_info(self):
        """Collect system information for benchmark context."""
        import psutil

        self.benchmark_results["system_info"] = {
            "cpu_count": os.cpu_count(),
            "memory_gb": round(psutil.virtual_memory().total / (1024**3), 1),
            "python_version": sys.version,
            "platform": sys.platform,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
        }

    def run_baseline_benchmark(self) -> Dict[str, Any]:
        """Run baseline performance benchmark without optimizations."""
        print("🔍 Running Baseline Performance Benchmark")
        print("=" * 50)

        baseline_results = {
            "foundation_setup_ms": 0,
            "year_processing_ms": 0,
            "total_simulation_ms": 0,
            "operations": {},
            "errors": []
        }

        simulation_start = time.perf_counter()

        try:
            # Foundation Setup Baseline
            print("1️⃣  Baseline Foundation Setup...")
            foundation_start = time.perf_counter()

            # Clear database without optimizations
            clear_database()

            # Load seeds without optimization
            self._run_dbt_command(["dbt", "seed", "--full-refresh"])

            # Build staging models sequentially
            self._run_dbt_command(["dbt", "run", "--models", "stg_census_data"])

            foundation_time = (time.perf_counter() - foundation_start) * 1000
            baseline_results["foundation_setup_ms"] = foundation_time
            baseline_results["operations"]["foundation_setup"] = foundation_time

            print(f"    ⏱️  Foundation setup: {foundation_time:.0f}ms ({foundation_time/1000:.1f}s)")

            # Year Processing Baseline
            print("2️⃣  Baseline Year Processing...")
            year_times = []

            for year in self.simulation_years[:2]:  # Test with first 2 years for baseline
                year_start = time.perf_counter()

                # Set year variable
                os.environ["DBT_SIMULATION_YEAR"] = str(year)

                # Run intermediate models sequentially
                intermediate_models = [
                    "int_baseline_workforce",
                    "int_employee_compensation_by_year",
                    "int_enrollment_events",
                    "int_workforce_active_for_events"
                ]

                for model in intermediate_models:
                    self._run_dbt_command(["dbt", "run", "--models", model])

                # Run marts models
                marts_models = ["fct_yearly_events", "fct_workforce_snapshot"]
                for model in marts_models:
                    self._run_dbt_command(["dbt", "run", "--models", model])

                year_time = (time.perf_counter() - year_start) * 1000
                year_times.append(year_time)

                print(f"    📅 Year {year}: {year_time:.0f}ms ({year_time/1000/60:.1f}min)")

            avg_year_time = sum(year_times) / len(year_times) if year_times else 0
            baseline_results["year_processing_ms"] = avg_year_time
            baseline_results["operations"]["year_processing"] = avg_year_time

        except Exception as e:
            baseline_results["errors"].append(f"Baseline benchmark error: {str(e)}")
            print(f"    ❌ Baseline benchmark failed: {e}")

        total_time = (time.perf_counter() - simulation_start) * 1000
        baseline_results["total_simulation_ms"] = total_time

        print(f"\n📊 Baseline Benchmark Results:")
        print(f"  🏗️  Foundation Setup: {baseline_results['foundation_setup_ms']:.0f}ms")
        print(f"  📅 Avg Year Processing: {baseline_results['year_processing_ms']:.0f}ms")
        print(f"  ⏱️  Total Time: {total_time:.0f}ms ({total_time/1000:.1f}s)")

        self.benchmark_results["baseline"] = baseline_results
        return baseline_results

    def run_optimized_benchmark(self) -> Dict[str, Any]:
        """Run optimized performance benchmark with all optimizations."""
        print("\n🚀 Running Optimized Performance Benchmark")
        print("=" * 50)

        optimized_results = {
            "foundation_setup_ms": 0,
            "year_processing_ms": 0,
            "total_simulation_ms": 0,
            "operations": {},
            "compression_stats": {},
            "errors": []
        }

        simulation_start = time.perf_counter()

        try:
            # Create optimized engine
            baseline_metrics = self.benchmark_results.get("baseline", {}).get("operations", {})

            engine = create_optimized_multi_year_engine(
                dbt_project_path=str(self.dbt_project_path),
                simulation_years=self.simulation_years[:2],  # Test with first 2 years
                baseline_metrics=baseline_metrics,
                pool_size=4
            )

            # Run optimized foundation setup
            print("1️⃣  Optimized Foundation Setup...")
            foundation_result = engine.execute_foundation_setup_optimized()

            optimized_results["foundation_setup_ms"] = foundation_result.get("execution_time_ms", 0)
            optimized_results["operations"]["foundation_setup"] = foundation_result.get("execution_time_ms", 0)

            print(f"    ⏱️  Foundation setup: {foundation_result.get('execution_time_ms', 0):.0f}ms")
            print(f"    🎯 Improvement: {foundation_result.get('performance_improvement', 0):.1f}%")

            # Run optimized year processing
            print("2️⃣  Optimized Year Processing...")
            year_times = []
            compression_ratios = []

            previous_year_data = None
            for year in self.simulation_years[:2]:
                year_result = engine.execute_year_processing_optimized(year, previous_year_data)

                year_time = year_result.get("execution_time_ms", 0)
                year_times.append(year_time)
                compression_ratios.append(year_result.get("state_compression_ratio", 0))

                print(f"    📅 Year {year}: {year_time:.0f}ms ({year_time/1000/60:.1f}min)")
                print(f"    🗜️  Compression: {year_result.get('state_compression_ratio', 0):.1f}x")
                print(f"    🎯 Improvement: {year_result.get('performance_improvement', 0):.1f}%")

                previous_year_data = engine._get_compressed_year_data(year)

            avg_year_time = sum(year_times) / len(year_times) if year_times else 0
            avg_compression = sum(compression_ratios) / len(compression_ratios) if compression_ratios else 0

            optimized_results["year_processing_ms"] = avg_year_time
            optimized_results["operations"]["year_processing"] = avg_year_time
            optimized_results["compression_stats"]["avg_compression_ratio"] = avg_compression

            # Cleanup
            engine.cleanup()

        except Exception as e:
            optimized_results["errors"].append(f"Optimized benchmark error: {str(e)}")
            print(f"    ❌ Optimized benchmark failed: {e}")

        total_time = (time.perf_counter() - simulation_start) * 1000
        optimized_results["total_simulation_ms"] = total_time

        print(f"\n📊 Optimized Benchmark Results:")
        print(f"  🏗️  Foundation Setup: {optimized_results['foundation_setup_ms']:.0f}ms")
        print(f"  📅 Avg Year Processing: {optimized_results['year_processing_ms']:.0f}ms")
        print(f"  🗜️  Avg Compression: {optimized_results['compression_stats'].get('avg_compression_ratio', 0):.1f}x")
        print(f"  ⏱️  Total Time: {total_time:.0f}ms ({total_time/1000:.1f}s)")

        self.benchmark_results["optimized"] = optimized_results
        return optimized_results

    def calculate_performance_comparison(self) -> Dict[str, Any]:
        """Calculate comprehensive performance comparison."""
        print("\n📈 Calculating Performance Comparison")
        print("=" * 50)

        baseline = self.benchmark_results.get("baseline", {})
        optimized = self.benchmark_results.get("optimized", {})

        if not baseline or not optimized:
            print("❌ Cannot calculate comparison - missing baseline or optimized results")
            return {}

        comparison_results = {
            "foundation_setup": {},
            "year_processing": {},
            "total_simulation": {},
            "overall_improvement": 0.0,
            "target_achievement": "Unknown"
        }

        # Calculate improvements for each operation
        operations = ["foundation_setup_ms", "year_processing_ms", "total_simulation_ms"]
        operation_names = ["foundation_setup", "year_processing", "total_simulation"]

        for op, name in zip(operations, operation_names):
            baseline_time = baseline.get(op, 0)
            optimized_time = optimized.get(op, 0)

            if baseline_time > 0:
                improvement = ((baseline_time - optimized_time) / baseline_time) * 100
                speedup = baseline_time / optimized_time if optimized_time > 0 else 0

                comparison_results[name] = {
                    "baseline_ms": baseline_time,
                    "optimized_ms": optimized_time,
                    "improvement_percent": improvement,
                    "speedup_factor": speedup,
                    "time_saved_ms": baseline_time - optimized_time
                }

                print(f"🔍 {name.replace('_', ' ').title()}:")
                print(f"    📊 Baseline: {baseline_time:.0f}ms")
                print(f"    ⚡ Optimized: {optimized_time:.0f}ms")
                print(f"    🎯 Improvement: {improvement:.1f}%")
                print(f"    📈 Speedup: {speedup:.1f}x")
                print(f"    💾 Time Saved: {(baseline_time - optimized_time):.0f}ms")
                print()

        # Calculate overall improvement
        baseline_total = baseline.get("total_simulation_ms", 0)
        optimized_total = optimized.get("total_simulation_ms", 0)

        if baseline_total > 0:
            overall_improvement = ((baseline_total - optimized_total) / baseline_total) * 100
            comparison_results["overall_improvement"] = overall_improvement

            # Determine target achievement
            if overall_improvement >= 82:
                comparison_results["target_achievement"] = "✅ Target Achieved (82%+)"
                achievement_status = "TARGET ACHIEVED"
            elif overall_improvement >= 50:
                comparison_results["target_achievement"] = "🔶 Significant Improvement"
                achievement_status = "SIGNIFICANT IMPROVEMENT"
            else:
                comparison_results["target_achievement"] = "⚠️ Below Target"
                achievement_status = "BELOW TARGET"

            print(f"🏆 Overall Performance Achievement:")
            print(f"    📈 Total Improvement: {overall_improvement:.1f}%")
            print(f"    🎯 Target (82%): {achievement_status}")
            print(f"    ⏱️  Total Time Saved: {(baseline_total - optimized_total)/1000:.1f}s")

            # Additional insights
            if overall_improvement >= 82:
                print(f"    🎉 Congratulations! Performance target exceeded!")
            elif overall_improvement >= 70:
                print(f"    🔶 Very close to target - additional optimizations may reach 82%")
            else:
                print(f"    💡 Consider additional optimization strategies")

        self.benchmark_results["comparison"] = comparison_results
        return comparison_results

    def generate_performance_report(self) -> str:
        """Generate comprehensive performance report."""
        report_lines = [
            "🚀 PlanWise Navigator Performance Optimization Report",
            "=" * 60,
            f"📅 Benchmark Date: {self.benchmark_results['system_info']['timestamp']}",
            f"💻 System: {self.benchmark_results['system_info']['cpu_count']} CPUs, "
            f"{self.benchmark_results['system_info']['memory_gb']}GB RAM",
            f"📁 dbt Project: {self.dbt_project_path}",
            f"🗓️  Test Years: {len(self.simulation_years)} years ({min(self.simulation_years)}-{max(self.simulation_years)})",
            "",
            "📊 PERFORMANCE COMPARISON",
            "-" * 30
        ]

        comparison = self.benchmark_results.get("comparison", {})

        if comparison:
            # Foundation Setup
            foundation = comparison.get("foundation_setup", {})
            if foundation:
                report_lines.extend([
                    "🏗️  Foundation Setup:",
                    f"    Baseline:    {foundation['baseline_ms']:.0f}ms ({foundation['baseline_ms']/1000:.1f}s)",
                    f"    Optimized:   {foundation['optimized_ms']:.0f}ms ({foundation['optimized_ms']/1000:.1f}s)",
                    f"    Improvement: {foundation['improvement_percent']:.1f}% ({foundation['speedup_factor']:.1f}x faster)",
                    ""
                ])

            # Year Processing
            year_proc = comparison.get("year_processing", {})
            if year_proc:
                report_lines.extend([
                    "📅 Year Processing:",
                    f"    Baseline:    {year_proc['baseline_ms']:.0f}ms ({year_proc['baseline_ms']/1000/60:.1f}min)",
                    f"    Optimized:   {year_proc['optimized_ms']:.0f}ms ({year_proc['optimized_ms']/1000/60:.1f}min)",
                    f"    Improvement: {year_proc['improvement_percent']:.1f}% ({year_proc['speedup_factor']:.1f}x faster)",
                    ""
                ])

            # Overall Results
            report_lines.extend([
                "🎯 OVERALL ACHIEVEMENT",
                "-" * 25,
                f"📈 Total Performance Improvement: {comparison['overall_improvement']:.1f}%",
                f"🏆 Target Achievement: {comparison['target_achievement']}",
                f"⏱️  Total Time Saved: {comparison.get('total_simulation', {}).get('time_saved_ms', 0)/1000:.1f}s",
                ""
            ])

            # Recommendations
            improvement = comparison['overall_improvement']
            report_lines.extend([
                "💡 RECOMMENDATIONS",
                "-" * 20
            ])

            if improvement >= 82:
                report_lines.extend([
                    "✅ Performance target achieved! Consider:",
                    "   • Monitoring production performance",
                    "   • Scaling optimizations to larger datasets",
                    "   • Documenting optimization strategies"
                ])
            elif improvement >= 70:
                report_lines.extend([
                    "🔶 Very close to target! Consider:",
                    "   • Fine-tuning DuckDB memory settings",
                    "   • Additional query optimization",
                    "   • Hardware-specific optimizations"
                ])
            else:
                report_lines.extend([
                    "⚠️ Additional optimization needed:",
                    "   • Review query execution plans",
                    "   • Consider hardware upgrades",
                    "   • Analyze bottleneck operations",
                    "   • Implement additional caching strategies"
                ])

        report_lines.extend([
            "",
            "=" * 60,
            "📋 Report generated by PlanWise Navigator Performance Benchmark"
        ])

        return "\n".join(report_lines)

    def save_results(self, output_file: str):
        """Save benchmark results to JSON file."""
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        with open(output_path, 'w') as f:
            json.dump(self.benchmark_results, f, indent=2)

        print(f"📁 Benchmark results saved to: {output_path}")

    def _run_dbt_command(self, cmd: List[str], timeout: int = 300):
        """Run dbt command with timeout."""
        import subprocess

        try:
            result = subprocess.run(
                cmd,
                cwd=self.dbt_project_path,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=True
            )
            return result
        except subprocess.CalledProcessError as e:
            print(f"    ⚠️ Command failed: {' '.join(cmd)}")
            print(f"    Error: {e.stderr}")
            raise
        except subprocess.TimeoutExpired:
            print(f"    ⏰ Command timed out: {' '.join(cmd)}")
            raise


def main():
    """Main benchmark execution function."""
    parser = argparse.ArgumentParser(description="Performance Optimization Benchmark")
    parser.add_argument("--baseline-only", action="store_true", help="Run only baseline benchmark")
    parser.add_argument("--optimized-only", action="store_true", help="Run only optimized benchmark")
    parser.add_argument("--full-benchmark", action="store_true", help="Run complete benchmark suite")
    parser.add_argument("--dbt-project", default="dbt", help="Path to dbt project")
    parser.add_argument("--years", nargs="+", type=int, default=[2024, 2025, 2026], help="Simulation years")
    parser.add_argument("--output", default="benchmark_results.json", help="Output file for results")

    args = parser.parse_args()

    # Default to full benchmark if no specific option is provided
    if not (args.baseline_only or args.optimized_only or args.full_benchmark):
        args.full_benchmark = True

    print("🚀 PlanWise Navigator Performance Benchmark")
    print("=" * 60)
    print(f"📁 dbt Project: {args.dbt_project}")
    print(f"📅 Test Years: {args.years}")
    print(f"📊 Output: {args.output}")
    print()

    # Initialize benchmark
    benchmark = PerformanceBenchmark(args.dbt_project, args.years)

    try:
        # Run baseline benchmark
        if args.baseline_only or args.full_benchmark:
            benchmark.run_baseline_benchmark()

        # Run optimized benchmark
        if args.optimized_only or args.full_benchmark:
            benchmark.run_optimized_benchmark()

        # Calculate comparison if we have both results
        if args.full_benchmark or (args.baseline_only and args.optimized_only):
            benchmark.calculate_performance_comparison()

        # Generate and display report
        report = benchmark.generate_performance_report()
        print(f"\n{report}")

        # Save results
        benchmark.save_results(args.output)

        # Print final summary
        comparison = benchmark.benchmark_results.get("comparison", {})
        if comparison:
            improvement = comparison.get("overall_improvement", 0)
            if improvement >= 82:
                print(f"\n🎉 SUCCESS: {improvement:.1f}% improvement achieved! (Target: 82%)")
                sys.exit(0)
            else:
                print(f"\n⚠️ PARTIAL: {improvement:.1f}% improvement (Target: 82%)")
                sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n⏹️  Benchmark interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n❌ Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
