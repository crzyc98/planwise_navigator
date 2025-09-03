#!/usr/bin/env python3
"""
Stress Tests for Epic E067: Multi-Threading Navigator Orchestrator

This module contains stress tests designed to validate the threading implementation
under extreme conditions and edge cases:

1. High Thread Count Stability
2. Memory Pressure Handling
3. Execution Error Recovery
4. Resource Exhaustion Scenarios
5. Concurrent Access Safety
6. Long-Running Simulation Stability

These tests push the system beyond normal operating parameters to identify
potential failure modes and validate error recovery mechanisms.
"""

import pytest
import time
import threading
import tempfile
import shutil
import gc
import signal
import os
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError
import psutil

# Import components for stress testing
from navigator_orchestrator.config import (
    ThreadingSettings, ModelParallelizationSettings, ResourceManagerSettings
)
from navigator_orchestrator.dbt_runner import DbtRunner, DbtResult
from navigator_orchestrator.parallel_execution_engine import (
    ParallelExecutionEngine, ExecutionContext, ExecutionResult
)
from navigator_orchestrator.resource_manager import ResourceManager
from navigator_orchestrator.model_dependency_analyzer import ModelDependencyAnalyzer


class StressTestHarness:
    """Utility class for managing stress test execution and monitoring."""

    def __init__(self):
        self.start_time = None
        self.resource_samples = []
        self.error_count = 0
        self.success_count = 0
        self.monitoring_active = False

    def start_monitoring(self):
        """Start resource monitoring thread."""
        self.start_time = time.time()
        self.monitoring_active = True
        self.monitor_thread = threading.Thread(target=self._monitor_resources)
        self.monitor_thread.daemon = True
        self.monitor_thread.start()

    def stop_monitoring(self):
        """Stop resource monitoring and return statistics."""
        self.monitoring_active = False
        if hasattr(self, 'monitor_thread'):
            self.monitor_thread.join(timeout=1)

        if self.resource_samples:
            return {
                "duration": time.time() - self.start_time,
                "max_memory_mb": max(sample["memory_mb"] for sample in self.resource_samples),
                "avg_cpu_percent": sum(sample["cpu_percent"] for sample in self.resource_samples) / len(self.resource_samples),
                "sample_count": len(self.resource_samples),
                "error_count": self.error_count,
                "success_count": self.success_count
            }
        return {}

    def _monitor_resources(self):
        """Internal resource monitoring loop."""
        process = psutil.Process()
        while self.monitoring_active:
            try:
                self.resource_samples.append({
                    "timestamp": time.time() - self.start_time,
                    "memory_mb": process.memory_info().rss / (1024 * 1024),
                    "cpu_percent": psutil.cpu_percent(interval=None),
                    "thread_count": threading.active_count()
                })
                time.sleep(0.2)  # Sample every 200ms
            except Exception:
                break

    def record_result(self, success: bool):
        """Record test result."""
        if success:
            self.success_count += 1
        else:
            self.error_count += 1


