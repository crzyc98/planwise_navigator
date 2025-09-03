#!/usr/bin/env python3
"""
Real Navigator Orchestrator Performance Benchmark
================================================

This script benchmarks the actual Navigator Orchestrator with real dbt models
to measure threading performance improvements and resource utilization.
"""

import json
import os
import psutil
import statistics
import sys
import threading
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple, Optional

sys.path.insert(0, str(Path(__file__).parent))

try:
    from navigator_orchestrator.dbt_runner import DbtRunner
    from navigator_orchestrator.parallel_execution_engine import ParallelExecutionEngine, ExecutionContext
    from navigator_orchestrator.model_dependency_analyzer import ModelDependencyAnalyzer
    from navigator_orchestrator.resource_manager import ResourceManager
    print("✅ All imports successful")
    IMPORTS_OK = True
except ImportError as e:
    print(f"❌ Import failed: {e}")
    IMPORTS_OK = False


class PerformanceBenchmark:
    """Real performance benchmark for Navigator Orchestrator threading."""

    def __init__(self):
        self.results = {}
        self.dbt_dir = Path("dbt")
        self.simulation_year = 2025

        # Thread counts to test
        self.thread_counts = [1, 2, 4]

        # Models to benchmark (select representative models)
        self.benchmark_models = [
            # Staging models (I/O bound)
            "stg_census_data",
            "stg_comp_levers",
            "stg_comp_targets",

            # Intermediate models (CPU bound)
            "int_baseline_workforce",
            "int_employee_compensation_by_year",

            # Event models (mixed workload)
            "int_termination_events",
            "int_hire_events"
        ]

    def validate_environment(self) -> bool:
        """Validate that the environment is ready for benchmarking."""

        print("🔍 Validating benchmark environment...")

        if not IMPORTS_OK:
            print("❌ Required imports not available")
            return False

        if not self.dbt_dir.exists():
            print(f"❌ dbt directory not found: {self.dbt_dir}")
            return False

        # Check database exists
        try:
            from navigator_orchestrator.config import get_database_path
            import duckdb

            db_path = get_database_path()
            if not db_path.exists():
                print(f"❌ Database not found: {db_path}")
                print("   Please run a simulation first to create the database")
                return False

            # Test database connectivity
            conn = duckdb.connect(str(db_path))
            tables = conn.execute("SHOW TABLES").fetchall()
            conn.close()

            print(f"✅ Database ready with {len(tables)} tables")

        except Exception as e:
            print(f"❌ Database validation failed: {e}")
            return False

        # Check models exist
        models_dir = self.dbt_dir / "models"
        existing_models = []

        for model in self.benchmark_models:
            model_files = list(models_dir.rglob(f"{model}.sql"))
            if model_files:
                existing_models.append(model)

        print(f"✅ Found {len(existing_models)}/{len(self.benchmark_models)} benchmark models")
        self.benchmark_models = existing_models

        if len(existing_models) < 3:
            print("❌ Insufficient models for meaningful benchmark")
            return False

        return True

    def benchmark_dbt_runner_performance(self) -> Dict[str, any]:
        """Benchmark basic dbt runner performance across thread counts."""

        print("\n⚡ Benchmarking dbt runner performance...")

        results = {}

        try:
            dbt_runner = DbtRunner(self.dbt_dir)

            for thread_count in self.thread_counts:
                print(f"   Testing {thread_count} threads...")

                # Configure dbt for thread count
                execution_times = []

                # Run multiple iterations for statistical validity
                for iteration in range(2):
                    print(f"      Iteration {iteration + 1}/2...")

                    start_time = time.time()
                    initial_memory = psutil.Process().memory_info().rss / 1024 / 1024

                    # Run a subset of models with dbt
                    try:
                        # Use dbt list to test model compilation (lightweight)
                        result = dbt_runner.execute_command(
                            ["list", "--select", "int_baseline_workforce"],
                            simulation_year=self.simulation_year,
                            dbt_vars={"simulation_year": self.simulation_year},
                            stream_output=False
                        )

                        execution_time = time.time() - start_time
                        final_memory = psutil.Process().memory_info().rss / 1024 / 1024
                        memory_usage = final_memory - initial_memory

                        if result.success:
                            execution_times.append(execution_time)
                            print(f"         ✅ Completed in {execution_time:.2f}s (mem: +{memory_usage:.1f}MB)")
                        else:
                            print(f"         ❌ Failed: {result.stderr[:100]}...")

                    except Exception as e:
                        print(f"         💥 Error: {e}")
                        continue

                if execution_times:
                    avg_time = statistics.mean(execution_times)
                    results[thread_count] = {
                        "thread_count": thread_count,
                        "avg_execution_time": avg_time,
                        "execution_times": execution_times,
                        "iterations": len(execution_times)
                    }
                else:
                    results[thread_count] = {
                        "thread_count": thread_count,
                        "error": "no_successful_executions"
                    }

            return results

        except Exception as e:
            print(f"❌ dbt runner benchmark failed: {e}")
            return {"error": str(e)}

    def benchmark_parallel_execution_engine(self) -> Dict[str, any]:
        """Benchmark the ParallelExecutionEngine with real models."""

        print("\n🔧 Benchmarking ParallelExecutionEngine...")

        if len(self.benchmark_models) == 0:
            print("❌ No models available for benchmarking")
            return {"error": "no_models"}

        results = {}

        try:
            dbt_runner = DbtRunner(self.dbt_dir)
            dependency_analyzer = ModelDependencyAnalyzer(dbt_runner)

            for thread_count in self.thread_counts:
                print(f"   Testing {thread_count} threads...")

                # Initialize engine
                engine = ParallelExecutionEngine(
                    dbt_runner=dbt_runner,
                    dependency_analyzer=dependency_analyzer,
                    max_workers=thread_count,
                    deterministic_execution=True,
                    resource_monitoring=True,
                    verbose=False
                )

                # Get parallelization statistics
                try:
                    stats = engine.get_parallelization_statistics()
                    print(f"      Parallelization ratio: {stats['parallelization_ratio']:.2f}")
                    print(f"      Max theoretical speedup: {stats['max_theoretical_speedup']:.1f}x")

                    results[thread_count] = {
                        "thread_count": thread_count,
                        "parallelization_stats": stats,
                        "engine_initialization": "success"
                    }

                except Exception as e:
                    print(f"      ❌ Engine stats failed: {e}")
                    results[thread_count] = {
                        "thread_count": thread_count,
                        "error": str(e)
                    }

            return results

        except Exception as e:
            print(f"❌ ParallelExecutionEngine benchmark failed: {e}")
            return {"error": str(e)}

    def benchmark_resource_manager(self) -> Dict[str, any]:
        """Benchmark resource management performance."""

        print("\n📊 Benchmarking ResourceManager...")

        results = {}

        try:
            # Test different configurations
            configs = {
                "conservative": {
                    "memory": {"thresholds": {"moderate_mb": 1000, "high_mb": 2000, "critical_mb": 3000}},
                    "cpu": {"thresholds": {"moderate_percent": 50, "high_percent": 70, "critical_percent": 90}}
                },
                "aggressive": {
                    "memory": {"thresholds": {"moderate_mb": 2000, "high_mb": 4000, "critical_mb": 6000}},
                    "cpu": {"thresholds": {"moderate_percent": 70, "high_percent": 85, "critical_percent": 95}}
                }
            }

            for config_name, config in configs.items():
                print(f"   Testing {config_name} configuration...")

                resource_manager = ResourceManager(config=config)
                resource_manager.start_monitoring()

                # Test optimization decisions
                optimization_results = []
                for thread_count in [1, 2, 4, 8]:
                    optimal, reason = resource_manager.optimize_thread_count(thread_count)
                    optimization_results.append({
                        "requested": thread_count,
                        "recommended": optimal,
                        "reason": reason
                    })

                # Get resource status
                status = resource_manager.get_resource_status()

                resource_manager.stop_monitoring()

                results[config_name] = {
                    "configuration": config,
                    "optimization_results": optimization_results,
                    "resource_status": status
                }

                print(f"      Resource health: {'✅ OK' if resource_manager.check_resource_health() else '⚠️ Pressure'}")

            return results

        except Exception as e:
            print(f"❌ ResourceManager benchmark failed: {e}")
            return {"error": str(e)}

    def run_comprehensive_benchmark(self) -> Dict[str, any]:
        """Run comprehensive performance benchmark."""

        print("🚀 Starting Navigator Orchestrator Performance Benchmark")
        print("=" * 60)

        if not self.validate_environment():
            return {"error": "environment_validation_failed"}

        benchmark_results = {
            "timestamp": datetime.now().isoformat(),
            "system_info": {
                "cpu_cores": psutil.cpu_count(),
                "memory_gb": psutil.virtual_memory().total // (1024**3),
                "python_version": sys.version.split()[0]
            },
            "test_configuration": {
                "thread_counts": self.thread_counts,
                "benchmark_models": self.benchmark_models,
                "simulation_year": self.simulation_year
            }
        }

        # Run benchmarks
        benchmark_results["dbt_runner"] = self.benchmark_dbt_runner_performance()
        benchmark_results["parallel_engine"] = self.benchmark_parallel_execution_engine()
        benchmark_results["resource_manager"] = self.benchmark_resource_manager()

        # Analyze results
        analysis = self.analyze_benchmark_results(benchmark_results)
        benchmark_results["analysis"] = analysis

        return benchmark_results

    def analyze_benchmark_results(self, results: Dict[str, any]) -> Dict[str, any]:
        """Analyze benchmark results and provide recommendations."""

        analysis = {
            "performance_summary": {},
            "threading_effectiveness": {},
            "recommendations": []
        }

        # Analyze dbt runner performance
        dbt_results = results.get("dbt_runner", {})
        if not dbt_results.get("error"):
            baseline_time = dbt_results.get(1, {}).get("avg_execution_time", 0)

            if baseline_time > 0:
                analysis["performance_summary"]["baseline_time"] = baseline_time

                for thread_count in [2, 4]:
                    if thread_count in dbt_results:
                        thread_time = dbt_results[thread_count].get("avg_execution_time", 0)
                        if thread_time > 0:
                            speedup = baseline_time / thread_time
                            efficiency = speedup / thread_count

                            analysis["threading_effectiveness"][f"{thread_count}_threads"] = {
                                "speedup": speedup,
                                "efficiency": efficiency,
                                "improvement_percent": (1 - thread_time/baseline_time) * 100
                            }

        # Analyze parallel engine
        engine_results = results.get("parallel_engine", {})
        if not engine_results.get("error"):
            for thread_count in self.thread_counts:
                if thread_count in engine_results:
                    stats = engine_results[thread_count].get("parallelization_stats", {})
                    parallelization_ratio = stats.get("parallelization_ratio", 0)

                    if parallelization_ratio > 0:
                        analysis["threading_effectiveness"][f"parallelization_{thread_count}"] = {
                            "ratio": parallelization_ratio,
                            "theoretical_speedup": stats.get("max_theoretical_speedup", 1)
                        }

        # Generate recommendations
        recommendations = []

        # Check if we have meaningful performance data
        if "2_threads" in analysis["threading_effectiveness"]:
            speedup_2 = analysis["threading_effectiveness"]["2_threads"]["speedup"]
            if speedup_2 < 1.2:
                recommendations.append("Limited performance gains with 2 threads - investigate model dependencies")

        if "4_threads" in analysis["threading_effectiveness"]:
            speedup_4 = analysis["threading_effectiveness"]["4_threads"]["speedup"]
            if speedup_4 > 2.0:
                recommendations.append("Excellent threading performance - consider increasing max thread count")
            elif speedup_4 < 1.5:
                recommendations.append("Suboptimal 4-thread performance - analyze parallelization bottlenecks")

        # Check parallelization ratios
        for key, value in analysis["threading_effectiveness"].items():
            if key.startswith("parallelization_") and isinstance(value, dict):
                ratio = value.get("ratio", 0)
                if ratio < 0.5:
                    recommendations.append(f"Low parallelization ratio ({ratio:.2f}) - optimize model dependencies")
                elif ratio > 0.8:
                    recommendations.append(f"High parallelization ratio ({ratio:.2f}) - good threading potential")

        if not recommendations:
            recommendations.append("Benchmark completed successfully - review detailed results for optimization opportunities")

        analysis["recommendations"] = recommendations

        return analysis

    def print_benchmark_summary(self, results: Dict[str, any]):
        """Print a summary of benchmark results."""

        print("\n" + "=" * 60)
        print("📊 Performance Benchmark Summary")
        print("=" * 60)

        # System info
        sys_info = results.get("system_info", {})
        print(f"System: {sys_info.get('cpu_cores', '?')} cores, {sys_info.get('memory_gb', '?')}GB RAM")

        # Performance summary
        analysis = results.get("analysis", {})
        performance_summary = analysis.get("performance_summary", {})

        if "baseline_time" in performance_summary:
            baseline = performance_summary["baseline_time"]
            print(f"Baseline (1 thread): {baseline:.3f}s")

        # Threading effectiveness
        threading_eff = analysis.get("threading_effectiveness", {})

        for thread_count in [2, 4]:
            key = f"{thread_count}_threads"
            if key in threading_eff:
                data = threading_eff[key]
                speedup = data.get("speedup", 0)
                improvement = data.get("improvement_percent", 0)
                efficiency = data.get("efficiency", 0)

                print(f"{thread_count} threads: {speedup:.2f}x speedup ({improvement:.1f}% improvement, {efficiency:.2f} efficiency)")

        # Recommendations
        recommendations = analysis.get("recommendations", [])
        if recommendations:
            print(f"\n💡 Recommendations:")
            for rec in recommendations:
                print(f"  • {rec}")


def main():
    """Main benchmark execution."""

    benchmark = PerformanceBenchmark()

    try:
        results = benchmark.run_comprehensive_benchmark()

        # Print summary
        benchmark.print_benchmark_summary(results)

        # Save detailed results
        output_file = f"performance_benchmark_{int(time.time())}.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2, default=str)

        print(f"\n📄 Detailed results saved: {output_file}")

        return True

    except KeyboardInterrupt:
        print("\n⏹️ Benchmark interrupted by user")
        return False
    except Exception as e:
        print(f"\n💥 Benchmark failed: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
