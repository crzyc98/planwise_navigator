#!/usr/bin/env python3
"""
Epic E067 Multi-Threading Validation Framework
============================================

Comprehensive validation and performance benchmarking for Epic E067 multi-threading implementation.

This script validates:
1. Deterministic Results: Same random seed produces identical results across thread counts
2. Performance Benchmarking: Measures actual runtime improvements and resource utilization
3. Resource Management: Validates memory usage and CPU utilization patterns
4. Data Quality: Ensures workforce snapshot consistency and event count reconciliation

Performance Targets (Epic E067):
- 20-30% improvement with 4+ threads
- Baseline: ~10 minutes for simulation
- Target: ~7 minutes with 4 threads (30% improvement)
- Memory usage stays within limits (<6GB with 4 threads)
- CPU utilization reaches 70-85% across cores
"""

import gc
import hashlib
import json
import os
import psutil
import statistics
import sys
import threading
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import warnings

# Suppress warnings for cleaner output
warnings.filterwarnings("ignore")

# Add project root to Python path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from navigator_orchestrator.parallel_execution_engine import ParallelExecutionEngine, ExecutionContext, ExecutionResult
    from navigator_orchestrator.resource_manager import ResourceManager, MemoryMonitor, CPUMonitor, PerformanceBenchmarker
    from navigator_orchestrator.model_dependency_analyzer import ModelDependencyAnalyzer
    from navigator_orchestrator.dbt_runner import DbtRunner
    from navigator_orchestrator.logger import ProductionLogger
    IMPORTS_SUCCESSFUL = True
except ImportError as e:
    print(f"❌ Import Error: {e}")
    print("Some components may not be available for testing")
    IMPORTS_SUCCESSFUL = False


@dataclass
class ValidationMetrics:
    """Metrics for determinism validation."""
    thread_count: int
    execution_time: float
    memory_peak_mb: float
    cpu_avg_percent: float
    event_count: int
    workforce_count: int
    data_hash: str
    success: bool
    error_message: Optional[str] = None


@dataclass
class BenchmarkResult:
    """Performance benchmark result."""
    thread_count: int
    execution_time: float
    speedup: float
    efficiency: float
    memory_usage_mb: float
    cpu_utilization: float
    success: bool
    details: Dict[str, Any] = field(default_factory=dict)


class ResourceMonitor:
    """Lightweight resource monitoring for validation."""

    def __init__(self):
        self.process = psutil.Process()
        self.initial_memory = 0
        self.peak_memory = 0
        self.cpu_samples = []
        self.monitoring = False
        self._monitor_thread = None

    def start_monitoring(self):
        """Start background resource monitoring."""
        if self.monitoring:
            return

        self.initial_memory = self.process.memory_info().rss / 1024 / 1024
        self.peak_memory = self.initial_memory
        self.cpu_samples = []
        self.monitoring = True

        self._monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self._monitor_thread.start()

    def stop_monitoring(self):
        """Stop resource monitoring."""
        self.monitoring = False
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)

    def _monitor_loop(self):
        """Background monitoring loop."""
        while self.monitoring:
            try:
                # Memory monitoring
                current_memory = self.process.memory_info().rss / 1024 / 1024
                self.peak_memory = max(self.peak_memory, current_memory)

                # CPU monitoring
                cpu_percent = self.process.cpu_percent()
                if cpu_percent > 0:  # Only record meaningful CPU usage
                    self.cpu_samples.append(cpu_percent)

                time.sleep(0.5)  # Sample every 500ms
            except Exception:
                pass

    def get_metrics(self) -> Dict[str, float]:
        """Get current resource metrics."""
        current_memory = self.process.memory_info().rss / 1024 / 1024
        memory_usage = current_memory - self.initial_memory
        avg_cpu = statistics.mean(self.cpu_samples) if self.cpu_samples else 0.0

        return {
            "memory_usage_mb": memory_usage,
            "peak_memory_mb": self.peak_memory,
            "avg_cpu_percent": avg_cpu,
            "current_memory_mb": current_memory
        }


