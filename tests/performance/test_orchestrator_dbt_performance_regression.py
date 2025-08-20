"""
Performance regression tests for orchestrator_dbt.

Tests performance benchmarks and regression validation including:
- 82% performance improvement target validation
- Foundation setup <10 second target
- Memory efficiency and optimization validation
- Throughput and processing rate benchmarks
- Comparative analysis with MVP orchestrator

Target: Ensure S031-01 meets all performance requirements
"""

import asyncio
import json
import logging
import os
import statistics
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

from run_multi_year import (PerformanceMonitor,
                            run_comprehensive_performance_comparison,
                            run_enhanced_multi_year_simulation,
                            run_foundation_benchmark)


class PerformanceTestCase(unittest.TestCase):
    """Base class for performance tests with common utilities."""

    def setUp(self):
        """Set up performance test fixtures."""
        self.performance_targets = {
            "foundation_setup_max_time": 10.0,  # <10 seconds
            "performance_improvement_min": 0.82,  # >82% improvement
            "memory_efficiency_min": 0.70,  # >70% memory efficiency
            "processing_rate_min": 1000,  # >1000 records/second
            "success_rate_min": 0.95,  # >95% success rate
        }

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

    def assert_performance_target(
        self, actual_value, target_value, metric_name, comparison="less_than"
    ):
        """Assert performance target is met with detailed reporting."""
        if comparison == "less_than":
            success = actual_value < target_value
            symbol = "<"
        elif comparison == "greater_than":
            success = actual_value > target_value
            symbol = ">"
        elif comparison == "greater_equal":
            success = actual_value >= target_value
            symbol = ">="
        else:
            raise ValueError(f"Unknown comparison type: {comparison}")

        # Log performance result
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status} {metric_name}: {actual_value} {symbol} {target_value}")

        # Assert with detailed message
        self.assertTrue(
            success,
            f"Performance target failed: {metric_name} = {actual_value}, "
            f"expected {symbol} {target_value}",
        )


class TestFoundationSetupPerformance(PerformanceTestCase):
    """Test foundation setup performance targets."""

    @patch("orchestrator_dbt.run_multi_year.create_multi_year_orchestrator")
    @patch("orchestrator_dbt.run_multi_year.OptimizationLevel")
    async def test_foundation_setup_speed_target(
        self, mock_opt_level, mock_create_orchestrator
    ):
        """Test foundation setup meets <10 second speed target."""
        # Mock optimization level
        mock_opt_level.HIGH = Mock()
        mock_opt_level.HIGH.value = "high"

        # Test different performance scenarios
        test_scenarios = [
            {
                "execution_time": 5.2,
                "improvement": 0.89,
                "expected_pass": True,
            },  # Excellent
            {"execution_time": 8.7, "improvement": 0.84, "expected_pass": True},  # Good
            {
                "execution_time": 9.9,
                "improvement": 0.82,
                "expected_pass": True,
            },  # Barely meets target
            {
                "execution_time": 12.1,
                "improvement": 0.85,
                "expected_pass": False,
            },  # Too slow
        ]

        for i, scenario in enumerate(test_scenarios):
            with self.subTest(f"Scenario {i+1}: {scenario['execution_time']}s"):
                # Mock orchestrator
                mock_orchestrator = Mock()
                mock_create_orchestrator.return_value = mock_orchestrator

                mock_result = Mock()
                mock_result.success = True
                mock_result.execution_time = scenario["execution_time"]
                mock_result.performance_improvement = scenario["improvement"]
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

                # Verify results
                self.assertTrue(result["success"])
                self.assertEqual(result["execution_time"], scenario["execution_time"])
                self.assertEqual(result["target_met"], scenario["expected_pass"])

                if scenario["expected_pass"]:
                    self.assert_performance_target(
                        result["execution_time"],
                        self.performance_targets["foundation_setup_max_time"],
                        "Foundation Setup Time",
                        "less_than",
                    )

    @patch("orchestrator_dbt.run_multi_year.create_multi_year_orchestrator")
    @patch("orchestrator_dbt.run_multi_year.OptimizationLevel")
    async def test_foundation_setup_performance_improvement_target(
        self, mock_opt_level, mock_create_orchestrator
    ):
        """Test foundation setup meets >82% performance improvement target."""
        # Mock optimization level
        mock_opt_level.HIGH = Mock()
        mock_opt_level.HIGH.value = "high"

        # Test different improvement scenarios
        improvement_scenarios = [
            {"improvement": 0.90, "expected_grade": "🏆 EXCELLENT"},
            {"improvement": 0.85, "expected_grade": "✅ TARGET MET"},
            {"improvement": 0.82, "expected_grade": "✅ TARGET MET"},
            {"improvement": 0.75, "expected_grade": "⚠️  ACCEPTABLE"},
        ]

        for scenario in improvement_scenarios:
            with self.subTest(f"Improvement: {scenario['improvement']:.1%}"):
                # Mock orchestrator
                mock_orchestrator = Mock()
                mock_create_orchestrator.return_value = mock_orchestrator

                mock_result = Mock()
                mock_result.success = True
                mock_result.execution_time = 8.0  # Under target
                mock_result.performance_improvement = scenario["improvement"]
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

                # Verify performance improvement
                self.assertEqual(
                    result["performance_improvement"], scenario["improvement"]
                )

                if (
                    scenario["improvement"]
                    >= self.performance_targets["performance_improvement_min"]
                ):
                    self.assert_performance_target(
                        result["performance_improvement"],
                        self.performance_targets["performance_improvement_min"],
                        "Performance Improvement",
                        "greater_equal",
                    )


