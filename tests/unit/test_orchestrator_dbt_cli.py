"""
Unit tests for orchestrator_dbt CLI interface.

Tests comprehensive CLI functionality including:
- Configuration loading and validation
- Performance monitoring
- Error handling with troubleshooting
- Multi-year orchestration workflows
- Regression testing capabilities

Target: >90% test coverage for S031-01 components
"""

import asyncio
import json
import logging
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import pytest
import yaml

# Import system under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "orchestrator_dbt"))

from run_multi_year import (
    PerformanceMonitor,
    setup_comprehensive_logging,
    validate_configuration,
    load_and_validate_config,
    test_configuration_compatibility,
    run_foundation_benchmark,
    run_enhanced_multi_year_simulation,
    run_comprehensive_performance_comparison,
    error_context,
    parse_arguments
)


class TestPerformanceMonitor(unittest.TestCase):
    """Test performance monitoring functionality."""

    def test_performance_monitor_initialization(self):
        """Test PerformanceMonitor initializes correctly."""
        monitor = PerformanceMonitor()

        self.assertIsNone(monitor.start_time)
        self.assertEqual(monitor.checkpoints, {})
        self.assertEqual(monitor.memory_usage, [])
        self.assertIsNotNone(monitor.process)

    def test_performance_monitor_start(self):
        """Test performance monitoring start functionality."""
        monitor = PerformanceMonitor()
        monitor.start()

        self.assertIsNotNone(monitor.start_time)
        self.assertEqual(len(monitor.memory_usage), 1)
        self.assertGreater(monitor.memory_usage[0], 0)  # Memory usage should be positive

    def test_performance_monitor_checkpoint(self):
        """Test checkpoint recording functionality."""
        monitor = PerformanceMonitor()
        monitor.start()

        elapsed = monitor.checkpoint("test_checkpoint")

        self.assertIn("test_checkpoint", monitor.checkpoints)
        self.assertGreater(elapsed, 0)

        checkpoint_data = monitor.checkpoints["test_checkpoint"]
        self.assertIn("elapsed_time", checkpoint_data)
        self.assertIn("memory_mb", checkpoint_data)
        self.assertIn("timestamp", checkpoint_data)
        self.assertGreater(checkpoint_data["memory_mb"], 0)

    def test_performance_monitor_summary(self):
        """Test performance summary generation."""
        monitor = PerformanceMonitor()
        monitor.start()
        monitor.checkpoint("checkpoint1")
        monitor.checkpoint("checkpoint2")

        summary = monitor.get_summary()

        self.assertIn("total_time", summary)
        self.assertIn("peak_memory_mb", summary)
        self.assertIn("avg_memory_mb", summary)
        self.assertIn("memory_efficiency", summary)
        self.assertIn("checkpoints", summary)

        self.assertEqual(len(summary["checkpoints"]), 2)
        self.assertGreater(summary["total_time"], 0)
        self.assertGreater(summary["peak_memory_mb"], 0)
        self.assertLessEqual(summary["memory_efficiency"], 1.0)


