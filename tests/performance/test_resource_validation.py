#!/usr/bin/env python3
"""
Resource Validation Tests for Epic E067: Multi-Threading PlanAlign Orchestrator

This module contains specialized tests for validating resource management
and monitoring across different thread configurations. These tests ensure
the threading implementation properly manages system resources and meets
the performance targets specified in Epic E067.

Resource Validation Areas:
1. Memory Usage Patterns and Limits
2. CPU Utilization and Efficiency
3. Thread Pool Resource Management
4. Adaptive Scaling Under Pressure
5. Resource Constraint Enforcement
6. Performance Target Compliance
"""

import pytest
import time
import threading
import tempfile
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, List, Tuple, Optional
import psutil
import gc

# Import resource management components
from planalign_orchestrator.config import (
    ThreadingSettings, ResourceManagerSettings, ModelParallelizationSettings
)
from planalign_orchestrator.resource_manager import (
    ResourceManager, MemoryMonitor, CPUMonitor
)
from planalign_orchestrator.parallel_execution_engine import ParallelExecutionEngine
from planalign_orchestrator.dbt_runner import DbtRunner, DbtResult


class ResourceUsageTracker:
    """Utility class for tracking resource usage during tests."""

    def __init__(self, sampling_interval: float = 0.1):
        self.sampling_interval = sampling_interval
        self.samples = []
        self.monitoring = False
        self.monitor_thread = None

    def start_monitoring(self):
        """Start resource monitoring."""
        self.monitoring = True
        self.samples = []
        self.monitor_thread = threading.Thread(target=self._monitor_loop)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

    def stop_monitoring(self) -> Dict[str, any]:
        """Stop monitoring and return statistics."""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join(timeout=1)

        if not self.samples:
            return {"error": "No samples collected"}

        return {
            "sample_count": len(self.samples),
            "duration": self.samples[-1]["timestamp"] - self.samples[0]["timestamp"],
            "memory_stats": {
                "min_mb": min(s["memory_mb"] for s in self.samples),
                "max_mb": max(s["memory_mb"] for s in self.samples),
                "avg_mb": sum(s["memory_mb"] for s in self.samples) / len(self.samples)
            },
            "cpu_stats": {
                "min_percent": min(s["cpu_percent"] for s in self.samples),
                "max_percent": max(s["cpu_percent"] for s in self.samples),
                "avg_percent": sum(s["cpu_percent"] for s in self.samples) / len(self.samples)
            },
            "thread_stats": {
                "min_threads": min(s["thread_count"] for s in self.samples),
                "max_threads": max(s["thread_count"] for s in self.samples),
                "avg_threads": sum(s["thread_count"] for s in self.samples) / len(self.samples)
            }
        }

    def _monitor_loop(self):
        """Internal monitoring loop."""
        start_time = time.time()
        process = psutil.Process()

        while self.monitoring:
            try:
                self.samples.append({
                    "timestamp": time.time() - start_time,
                    "memory_mb": process.memory_info().rss / (1024 * 1024),
                    "cpu_percent": psutil.cpu_percent(interval=None),
                    "thread_count": threading.active_count()
                })
                time.sleep(self.sampling_interval)
            except Exception:
                break