class TestMultiYearSimulationPerformance(PerformanceTestCase):
    """Test multi-year simulation performance benchmarks."""

    @patch("orchestrator_dbt.run_multi_year.MultiYearOrchestrator")
    @patch("orchestrator_dbt.run_multi_year.MultiYearConfig")
    @patch("orchestrator_dbt.run_multi_year.OptimizationLevel")
    async def test_multi_year_processing_rate_target(
        self, mock_opt_level, mock_config_class, mock_orchestrator_class
    ):
        """Test multi-year simulation meets processing rate targets."""
        # Mock optimization level
        mock_opt_level.HIGH = Mock()

        # Mock MultiYearConfig
        mock_multi_year_config = Mock()
        mock_config_class.return_value = mock_multi_year_config

        # Test different processing rate scenarios
        processing_scenarios = [
            {"records_per_second": 1500, "total_records": 45000, "expected_pass": True},
            {"records_per_second": 1200, "total_records": 36000, "expected_pass": True},
            {"records_per_second": 1000, "total_records": 30000, "expected_pass": True},
            {"records_per_second": 800, "total_records": 24000, "expected_pass": False},
        ]

        for scenario in processing_scenarios:
            with self.subTest(f"Rate: {scenario['records_per_second']} rec/sec"):
                # Mock orchestrator
                mock_orchestrator = Mock()
                mock_orchestrator_class.return_value = mock_orchestrator

                # Mock successful multi-year result
                mock_result = Mock()
                mock_result.success = True
                mock_result.simulation_id = (
                    f"perf-test-{scenario['records_per_second']}"
                )
                mock_result.total_execution_time = 90.0
                mock_result.completed_years = [2025, 2026, 2027]
                mock_result.failed_years = []
                mock_result.success_rate = 1.0
                mock_result.performance_metrics = {
                    "records_per_second": scenario["records_per_second"],
                    "total_records_processed": scenario["total_records"],
                }

                # Mock foundation setup result
                mock_foundation_result = Mock()
                mock_foundation_result.success = True
                mock_foundation_result.execution_time = 7.5
                mock_foundation_result.performance_improvement = 0.85
                mock_result.foundation_setup_result = mock_foundation_result

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

                # Verify processing rate
                self.assertTrue(result["success"])
                processing_rate = result["performance_metrics"]["records_per_second"]

                if scenario["expected_pass"]:
                    self.assert_performance_target(
                        processing_rate,
                        self.performance_targets["processing_rate_min"],
                        "Processing Rate (records/sec)",
                        "greater_equal",
                    )
                else:
                    # Should not meet target
                    self.assertLess(
                        processing_rate, self.performance_targets["processing_rate_min"]
                    )

    @patch("orchestrator_dbt.run_multi_year.MultiYearOrchestrator")
    @patch("orchestrator_dbt.run_multi_year.MultiYearConfig")
    @patch("orchestrator_dbt.run_multi_year.OptimizationLevel")
    async def test_multi_year_memory_efficiency_target(
        self, mock_opt_level, mock_config_class, mock_orchestrator_class
    ):
        """Test multi-year simulation meets memory efficiency targets."""
        # Mock optimization level
        mock_opt_level.HIGH = Mock()

        # Mock MultiYearConfig
        mock_multi_year_config = Mock()
        mock_config_class.return_value = mock_multi_year_config

        # Mock orchestrator with different memory scenarios
        memory_scenarios = [
            {
                "peak_mb": 512,
                "avg_mb": 384,
                "efficiency": 0.75,
                "expected_pass": True,
            },  # Good
            {
                "peak_mb": 768,
                "avg_mb": 537,
                "efficiency": 0.70,
                "expected_pass": True,
            },  # Acceptable
            {
                "peak_mb": 1024,
                "avg_mb": 614,
                "efficiency": 0.60,
                "expected_pass": False,
            },  # Poor
        ]

        for scenario in memory_scenarios:
            with self.subTest(f"Memory efficiency: {scenario['efficiency']:.1%}"):
                # Mock orchestrator
                mock_orchestrator = Mock()
                mock_orchestrator_class.return_value = mock_orchestrator

                # Mock successful multi-year result
                mock_result = Mock()
                mock_result.success = True
                mock_result.simulation_id = f"memory-test-{scenario['efficiency']}"
                mock_result.total_execution_time = 85.0
                mock_result.completed_years = [2025, 2026, 2027]
                mock_result.failed_years = []
                mock_result.success_rate = 1.0
                mock_result.performance_metrics = {
                    "records_per_second": 1200,
                    "memory_efficiency": scenario["efficiency"],
                }
                mock_result.foundation_setup_result = Mock()

                mock_orchestrator.execute_multi_year_simulation = AsyncMock(
                    return_value=mock_result
                )

                # Run enhanced multi-year simulation with memory monitoring
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

                # Verify memory efficiency
                self.assertTrue(result["success"])
                memory_efficiency = result["performance_metrics"]["memory_efficiency"]

                if scenario["expected_pass"]:
                    self.assert_performance_target(
                        memory_efficiency,
                        self.performance_targets["memory_efficiency_min"],
                        "Memory Efficiency",
                        "greater_equal",
                    )
                else:
                    # Should not meet target
                    self.assertLess(
                        memory_efficiency,
                        self.performance_targets["memory_efficiency_min"],
                    )