class TestConfigurationValidation(unittest.TestCase):
    """Test configuration validation and loading."""

    def test_validate_configuration_valid_config(self):
        """Test configuration validation with valid config."""
        valid_config = {
            'simulation': {
                'start_year': 2025,
                'end_year': 2027,
                'target_growth_rate': 0.03
            },
            'workforce': {
                'total_termination_rate': 0.12
            },
            'random_seed': 42
        }

        is_valid, errors = validate_configuration(valid_config)

        self.assertTrue(is_valid)
        self.assertEqual(len(errors), 0)

    def test_validate_configuration_missing_section(self):
        """Test configuration validation with missing required section."""
        invalid_config = {
            'workforce': {
                'total_termination_rate': 0.12
            },
            'random_seed': 42
        }

        is_valid, errors = validate_configuration(invalid_config)

        self.assertFalse(is_valid)
        self.assertIn("Missing required section: simulation", errors)

    def test_validate_configuration_invalid_year_range(self):
        """Test configuration validation with invalid year range."""
        invalid_config = {
            'simulation': {
                'start_year': 2027,
                'end_year': 2025,  # End year before start year
                'target_growth_rate': 0.03
            },
            'workforce': {
                'total_termination_rate': 0.12
            },
            'random_seed': 42
        }

        is_valid, errors = validate_configuration(invalid_config)

        self.assertFalse(is_valid)
        self.assertIn("end_year must be greater than start_year", errors)

    def test_validate_configuration_invalid_rates(self):
        """Test configuration validation with invalid rate values."""
        invalid_config = {
            'simulation': {
                'start_year': 2025,
                'end_year': 2027,
                'target_growth_rate': 1.5  # > 1.0
            },
            'workforce': {
                'total_termination_rate': -0.1  # Negative
            },
            'random_seed': 42
        }

        is_valid, errors = validate_configuration(invalid_config)

        self.assertFalse(is_valid)
        self.assertIn("target_growth_rate must be between 0.0 and 1.0", errors)
        self.assertIn("total_termination_rate must be between 0.0 and 1.0", errors)

    def test_load_and_validate_config_default(self):
        """Test loading default configuration."""
        config = load_and_validate_config(None)

        self.assertIn('simulation', config)
        self.assertIn('workforce', config)
        self.assertIn('random_seed', config)

        # Validate default values
        self.assertEqual(config['simulation']['start_year'], 2025)
        self.assertEqual(config['simulation']['target_growth_rate'], 0.03)
        self.assertEqual(config['workforce']['total_termination_rate'], 0.12)

    def test_load_and_validate_config_from_file(self):
        """Test loading configuration from file."""
        test_config = {
            'simulation': {
                'start_year': 2026,
                'end_year': 2028,
                'target_growth_rate': 0.05
            },
            'workforce': {
                'total_termination_rate': 0.15
            },
            'random_seed': 123
        }

        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            yaml.dump(test_config, f)
            config_path = f.name

        try:
            config = load_and_validate_config(config_path)

            self.assertEqual(config['simulation']['start_year'], 2026)
            self.assertEqual(config['simulation']['target_growth_rate'], 0.05)
            self.assertEqual(config['workforce']['total_termination_rate'], 0.15)
            self.assertEqual(config['random_seed'], 123)
        finally:
            os.unlink(config_path)

    def test_load_and_validate_config_invalid_file(self):
        """Test loading configuration from invalid file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
            f.write("invalid: yaml: content: [")
            config_path = f.name

        try:
            config = load_and_validate_config(config_path)

            # Should fall back to defaults on invalid file
            self.assertEqual(config['simulation']['start_year'], 2025)
        finally:
            os.unlink(config_path)


class TestErrorHandling(unittest.TestCase):
    """Test error handling and troubleshooting guidance."""

    def test_error_context_basic_exception(self):
        """Test basic error context handling."""
        with self.assertRaises(ValueError):
            with error_context("Test operation"):
                raise ValueError("Test error")

    def test_error_context_with_troubleshooting(self):
        """Test error context with troubleshooting guide."""
        troubleshooting = "1. Check configuration\n2. Verify database connection"

        with self.assertRaises(ValueError):
            with error_context("Test operation", troubleshooting):
                raise ValueError("Test error")

    @patch('logging.getLogger')
    def test_error_context_database_error_guidance(self, mock_logger):
        """Test database-specific error guidance."""
        mock_logger_instance = Mock()
        mock_logger.return_value = mock_logger_instance

        with self.assertRaises(ValueError):
            with error_context("Database operation"):
                raise ValueError("Database connection failed")

        # Verify database troubleshooting was logged
        mock_logger_instance.error.assert_called()
        error_calls = [call[0][0] for call in mock_logger_instance.error.call_args_list]

        self.assertTrue(any("Database troubleshooting" in call for call in error_calls))

    @patch('logging.getLogger')
    def test_error_context_memory_error_guidance(self, mock_logger):
        """Test memory-specific error guidance."""
        mock_logger_instance = Mock()
        mock_logger.return_value = mock_logger_instance

        with self.assertRaises(MemoryError):
            with error_context("Memory operation"):
                raise MemoryError("Out of memory")

        # Verify memory troubleshooting was logged
        error_calls = [call[0][0] for call in mock_logger_instance.error.call_args_list]
        self.assertTrue(any("Memory troubleshooting" in call for call in error_calls))


class TestLoggingSetup(unittest.TestCase):
    """Test logging configuration."""

    def test_setup_comprehensive_logging_basic(self):
        """Test basic logging setup."""
        logger = setup_comprehensive_logging()

        self.assertIsInstance(logger, logging.Logger)
        self.assertEqual(logger.level, logging.INFO)

    def test_setup_comprehensive_logging_verbose(self):
        """Test verbose logging setup."""
        logger = setup_comprehensive_logging(verbose=True)

        self.assertEqual(logger.level, logging.DEBUG)

    def test_setup_comprehensive_logging_with_file(self):
        """Test logging setup with file output."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            log_file = f.name

        try:
            logger = setup_comprehensive_logging(log_file=log_file)

            # Test that logging to file works
            logger.info("Test log message")

            with open(log_file, 'r') as f:
                log_content = f.read()
                self.assertIn("Test log message", log_content)
        finally:
            os.unlink(log_file)

    def test_setup_comprehensive_logging_structured(self):
        """Test structured logging format."""
        logger = setup_comprehensive_logging(structured=True)

        # Verify logger is configured (actual format testing would require
        # capturing handler output, which is complex)
        self.assertIsInstance(logger, logging.Logger)