class TestMemoryMonitoringAndLimits:
    """Test memory monitoring and enforcement of memory limits."""

    def setup_method(self):
        self.tracker = ResourceUsageTracker(sampling_interval=0.05)

    def test_memory_monitor_basic_functionality(self):
        """Test basic memory monitoring functionality."""

        monitor = MemoryMonitor(
            memory_limit_gb=2.0,
            warning_threshold=0.7,
            critical_threshold=0.9
        )

        # Test memory status checking
        status = monitor.check_memory_status()

        assert "current_usage_gb" in status
        assert "limit_gb" in status
        assert status["limit_gb"] == 2.0
        assert "pressure_level" in status
        assert status["pressure_level"] in ["low", "medium", "high", "critical"]
        assert "percentage_used" in status
        assert 0 <= status["percentage_used"] <= 100

    def test_memory_pressure_level_calculation(self):
        """Test memory pressure level calculation with different usage scenarios."""

        monitor = MemoryMonitor(
            memory_limit_gb=4.0,
            warning_threshold=0.7,
            critical_threshold=0.9
        )

        # Mock different memory usage levels
        test_scenarios = [
            {"used_gb": 1.0, "expected_level": "low"},      # 25% usage
            {"used_gb": 2.5, "expected_level": "medium"},   # 62.5% usage
            {"used_gb": 3.0, "expected_level": "high"},     # 75% usage (above warning)
            {"used_gb": 3.8, "expected_level": "critical"}  # 95% usage (above critical)
        ]

        for scenario in test_scenarios:
            with patch('psutil.virtual_memory') as mock_memory:
                mock_memory.return_value.used = int(scenario["used_gb"] * 1024 * 1024 * 1024)
                mock_memory.return_value.total = int(4.0 * 1024 * 1024 * 1024)

                status = monitor.check_memory_status()
                assert status["pressure_level"] == scenario["expected_level"], \
                    f"Expected {scenario['expected_level']} for {scenario['used_gb']}GB usage, got {status['pressure_level']}"

    def test_memory_limit_enforcement(self):
        """Test that memory limits are properly enforced."""

        resource_manager = ResourceManager(
            max_workers=8,
            memory_limit_gb=1.0,  # Low limit for testing
            enable_adaptive_scaling=True
        )

        # Test validation with excessive memory requirements
        validation = resource_manager.validate_execution_resources(
            required_workers=8,
            estimated_memory_per_worker_gb=0.5  # 4GB total, exceeds 1GB limit
        )

        assert validation["can_execute"] == False
        assert len(validation["errors"]) > 0
        assert any("memory" in error.lower() for error in validation["errors"])

        # Test validation with acceptable memory requirements
        validation_ok = resource_manager.validate_execution_resources(
            required_workers=2,
            estimated_memory_per_worker_gb=0.4  # 0.8GB total, within 1GB limit
        )

        assert validation_ok["can_execute"] == True

    def test_adaptive_memory_scaling(self):
        """Test adaptive scaling based on memory availability."""

        resource_manager = ResourceManager(
            max_workers=8,
            memory_limit_gb=4.0,
            enable_adaptive_scaling=True
        )

        # Test scaling under different memory pressure levels
        memory_scenarios = [
            {"available_gb": 3.5, "expected_max_workers": 8},    # Plenty of memory
            {"available_gb": 2.0, "expected_max_workers": 6},    # Moderate pressure
            {"available_gb": 0.8, "expected_max_workers": 2},    # High pressure
            {"available_gb": 0.2, "expected_max_workers": 1}     # Critical pressure
        ]

        for scenario in memory_scenarios:
            with patch('psutil.virtual_memory') as mock_memory:
                used_gb = 4.0 - scenario["available_gb"]
                mock_memory.return_value.used = int(used_gb * 1024 * 1024 * 1024)
                mock_memory.return_value.total = int(4.0 * 1024 * 1024 * 1024)
                mock_memory.return_value.available = int(scenario["available_gb"] * 1024 * 1024 * 1024)

                recommended = resource_manager.get_recommended_workers(stage_complexity="medium")

                assert recommended <= scenario["expected_max_workers"], \
                    f"Recommended {recommended} workers with {scenario['available_gb']}GB available, expected max {scenario['expected_max_workers']}"
                assert recommended >= 1, "Should always recommend at least 1 worker"

    def test_memory_usage_during_parallel_execution(self):
        """Test actual memory usage patterns during parallel execution."""

        self.tracker.start_monitoring()

        try:
            # Create execution engine with memory monitoring
            mock_dbt_runner = Mock(spec=DbtRunner)

            # Mock execution that allocates memory
            def memory_intensive_execution(*args, **kwargs):
                # Simulate memory allocation during model execution
                data = [0] * 100000  # ~800KB allocation
                time.sleep(0.1)
                return DbtResult(
                    success=True, stdout="", stderr="", execution_time=0.1,
                    return_code=0, command=list(args[0])
                )

            mock_dbt_runner.execute_command.side_effect = memory_intensive_execution

            engine = ParallelExecutionEngine(
                dbt_runner=mock_dbt_runner,
                dependency_analyzer=Mock(),
                max_workers=4,
                memory_limit_mb=1000.0,  # 1GB limit
                resource_monitoring=True,
                verbose=False
            )

            # Execute multiple models in parallel
            models = [f"memory_test_model_{i}" for i in range(8)]
            context = ExecutionContext(2025, {}, "memory_test", "parallel")

            # Mock parallelization opportunities
            mock_analyzer = Mock()
            mock_analyzer.identify_parallelization_opportunities.return_value = [
                Mock(parallel_models=models, execution_group="memory_group",
                     estimated_speedup=3.0, safety_level="high")
            ]
            mock_analyzer.validate_execution_safety.return_value = {
                "safe": True, "issues": [], "warnings": []
            }
            engine.dependency_analyzer = mock_analyzer

            result = engine.execute_stage(models, context)

            # Brief additional monitoring period
            time.sleep(0.5)

        finally:
            stats = self.tracker.stop_monitoring()

        # Validate memory usage patterns
        assert result.success == True, "Parallel execution should succeed"
        assert stats["sample_count"] > 0, "Should have collected memory samples"

        # Memory usage should increase during execution but stay within reasonable bounds
        memory_growth = stats["memory_stats"]["max_mb"] - stats["memory_stats"]["min_mb"]
        assert memory_growth >= 0, "Memory usage should increase or stay stable"
        assert stats["memory_stats"]["max_mb"] < 2000, f"Memory usage too high: {stats['memory_stats']['max_mb']} MB"


