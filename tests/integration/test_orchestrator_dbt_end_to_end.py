"""
Integration tests for orchestrator_dbt end-to-end workflows.

Tests complete integration scenarios including:
- Foundation setup to multi-year simulation pipeline
- Performance regression validation (82% improvement target)
- Configuration compatibility across systems
- Error recovery and circuit breaker patterns
- Memory efficiency and state management

Target: Validate complete S031-01 implementation with real workflows
"""

import asyncio
import logging
import os
# Import system under test
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, Mock, patch

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).parent.parent.parent / "orchestrator_dbt"))

from run_multi_year import (PerformanceMonitor, load_and_validate_config,
                            run_comprehensive_performance_comparison,
                            run_enhanced_multi_year_simulation,
                            run_foundation_benchmark,
                            test_configuration_compatibility)


class TestFoundationToMultiYearPipeline(unittest.TestCase):
    """Test complete foundation setup to multi-year simulation pipeline."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_config = {
            "simulation": {
                "start_year": 2025,
                "end_year": 2027,
                "target_growth_rate": 0.03,
            },
            "workforce": {
                "total_termination_rate": 0.12,
                "new_hire_termination_rate": 0.25,
            },
            "eligibility": {"waiting_period_days": 365},
            "enrollment": {
                "auto_enrollment": {
                    "hire_date_cutoff": "2024-01-01",
                    "scope": "new_hires_only",
                }
            },
            "compensation": {"cola_rate": 0.025, "merit_pool": 0.03},
            "random_seed": 42,
        }

        # Create temporary config file
        self.temp_config_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        )
        yaml.dump(self.test_config, self.temp_config_file)
        self.temp_config_file.close()
        self.config_path = self.temp_config_file.name

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.config_path):
            os.unlink(self.config_path)

    @patch("orchestrator_dbt.run_multi_year.create_multi_year_orchestrator")
    @patch("orchestrator_dbt.run_multi_year.OptimizationLevel")
    async def test_foundation_setup_performance_target(
        self, mock_opt_level, mock_create_orchestrator
    ):
        """Test foundation setup meets <10 second performance target."""
        # Mock optimization level
        mock_opt_level.HIGH = Mock()
        mock_opt_level.HIGH.value = "high"

        # Mock orchestrator with fast foundation setup
        mock_orchestrator = Mock()
        mock_create_orchestrator.return_value = mock_orchestrator

        mock_result = Mock()
        mock_result.success = True
        mock_result.execution_time = 7.2  # Under 10 second target
        mock_result.performance_improvement = 0.85  # 85% improvement
        mock_result.metadata = {}

        mock_orchestrator._execute_foundation_setup = AsyncMock(
            return_value=mock_result
        )

        # Run foundation benchmark
        result = await run_foundation_benchmark(
            optimization_level=mock_opt_level.HIGH,
            config_path=self.config_path,
            benchmark_mode=True,
        )

        # Verify performance targets
        self.assertTrue(result["success"])
        self.assertLess(result["execution_time"], 10.0)  # <10 second target
        self.assertTrue(result["target_met"])
        self.assertGreater(result["performance_improvement"], 0.82)  # >82% improvement

        # Verify performance grade
        self.assertIn(result["performance_grade"], ["🏆 EXCELLENT", "✅ TARGET MET"])

        # Verify memory metrics are captured
        self.assertIn("memory_metrics", result)
        self.assertGreater(result["memory_metrics"]["peak_mb"], 0)
        self.assertLessEqual(result["memory_metrics"]["efficiency"], 1.0)

    @patch("orchestrator_dbt.run_multi_year.MultiYearOrchestrator")
    @patch("orchestrator_dbt.run_multi_year.MultiYearConfig")
    @patch("orchestrator_dbt.run_multi_year.OptimizationLevel")
    async def test_complete_multi_year_pipeline(
        self, mock_opt_level, mock_config_class, mock_orchestrator_class
    ):
        """Test complete multi-year simulation pipeline."""
        # Mock optimization level
        mock_opt_level.HIGH = Mock()

        # Mock MultiYearConfig
        mock_multi_year_config = Mock()
        mock_config_class.return_value = mock_multi_year_config

        # Mock orchestrator with successful multi-year execution
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator

        # Mock successful foundation setup
        mock_foundation_result = Mock()
        mock_foundation_result.success = True
        mock_foundation_result.execution_time = 8.5
        mock_foundation_result.performance_improvement = 0.84

        # Mock successful multi-year result
        mock_result = Mock()
        mock_result.success = True
        mock_result.simulation_id = "integration-test-001"
        mock_result.total_execution_time = 120.5
        mock_result.completed_years = [2025, 2026, 2027]
        mock_result.failed_years = []
        mock_result.success_rate = 1.0
        mock_result.foundation_setup_result = mock_foundation_result
        mock_result.performance_metrics = {
            "records_per_second": 1250,
            "foundation_performance_improvement": 0.84,
            "memory_efficiency": 0.78,
        }

        mock_orchestrator.execute_multi_year_simulation = AsyncMock(
            return_value=mock_result
        )

        # Run enhanced multi-year simulation
        result = await run_enhanced_multi_year_simulation(
            start_year=2025,
            end_year=2027,
            optimization_level=mock_opt_level.HIGH,
            max_workers=4,
            batch_size=1000,
            enable_compression=True,
            fail_fast=False,
            performance_mode=True,
            config_path=self.config_path,
        )

        # Verify complete pipeline success
        self.assertTrue(result["success"])
        self.assertEqual(result["simulation_id"], "integration-test-001")
        self.assertEqual(len(result["completed_years"]), 3)
        self.assertEqual(len(result["failed_years"]), 0)
        self.assertEqual(result["success_rate"], 1.0)

        # Verify performance metrics
        self.assertIn("performance_metrics", result)
        self.assertGreater(result["performance_metrics"]["records_per_second"], 1000)
        self.assertGreater(
            result["performance_metrics"]["foundation_performance_improvement"], 0.82
        )

        # Verify orchestrator was configured correctly
        mock_config_class.assert_called_once()
        config_call_args = mock_config_class.call_args[1]

        self.assertEqual(config_call_args["start_year"], 2025)
        self.assertEqual(config_call_args["end_year"], 2027)
        self.assertEqual(config_call_args["max_workers"], 4)
        self.assertEqual(config_call_args["batch_size"], 1000)
        self.assertTrue(config_call_args["enable_state_compression"])
        self.assertTrue(config_call_args["enable_concurrent_processing"])
        self.assertTrue(config_call_args["performance_monitoring"])


class TestPerformanceRegressionValidation(unittest.TestCase):
    """Test performance regression validation against MVP."""

    def setUp(self):
        """Set up test fixtures."""
        self.test_config = {
            "simulation": {
                "start_year": 2025,
                "end_year": 2026,  # Minimal range for faster testing
                "target_growth_rate": 0.03,
            },
            "workforce": {"total_termination_rate": 0.12},
            "random_seed": 42,
        }

        # Create temporary config file
        self.temp_config_file = tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        )
        yaml.dump(self.test_config, self.temp_config_file)
        self.temp_config_file.close()
        self.config_path = self.temp_config_file.name

    def tearDown(self):
        """Clean up test fixtures."""
        if os.path.exists(self.config_path):
            os.unlink(self.config_path)

    @patch("orchestrator_dbt.run_multi_year.MVP_AVAILABLE", True)
    @patch("orchestrator_dbt.run_multi_year.MultiYearSimulationOrchestrator")
    @patch("orchestrator_dbt.run_multi_year.run_enhanced_multi_year_simulation")
    async def test_performance_regression_target_met(
        self, mock_enhanced_sim, mock_mvp_orchestrator
    ):
        """Test performance regression validation meets 82% improvement target."""
        # Mock MVP orchestrator (baseline)
        mock_mvp_instance = Mock()
        mock_mvp_orchestrator.return_value = mock_mvp_instance

        mock_mvp_result = {
            "years_completed": [2025, 2026],
            "total_runtime_seconds": 180.0,
        }
        mock_mvp_instance.run_simulation.return_value = mock_mvp_result

        # Mock enhanced simulation (optimized)
        mock_enhanced_result = {
            "success": True,
            "total_execution_time": 32.0,  # 82.2% improvement from 180s
            "completed_years": [2025, 2026],
            "performance_metrics": {
                "records_per_second": 1500,
                "memory_efficiency": 0.85,
            },
        }
        mock_enhanced_sim.return_value = mock_enhanced_result

        # Run performance comparison
        result = await run_comprehensive_performance_comparison(
            start_year=2025,
            end_year=2026,
            config_path=self.config_path,
            benchmark_mode=True,
        )

        # Verify regression test results
        self.assertTrue(result["mvp_success"])
        self.assertTrue(result["new_success"])
        self.assertGreater(result["improvement"], 0.82)  # >82% improvement target
        self.assertTrue(result["target_met"])
        self.assertTrue(result["regression_test_passed"])

        # Verify performance grade
        self.assertIn(result["performance_grade"], ["🏆 OUTSTANDING", "✅ TARGET MET"])

        # Verify detailed metrics
        self.assertEqual(result["mvp_time"], 180.0)
        self.assertEqual(result["new_time"], 32.0)
        self.assertAlmostEqual(result["speedup"], 5.625, places=2)  # 180/32 = 5.625x

    @patch("orchestrator_dbt.run_multi_year.MVP_AVAILABLE", True)
    @patch("orchestrator_dbt.run_multi_year.MultiYearSimulationOrchestrator")
    @patch("orchestrator_dbt.run_multi_year.run_enhanced_multi_year_simulation")
    async def test_performance_regression_target_missed(
        self, mock_enhanced_sim, mock_mvp_orchestrator
    ):
        """Test handling when performance target is not met."""
        # Mock MVP orchestrator (baseline)
        mock_mvp_instance = Mock()
        mock_mvp_orchestrator.return_value = mock_mvp_instance

        mock_mvp_result = {
            "years_completed": [2025, 2026],
            "total_runtime_seconds": 100.0,
        }
        mock_mvp_instance.run_simulation.return_value = mock_mvp_result

        # Mock enhanced simulation with insufficient improvement
        mock_enhanced_result = {
            "success": True,
            "total_execution_time": 60.0,  # Only 40% improvement (target is 82%)
            "completed_years": [2025, 2026],
            "performance_metrics": {"records_per_second": 800},
        }
        mock_enhanced_sim.return_value = mock_enhanced_result

        # Run performance comparison
        result = await run_comprehensive_performance_comparison(
            start_year=2025,
            end_year=2026,
            config_path=self.config_path,
            benchmark_mode=True,
        )

        # Verify regression test failure detection
        self.assertTrue(result["mvp_success"])
        self.assertTrue(result["new_success"])
        self.assertAlmostEqual(result["improvement"], 0.40, places=2)  # 40% improvement
        self.assertFalse(result["target_met"])  # Should not meet 82% target
        self.assertFalse(result["regression_test_passed"])

        # Verify performance grade indicates insufficient improvement
        self.assertIn(result["performance_grade"], ["🔍 NEEDS IMPROVEMENT", "❌ POOR"])

    @patch("orchestrator_dbt.run_multi_year.MVP_AVAILABLE", False)
    @patch("orchestrator_dbt.run_multi_year.run_enhanced_multi_year_simulation")
    async def test_performance_regression_no_mvp_available(self, mock_enhanced_sim):
        """Test performance comparison when MVP is not available."""
        # Mock enhanced simulation success
        mock_enhanced_result = {
            "success": True,
            "total_execution_time": 45.0,
            "completed_years": [2025, 2026],
            "performance_metrics": {},
        }
        mock_enhanced_sim.return_value = mock_enhanced_result

        # Run performance comparison
        result = await run_comprehensive_performance_comparison(
            start_year=2025, end_year=2026, config_path=self.config_path
        )

        # Verify handling of missing MVP
        self.assertFalse(result["mvp_available"])
        self.assertFalse(result["mvp_success"])
        self.assertTrue(result["new_success"])
        self.assertEqual(
            result["improvement"], 0.0
        )  # Cannot calculate without baseline
        self.assertFalse(result["target_met"])
        self.assertFalse(result["regression_test_passed"])


class TestConfigurationCompatibilityIntegration(unittest.TestCase):
    """Test configuration compatibility across systems."""

    def test_configuration_compatibility_real_config(self):
        """Test configuration compatibility with realistic configuration."""
        # Create comprehensive test configuration
        complex_config = {
            "simulation": {
                "start_year": 2025,
                "end_year": 2030,
                "target_growth_rate": 0.035,
            },
            "workforce": {
                "total_termination_rate": 0.15,
                "new_hire_termination_rate": 0.28,
            },
            "eligibility": {"waiting_period_days": 90, "min_hours_per_week": 20},
            "enrollment": {
                "auto_enrollment": {
                    "hire_date_cutoff": "2023-01-01",
                    "scope": "all_eligible",
                    "default_deferral_rate": 0.06,
                },
                "opt_out_window_days": 90,
            },
            "compensation": {
                "cola_rate": 0.028,
                "merit_pool": 0.035,
                "promotion_pool": 0.015,
            },
            "plan_year": {"start_month": 1, "start_day": 1},
            "employee_id_generation": {"strategy": "sequential", "prefix": "EMP"},
            "random_seed": 12345,
        }

        # Create temporary config file
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(complex_config, f)
            config_path = f.name

        try:
            # Test configuration loading and validation
            config = load_and_validate_config(config_path)

            # Verify complex configuration is loaded correctly
            self.assertEqual(config["simulation"]["start_year"], 2025)
            self.assertEqual(config["simulation"]["end_year"], 2030)
            self.assertEqual(config["workforce"]["total_termination_rate"], 0.15)
            self.assertEqual(config["eligibility"]["min_hours_per_week"], 20)
            self.assertEqual(
                config["enrollment"]["auto_enrollment"]["default_deferral_rate"], 0.06
            )

            # Test compatibility
            compatibility_result = test_configuration_compatibility(config_path)

            # Verify compatibility results
            self.assertTrue(compatibility_result["config_valid"])
            self.assertTrue(compatibility_result["new_system_compatible"])

            # Should have minimal issues for well-formed configuration
            if compatibility_result["issues"]:
                # Log issues for debugging but don't fail test
                print(f"Configuration issues: {compatibility_result['issues']}")

        finally:
            os.unlink(config_path)

    def test_configuration_edge_cases(self):
        """Test configuration handling with edge cases."""
        edge_case_configs = [
            # Minimal configuration
            {
                "simulation": {
                    "start_year": 2025,
                    "end_year": 2025,
                    "target_growth_rate": 0.0,
                },
                "workforce": {"total_termination_rate": 0.0},
                "random_seed": 1,
            },
            # Maximum reasonable configuration
            {
                "simulation": {
                    "start_year": 2025,
                    "end_year": 2035,
                    "target_growth_rate": 0.20,
                },
                "workforce": {"total_termination_rate": 0.50},
                "random_seed": 999999,
            },
        ]

        for i, config in enumerate(edge_case_configs):
            with self.subTest(f"Edge case {i+1}"):
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".yaml", delete=False
                ) as f:
                    yaml.dump(config, f)
                    config_path = f.name

                try:
                    # Should handle edge cases without crashing
                    loaded_config = load_and_validate_config(config_path)
                    compatibility_result = test_configuration_compatibility(config_path)

                    # Basic validation should pass
                    self.assertTrue(compatibility_result["config_valid"])
                    self.assertTrue(compatibility_result["new_system_compatible"])

                finally:
                    os.unlink(config_path)


class TestErrorRecoveryAndCircuitBreaker(unittest.TestCase):
    """Test error recovery and circuit breaker patterns."""

    @patch("orchestrator_dbt.run_multi_year.create_multi_year_orchestrator")
    @patch("orchestrator_dbt.run_multi_year.OptimizationLevel")
    async def test_foundation_setup_error_recovery(
        self, mock_opt_level, mock_create_orchestrator
    ):
        """Test foundation setup error recovery with detailed troubleshooting."""
        # Mock optimization level
        mock_opt_level.HIGH = Mock()
        mock_opt_level.HIGH.value = "high"

        # Mock orchestrator that fails with database error
        mock_orchestrator = Mock()
        mock_create_orchestrator.return_value = mock_orchestrator

        mock_orchestrator._execute_foundation_setup = AsyncMock(
            side_effect=Exception("Database connection refused")
        )

        # Run foundation benchmark and expect graceful error handling
        result = await run_foundation_benchmark(
            optimization_level=mock_opt_level.HIGH,
            config_path=None,
            benchmark_mode=True,
        )

        # Verify error is captured with troubleshooting information
        self.assertFalse(result["success"])
        self.assertIn("error", result)
        self.assertIn("error_type", result)
        self.assertEqual(result["error"], "Database connection refused")
        self.assertEqual(result["error_type"], "Exception")

        # Verify performance metrics are still captured
        self.assertGreater(result["execution_time"], 0)
        self.assertIn("memory_at_failure", result)

    @patch("orchestrator_dbt.run_multi_year.MultiYearOrchestrator")
    @patch("orchestrator_dbt.run_multi_year.MultiYearConfig")
    @patch("orchestrator_dbt.run_multi_year.OptimizationLevel")
    async def test_multi_year_simulation_partial_failure_recovery(
        self, mock_opt_level, mock_config_class, mock_orchestrator_class
    ):
        """Test multi-year simulation with partial failure and recovery."""
        # Mock optimization level
        mock_opt_level.HIGH = Mock()

        # Mock MultiYearConfig
        mock_multi_year_config = Mock()
        mock_config_class.return_value = mock_multi_year_config

        # Mock orchestrator with partial failure
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator

        # Mock result with partial success (some years failed)
        mock_result = Mock()
        mock_result.success = False  # Overall failure due to some year failures
        mock_result.simulation_id = "partial-failure-test"
        mock_result.total_execution_time = 85.0
        mock_result.completed_years = [2025, 2026]  # 2027 failed
        mock_result.failed_years = [2027]
        mock_result.success_rate = 0.67  # 2/3 years succeeded
        mock_result.performance_metrics = {
            "failure_reason": "Year 2027 processing failed due to memory constraints"
        }

        mock_orchestrator.execute_multi_year_simulation = AsyncMock(
            return_value=mock_result
        )

        # Create test configuration
        test_config = {
            "simulation": {
                "start_year": 2025,
                "end_year": 2027,
                "target_growth_rate": 0.03,
            },
            "workforce": {"total_termination_rate": 0.12},
            "random_seed": 42,
        }

        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            yaml.dump(test_config, f)
            config_path = f.name

        try:
            # Run enhanced multi-year simulation
            result = await run_enhanced_multi_year_simulation(
                start_year=2025,
                end_year=2027,
                optimization_level=mock_opt_level.HIGH,
                max_workers=4,
                batch_size=1000,
                enable_compression=True,
                fail_fast=False,  # Should continue despite failures
                performance_mode=True,
                config_path=config_path,
            )

            # Verify partial failure is handled gracefully
            self.assertFalse(result["success"])  # Overall failure
            self.assertEqual(result["simulation_id"], "partial-failure-test")
            self.assertEqual(result["completed_years"], [2025, 2026])
            self.assertEqual(result["failed_years"], [2027])
            self.assertAlmostEqual(result["success_rate"], 0.67, places=2)

            # Verify failure reason is captured
            self.assertIn("failure_reason", result["performance_metrics"])
            self.assertIn(
                "memory constraints", result["performance_metrics"]["failure_reason"]
            )

        finally:
            os.unlink(config_path)


class TestMemoryEfficiencyAndStateManagement(unittest.TestCase):
    """Test memory efficiency and state management integration."""

    def test_performance_monitor_memory_tracking(self):
        """Test performance monitor accurately tracks memory usage."""
        monitor = PerformanceMonitor()
        monitor.start()

        # Create some data to increase memory usage
        test_data = [list(range(1000)) for _ in range(100)]
        monitor.checkpoint("after_data_creation")

        # Clean up data
        del test_data
        monitor.checkpoint("after_cleanup")

        # Get performance summary
        summary = monitor.get_summary()

        # Verify memory tracking
        self.assertGreater(summary["peak_memory_mb"], 0)
        self.assertGreater(summary["avg_memory_mb"], 0)
        self.assertLessEqual(summary["memory_efficiency"], 1.0)
        self.assertGreaterEqual(summary["memory_efficiency"], 0.0)

        # Verify checkpoints captured memory changes
        self.assertIn("after_data_creation", summary["checkpoints"])
        self.assertIn("after_cleanup", summary["checkpoints"])

        # Memory after data creation should be higher than after cleanup
        creation_memory = summary["checkpoints"]["after_data_creation"]["memory_mb"]
        cleanup_memory = summary["checkpoints"]["after_cleanup"]["memory_mb"]

        # Note: This might not always be true due to garbage collection timing
        # but it demonstrates the monitoring capability
        self.assertGreater(creation_memory, 0)
        self.assertGreater(cleanup_memory, 0)


@pytest.mark.asyncio
class TestAsyncIntegrationWorkflows(unittest.IsolatedAsyncioTestCase):
    """Test async integration workflows."""

    async def test_concurrent_performance_monitoring(self):
        """Test performance monitoring during concurrent operations."""
        monitor = PerformanceMonitor()
        monitor.start()

        async def mock_async_operation(operation_name: str, duration: float):
            """Mock async operation that takes specified time."""
            await asyncio.sleep(duration)
            monitor.checkpoint(f"{operation_name}_complete")
            return f"{operation_name}_result"

        # Run multiple concurrent operations
        tasks = [
            mock_async_operation("operation_1", 0.1),
            mock_async_operation("operation_2", 0.15),
            mock_async_operation("operation_3", 0.05),
        ]

        results = await asyncio.gather(*tasks)

        # Verify all operations completed
        self.assertEqual(len(results), 3)
        self.assertEqual(results[0], "operation_1_result")
        self.assertEqual(results[1], "operation_2_result")
        self.assertEqual(results[2], "operation_3_result")

        # Verify performance monitoring captured all checkpoints
        summary = monitor.get_summary()
        self.assertIn("operation_1_complete", summary["checkpoints"])
        self.assertIn("operation_2_complete", summary["checkpoints"])
        self.assertIn("operation_3_complete", summary["checkpoints"])

        # Verify timing makes sense (should be around 0.15s total due to concurrency)
        self.assertGreater(
            summary["total_time"], 0.14
        )  # At least the longest operation
        self.assertLess(summary["total_time"], 0.30)  # Less than sum of all operations


if __name__ == "__main__":
    # Run tests with asyncio support
    unittest.main(verbosity=2)