@pytest.mark.asyncio
class TestAsyncFunctions(unittest.IsolatedAsyncioTestCase):
    """Test async functions with proper async test framework."""

    @patch('orchestrator_dbt.run_multi_year.create_multi_year_orchestrator')
    @patch('orchestrator_dbt.run_multi_year.load_and_validate_config')
    async def test_run_foundation_benchmark_success(self, mock_load_config, mock_create_orchestrator):
        """Test successful foundation benchmark run."""
        # Mock configuration
        mock_config = {
            'simulation': {'start_year': 2025, 'end_year': 2025, 'target_growth_rate': 0.03},
            'workforce': {'total_termination_rate': 0.12},
            'random_seed': 42
        }
        mock_load_config.return_value = mock_config

        # Mock orchestrator and result
        mock_orchestrator = Mock()
        mock_create_orchestrator.return_value = mock_orchestrator

        mock_result = Mock()
        mock_result.success = True
        mock_result.execution_time = 8.5  # Under 10 second target
        mock_result.performance_improvement = 0.85  # 85% improvement
        mock_result.metadata = {}

        mock_orchestrator._execute_foundation_setup = AsyncMock(return_value=mock_result)

        # Mock OptimizationLevel
        with patch('orchestrator_dbt.run_multi_year.OptimizationLevel') as mock_opt_level:
            mock_opt_level.HIGH = Mock()
            mock_opt_level.HIGH.value = "high"

            result = await run_foundation_benchmark(
                optimization_level=mock_opt_level.HIGH,
                config_path=None,
                benchmark_mode=True
            )

        # Verify results
        self.assertTrue(result['success'])
        self.assertEqual(result['execution_time'], 8.5)
        self.assertEqual(result['performance_improvement'], 0.85)
        self.assertTrue(result['target_met'])
        self.assertIn('memory_metrics', result)
        self.assertIn('detailed_timing', result)

    @patch('orchestrator_dbt.run_multi_year.create_multi_year_orchestrator')
    @patch('orchestrator_dbt.run_multi_year.load_and_validate_config')
    async def test_run_foundation_benchmark_failure(self, mock_load_config, mock_create_orchestrator):
        """Test foundation benchmark failure handling."""
        # Mock configuration
        mock_config = {
            'simulation': {'start_year': 2025, 'end_year': 2025, 'target_growth_rate': 0.03},
            'workforce': {'total_termination_rate': 0.12},
            'random_seed': 42
        }
        mock_load_config.return_value = mock_config

        # Mock orchestrator to raise exception
        mock_orchestrator = Mock()
        mock_create_orchestrator.return_value = mock_orchestrator

        mock_orchestrator._execute_foundation_setup = AsyncMock(
            side_effect=Exception("Database connection failed")
        )

        # Mock OptimizationLevel
        with patch('orchestrator_dbt.run_multi_year.OptimizationLevel') as mock_opt_level:
            mock_opt_level.HIGH = Mock()
            mock_opt_level.HIGH.value = "high"

            result = await run_foundation_benchmark(
                optimization_level=mock_opt_level.HIGH,
                config_path=None,
                benchmark_mode=False
            )

        # Verify failure is handled correctly
        self.assertFalse(result['success'])
        self.assertIn('error', result)
        self.assertEqual(result['error'], "Database connection failed")
        self.assertIn('error_type', result)

    @patch('orchestrator_dbt.run_multi_year.MultiYearOrchestrator')
    @patch('orchestrator_dbt.run_multi_year.MultiYearConfig')
    @patch('orchestrator_dbt.run_multi_year.load_and_validate_config')
    async def test_run_enhanced_multi_year_simulation_success(
        self, mock_load_config, mock_config_class, mock_orchestrator_class
    ):
        """Test successful multi-year simulation."""
        # Mock configuration
        mock_config = {
            'simulation': {'start_year': 2025, 'end_year': 2027, 'target_growth_rate': 0.03},
            'workforce': {'total_termination_rate': 0.12},
            'random_seed': 42
        }
        mock_load_config.return_value = mock_config

        # Mock MultiYearConfig
        mock_multi_year_config = Mock()
        mock_config_class.return_value = mock_multi_year_config

        # Mock orchestrator and result
        mock_orchestrator = Mock()
        mock_orchestrator_class.return_value = mock_orchestrator

        mock_result = Mock()
        mock_result.success = True
        mock_result.simulation_id = "test-sim-123"
        mock_result.total_execution_time = 45.2
        mock_result.completed_years = [2025, 2026, 2027]
        mock_result.failed_years = []
        mock_result.success_rate = 1.0
        mock_result.performance_metrics = {'records_per_second': 1500}
        mock_result.foundation_setup_result = Mock()
        mock_result.foundation_setup_result.execution_time = 7.8
        mock_result.foundation_setup_result.performance_improvement = 0.84

        mock_orchestrator.execute_multi_year_simulation = AsyncMock(return_value=mock_result)

        # Mock OptimizationLevel
        with patch('orchestrator_dbt.run_multi_year.OptimizationLevel') as mock_opt_level:
            mock_opt_level.HIGH = Mock()

            result = await run_enhanced_multi_year_simulation(
                start_year=2025,
                end_year=2027,
                optimization_level=mock_opt_level.HIGH,
                max_workers=4,
                batch_size=1000,
                enable_compression=True,
                fail_fast=False,
                performance_mode=True,
                config_path=None
            )

        # Verify results
        self.assertTrue(result['success'])
        self.assertEqual(result['simulation_id'], "test-sim-123")
        self.assertEqual(result['total_execution_time'], 45.2)
        self.assertEqual(result['completed_years'], [2025, 2026, 2027])
        self.assertEqual(result['failed_years'], [])
        self.assertEqual(result['success_rate'], 1.0)
        self.assertIn('performance_metrics', result)