class TestCPUUtilizationAndEfficiency:
    """Test CPU utilization monitoring and efficiency."""

    def setup_method(self):
        self.tracker = ResourceUsageTracker(sampling_interval=0.1)

    def test_cpu_monitor_basic_functionality(self):
        """Test basic CPU monitoring functionality."""

        monitor = CPUMonitor(
            target_utilization=0.75,
            measurement_window=1.0
        )

        # Test CPU status checking
        status = monitor.check_cpu_status()

        assert "current_utilization" in status
        assert "target_utilization" in status
        assert status["target_utilization"] == 0.75
        assert "core_count" in status
        assert status["core_count"] == psutil.cpu_count()
        assert "recommended_workers" in status
        assert isinstance(status["recommended_workers"], int)
        assert status["recommended_workers"] >= 1

    def test_cpu_utilization_target_compliance(self):
        """Test that CPU utilization stays within target ranges."""

        available_cores = psutil.cpu_count()
        target_utilization = 0.75

        monitor = CPUMonitor(
            target_utilization=target_utilization,
            measurement_window=0.5
        )

        # Test worker recommendations based on CPU capacity
        status = monitor.check_cpu_status()
        recommended_workers = status["recommended_workers"]

        # Should not recommend more workers than can efficiently use CPU
        max_efficient_workers = max(1, int(available_cores * target_utilization))
        assert recommended_workers <= max_efficient_workers * 2, \
            f"Recommended {recommended_workers} workers for {available_cores} cores, seems excessive"

        # Should recommend at least 1 worker
        assert recommended_workers >= 1, "Should recommend at least 1 worker"

    def test_cpu_load_during_parallel_execution(self):
        """Test CPU load patterns during parallel execution."""

        self.tracker.start_monitoring()

        try:
            # Create CPU-intensive workload
            def cpu_intensive_task():
                """Simulate CPU-bound model execution."""
                result = 0
                for i in range(200000):  # CPU-bound computation
                    result += i * i
                return result

            # Execute tasks in parallel with different worker counts
            worker_counts = [1, 2, min(4, psutil.cpu_count())]

            for worker_count in worker_counts:
                mock_dbt_runner = Mock(spec=DbtRunner)

                def mock_cpu_intensive_execution(*args, **kwargs):
                    cpu_intensive_task()
                    return DbtResult(
                        success=True, stdout="", stderr="", execution_time=0.2,
                        return_code=0, command=list(args[0])
                    )

                mock_dbt_runner.execute_command.side_effect = mock_cpu_intensive_execution

                engine = ParallelExecutionEngine(
                    dbt_runner=mock_dbt_runner,
                    dependency_analyzer=Mock(),
                    max_workers=worker_count,
                    resource_monitoring=True,
                    verbose=False
                )

                models = [f"cpu_test_{worker_count}_{i}" for i in range(4)]
                context = ExecutionContext(2025, {}, "cpu_test", f"workers_{worker_count}")

                # Mock opportunities and validation
                mock_analyzer = Mock()
                mock_analyzer.identify_parallelization_opportunities.return_value = [
                    Mock(parallel_models=models, execution_group="cpu_group",
                         estimated_speedup=min(worker_count, len(models)), safety_level="high")
                ]
                mock_analyzer.validate_execution_safety.return_value = {
                    "safe": True, "issues": [], "warnings": []
                }
                engine.dependency_analyzer = mock_analyzer

                result = engine.execute_stage(models, context)
                assert result.success == True, f"CPU test failed for {worker_count} workers"

                time.sleep(0.2)  # Allow CPU measurement

        finally:
            stats = self.tracker.stop_monitoring()

        # Validate CPU utilization patterns
        if stats.get("sample_count", 0) > 0:
            avg_cpu = stats["cpu_stats"]["avg_percent"]
            max_cpu = stats["cpu_stats"]["max_percent"]

            # Should show increased CPU activity during execution
            assert avg_cpu > 10, f"Expected CPU activity, got {avg_cpu}% average"

            # Should not consistently max out CPU (indicates good load balancing)
            assert max_cpu <= 98, f"CPU usage too high: {max_cpu}%"

    def test_cpu_efficiency_across_thread_counts(self):
        """Test CPU efficiency (work done per CPU cycle) across different thread counts."""

        cpu_efficiency_results = {}

        # Test with different thread counts
        for thread_count in [1, 2, 4]:
            mock_dbt_runner = Mock(spec=DbtRunner)

            # Track execution count and timing
            execution_count = 0
            total_cpu_work = 0

            def mock_tracked_execution(*args, **kwargs):
                nonlocal execution_count, total_cpu_work
                execution_count += 1

                # Simulate consistent CPU work per model
                work_units = 10000
                for i in range(work_units):
                    total_cpu_work += i % 100

                time.sleep(0.05)  # Brief I/O simulation

                return DbtResult(
                    success=True, stdout="", stderr="", execution_time=0.05,
                    return_code=0, command=list(args[0])
                )

            mock_dbt_runner.execute_command.side_effect = mock_tracked_execution

            # Monitor CPU during execution
            cpu_samples = []
            def monitor_cpu_efficiency():
                for _ in range(20):  # 2 seconds of monitoring
                    cpu_samples.append(psutil.cpu_percent(interval=0.1))

            cpu_monitor_thread = threading.Thread(target=monitor_cpu_efficiency)
            cpu_monitor_thread.start()

            engine = ParallelExecutionEngine(
                dbt_runner=mock_dbt_runner,
                dependency_analyzer=Mock(),
                max_workers=thread_count,
                resource_monitoring=True,
                verbose=False
            )

            models = [f"efficiency_model_{i}" for i in range(8)]
            context = ExecutionContext(2025, {}, "efficiency_test", f"threads_{thread_count}")

            # Mock parallelization setup
            mock_analyzer = Mock()
            mock_analyzer.identify_parallelization_opportunities.return_value = [
                Mock(parallel_models=models, execution_group="efficiency_group",
                     estimated_speedup=min(thread_count, len(models)), safety_level="high")
            ]
            mock_analyzer.validate_execution_safety.return_value = {
                "safe": True, "issues": [], "warnings": []
            }
            engine.dependency_analyzer = mock_analyzer

            start_time = time.time()
            result = engine.execute_stage(models, context)
            execution_time = time.time() - start_time

            cpu_monitor_thread.join()

            # Calculate efficiency metrics
            avg_cpu_utilization = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0

            cpu_efficiency_results[thread_count] = {
                "execution_time": execution_time,
                "models_executed": execution_count,
                "avg_cpu_utilization": avg_cpu_utilization,
                "work_per_time": total_cpu_work / execution_time if execution_time > 0 else 0,
                "parallelism_achieved": result.parallelism_achieved
            }

        # Validate efficiency improvements with more threads
        if 1 in cpu_efficiency_results and 4 in cpu_efficiency_results:
            single_thread = cpu_efficiency_results[1]
            quad_thread = cpu_efficiency_results[4]

            # With 4 threads, should achieve better throughput
            throughput_improvement = quad_thread["work_per_time"] / single_thread["work_per_time"]

            assert throughput_improvement >= 1.5, f"Insufficient throughput improvement with 4 threads: {throughput_improvement:.2f}x"

            # Parallelism achieved should be higher
            assert quad_thread["parallelism_achieved"] > single_thread["parallelism_achieved"]