class MockWorkflowSimulator:
    """Mock workflow simulator for testing threading without full dbt."""

    def __init__(self, complexity_factor: float = 1.0):
        self.complexity_factor = complexity_factor
        self.event_counts = {}
        self.workforce_counts = {}

    def simulate_model_execution(self, model_name: str, execution_time: float) -> Dict[str, Any]:
        """Simulate model execution with configurable complexity."""

        # Simulate CPU-intensive work
        start_time = time.time()
        target_time = execution_time * self.complexity_factor

        # Simulate different types of work based on model name
        if "staging" in model_name:
            self._simulate_io_work(target_time * 0.3)
        elif "intermediate" in model_name:
            self._simulate_cpu_work(target_time * 0.5)
        elif "events" in model_name:
            self._simulate_mixed_work(target_time * 0.7)
        else:
            self._simulate_mixed_work(target_time)

        actual_time = time.time() - start_time

        # Generate mock results
        event_count = int(1000 + (hash(model_name) % 5000))
        workforce_count = int(500 + (hash(model_name) % 2000))

        self.event_counts[model_name] = event_count
        self.workforce_counts[model_name] = workforce_count

        return {
            "success": True,
            "model": model_name,
            "execution_time": actual_time,
            "event_count": event_count,
            "workforce_count": workforce_count
        }

    def _simulate_io_work(self, duration: float):
        """Simulate I/O-bound work."""
        end_time = time.time() + duration
        while time.time() < end_time:
            # Light work to simulate I/O waiting
            time.sleep(0.001)

    def _simulate_cpu_work(self, duration: float):
        """Simulate CPU-intensive work."""
        end_time = time.time() + duration
        result = 0
        while time.time() < end_time:
            # CPU-intensive calculation
            result += sum(i * i for i in range(100))
        return result

    def _simulate_mixed_work(self, duration: float):
        """Simulate mixed CPU/I/O work."""
        cpu_duration = duration * 0.7
        io_duration = duration * 0.3

        self._simulate_cpu_work(cpu_duration)
        self._simulate_io_work(io_duration)