class TestConfigurationCompatibility(unittest.TestCase):
    """Test configuration compatibility testing."""

    @patch('orchestrator_dbt.run_multi_year.MVP_AVAILABLE', True)
    @patch('orchestrator_dbt.run_multi_year.MultiYearSimulationOrchestrator')
    @patch('orchestrator_dbt.run_multi_year.load_and_validate_config')
    def test_configuration_compatibility_success(self, mock_load_config, mock_mvp_orchestrator):
        """Test successful configuration compatibility check."""
        # Mock configuration
        mock_config = {
            'simulation': {'start_year': 2025, 'end_year': 2026, 'target_growth_rate': 0.03},
            'workforce': {'total_termination_rate': 0.12},
            'random_seed': 42
        }
        mock_load_config.return_value = mock_config

        # Mock MVP orchestrator creation (should not raise exception)
        mock_mvp_orchestrator.return_value = Mock()

        result = test_configuration_compatibility(None)

        # Verify compatibility results
        self.assertTrue(result['config_valid'])
        self.assertTrue(result['new_system_compatible'])
        self.assertTrue(result['legacy_compatible'])
        self.assertEqual(len(result['issues']), 0)
        self.assertIn('recommendations', result)

    @patch('orchestrator_dbt.run_multi_year.MVP_AVAILABLE', True)
    @patch('orchestrator_dbt.run_multi_year.MultiYearSimulationOrchestrator')
    @patch('orchestrator_dbt.run_multi_year.load_and_validate_config')
    def test_configuration_compatibility_legacy_failure(self, mock_load_config, mock_mvp_orchestrator):
        """Test configuration compatibility with legacy system failure."""
        # Mock configuration
        mock_config = {
            'simulation': {'start_year': 2025, 'end_year': 2026, 'target_growth_rate': 0.03},
            'workforce': {'total_termination_rate': 0.12},
            'random_seed': 42
        }
        mock_load_config.return_value = mock_config

        # Mock MVP orchestrator to raise exception
        mock_mvp_orchestrator.side_effect = Exception("Legacy system incompatible")

        result = test_configuration_compatibility(None)

        # Verify compatibility results
        self.assertTrue(result['config_valid'])
        self.assertTrue(result['new_system_compatible'])
        self.assertFalse(result['legacy_compatible'])
        self.assertGreater(len(result['issues']), 0)
        self.assertIn("Legacy compatibility issue", str(result['issues']))

    @patch('orchestrator_dbt.run_multi_year.MVP_AVAILABLE', False)
    @patch('orchestrator_dbt.run_multi_year.load_and_validate_config')
    def test_configuration_compatibility_no_mvp(self, mock_load_config):
        """Test configuration compatibility when MVP is not available."""
        # Mock configuration
        mock_config = {
            'simulation': {'start_year': 2025, 'end_year': 2026, 'target_growth_rate': 0.03},
            'workforce': {'total_termination_rate': 0.12},
            'random_seed': 42
        }
        mock_load_config.return_value = mock_config

        result = test_configuration_compatibility(None)

        # Verify compatibility results
        self.assertTrue(result['config_valid'])
        self.assertTrue(result['new_system_compatible'])
        self.assertFalse(result['legacy_compatible'])  # Should be false when MVP not available