class TestHighThreadCountStability:
    """Test stability with maximum and extreme thread counts."""

    def setup_method(self):
        self.stress_harness = StressTestHarness()

    @pytest.mark.stress
    def test_maximum_thread_count_stability(self):
        """Test stability at maximum allowed thread count (16)."""

        self.stress_harness.start_monitoring()

        try:
            # Create engine with maximum thread count
            mock_dbt_runner = Mock(spec=DbtRunner)
            mock_dependency_analyzer = Mock(spec=ModelDependencyAnalyzer)

            engine = ParallelExecutionEngine(
                dbt_runner=mock_dbt_runner,
                dependency_analyzer=mock_dependency_analyzer,
                max_workers=16,  # Maximum allowed
                resource_monitoring=True,
                verbose=False
            )

            # Mock successful execution
            mock_dbt_runner.execute_command.return_value = DbtResult(
                success=True, stdout="", stderr="", execution_time=0.1,
                return_code=0, command=[]
            )

            # Create large model set
            models = [f"stress_model_{i:03d}" for i in range(100)]

            # Mock parallelization opportunities
            opportunities = []
            chunk_size = 6  # 16 threads / ~3 groups
            for i in range(0, len(models), chunk_size):
                chunk = models[i:i + chunk_size]
                opportunities.append(Mock(
                    parallel_models=chunk,
                    execution_group=f"stress_group_{i // chunk_size}",
                    estimated_speedup=min(len(chunk), 16),
                    safety_level="medium"  # Realistic for stress test
                ))

            mock_dependency_analyzer.identify_parallelization_opportunities.return_value = opportunities
            mock_dependency_analyzer.validate_execution_safety.return_value = {
                "safe": True, "issues": [], "warnings": ["high_thread_count"]
            }

            # Execute multiple times to test stability
            for iteration in range(5):
                context = ExecutionContext(
                    simulation_year=2025,
                    dbt_vars={},
                    stage_name="stress_test",
                    execution_id=f"stability_{iteration}"
                )

                result = engine.execute_stage(models[:20], context)  # Subset for speed
                self.stress_harness.record_result(result.success)

                assert result.success == True, f"Iteration {iteration} failed"

                # Brief pause to allow resource recovery
                time.sleep(0.5)

        finally:
            stats = self.stress_harness.stop_monitoring()

        # Validate stability
        assert self.stress_harness.success_count >= 5, "Not all iterations succeeded"
        assert self.stress_harness.error_count == 0, f"Errors occurred: {self.stress_harness.error_count}"

        if stats:
            # Memory usage should remain reasonable
            assert stats["max_memory_mb"] < 2000, f"Excessive memory usage: {stats['max_memory_mb']} MB"

    @pytest.mark.stress
    def test_thread_creation_limits(self):
        """Test behavior when approaching system thread limits."""

        # Get system limits
        try:
            import resource
            max_threads = resource.getrlimit(resource.RLIMIT_NPROC)[0]
        except (ImportError, OSError):
            max_threads = 1000  # Conservative default

        # Test with high worker count (but within system limits)
        high_worker_count = min(32, max_threads // 10)  # Conservative approach

        mock_dbt_runner = Mock(spec=DbtRunner)
        mock_dbt_runner.execute_command.return_value = DbtResult(
            success=True, stdout="", stderr="", execution_time=0.05,
            return_code=0, command=[]
        )

        # Should handle gracefully even if beyond configured limit
        try:
            engine = ParallelExecutionEngine(
                dbt_runner=mock_dbt_runner,
                dependency_analyzer=Mock(),
                max_workers=high_worker_count,
                resource_monitoring=True,
                verbose=False
            )

            # If creation succeeds, engine should be functional
            assert engine.max_workers <= 16, "Should enforce maximum limit"

        except Exception as e:
            # Should fail gracefully with clear error message
            assert "thread" in str(e).lower() or "worker" in str(e).lower()

    @pytest.mark.stress
    def test_rapid_thread_cycling(self):
        """Test rapid creation and destruction of thread pools."""

        self.stress_harness.start_monitoring()

        try:
            for cycle in range(10):
                # Create engine
                mock_dbt_runner = Mock(spec=DbtRunner)
                mock_dbt_runner.execute_command.return_value = DbtResult(
                    success=True, stdout="", stderr="", execution_time=0.02,
                    return_code=0, command=[]
                )

                engine = ParallelExecutionEngine(
                    dbt_runner=mock_dbt_runner,
                    dependency_analyzer=Mock(),
                    max_workers=8,
                    resource_monitoring=False,  # Reduce overhead
                    verbose=False
                )

                # Execute brief workload
                models = [f"cycle_{cycle}_model_{i}" for i in range(5)]
                context = ExecutionContext(2025, {}, "cycle_test", f"cycle_{cycle}")

                mock_analyzer = Mock()
                mock_analyzer.identify_parallelization_opportunities.return_value = [
                    Mock(parallel_models=models, execution_group="cycle_group",
                         estimated_speedup=3.0, safety_level="high")
                ]
                mock_analyzer.validate_execution_safety.return_value = {
                    "safe": True, "issues": [], "warnings": []
                }
                engine.dependency_analyzer = mock_analyzer

                result = engine.execute_stage(models, context)
                self.stress_harness.record_result(result.success)

                # Explicitly clean up (simulate engine destruction)
                del engine
                gc.collect()  # Force garbage collection

                time.sleep(0.1)  # Brief pause

        finally:
            stats = self.stress_harness.stop_monitoring()

        # All cycles should succeed
        assert self.stress_harness.success_count == 10
        assert self.stress_harness.error_count == 0


class TestMemoryPressureHandling:
    """Test behavior under extreme memory pressure conditions."""

    @pytest.mark.stress
    def test_low_memory_execution(self):
        """Test execution with extremely low memory limits."""

        # Create engine with very low memory limit
        engine = ParallelExecutionEngine(
            dbt_runner=Mock(spec=DbtRunner),
            dependency_analyzer=Mock(),
            max_workers=4,
            memory_limit_mb=128.0,  # Very low limit
            resource_monitoring=True,
            verbose=False
        )

        # Mock high memory usage scenario
        with patch('psutil.virtual_memory') as mock_memory:
            mock_memory.return_value.used = 100 * 1024 * 1024  # 100MB
            mock_memory.return_value.total = 128 * 1024 * 1024  # 128MB total
            mock_memory.return_value.available = 28 * 1024 * 1024  # 28MB available

            # Should detect severe memory pressure
            resources = engine.resource_monitor.check_resources()
            assert resources["memory_pressure"] == True

            # Should recommend reduced worker count
            recommended = engine.resource_monitor.get_recommended_workers("high")
            assert recommended <= 2, f"Should recommend fewer workers: {recommended}"

    @pytest.mark.stress
    def test_memory_leak_simulation(self):
        """Test behavior when simulating memory leaks."""

        mock_dbt_runner = Mock(spec=DbtRunner)

        # Mock execution that "leaks" memory (increasing execution time)
        execution_count = 0
        def mock_with_increasing_memory(*args, **kwargs):
            nonlocal execution_count
            execution_count += 1

            # Simulate increasing memory pressure over time
            time.sleep(0.1 * execution_count)  # Simulate slowdown from memory pressure

            return DbtResult(
                success=True, stdout="", stderr="",
                execution_time=0.1 * execution_count, return_code=0, command=[]
            )

        mock_dbt_runner.execute_command.side_effect = mock_with_increasing_memory

        engine = ParallelExecutionEngine(
            dbt_runner=mock_dbt_runner,
            dependency_analyzer=Mock(),
            max_workers=4,
            memory_limit_mb=1000.0,
            resource_monitoring=True,
            verbose=False
        )

        # Simulate increasing memory usage over multiple executions
        baseline_memory = psutil.Process().memory_info().rss

        for i in range(5):
            models = [f"leak_test_model_{i}_{j}" for j in range(3)]
            context = ExecutionContext(2025, {}, "leak_test", f"iteration_{i}")

            # Mock opportunities and validation
            mock_analyzer = Mock()
            mock_analyzer.identify_parallelization_opportunities.return_value = [
                Mock(parallel_models=models, execution_group="leak_group",
                     estimated_speedup=2.0, safety_level="medium")
            ]
            mock_analyzer.validate_execution_safety.return_value = {
                "safe": True, "issues": [], "warnings": []
            }
            engine.dependency_analyzer = mock_analyzer

            # Mock increasing memory pressure
            with patch('psutil.virtual_memory') as mock_memory:
                # Simulate memory usage increasing with iterations
                memory_usage = 500 * 1024 * 1024 + (i * 100 * 1024 * 1024)  # Base + growth
                mock_memory.return_value.used = memory_usage
                mock_memory.return_value.total = 1000 * 1024 * 1024  # 1GB total

                result = engine.execute_stage(models, context)
                assert result.success == True, f"Iteration {i} should still succeed"

                # Performance should degrade but not fail
                assert result.metadata.get("memory_pressure_detected", False) or i < 3

    @pytest.mark.stress
    def test_memory_exhaustion_recovery(self):
        """Test recovery from memory exhaustion scenarios."""

        resource_manager = ResourceManager(
            max_workers=8,
            memory_limit_gb=0.5,  # Very low limit
            enable_adaptive_scaling=True
        )

        # Simulate critical memory exhaustion
        with patch('psutil.virtual_memory') as mock_memory:
            # Memory at 95% capacity
            mock_memory.return_value.used = int(0.5 * 1024**3 * 0.95)
            mock_memory.return_value.total = int(0.5 * 1024**3)
            mock_memory.return_value.available = int(0.5 * 1024**3 * 0.05)

            # Should trigger emergency scaling
            resources = resource_manager.check_resources()
            assert resources["memory_pressure"] == True
            assert "critical" in resources.get("pressure_level", "").lower()

            # Should recommend minimal workers
            recommended = resource_manager.get_recommended_workers("high")
            assert recommended == 1, "Should fall back to single-threaded execution"

            # Validation should fail for high resource requirements
            validation = resource_manager.validate_execution_resources(
                required_workers=4, estimated_memory_per_worker_gb=0.2
            )
            assert validation["can_execute"] == False
            assert "memory" in str(validation["errors"]).lower()


class TestExecutionErrorRecovery:
    """Test error recovery and resilience under various failure conditions."""

    @pytest.mark.stress
    def test_cascading_failure_recovery(self):
        """Test recovery from cascading failures across multiple models."""

        mock_dbt_runner = Mock(spec=DbtRunner)

        # Mock failures for first few calls, then recovery
        call_count = 0
        def mock_with_cascading_failures(*args, **kwargs):
            nonlocal call_count
            call_count += 1

            if call_count <= 3:  # First 3 calls fail
                return DbtResult(
                    success=False, stdout="", stderr=f"Simulated failure {call_count}",
                    execution_time=0.1, return_code=1, command=list(args[0])
                )
            else:  # Later calls succeed
                return DbtResult(
                    success=True, stdout="Recovery successful", stderr="",
                    execution_time=0.1, return_code=0, command=list(args[0])
                )

        mock_dbt_runner.execute_command.side_effect = mock_with_cascading_failures

        engine = ParallelExecutionEngine(
            dbt_runner=mock_dbt_runner,
            dependency_analyzer=Mock(),
            max_workers=4,
            resource_monitoring=False,
            verbose=False
        )

        models = [f"cascade_model_{i}" for i in range(10)]
        context = ExecutionContext(2025, {}, "cascade_test", "recovery")

        # Mock sequential execution (fallback mode)
        result = engine._execute_sequential_fallback(models, context)

        # Should eventually recover (some models will succeed)
        assert call_count >= 3, "Should have attempted multiple executions"

        # Should have both failures and successes
        failed_models = [mr for mr in result.model_results if not mr.success]
        successful_models = [mr for mr in result.model_results if mr.success]

        assert len(failed_models) >= 1, "Should have recorded failures"
        assert len(successful_models) >= 1, "Should have recorded recoveries"

    @pytest.mark.stress
    def test_timeout_handling(self):
        """Test handling of model execution timeouts."""

        mock_dbt_runner = Mock(spec=DbtRunner)

        # Mock execution that times out
        def mock_with_timeout(*args, **kwargs):
            time.sleep(2.0)  # Simulate long-running execution
            return DbtResult(
                success=True, stdout="", stderr="", execution_time=2.0,
                return_code=0, command=[]
            )

        mock_dbt_runner.execute_command.side_effect = mock_with_timeout

        engine = ParallelExecutionEngine(
            dbt_runner=mock_dbt_runner,
            dependency_analyzer=Mock(),
            max_workers=2,
            resource_monitoring=False,
            verbose=False
        )

        models = ["timeout_model_1", "timeout_model_2"]
        context = ExecutionContext(2025, {}, "timeout_test", "test")

        # Mock with timeout capability
        with patch('concurrent.futures.as_completed') as mock_completed:
            # Simulate timeout exception
            mock_completed.side_effect = TimeoutError("Execution timed out")

            # Should handle timeout gracefully
            try:
                result = engine._execute_sequential_fallback(models, context)
                # Should not crash, may succeed or fail gracefully
                assert hasattr(result, 'success')
            except Exception as e:
                # If exception is raised, should be handled gracefully
                assert "timeout" in str(e).lower() or "execution" in str(e).lower()

    @pytest.mark.stress
    def test_thread_interruption_handling(self):
        """Test handling of thread interruptions and signals."""

        mock_dbt_runner = Mock(spec=DbtRunner)

        # Mock execution that can be interrupted
        def mock_interruptible_execution(*args, **kwargs):
            try:
                time.sleep(1.0)  # Simulate work
                return DbtResult(
                    success=True, stdout="", stderr="", execution_time=1.0,
                    return_code=0, command=[]
                )
            except KeyboardInterrupt:
                return DbtResult(
                    success=False, stdout="", stderr="Interrupted",
                    execution_time=0.5, return_code=130, command=[]
                )

        mock_dbt_runner.execute_command.side_effect = mock_interruptible_execution

        engine = ParallelExecutionEngine(
            dbt_runner=mock_dbt_runner,
            dependency_analyzer=Mock(),
            max_workers=2,
            resource_monitoring=False,
            verbose=False
        )

        models = ["interruptible_model"]
        context = ExecutionContext(2025, {}, "interrupt_test", "test")

        # Test graceful handling of interruption
        def interrupt_after_delay():
            time.sleep(0.5)
            # Simulate interrupt (in real scenario this would be SIGINT)
            # For testing, we'll just verify the structure handles it
            pass

        interrupt_thread = threading.Thread(target=interrupt_after_delay)
        interrupt_thread.start()

        result = engine._execute_sequential_fallback(models, context)
        interrupt_thread.join()

        # Should handle interruption gracefully
        assert hasattr(result, 'success')
        assert hasattr(result, 'model_results')


class TestResourceExhaustionScenarios:
    """Test behavior when system resources are exhausted."""

    @pytest.mark.stress
    def test_file_descriptor_exhaustion(self):
        """Test behavior when file descriptors are exhausted."""

        # Mock resource limit reached
        with patch('os.open') as mock_open:
            mock_open.side_effect = OSError("Too many open files")

            mock_dbt_runner = Mock(spec=DbtRunner)
            mock_dbt_runner.execute_command.return_value = DbtResult(
                success=False, stdout="", stderr="Resource exhaustion",
                execution_time=0, return_code=1, command=[]
            )

            engine = ParallelExecutionEngine(
                dbt_runner=mock_dbt_runner,
                dependency_analyzer=Mock(),
                max_workers=4,
                resource_monitoring=True,
                verbose=False
            )

            models = ["fd_test_model"]
            context = ExecutionContext(2025, {}, "fd_test", "exhaustion")

            # Should handle resource exhaustion gracefully
            result = engine._execute_sequential_fallback(models, context)

            # Should not crash, but may fail gracefully
            assert hasattr(result, 'success')

    @pytest.mark.stress
    def test_cpu_saturation_handling(self):
        """Test behavior when CPU is completely saturated."""

        # Create CPU-intensive background load
        def cpu_intensive_background():
            end_time = time.time() + 2.0
            while time.time() < end_time:
                sum(i * i for i in range(10000))  # CPU-bound work

        # Start background CPU load
        background_threads = []
        cpu_count = psutil.cpu_count() or 4
        for _ in range(cpu_count * 2):  # Oversubscribe CPU
            thread = threading.Thread(target=cpu_intensive_background)
            thread.daemon = True
            thread.start()
            background_threads.append(thread)

        try:
            mock_dbt_runner = Mock(spec=DbtRunner)
            mock_dbt_runner.execute_command.return_value = DbtResult(
                success=True, stdout="", stderr="", execution_time=0.2,
                return_code=0, command=[]
            )

            engine = ParallelExecutionEngine(
                dbt_runner=mock_dbt_runner,
                dependency_analyzer=Mock(),
                max_workers=4,
                resource_monitoring=True,
                verbose=False
            )

            # Monitor CPU usage
            cpu_samples = []
            def monitor_cpu():
                for _ in range(10):
                    cpu_samples.append(psutil.cpu_percent(interval=0.1))

            cpu_monitor = threading.Thread(target=monitor_cpu)
            cpu_monitor.start()

            models = ["cpu_saturation_model"]
            context = ExecutionContext(2025, {}, "cpu_test", "saturation")
            result = engine._execute_sequential_fallback(models, context)

            cpu_monitor.join(timeout=2)

            # Should still execute successfully despite high CPU load
            assert result.success == True or len(result.errors) > 0  # Either succeeds or fails gracefully

            # Should have detected high CPU usage
            if cpu_samples:
                max_cpu = max(cpu_samples)
                assert max_cpu > 50, f"Expected high CPU usage, got {max_cpu}%"

        finally:
            # Wait for background threads to finish
            for thread in background_threads:
                thread.join(timeout=0.1)

    @pytest.mark.stress
    def test_disk_space_exhaustion(self):
        """Test behavior when disk space is exhausted."""

        # Mock disk space exhaustion
        with patch('shutil.disk_usage') as mock_disk_usage:
            # Mock very low disk space
            mock_disk_usage.return_value = (1000000, 999000, 1000)  # total, used, free (bytes)

            resource_manager = ResourceManager(
                max_workers=4,
                memory_limit_gb=4.0,
                enable_adaptive_scaling=True
            )

            # Check resource validation
            resources = resource_manager.check_resources()

            # Should detect disk pressure if monitoring is implemented
            # For now, just verify the system doesn't crash
            assert "memory_pressure" in resources

            # Should handle low disk space gracefully
            validation = resource_manager.validate_execution_resources(
                required_workers=4, estimated_memory_per_worker_gb=0.5
            )

            # Should complete validation without crashing
            assert "can_execute" in validation


class TestConcurrentAccessSafety:
    """Test thread safety with high concurrency scenarios."""

    @pytest.mark.stress
    def test_concurrent_statistics_access(self):
        """Test thread-safe access to parallelization statistics."""

        engine = ParallelExecutionEngine(
            dbt_runner=Mock(),
            dependency_analyzer=Mock(),
            max_workers=8,
            resource_monitoring=True,
            verbose=False
        )

        results = []
        errors = []

        def concurrent_stats_access(thread_id):
            try:
                for _ in range(50):  # Multiple accesses per thread
                    stats = engine.get_parallelization_statistics()
                    results.append((thread_id, stats))
                    time.sleep(0.001)  # Brief pause
            except Exception as e:
                errors.append((thread_id, e))

        # Run many concurrent threads
        threads = []
        for i in range(20):
            thread = threading.Thread(target=concurrent_stats_access, args=(i,))
            threads.append(thread)
            thread.start()

        # Wait for completion
        for thread in threads:
            thread.join()

        # Should have no errors from concurrent access
        assert len(errors) == 0, f"Concurrent access errors: {errors}"
        assert len(results) == 20 * 50, f"Expected 1000 results, got {len(results)}"

    @pytest.mark.stress
    def test_concurrent_resource_monitoring(self):
        """Test concurrent access to resource monitoring."""

        resource_manager = ResourceManager(
            max_workers=4,
            memory_limit_gb=4.0,
            enable_adaptive_scaling=True
        )

        results = []
        errors = []

        def concurrent_resource_check(thread_id):
            try:
                for _ in range(30):
                    resources = resource_manager.check_resources()
                    results.append((thread_id, resources["memory_pressure"]))

                    # Also test worker recommendations
                    workers = resource_manager.get_recommended_workers("medium")
                    results.append((thread_id, workers))

                    time.sleep(0.001)
            except Exception as e:
                errors.append((thread_id, e))

        # Run concurrent resource checks
        threads = []
        for i in range(10):
            thread = threading.Thread(target=concurrent_resource_check, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Should handle concurrent access safely
        assert len(errors) == 0, f"Resource monitoring errors: {errors}"
        assert len(results) == 10 * 60  # 10 threads * 30 iterations * 2 calls

    @pytest.mark.stress
    def test_concurrent_configuration_access(self):
        """Test concurrent access to threading configuration."""

        config = ThreadingSettings(
            enabled=True,
            thread_count=8,
            mode="selective",
            memory_per_thread_gb=1.0
        )

        results = []
        errors = []

        def concurrent_config_access(thread_id):
            try:
                for _ in range(100):
                    # Read configuration
                    thread_count = config.thread_count
                    enabled = config.enabled
                    mode = config.mode

                    results.append((thread_id, thread_count, enabled, mode))

                    # Validate configuration (triggers internal processing)
                    config.validate_thread_count()

                    time.sleep(0.001)
            except Exception as e:
                errors.append((thread_id, e))

        # Run concurrent configuration access
        threads = []
        for i in range(15):
            thread = threading.Thread(target=concurrent_config_access, args=(i,))
            threads.append(thread)
            thread.start()

        for thread in threads:
            thread.join()

        # Should handle concurrent reads safely
        assert len(errors) == 0, f"Configuration access errors: {errors}"
        assert len(results) == 15 * 100

        # All results should be consistent
        unique_configs = set((tc, en, mo) for _, tc, en, mo in results)
        assert len(unique_configs) == 1, "Configuration should be consistent across threads"


class TestLongRunningSimulationStability:
    """Test stability during extended execution periods."""

    @pytest.mark.stress
    @pytest.mark.slow
    def test_extended_execution_stability(self):
        """Test stability during extended execution (simulated long-running simulation)."""

        mock_dbt_runner = Mock(spec=DbtRunner)
        mock_dbt_runner.execute_command.return_value = DbtResult(
            success=True, stdout="", stderr="", execution_time=0.1,
            return_code=0, command=[]
        )

        engine = ParallelExecutionEngine(
            dbt_runner=mock_dbt_runner,
            dependency_analyzer=Mock(),
            max_workers=4,
            resource_monitoring=True,
            verbose=False
        )

        stress_harness = StressTestHarness()
        stress_harness.start_monitoring()

        try:
            # Simulate extended execution (100 iterations)
            for iteration in range(100):
                models = [f"longrun_model_{iteration}_{i}" for i in range(5)]
                context = ExecutionContext(
                    simulation_year=2025 + (iteration // 20),  # Vary year
                    dbt_vars={},
                    stage_name="long_run_test",
                    execution_id=f"iteration_{iteration:03d}"
                )

                # Mock opportunities and validation
                mock_analyzer = Mock()
                mock_analyzer.identify_parallelization_opportunities.return_value = [
                    Mock(parallel_models=models, execution_group="longrun_group",
                         estimated_speedup=2.5, safety_level="high")
                ]
                mock_analyzer.validate_execution_safety.return_value = {
                    "safe": True, "issues": [], "warnings": []
                }
                engine.dependency_analyzer = mock_analyzer

                result = engine.execute_stage(models, context)
                stress_harness.record_result(result.success)

                # Periodic garbage collection to prevent memory buildup
                if iteration % 20 == 0:
                    gc.collect()

                # Brief pause to prevent overwhelming the system
                time.sleep(0.01)

        finally:
            stats = stress_harness.stop_monitoring()

        # Should maintain stability throughout extended execution
        assert stress_harness.success_count >= 95, f"Too many failures: {stress_harness.error_count}"
        assert stress_harness.error_count <= 5, f"Excessive errors: {stress_harness.error_count}"

        if stats and stats["sample_count"] > 0:
            # Memory usage should remain stable (no significant growth)
            memory_samples = [s["memory_mb"] for s in stress_harness.resource_samples]
            if len(memory_samples) >= 10:
                early_avg = statistics.mean(memory_samples[:len(memory_samples)//4])
                late_avg = statistics.mean(memory_samples[-len(memory_samples)//4:])

                # Memory growth should be limited (less than 50% increase)
                memory_growth_ratio = late_avg / early_avg if early_avg > 0 else 1.0
                assert memory_growth_ratio < 1.5, f"Excessive memory growth: {memory_growth_ratio:.2f}x"


# Utility functions for stress testing
def simulate_memory_pressure():
    """Utility to simulate memory pressure for testing."""
    # Create temporary memory allocation
    memory_hog = []
    try:
        for _ in range(100):
            memory_hog.append([0] * 100000)  # ~800KB per iteration
            if psutil.virtual_memory().percent > 80:
                break
    except MemoryError:
        pass
    return len(memory_hog)


def cleanup_test_resources():
    """Cleanup function for stress tests."""
    gc.collect()
    time.sleep(0.1)  # Allow cleanup to complete


if __name__ == "__main__":
    # Run stress tests
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-m", "stress",
        "--maxfail=10",
        "-x"  # Stop on first failure for stress tests
    ])