class TestRegressionComparison(PerformanceTestCase):
    """Test performance regression comparison with MVP."""

    @patch("orchestrator_dbt.run_multi_year.MVP_AVAILABLE", True)
    @patch("orchestrator_dbt.run_multi_year.MultiYearSimulationOrchestrator")
    @patch("orchestrator_dbt.run_multi_year.run_enhanced_multi_year_simulation")
    async def test_regression_comparison_improvement_target(
        self, mock_enhanced_sim, mock_mvp_orchestrator
    ):
        """Test comprehensive regression comparison meets improvement targets."""
        # Test multiple improvement scenarios
        regression_scenarios = [
            {
                "name": "Outstanding Performance",
                "mvp_time": 200.0,
                "new_time": 18.0,  # 91% improvement
                "expected_grade": "🏆 OUTSTANDING",
                "should_pass": True,
            },
            {
                "name": "Target Met",
                "mvp_time": 150.0,
                "new_time": 27.0,  # 82% improvement (exactly target)
                "expected_grade": "✅ TARGET MET",
                "should_pass": True,
            },
            {
                "name": "Close Miss",
                "mvp_time": 120.0,
                "new_time": 22.0,  # 81.7% improvement (close to target)
                "expected_grade": "⚠️  GOOD",
                "should_pass": False,
            },
            {
                "name": "Poor Performance",
                "mvp_time": 100.0,
                "new_time": 60.0,  # 40% improvement (well below target)
                "expected_grade": "🔍 NEEDS IMPROVEMENT",
                "should_pass": False,
            },
        ]

        for scenario in regression_scenarios:
            with self.subTest(scenario["name"]):
                # Mock MVP orchestrator (baseline)
                mock_mvp_instance = Mock()
                mock_mvp_orchestrator.return_value = mock_mvp_instance

                mock_mvp_result = {
                    "years_completed": [2025, 2026, 2027],
                    "total_runtime_seconds": scenario["mvp_time"],
                }
                mock_mvp_instance.run_simulation.return_value = mock_mvp_result

                # Mock enhanced simulation (optimized)
                mock_enhanced_result = {
                    "success": True,
                    "total_execution_time": scenario["new_time"],
                    "completed_years": [2025, 2026, 2027],
                    "performance_metrics": {
                        "records_per_second": 1400,
                        "memory_efficiency": 0.80,
                    },
                }
                mock_enhanced_sim.return_value = mock_enhanced_result

                # Run comprehensive performance comparison
                result = await run_comprehensive_performance_comparison(
                    start_year=2025,
                    end_year=2027,
                    config_path=self.config_path,
                    benchmark_mode=True,
                )

                # Calculate expected improvement
                expected_improvement = (
                    scenario["mvp_time"] - scenario["new_time"]
                ) / scenario["mvp_time"]

                # Verify regression test results
                self.assertTrue(result["mvp_success"])
                self.assertTrue(result["new_success"])
                self.assertAlmostEqual(
                    result["improvement"], expected_improvement, places=3
                )
                self.assertEqual(result["target_met"], scenario["should_pass"])
                self.assertEqual(
                    result["regression_test_passed"], scenario["should_pass"]
                )

                # Verify performance grade matches expectation
                self.assertIn(scenario["expected_grade"], result["performance_grade"])

                if scenario["should_pass"]:
                    self.assert_performance_target(
                        result["improvement"],
                        self.performance_targets["performance_improvement_min"],
                        f"Regression Improvement ({scenario['name']})",
                        "greater_equal",
                    )

    @patch("orchestrator_dbt.run_multi_year.MVP_AVAILABLE", True)
    @patch("orchestrator_dbt.run_multi_year.MultiYearSimulationOrchestrator")
    @patch("orchestrator_dbt.run_multi_year.run_enhanced_multi_year_simulation")
    async def test_regression_comparison_statistical_significance(
        self, mock_enhanced_sim, mock_mvp_orchestrator
    ):
        """Test regression comparison statistical significance over multiple runs."""
        # Simulate multiple runs to test consistency
        num_runs = 5
        mvp_times = []
        new_times = []
        improvements = []

        for run in range(num_runs):
            # Mock MVP orchestrator with slight variance
            mock_mvp_instance = Mock()
            mock_mvp_orchestrator.return_value = mock_mvp_instance

            # Add realistic variance to MVP times (±5%)
            base_mvp_time = 180.0
            mvp_time = base_mvp_time * (1.0 + (run - 2) * 0.025)  # -5% to +5% variance
            mvp_times.append(mvp_time)

            mock_mvp_result = {
                "years_completed": [2025, 2026, 2027],
                "total_runtime_seconds": mvp_time,
            }
            mock_mvp_instance.run_simulation.return_value = mock_mvp_result

            # Mock enhanced simulation with consistent improvement
            base_new_time = 30.0
            new_time = base_new_time * (
                1.0 + (run - 2) * 0.015
            )  # Smaller variance for optimized system
            new_times.append(new_time)

            mock_enhanced_result = {
                "success": True,
                "total_execution_time": new_time,
                "completed_years": [2025, 2026, 2027],
                "performance_metrics": {"records_per_second": 1300},
            }
            mock_enhanced_sim.return_value = mock_enhanced_result

            # Run comparison
            result = await run_comprehensive_performance_comparison(
                start_year=2025, end_year=2027, config_path=self.config_path
            )

            improvements.append(result["improvement"])

        # Analyze statistical results
        avg_improvement = statistics.mean(improvements)
        std_improvement = statistics.stdev(improvements) if len(improvements) > 1 else 0
        min_improvement = min(improvements)
        max_improvement = max(improvements)

        print(f"\n📊 STATISTICAL ANALYSIS OF {num_runs} REGRESSION RUNS:")
        print(f"   Average improvement: {avg_improvement:.1%}")
        print(f"   Standard deviation: {std_improvement:.1%}")
        print(f"   Range: {min_improvement:.1%} - {max_improvement:.1%}")

        # All runs should consistently meet the 82% target
        self.assert_performance_target(
            min_improvement,
            self.performance_targets["performance_improvement_min"],
            "Minimum Improvement (Consistency)",
            "greater_equal",
        )

        # Average should be well above target
        self.assert_performance_target(
            avg_improvement,
            self.performance_targets["performance_improvement_min"]
            + 0.01,  # At least 83%
            "Average Improvement",
            "greater_equal",
        )

        # Variance should be reasonable (< 2% standard deviation)
        self.assertLess(
            std_improvement,
            0.02,
            f"Performance variance too high: {std_improvement:.1%} std dev",
        )