class TestCLIArguments(unittest.TestCase):
    """Test CLI argument parsing."""

    def test_parse_arguments_basic(self):
        """Test basic argument parsing."""
        test_args = ['--start-year', '2025', '--end-year', '2027']

        with patch('sys.argv', ['run_multi_year.py'] + test_args):
            args = parse_arguments()

        self.assertEqual(args.start_year, 2025)
        self.assertEqual(args.end_year, 2027)
        self.assertEqual(args.optimization, 'high')  # Default
        self.assertEqual(args.max_workers, 4)  # Default
        self.assertFalse(args.foundation_only)
        self.assertFalse(args.compare_mvp)

    def test_parse_arguments_all_options(self):
        """Test parsing all available options."""
        test_args = [
            '--start-year', '2025',
            '--end-year', '2029',
            '--optimization', 'medium',
            '--max-workers', '8',
            '--batch-size', '2000',
            '--enable-compression',
            '--fail-fast',
            '--performance-mode',
            '--config', '/path/to/config.yaml',
            '--verbose',
            '--structured-logs',
            '--benchmark'
        ]

        with patch('sys.argv', ['run_multi_year.py'] + test_args):
            args = parse_arguments()

        self.assertEqual(args.start_year, 2025)
        self.assertEqual(args.end_year, 2029)
        self.assertEqual(args.optimization, 'medium')
        self.assertEqual(args.max_workers, 8)
        self.assertEqual(args.batch_size, 2000)
        self.assertTrue(args.enable_compression)
        self.assertTrue(args.fail_fast)
        self.assertTrue(args.performance_mode)
        self.assertEqual(args.config, '/path/to/config.yaml')
        self.assertTrue(args.verbose)
        self.assertTrue(args.structured_logs)
        self.assertTrue(args.benchmark)

    def test_parse_arguments_operational_modes(self):
        """Test operational mode arguments."""
        # Test foundation-only mode
        with patch('sys.argv', ['run_multi_year.py', '--foundation-only']):
            args = parse_arguments()
            self.assertTrue(args.foundation_only)

        # Test compare-mvp mode
        with patch('sys.argv', ['run_multi_year.py', '--compare-mvp', '--start-year', '2025', '--end-year', '2027']):
            args = parse_arguments()
            self.assertTrue(args.compare_mvp)

        # Test config test mode
        with patch('sys.argv', ['run_multi_year.py', '--test-config']):
            args = parse_arguments()
            self.assertTrue(args.test_config)


if __name__ == '__main__':
    # Run tests with coverage if pytest is available
    try:
        import pytest
        pytest.main([__file__, '-v', '--cov=orchestrator_dbt.run_multi_year', '--cov-report=term-missing'])
    except ImportError:
        unittest.main(verbosity=2)