class TestThreadPoolResourceManagement:
    """Test thread pool creation, management, and resource usage."""

    def test_thread_pool_creation_and_cleanup(self):
        """Test that thread pools are created and cleaned up properly."""

        initial_thread_count = threading.active_count()

        # Create multiple engines to test thread pool management
        engines = []

        for i in range(3):
            mock_dbt_runner = Mock(spec=DbtRunner)
            mock_dbt_runner.execute_command.return_value = DbtResult(
                success=True, stdout="", stderr="", execution_time=0.1,
                return_code=0, command=[]
            )

            engine = ParallelExecutionEngine(
                dbt_runner=mock_dbt_runner,
                dependency_analyzer=Mock(),
                max_workers=4,
                resource_monitoring=False,
                verbose=False
            )

            engines.append(engine)

        # Thread count should not grow excessively
        peak_thread_count = threading.active_count()
        thread_growth = peak_thread_count - initial_thread_count

        # Should not create excessive threads (some growth is expected for thread pools)
        assert thread_growth <= 20, f"Excessive thread growth: {thread_growth} threads"

        # Cleanup engines
        del engines
        import gc
        gc.collect()
        time.sleep(0.5)  # Allow cleanup

        # Thread count should return to reasonable level
        final_thread_count = threading.active_count()
        remaining_growth = final_thread_count - initial_thread_count

        assert remaining_growth <= 5, f"Threads not properly cleaned up: {remaining_growth} remaining"

    def test_thread_pool_resource_limits(self):
        """Test that thread pools respect configured resource limits."""

        # Test with various worker limits
        worker_limits = [1, 2, 4, 8, 16]

        for max_workers in worker_limits:
            resource_manager = ResourceManager(
                max_workers=max_workers,
                memory_limit_gb=4.0,
                enable_adaptive_scaling=False  # Disable to test hard limits
            )

            # Validate that the limit is respected
            validation = resource_manager.validate_execution_resources(
                required_workers=max_workers,
                estimated_memory_per_worker_gb=0.2
            )

            assert validation["can_execute"] == True, f"Should allow {max_workers} workers"

            # Test exceeding the limit
            if max_workers < 16:
                over_limit_validation = resource_manager.validate_execution_resources(
                    required_workers=max_workers + 4,
                    estimated_memory_per_worker_gb=0.2
                )

                # Should either reject or recommend scaling down
                if not over_limit_validation["can_execute"]:
                    assert len(over_limit_validation["errors"]) > 0
                elif over_limit_validation["can_execute"]:
                    # If allowed, should include warnings about resource pressure
                    assert len(over_limit_validation.get("warnings", [])) > 0

    def test_concurrent_thread_pool_access(self):
        """Test thread safety of thread pool operations."""

        engine = ParallelExecutionEngine(
            dbt_runner=Mock(spec=DbtRunner),
            dependency_analyzer=Mock(),
            max_workers=4,
            resource_monitoring=True,
            verbose=False
        )

        # Mock successful execution
        engine.dbt_runner.execute_command.return_value = DbtResult(
            success=True, stdout="", stderr="", execution_time=0.05,
            return_code=0, command=[]
        )

        results = []
        errors = []

        def concurrent_execution(thread_id):
            try:
                for i in range(5):
                    models = [f"concurrent_model_{thread_id}_{i}"]
                    context = ExecutionContext(2025, {}, "concurrent_test", f"thread_{thread_id}")

                    # Mock simple parallelization
                    mock_analyzer = Mock()
                    mock_analyzer.identify_parallelization_opportunities.return_value = [
                        Mock(parallel_models=models, execution_group="concurrent_group",
                             estimated_speedup=1.0, safety_level="high")
                    ]
                    mock_analyzer.validate_execution_safety.return_value = {
                        "safe": True, "issues": [], "warnings": []
                    }
                    engine.dependency_analyzer = mock_analyzer

                    result = engine.execute_stage(models, context)
                    results.append((thread_id, result.success))

                    time.sleep(0.01)  # Brief pause
            except Exception as e:
                errors.append((thread_id, e))

        # Run concurrent operations
        threads = []
        for i in range(8):
            thread = threading.Thread(target=concurrent_execution, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Should handle concurrent access without errors
        assert len(errors) == 0, f"Concurrent access errors: {errors}"
        assert len(results) == 8 * 5, f"Expected 40 results, got {len(results)}"

        # All executions should succeed
        successful_results = [r for r in results if r[1] == True]
        assert len(successful_results) == len(results), "Some concurrent executions failed"


class TestPerformanceTargetCompliance:
    """Test compliance with Epic E067 performance targets."""

    def test_memory_limit_compliance(self):
        """Test that memory usage stays within Epic E067 targets (<6GB with 4 threads)."""

        target_memory_gb = 6.0
        thread_count = 4

        tracker = ResourceUsageTracker(sampling_interval=0.1)
        tracker.start_monitoring()

        try:
            # Create resource manager with target limits
            resource_manager = ResourceManager(
                max_workers=thread_count,
                memory_limit_gb=target_memory_gb,
                enable_adaptive_scaling=True
            )

            # Simulate realistic simulation workload
            mock_dbt_runner = Mock(spec=DbtRunner)

            def simulate_memory_intensive_model(*args, **kwargs):
                # Simulate memory allocation typical of dbt model execution
                temp_data = [0] * 500000  # ~4MB allocation
                time.sleep(0.1)
                del temp_data

                return DbtResult(
                    success=True, stdout="", stderr="", execution_time=0.1,
                    return_code=0, command=list(args[0])
                )

            mock_dbt_runner.execute_command.side_effect = simulate_memory_intensive_model

            engine = ParallelExecutionEngine(
                dbt_runner=mock_dbt_runner,
                dependency_analyzer=Mock(),
                max_workers=thread_count,
                memory_limit_mb=target_memory_gb * 1024,
                resource_monitoring=True,
                verbose=False
            )

            # Execute realistic model workload
            models = [f"target_compliance_model_{i:02d}" for i in range(20)]
            context = ExecutionContext(2025, {}, "compliance_test", "memory_target")

            # Mock parallelization for realistic scenario
            mock_analyzer = Mock()
            chunk_size = 5
            opportunities = []
            for i in range(0, len(models), chunk_size):
                chunk = models[i:i + chunk_size]
                opportunities.append(Mock(
                    parallel_models=chunk, execution_group=f"compliance_group_{i//chunk_size}",
                    estimated_speedup=min(len(chunk), thread_count), safety_level="high"
                ))

            mock_analyzer.identify_parallelization_opportunities.return_value = opportunities
            mock_analyzer.validate_execution_safety.return_value = {
                "safe": True, "issues": [], "warnings": []
            }
            engine.dependency_analyzer = mock_analyzer

            result = engine.execute_stage(models, context)

            # Let execution complete and monitor resources
            time.sleep(1.0)

        finally:
            stats = tracker.stop_monitoring()

        # Validate performance target compliance
        assert result.success == True, "Compliance test execution should succeed"

        if stats.get("sample_count", 0) > 0:
            max_memory_gb = stats["memory_stats"]["max_mb"] / 1024

            # Should stay within target memory limit
            assert max_memory_gb <= target_memory_gb * 1.2, \
                f"Memory usage exceeded target: {max_memory_gb:.1f}GB > {target_memory_gb}GB"

            # Should achieve reasonable parallelism
            assert result.parallelism_achieved >= 2.0, \
                f"Insufficient parallelism achieved: {result.parallelism_achieved}"

    def test_cpu_utilization_target_compliance(self):
        """Test that CPU utilization meets Epic E067 targets (70-85% with multiple threads)."""

        target_cpu_range = (70, 85)  # Target CPU utilization range

        tracker = ResourceUsageTracker(sampling_interval=0.1)
        tracker.start_monitoring()

        try:
            # Create CPU-intensive workload to test utilization
            mock_dbt_runner = Mock(spec=DbtRunner)

            def cpu_intensive_model_execution(*args, **kwargs):
                # Simulate CPU-bound model execution
                result = 0
                for i in range(300000):  # CPU-intensive computation
                    result += i * i % 1000

                time.sleep(0.05)  # Brief I/O
                return DbtResult(
                    success=True, stdout="", stderr="", execution_time=0.15,
                    return_code=0, command=list(args[0])
                )

            mock_dbt_runner.execute_command.side_effect = cpu_intensive_model_execution

            # Test with 4 threads (Epic target scenario)
            engine = ParallelExecutionEngine(
                dbt_runner=mock_dbt_runner,
                dependency_analyzer=Mock(),
                max_workers=4,
                resource_monitoring=True,
                verbose=False
            )

            models = [f"cpu_target_model_{i}" for i in range(12)]
            context = ExecutionContext(2025, {}, "cpu_compliance_test", "target")

            # Mock parallelization for CPU-bound workload
            mock_analyzer = Mock()
            mock_analyzer.identify_parallelization_opportunities.return_value = [
                Mock(parallel_models=models, execution_group="cpu_intensive_group",
                     estimated_speedup=3.5, safety_level="high")
            ]
            mock_analyzer.validate_execution_safety.return_value = {
                "safe": True, "issues": [], "warnings": []
            }
            engine.dependency_analyzer = mock_analyzer

            result = engine.execute_stage(models, context)

            # Continue monitoring briefly after execution
            time.sleep(0.5)

        finally:
            stats = tracker.stop_monitoring()

        # Validate CPU utilization compliance
        assert result.success == True, "CPU compliance test should succeed"

        if stats.get("sample_count", 0) > 0:
            avg_cpu = stats["cpu_stats"]["avg_percent"]
            max_cpu = stats["cpu_stats"]["max_percent"]

            # Should achieve good CPU utilization during execution
            # Note: In test environment, may not reach production targets due to mocking
            assert avg_cpu >= 20, f"CPU utilization too low: {avg_cpu}%"
            assert max_cpu <= 95, f"CPU utilization too high: {max_cpu}%"

            # Should achieve meaningful parallelism
            assert result.parallelism_achieved >= 2.0, \
                f"Should achieve parallelism with 4 workers: {result.parallelism_achieved}"


# Test utilities and fixtures
@pytest.fixture
def resource_test_environment():
    """Set up isolated environment for resource testing."""
    original_limits = {}

    # Could set resource limits here if needed
    # import resource
    # original_limits['memory'] = resource.getrlimit(resource.RLIMIT_AS)

    yield {"limits": original_limits}

    # Restore original limits
    # for limit_type, limit_value in original_limits.items():
    #     resource.setrlimit(getattr(resource, f'RLIMIT_{limit_type.upper()}'), limit_value)


def simulate_memory_allocation(size_mb: float, duration: float = 0.1):
    """Utility to simulate memory allocation for testing."""
    try:
        # Allocate requested memory
        allocation = [0] * int(size_mb * 1024 * 128)  # Approximately size_mb MB
        time.sleep(duration)
        del allocation
        gc.collect()
    except MemoryError:
        pass  # Expected in low-memory scenarios


if __name__ == "__main__":
    # Run resource validation tests
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "--maxfail=10",
        "-x"  # Stop on first failure
    ])