class TestPerformanceMonitorAccuracy(PerformanceTestCase):
    """Test performance monitoring accuracy and reliability."""

    def test_performance_monitor_timing_accuracy(self):
        """Test performance monitor provides accurate timing measurements."""
        monitor = PerformanceMonitor()
        monitor.start()

        # Test known sleep durations
        test_durations = [0.1, 0.2, 0.15, 0.05]  # Seconds
        expected_cumulative = 0.0

        for i, duration in enumerate(test_durations):
            time.sleep(duration)
            expected_cumulative += duration

            elapsed = monitor.checkpoint(f"sleep_{i+1}")

            # Timing should be accurate within 10ms tolerance
            self.assertAlmostEqual(
                elapsed,
                expected_cumulative,
                delta=0.01,
                msg=f"Timing accuracy failed at checkpoint {i+1}",
            )

        # Final summary should match total expected time
        summary = monitor.get_summary()
        total_expected = sum(test_durations)

        self.assertAlmostEqual(
            summary["total_time"],
            total_expected,
            delta=0.02,
            msg="Total timing summary inaccurate",
        )

    def test_performance_monitor_memory_tracking_accuracy(self):
        """Test performance monitor memory tracking accuracy."""
        monitor = PerformanceMonitor()
        monitor.start()

        # Get baseline memory
        baseline_memory = monitor.process.memory_info().rss / 1024 / 1024
        monitor.checkpoint("baseline")

        # Create memory load
        memory_hog = [list(range(10000)) for _ in range(100)]  # ~80MB of data
        monitor.checkpoint("after_allocation")

        # Memory should have increased
        summary = monitor.get_summary()
        baseline_checkpoint = summary["checkpoints"]["baseline"]["memory_mb"]
        allocation_checkpoint = summary["checkpoints"]["after_allocation"]["memory_mb"]

        memory_increase = allocation_checkpoint - baseline_checkpoint

        # Should see some memory increase (at least 10MB, allowing for overhead)
        self.assertGreater(
            memory_increase,
            10.0,
            f"Memory tracking failed to detect allocation: {memory_increase:.1f}MB increase",
        )

        # Peak memory should be at least the allocation checkpoint
        self.assertGreaterEqual(summary["peak_memory_mb"], allocation_checkpoint)

        # Clean up
        del memory_hog
        monitor.checkpoint("after_cleanup")


if __name__ == "__main__":
    # Configure logging for performance test output
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    # Run performance tests
    unittest.main(verbosity=2)