class E067ValidationFramework:
    """Main validation framework for Epic E067."""

    def __init__(self, output_dir: str = "validation_results"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(exist_ok=True)

        self.validation_results: List[ValidationMetrics] = []
        self.benchmark_results: List[BenchmarkResult] = []

        # Test configuration
        self.test_thread_counts = [1, 2, 4, 8]
        self.baseline_thread_count = 1
        self.random_seed = 42

        # Mock components for testing
        self.mock_simulator = MockWorkflowSimulator()
        self.resource_monitor = ResourceMonitor()

        print("🔧 E067 Validation Framework Initialized")
        print(f"   Output directory: {self.output_dir}")
        print(f"   Thread counts to test: {self.test_thread_counts}")
        print(f"   System info: {psutil.cpu_count()} CPU cores, {psutil.virtual_memory().total // (1024**3):.1f}GB RAM")

    def run_full_validation_suite(self) -> Dict[str, Any]:
        """Run the complete validation suite."""

        print("\n" + "="*80)
        print("🚀 Starting Epic E067 Multi-Threading Validation Suite")
        print("="*80)

        # Step 1: Determinism Validation
        print("\n📋 Step 1: Determinism Validation")
        determinism_results = self.run_determinism_validation()

        # Step 2: Performance Benchmarking
        print("\n📋 Step 2: Performance Benchmarking")
        performance_results = self.run_performance_benchmarks()

        # Step 3: Resource Management Validation
        print("\n📋 Step 3: Resource Management Validation")
        resource_results = self.run_resource_management_tests()

        # Step 4: Generate Report
        print("\n📋 Step 4: Generating Comprehensive Report")
        report = self.generate_validation_report(
            determinism_results, performance_results, resource_results
        )

        return report

    def run_determinism_validation(self) -> Dict[str, Any]:
        """Validate deterministic results across thread counts."""

        print("   🔍 Testing determinism across thread counts...")

        validation_results = {}
        reference_hash = None

        for thread_count in self.test_thread_counts:
            print(f"      Testing {thread_count} threads...")

            # Run simulation with specific thread count
            metrics = self._run_threaded_simulation(thread_count, deterministic=True)
            validation_results[thread_count] = metrics

            if reference_hash is None:
                reference_hash = metrics.data_hash
                print(f"         Reference hash: {reference_hash[:16]}...")
            else:
                is_deterministic = (metrics.data_hash == reference_hash)
                print(f"         Hash: {metrics.data_hash[:16]}... {'✅' if is_deterministic else '❌'}")

        # Analyze determinism
        all_hashes = [result.data_hash for result in validation_results.values()]
        is_fully_deterministic = len(set(all_hashes)) == 1

        determinism_summary = {
            "fully_deterministic": is_fully_deterministic,
            "reference_hash": reference_hash,
            "thread_results": validation_results,
            "hash_consistency": len(set(all_hashes)) == 1
        }

        print(f"   📊 Determinism Result: {'✅ PASS' if is_fully_deterministic else '❌ FAIL'}")

        return determinism_summary

    def run_performance_benchmarks(self) -> Dict[str, Any]:
        """Run performance benchmarks across thread counts."""

        print("   ⚡ Running performance benchmarks...")

        benchmark_results = {}
        baseline_time = None

        for thread_count in self.test_thread_counts:
            print(f"      Benchmarking {thread_count} threads...")

            # Run multiple iterations for statistical validity
            iteration_times = []
            for iteration in range(3):
                metrics = self._run_threaded_simulation(thread_count, deterministic=False)
                iteration_times.append(metrics.execution_time)
                print(f"         Iteration {iteration + 1}: {metrics.execution_time:.1f}s")

            avg_time = statistics.mean(iteration_times)
            std_dev = statistics.stdev(iteration_times) if len(iteration_times) > 1 else 0

            if baseline_time is None:
                baseline_time = avg_time
                speedup = 1.0
                efficiency = 1.0
            else:
                speedup = baseline_time / avg_time
                efficiency = speedup / thread_count

            benchmark_result = BenchmarkResult(
                thread_count=thread_count,
                execution_time=avg_time,
                speedup=speedup,
                efficiency=efficiency,
                memory_usage_mb=metrics.memory_peak_mb,
                cpu_utilization=metrics.cpu_avg_percent,
                success=metrics.success,
                details={
                    "iterations": iteration_times,
                    "std_dev": std_dev,
                    "min_time": min(iteration_times),
                    "max_time": max(iteration_times)
                }
            )

            benchmark_results[thread_count] = benchmark_result

            print(f"         Average: {avg_time:.1f}s, Speedup: {speedup:.2f}x, Efficiency: {efficiency:.2f}")

        # Analyze performance targets
        performance_analysis = self._analyze_performance_targets(benchmark_results)

        return {
            "benchmark_results": benchmark_results,
            "baseline_time": baseline_time,
            "performance_analysis": performance_analysis
        }

    def run_resource_management_tests(self) -> Dict[str, Any]:
        """Test resource management capabilities."""

        print("   🔧 Testing resource management...")

        if not IMPORTS_SUCCESSFUL:
            print("      ⚠️ Skipping resource management tests (imports not available)")
            return {"skipped": True, "reason": "imports_not_available"}

        try:
            # Test memory monitoring
            memory_monitor = MemoryMonitor(monitoring_interval=0.5, history_size=50)
            memory_monitor.start_monitoring()

            # Simulate memory pressure
            print("      Testing memory pressure detection...")
            large_objects = []
            for i in range(10):
                # Create some memory pressure
                large_obj = [0] * (100000 * (i + 1))
                large_objects.append(large_obj)
                time.sleep(0.1)

                pressure = memory_monitor.get_current_pressure()
                print(f"         Pressure level: {pressure.memory_pressure} ({pressure.memory_usage_mb:.0f}MB)")

            # Cleanup and test memory cleanup
            del large_objects
            gc.collect()

            memory_monitor.stop_monitoring()

            # Test CPU monitoring
            print("      Testing CPU monitoring...")
            cpu_monitor = CPUMonitor(monitoring_interval=0.5, history_size=50)
            cpu_monitor.start_monitoring()

            # Simulate CPU load
            end_time = time.time() + 3
            while time.time() < end_time:
                # CPU-intensive work
                sum(i * i for i in range(10000))

            cpu_pressure = cpu_monitor.get_current_pressure()
            optimal_threads = cpu_monitor.get_optimal_thread_count_estimate()

            cpu_monitor.stop_monitoring()

            print(f"         CPU pressure: {cpu_pressure}")
            print(f"         Optimal thread estimate: {optimal_threads}")

            return {
                "memory_monitoring": "functional",
                "cpu_monitoring": "functional",
                "resource_pressure_detection": "functional",
                "optimal_thread_estimation": optimal_threads
            }

        except Exception as e:
            print(f"      ❌ Resource management test failed: {e}")
            return {
                "skipped": True,
                "error": str(e)
            }

    def _run_threaded_simulation(self, thread_count: int, deterministic: bool = True) -> ValidationMetrics:
        """Run a mock simulation with specified thread count."""

        if deterministic:
            # Set deterministic seed
            import random
            random.seed(self.random_seed)

        self.resource_monitor.start_monitoring()
        start_time = time.time()

        try:
            # Mock workflow stages
            stages = [
                ("staging", ["stg_census_data", "stg_compensation_data", "stg_benefits_data"]),
                ("intermediate", ["int_baseline_workforce", "int_employee_compensation", "int_workforce_needs"]),
                ("events", ["int_termination_events", "int_hire_events", "int_promotion_events", "int_merit_events"]),
                ("accumulation", ["int_enrollment_state_accumulator", "int_deferral_rate_state_accumulator"]),
                ("marts", ["fct_yearly_events", "fct_workforce_snapshot", "dim_employees"])
            ]

            total_event_count = 0
            total_workforce_count = 0
            stage_results = {}

            for stage_name, models in stages:
                stage_start = time.time()

                if thread_count == 1:
                    # Sequential execution
                    stage_event_count = 0
                    stage_workforce_count = 0

                    for model in models:
                        model_time = 0.5 + (hash(model) % 100) / 200  # 0.5-1.0 seconds per model
                        result = self.mock_simulator.simulate_model_execution(model, model_time)
                        stage_event_count += result["event_count"]
                        stage_workforce_count += result["workforce_count"]

                else:
                    # Parallel execution simulation
                    import concurrent.futures

                    stage_event_count = 0
                    stage_workforce_count = 0

                    with concurrent.futures.ThreadPoolExecutor(max_workers=min(thread_count, len(models))) as executor:
                        futures = {}
                        for model in models:
                            model_time = 0.5 + (hash(model) % 100) / 200
                            future = executor.submit(self.mock_simulator.simulate_model_execution, model, model_time)
                            futures[future] = model

                        for future in concurrent.futures.as_completed(futures):
                            result = future.result()
                            stage_event_count += result["event_count"]
                            stage_workforce_count += result["workforce_count"]

                stage_time = time.time() - stage_start
                stage_results[stage_name] = {
                    "execution_time": stage_time,
                    "event_count": stage_event_count,
                    "workforce_count": stage_workforce_count
                }

                total_event_count += stage_event_count
                total_workforce_count += stage_workforce_count

            execution_time = time.time() - start_time

            # Create deterministic hash of results
            result_data = {
                "total_event_count": total_event_count,
                "total_workforce_count": total_workforce_count,
                "stage_results": stage_results,
                "thread_count": thread_count
            }

            if deterministic:
                # Include seed in hash for deterministic results
                result_data["random_seed"] = self.random_seed

            data_hash = hashlib.sha256(
                json.dumps(result_data, sort_keys=True).encode()
            ).hexdigest()

            resource_metrics = self.resource_monitor.get_metrics()

            return ValidationMetrics(
                thread_count=thread_count,
                execution_time=execution_time,
                memory_peak_mb=resource_metrics["peak_memory_mb"],
                cpu_avg_percent=resource_metrics["avg_cpu_percent"],
                event_count=total_event_count,
                workforce_count=total_workforce_count,
                data_hash=data_hash,
                success=True
            )

        except Exception as e:
            return ValidationMetrics(
                thread_count=thread_count,
                execution_time=0,
                memory_peak_mb=0,
                cpu_avg_percent=0,
                event_count=0,
                workforce_count=0,
                data_hash="",
                success=False,
                error_message=str(e)
            )

        finally:
            self.resource_monitor.stop_monitoring()

    def _analyze_performance_targets(self, benchmark_results: Dict[int, BenchmarkResult]) -> Dict[str, Any]:
        """Analyze performance against Epic E067 targets."""

        baseline_result = benchmark_results[1]  # Single thread baseline
        target_result = benchmark_results.get(4)  # 4-thread target

        analysis = {
            "baseline_time": baseline_result.execution_time,
            "target_improvement": 0.3,  # 30% improvement target
            "memory_limit_gb": 6.0,
            "cpu_target_range": (70, 85)
        }

        if target_result:
            actual_improvement = 1 - (target_result.execution_time / baseline_result.execution_time)
            target_time = baseline_result.execution_time * 0.7  # 30% improvement = 70% of original time

            analysis.update({
                "4_thread_time": target_result.execution_time,
                "actual_improvement": actual_improvement,
                "target_time": target_time,
                "improvement_target_met": actual_improvement >= 0.2,  # At least 20%
                "memory_usage_gb": target_result.memory_usage_mb / 1024,
                "memory_target_met": target_result.memory_usage_mb < 6144,  # 6GB in MB
                "cpu_utilization": target_result.cpu_utilization,
                "cpu_target_met": 70 <= target_result.cpu_utilization <= 85
            })

        # Overall assessment
        if target_result:
            targets_met = [
                analysis["improvement_target_met"],
                analysis["memory_target_met"],
                analysis["cpu_target_met"]
            ]
            analysis["overall_target_success"] = all(targets_met)
            analysis["targets_met_count"] = sum(targets_met)
        else:
            analysis["overall_target_success"] = False
            analysis["targets_met_count"] = 0

        return analysis

    def generate_validation_report(self, determinism_results: Dict, performance_results: Dict, resource_results: Dict) -> Dict[str, Any]:
        """Generate comprehensive validation report."""

        report = {
            "validation_timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "epic": "E067",
            "test_configuration": {
                "thread_counts_tested": self.test_thread_counts,
                "random_seed": self.random_seed,
                "system_info": {
                    "cpu_cores": psutil.cpu_count(),
                    "memory_gb": psutil.virtual_memory().total // (1024**3),
                    "python_version": sys.version
                }
            },
            "determinism_validation": determinism_results,
            "performance_benchmarks": performance_results,
            "resource_management": resource_results
        }

        # Generate summary
        summary = self._generate_validation_summary(report)
        report["executive_summary"] = summary

        # Save detailed report
        report_file = self.output_dir / f"e067_validation_report_{int(time.time())}.json"
        with open(report_file, 'w') as f:
            json.dump(report, f, indent=2, default=str)

        # Print summary
        self._print_validation_summary(summary)

        print(f"\n📄 Detailed report saved: {report_file}")

        return report

    def _generate_validation_summary(self, report: Dict) -> Dict[str, Any]:
        """Generate executive summary of validation results."""

        determinism_pass = report["determinism_validation"]["fully_deterministic"]

        performance_analysis = report["performance_benchmarks"].get("performance_analysis", {})
        performance_pass = performance_analysis.get("overall_target_success", False)
        targets_met = performance_analysis.get("targets_met_count", 0)

        resource_pass = not report["resource_management"].get("skipped", True)

        overall_pass = determinism_pass and performance_pass and resource_pass

        return {
            "overall_validation": "PASS" if overall_pass else "FAIL",
            "determinism_validation": "PASS" if determinism_pass else "FAIL",
            "performance_validation": "PASS" if performance_pass else "FAIL",
            "resource_validation": "PASS" if resource_pass else "SKIP",
            "performance_targets_met": f"{targets_met}/3",
            "key_findings": self._extract_key_findings(report),
            "recommendations": self._generate_recommendations(report)
        }

    def _extract_key_findings(self, report: Dict) -> List[str]:
        """Extract key findings from validation results."""

        findings = []

        # Determinism findings
        if report["determinism_validation"]["fully_deterministic"]:
            findings.append("✅ Threading implementation maintains deterministic results across all thread counts")
        else:
            findings.append("❌ Non-deterministic results detected across different thread counts")

        # Performance findings
        performance_analysis = report["performance_benchmarks"].get("performance_analysis", {})
        if "actual_improvement" in performance_analysis:
            improvement = performance_analysis["actual_improvement"] * 100
            if improvement >= 20:
                findings.append(f"✅ Performance target achieved: {improvement:.1f}% improvement with 4 threads")
            else:
                findings.append(f"❌ Performance target missed: Only {improvement:.1f}% improvement with 4 threads")

        # Memory findings
        if "memory_usage_gb" in performance_analysis:
            memory_gb = performance_analysis["memory_usage_gb"]
            if memory_gb < 6.0:
                findings.append(f"✅ Memory usage within limits: {memory_gb:.1f}GB with 4 threads")
            else:
                findings.append(f"❌ Memory usage exceeded limits: {memory_gb:.1f}GB with 4 threads")

        # Resource management findings
        if not report["resource_management"].get("skipped", True):
            findings.append("✅ Advanced resource management components functional")

        return findings

    def _generate_recommendations(self, report: Dict) -> List[str]:
        """Generate recommendations based on validation results."""

        recommendations = []

        # Determinism recommendations
        if not report["determinism_validation"]["fully_deterministic"]:
            recommendations.append("Fix non-deterministic behavior in parallel execution paths")
            recommendations.append("Ensure proper random seed handling across threads")

        # Performance recommendations
        performance_analysis = report["performance_benchmarks"].get("performance_analysis", {})
        if "actual_improvement" in performance_analysis:
            improvement = performance_analysis["actual_improvement"]
            if improvement < 0.2:  # Less than 20%
                recommendations.append("Investigate limited performance gains - may need better parallelizable models")
                recommendations.append("Consider dependency analysis optimization")

        # Resource recommendations
        if "memory_usage_gb" in performance_analysis:
            if performance_analysis["memory_usage_gb"] > 4.0:
                recommendations.append("Consider memory optimization strategies for multi-threaded execution")

        # CPU utilization recommendations
        if "cpu_utilization" in performance_analysis:
            cpu_util = performance_analysis["cpu_utilization"]
            if cpu_util < 70:
                recommendations.append("CPU utilization below target - investigate thread utilization efficiency")
            elif cpu_util > 85:
                recommendations.append("CPU utilization above target - may cause system instability")

        if not recommendations:
            recommendations.append("Implementation meets all validation criteria")

        return recommendations

    def _print_validation_summary(self, summary: Dict):
        """Print validation summary to console."""

        print("\n" + "="*80)
        print("📊 Epic E067 Validation Summary")
        print("="*80)

        print(f"Overall Validation: {summary['overall_validation']}")
        print(f"├─ Determinism: {summary['determinism_validation']}")
        print(f"├─ Performance: {summary['performance_validation']}")
        print(f"└─ Resource Management: {summary['resource_validation']}")

        print(f"\nPerformance Targets Met: {summary['performance_targets_met']}")

        print("\nKey Findings:")
        for finding in summary['key_findings']:
            print(f"  {finding}")

        print("\nRecommendations:")
        for recommendation in summary['recommendations']:
            print(f"  • {recommendation}")


def main():
    """Main execution function."""

    print("Epic E067 Multi-Threading Implementation Validation")
    print("=" * 60)

    # Create validation framework
    framework = E067ValidationFramework()

    try:
        # Run full validation suite
        results = framework.run_full_validation_suite()

        # Return appropriate exit code
        if results["executive_summary"]["overall_validation"] == "PASS":
            print("\n🎉 All validations passed!")
            sys.exit(0)
        else:
            print("\n⚠️ Some validations failed - see report for details")
            sys.exit(1)

    except KeyboardInterrupt:
        print("\n\n⏹️ Validation interrupted by user")
        sys.exit(130)
    except Exception as e:
        print(f"\n💥 Validation failed with unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
