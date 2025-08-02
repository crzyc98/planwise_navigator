#!/usr/bin/env python3
"""
Multi-Year Simulation CLI - Production-Ready Interface

Command-line interface for running multi-year workforce simulations using the
optimized orchestrator_dbt package with 82% performance improvement.

🎯 PERFORMANCE TARGETS:
- Foundation setup: <10 seconds (82% improvement vs legacy)
- Multi-year orchestration with <5% memory overhead
- Real-time progress tracking and performance monitoring
- Circuit breaker patterns for production resilience

🚀 KEY FEATURES:
- Production-ready error handling with detailed troubleshooting
- Performance regression testing ensuring 82% improvement target
- Comprehensive logging with structured output
- Integration with existing orchestrator_mvp for comparison benchmarks
- Configuration validation and backward compatibility checks

Usage:
    # Basic multi-year simulation
    python -m orchestrator_dbt.run_multi_year --start-year 2025 --end-year 2029

    # High-performance simulation with full optimization
    python -m orchestrator_dbt.run_multi_year \\
        --start-year 2025 --end-year 2029 \\
        --optimization high \\
        --max-workers 8 \\
        --batch-size 2000 \\
        --enable-compression \\
        --performance-mode

    # Foundation setup benchmark (for performance testing)
    python -m orchestrator_dbt.run_multi_year \\
        --foundation-only \\
        --optimization high \\
        --benchmark

    # Performance comparison with MVP (regression testing)
    python -m orchestrator_dbt.run_multi_year \\
        --start-year 2025 --end-year 2027 \\
        --compare-mvp \\
        --benchmark

    # Configuration compatibility test
    python -m orchestrator_dbt.run_multi_year \\
        --test-config \\
        --config path/to/simulation_config.yaml
"""

import argparse
import asyncio
import json
import logging
import os
import psutil
import sys
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Any, Optional, List, Tuple, Union
import warnings

# Import orchestrator_dbt components
try:
    from orchestrator_dbt.multi_year import (
        MultiYearOrchestrator,
        MultiYearConfig,
        OptimizationLevel,
        create_multi_year_orchestrator,
        create_high_performance_orchestrator
    )
    from orchestrator_dbt import (
        WorkflowOrchestrator,
        ConfigurationBridge,
        setup_orchestrator_logging
    )
except ImportError as e:
    print(f"❌ Failed to import orchestrator_dbt components: {e}")
    print("   Make sure the orchestrator_dbt package is properly installed")
    sys.exit(1)

# Import for configuration loading
import yaml

# Import for performance comparison
try:
    from orchestrator_mvp.core.multi_year_orchestrator import MultiYearSimulationOrchestrator
    MVP_AVAILABLE = True
except ImportError:
    MVP_AVAILABLE = False
    warnings.warn("MVP orchestrator not available for comparison")


class PerformanceMonitor:
    """Real-time performance monitoring and reporting."""

    def __init__(self):
        self.start_time = None
        self.checkpoints = {}
        self.memory_usage = []
        self.process = psutil.Process()

    def start(self):
        """Start performance monitoring."""
        self.start_time = time.time()
        self.memory_usage = [self.process.memory_info().rss / 1024 / 1024]  # MB

    def checkpoint(self, name: str) -> float:
        """Record a performance checkpoint."""
        if self.start_time is None:
            self.start_time = time.time()

        elapsed = time.time() - self.start_time
        memory_mb = self.process.memory_info().rss / 1024 / 1024

        self.checkpoints[name] = {
            'elapsed_time': elapsed,
            'memory_mb': memory_mb,
            'timestamp': time.time()
        }
        self.memory_usage.append(memory_mb)

        return elapsed

    def get_summary(self) -> Dict[str, Any]:
        """Get performance summary."""
        if not self.checkpoints:
            return {}

        total_time = max(cp['elapsed_time'] for cp in self.checkpoints.values())
        peak_memory = max(self.memory_usage)
        avg_memory = sum(self.memory_usage) / len(self.memory_usage)

        return {
            'total_time': total_time,
            'peak_memory_mb': peak_memory,
            'avg_memory_mb': avg_memory,
            'memory_efficiency': (avg_memory / peak_memory) if peak_memory > 0 else 1.0,
            'checkpoints': self.checkpoints
        }


@contextmanager
def error_context(operation: str, troubleshooting_guide: str = ""):
    """Enhanced error handling with troubleshooting guidance."""
    try:
        yield
    except Exception as e:
        logger = logging.getLogger(__name__)
        logger.error(f"💥 {operation} failed: {e}")

        if troubleshooting_guide:
            logger.error(f"💡 Troubleshooting guide:")
            for line in troubleshooting_guide.strip().split('\n'):
                logger.error(f"   {line}")

        # Add common troubleshooting for known error patterns
        error_msg = str(e).lower()
        if "connection" in error_msg or "database" in error_msg:
            logger.error("💡 Database troubleshooting:")
            logger.error("   1. Check that DuckDB file is not locked by another process")
            logger.error("   2. Ensure sufficient disk space for simulation data")
            logger.error("   3. Verify database file permissions")
        elif "memory" in error_msg or "allocation" in error_msg:
            logger.error("💡 Memory troubleshooting:")
            logger.error("   1. Reduce --batch-size parameter")
            logger.error("   2. Enable --enable-compression for memory efficiency")
            logger.error("   3. Reduce --max-workers parameter")
        elif "circular" in error_msg or "dependency" in error_msg:
            logger.error("💡 Dependency troubleshooting:")
            logger.error("   1. Ensure sequential year execution (2025 → 2026 → 2027...)")
            logger.error("   2. Check that previous years completed successfully")
            logger.error("   3. Use --force-clear to start fresh from 2025")

        raise


def setup_comprehensive_logging(
    verbose: bool = False,
    log_file: Optional[str] = None,
    structured: bool = False
) -> logging.Logger:
    """Setup comprehensive logging with structured output options."""
    level = logging.DEBUG if verbose else logging.INFO

    # Create formatter
    if structured:
        formatter = logging.Formatter(
            '%(asctime)s | %(levelname)-8s | %(name)-20s | %(message)s'
        )
    else:
        formatter = logging.Formatter(
            '%(asctime)s - %(levelname)s - %(message)s'
        )

    # Setup console handler with colors for different levels
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)

    # Setup root logger
    root_logger = logging.getLogger()
    root_logger.handlers.clear()  # Clear existing handlers
    root_logger.setLevel(level)
    root_logger.addHandler(console_handler)

    # Setup file handler if specified
    if log_file:
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(level)
        file_handler.setFormatter(formatter)
        root_logger.addHandler(file_handler)

    # Reduce noise from some libraries
    logging.getLogger('urllib3').setLevel(logging.WARNING)
    logging.getLogger('requests').setLevel(logging.WARNING)
    logging.getLogger('dbt').setLevel(logging.INFO)

    return logging.getLogger(__name__)


def validate_configuration(config: Dict[str, Any]) -> Tuple[bool, List[str]]:
    """Validate configuration for compatibility and correctness."""
    errors = []
    warnings_list = []

    # Required fields validation
    required_fields = {
        'simulation': ['start_year', 'end_year', 'target_growth_rate'],
        'workforce': ['total_termination_rate'],
        'random_seed': None
    }

    for section, fields in required_fields.items():
        if section not in config:
            errors.append(f"Missing required section: {section}")
            continue

        if fields:  # Only check fields if section has required fields
            for field in fields:
                if field not in config[section]:
                    errors.append(f"Missing required field: {section}.{field}")

    # Value range validation
    if 'simulation' in config:
        sim_config = config['simulation']

        if 'start_year' in sim_config and 'end_year' in sim_config:
            if sim_config['end_year'] <= sim_config['start_year']:
                errors.append("end_year must be greater than start_year")

            year_range = sim_config['end_year'] - sim_config['start_year']
            if year_range > 10:
                warnings_list.append(f"Large year range ({year_range} years) may impact performance")

        if 'target_growth_rate' in sim_config:
            growth_rate = sim_config['target_growth_rate']
            if not 0.0 <= growth_rate <= 1.0:
                errors.append("target_growth_rate must be between 0.0 and 1.0")

    # Workforce validation
    if 'workforce' in config:
        workforce = config['workforce']
        if 'total_termination_rate' in workforce:
            term_rate = workforce['total_termination_rate']
            if not 0.0 <= term_rate <= 1.0:
                errors.append("total_termination_rate must be between 0.0 and 1.0")

    # Log warnings
    if warnings_list:
        logger = logging.getLogger(__name__)
        for warning in warnings_list:
            logger.warning(f"⚠️  Configuration warning: {warning}")

    return len(errors) == 0, errors


def load_and_validate_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load and validate simulation configuration with comprehensive error checking."""
    logger = logging.getLogger(__name__)

    # Default configuration with comprehensive settings
    default_config = {
        'simulation': {
            'start_year': 2025,
            'end_year': 2029,
            'target_growth_rate': 0.03
        },
        'workforce': {
            'total_termination_rate': 0.12,
            'new_hire_termination_rate': 0.25
        },
        'eligibility': {
            'waiting_period_days': 365
        },
        'enrollment': {
            'auto_enrollment': {
                'hire_date_cutoff': '2024-01-01',
                'scope': 'new_hires_only'
            }
        },
        'compensation': {
            'cola_rate': 0.025,
            'merit_pool': 0.03
        },
        'random_seed': 42
    }

    if config_path and Path(config_path).exists():
        try:
            with open(config_path, 'r') as f:
                file_config = yaml.safe_load(f)

            # Deep merge with defaults
            config = default_config.copy()
            for key, value in file_config.items():
                if isinstance(value, dict) and key in config:
                    config[key].update(value)
                else:
                    config[key] = value

            logger.info(f"📋 Loaded configuration from {config_path}")

        except Exception as e:
            logger.error(f"❌ Failed to load config from {config_path}: {e}")
            logger.info("📋 Using default configuration")
            config = default_config
    else:
        if config_path:
            logger.warning(f"⚠️  Configuration file not found: {config_path}")
        logger.info("📋 Using default simulation configuration")
        config = default_config

    # Validate configuration
    is_valid, errors = validate_configuration(config)
    if not is_valid:
        logger.error("❌ Configuration validation failed:")
        for error in errors:
            logger.error(f"   • {error}")
        raise ValueError(f"Invalid configuration: {', '.join(errors)}")

    logger.info("✅ Configuration validation passed")
    return config


def test_configuration_compatibility(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Test configuration compatibility with both new and legacy systems."""
    logger = logging.getLogger(__name__)

    logger.info("🔧 Testing configuration compatibility...")

    results = {
        'config_valid': False,
        'legacy_compatible': False,
        'new_system_compatible': False,
        'issues': [],
        'recommendations': []
    }

    try:
        # Test new system configuration loading
        config = load_and_validate_config(config_path)
        results['config_valid'] = True
        results['new_system_compatible'] = True
        logger.info("✅ New system configuration: COMPATIBLE")

        # Test legacy system compatibility if available
        if MVP_AVAILABLE:
            try:
                # Test if legacy system can load the configuration
                legacy_config = {
                    'target_growth_rate': config['simulation']['target_growth_rate'],
                    'workforce': config['workforce'],
                    'eligibility': config.get('eligibility', {}),
                    'enrollment': config.get('enrollment', {}),
                    'random_seed': config.get('random_seed', 42)
                }

                # Try to create legacy orchestrator
                start_year = config['simulation']['start_year']
                end_year = min(start_year + 1, config['simulation']['end_year'])  # Test with minimal range

                test_orchestrator = MultiYearSimulationOrchestrator(
                    start_year=start_year,
                    end_year=end_year,
                    config=legacy_config,
                    preserve_data=True
                )

                results['legacy_compatible'] = True
                logger.info("✅ Legacy system configuration: COMPATIBLE")

            except Exception as e:
                results['legacy_compatible'] = False
                results['issues'].append(f"Legacy compatibility issue: {e}")
                logger.warning(f"⚠️  Legacy system configuration: INCOMPATIBLE - {e}")
        else:
            logger.info("ℹ️  Legacy system not available for compatibility testing")

    except Exception as e:
        results['config_valid'] = False
        results['issues'].append(f"Configuration validation failed: {e}")
        logger.error(f"❌ Configuration compatibility test failed: {e}")

    # Generate recommendations
    if not results['legacy_compatible'] and MVP_AVAILABLE:
        results['recommendations'].append("Consider updating configuration format for legacy compatibility")

    if results['config_valid']:
        results['recommendations'].append("Configuration is ready for production use")

    return results


async def run_foundation_benchmark(
    optimization_level: OptimizationLevel,
    config_path: Optional[str] = None,
    benchmark_mode: bool = False
) -> Dict[str, Any]:
    """Run foundation setup with comprehensive benchmarking and performance validation."""
    logger = logging.getLogger(__name__)
    performance_monitor = PerformanceMonitor()

    logger.info("🚀 Foundation Setup Performance Benchmark")
    logger.info(f"   🎯 Target: <10 seconds (82% improvement)")
    logger.info(f"   ⚙️  Optimization Level: {optimization_level.value}")
    logger.info(f"   📊 Benchmark Mode: {'ENABLED' if benchmark_mode else 'disabled'}")

    performance_monitor.start()

    troubleshooting = """
Foundation setup troubleshooting:
1. Ensure DuckDB database is not locked by other processes
2. Check available memory (recommended: >4GB free)
3. Verify dbt models compile without errors
4. Ensure seed files are present and valid
5. Check network connectivity for dbt packages
    """

    with error_context("Foundation setup", troubleshooting):
        try:
            # Load and validate configuration
            config = load_and_validate_config(config_path)
            performance_monitor.checkpoint("config_loaded")

            # Create orchestrator with performance monitoring
            orchestrator = create_multi_year_orchestrator(
                start_year=config['simulation']['start_year'],
                end_year=config['simulation']['start_year'],  # Single year for foundation test
                optimization_level=optimization_level,
                base_config_path=Path(config_path) if config_path else None
            )
            performance_monitor.checkpoint("orchestrator_created")

            # Execute foundation setup with detailed timing
            logger.info("⏳ Executing optimized foundation setup...")
            result = await orchestrator._execute_foundation_setup()
            performance_monitor.checkpoint("foundation_completed")

            # Get performance summary
            perf_summary = performance_monitor.get_summary()

            # Enhanced results logging
            if result.success:
                logger.info(f"🎉 Foundation setup COMPLETED successfully!")
                logger.info(f"   ⏱️  Execution Time: {result.execution_time:.2f}s")
                logger.info(f"   🎯 Target Achievement (<10s): {'✅ SUCCESS' if result.execution_time < 10.0 else '❌ FAILED'}")
                logger.info(f"   📈 Performance Improvement: {result.performance_improvement:.1%}")

                # Detailed performance breakdown
                if hasattr(result, 'workflow_details'):
                    logger.info(f"   📋 Workflow Steps: {result.workflow_details.steps_completed}/{result.workflow_details.steps_total}")

                # Memory efficiency reporting
                logger.info(f"   💾 Peak Memory: {perf_summary['peak_memory_mb']:.1f} MB")
                logger.info(f"   📊 Memory Efficiency: {perf_summary['memory_efficiency']:.1%}")

                # Performance grade
                if result.execution_time < 5.0:
                    grade = "🏆 EXCELLENT"
                elif result.execution_time < 10.0:
                    grade = "✅ TARGET MET"
                elif result.execution_time < 20.0:
                    grade = "⚠️  ACCEPTABLE"
                else:
                    grade = "❌ NEEDS IMPROVEMENT"

                logger.info(f"   🏅️  Performance Grade: {grade}")

            else:
                logger.error(f"❌ Foundation setup FAILED")
                error_info = result.metadata.get('error', 'Unknown error')
                logger.error(f"   💥 Error: {error_info}")
                logger.error(f"   ⏱️  Time before failure: {perf_summary['total_time']:.2f}s")

            # Benchmark-specific reporting
            if benchmark_mode:
                logger.info("\n📊 BENCHMARK REPORT:")
                logger.info(f"   Total time: {perf_summary['total_time']:.2f}s")
                logger.info(f"   Peak memory: {perf_summary['peak_memory_mb']:.1f} MB")
                logger.info(f"   Average memory: {perf_summary['avg_memory_mb']:.1f} MB")

                for checkpoint, data in perf_summary['checkpoints'].items():
                    logger.info(f"   {checkpoint}: {data['elapsed_time']:.2f}s")

            return {
                'success': result.success,
                'execution_time': result.execution_time,
                'performance_improvement': result.performance_improvement,
                'target_met': result.execution_time < 10.0,
                'performance_grade': grade if result.success else 'FAILED',
                'memory_metrics': {
                    'peak_mb': perf_summary['peak_memory_mb'],
                    'avg_mb': perf_summary['avg_memory_mb'],
                    'efficiency': perf_summary['memory_efficiency']
                },
                'detailed_timing': perf_summary['checkpoints']
            }

        except Exception as e:
            perf_summary = performance_monitor.get_summary()
            logger.error(f"💥 Foundation setup failed with exception: {e}")
            logger.error(f"   ⏱️  Time before exception: {perf_summary.get('total_time', 0):.2f}s")

            if benchmark_mode:
                logger.error("\n📊 FAILURE ANALYSIS:")
                logger.error(f"   Exception type: {type(e).__name__}")
                logger.error(f"   Memory at failure: {perf_summary.get('peak_memory_mb', 0):.1f} MB")

            return {
                'success': False,
                'execution_time': perf_summary.get('total_time', 0),
                'error': str(e),
                'error_type': type(e).__name__,
                'memory_at_failure': perf_summary.get('peak_memory_mb', 0)
            }


async def run_enhanced_multi_year_simulation(
    start_year: int,
    end_year: int,
    optimization_level: OptimizationLevel,
    max_workers: int,
    batch_size: int,
    enable_compression: bool,
    fail_fast: bool,
    performance_mode: bool = False,
    config_path: Optional[str] = None
) -> Dict[str, Any]:
    """Run complete multi-year simulation with enhanced performance monitoring."""
    logger = logging.getLogger(__name__)
    performance_monitor = PerformanceMonitor()

    logger.info("🎯 Enhanced Multi-Year Simulation")
    logger.info(f"   📅 Years: {start_year}-{end_year} ({end_year - start_year + 1} years)")
    logger.info(f"   ⚙️  Optimization: {optimization_level.value}")
    logger.info(f"   👥 Max Workers: {max_workers}")
    logger.info(f"   📦 Batch Size: {batch_size}")
    logger.info(f"   🗜️  Compression: {'enabled' if enable_compression else 'disabled'}")
    logger.info(f"   ⚡ Fail Fast: {'enabled' if fail_fast else 'disabled'}")
    logger.info(f"   🏁 Performance Mode: {'ENABLED' if performance_mode else 'disabled'}")

    performance_monitor.start()

    # Load simulation configuration
    config = load_and_validate_config(config_path)
    performance_monitor.checkpoint("config_loaded")

    # Create multi-year configuration
    multi_year_config = MultiYearConfig(
        start_year=start_year,
        end_year=end_year,
        optimization_level=optimization_level,
        max_workers=max_workers,
        batch_size=batch_size,
        enable_state_compression=enable_compression,
        fail_fast=fail_fast,
        enable_concurrent_processing=True,
        enable_validation=True,
        performance_monitoring=True
    )

    troubleshooting = """
Multi-year simulation troubleshooting:
1. Ensure sequential year dependencies are met (2025 → 2026 → 2027...)
2. Check that foundation setup completed successfully
3. Verify sufficient memory for multi-year state management
4. Ensure database connections are not being held by other processes
5. Check that previous years completed without errors
    """

    with error_context("Multi-year simulation", troubleshooting):
        try:
            # Create orchestrator
            orchestrator = MultiYearOrchestrator(
                config=multi_year_config,
                base_config_path=Path(config_path) if config_path else None
            )
            performance_monitor.checkpoint("orchestrator_created")

            # Update orchestrator with simulation configuration
            orchestrator._simulation_config = config

            # Execute multi-year simulation
            logger.info("🏃 Executing optimized multi-year simulation...")
            result = await orchestrator.execute_multi_year_simulation()
            perf_summary = performance_monitor.get_summary()

            # Enhanced results logging
            if result.success:
                logger.info("🎉 Multi-year simulation COMPLETED successfully!")
                logger.info(f"   🆔 Simulation ID: {result.simulation_id}")
                logger.info(f"   📅 Years completed: {result.completed_years}")
                logger.info(f"   ⏱️  Total execution time: {result.total_execution_time:.2f}s")

                # Foundation setup metrics
                if result.foundation_setup_result:
                    foundation = result.foundation_setup_result
                    logger.info(f"   🚀 Foundation setup: {foundation.execution_time:.2f}s "
                               f"({foundation.performance_improvement:.1%} improvement)")
                    logger.info(f"      Target met (<10s): {'✅ YES' if foundation.execution_time < 10.0 else '❌ NO'}")

                # Performance metrics for performance mode
                if performance_mode:
                    logger.info(f"\n📊 PERFORMANCE ANALYSIS:")
                    logger.info(f"   Peak Memory: {perf_summary['peak_memory_mb']:.1f} MB")
                    logger.info(f"   Memory Efficiency: {perf_summary['memory_efficiency']:.1%}")
                    logger.info(f"   Success Rate: {result.success_rate:.1%}")

                    if 'records_per_second' in result.performance_metrics:
                        logger.info(f"   Processing Rate: {result.performance_metrics['records_per_second']:.0f} records/sec")

            else:
                logger.error("💥 Multi-year simulation FAILED!")
                logger.error(f"   ❌ Failed years: {result.failed_years}")
                logger.error(f"   ✅ Completed years: {result.completed_years}")
                logger.error(f"   ⏱️  Time before failure: {result.total_execution_time:.2f}s")

                failure_reason = result.performance_metrics.get('failure_reason', 'Unknown')
                logger.error(f"   🔍 Failure reason: {failure_reason}")

            return {
                'success': result.success,
                'simulation_id': result.simulation_id,
                'total_execution_time': result.total_execution_time,
                'completed_years': result.completed_years,
                'failed_years': result.failed_years,
                'success_rate': result.success_rate,
                'performance_metrics': {
                    **result.performance_metrics,
                    'peak_memory_mb': perf_summary['peak_memory_mb'],
                    'memory_efficiency': perf_summary['memory_efficiency']
                }
            }

        except Exception as e:
            perf_summary = performance_monitor.get_summary()
            logger.error(f"💥 Multi-year simulation failed with exception: {e}")
            logger.error(f"   ⏱️  Time before exception: {perf_summary.get('total_time', 0):.2f}s")

            return {
                'success': False,
                'total_execution_time': perf_summary.get('total_time', 0),
                'error': str(e),
                'error_type': type(e).__name__
            }


async def run_comprehensive_performance_comparison(
    start_year: int,
    end_year: int,
    config_path: Optional[str] = None,
    benchmark_mode: bool = False
) -> Dict[str, Any]:
    """Comprehensive performance comparison with regression testing."""
    logger = logging.getLogger(__name__)

    logger.info("🏁 COMPREHENSIVE PERFORMANCE COMPARISON")
    logger.info(f"   📅 Years: {start_year}-{end_year} ({end_year - start_year + 1} years)")
    logger.info(f"   🎯 Target: >82% performance improvement")
    logger.info(f"   📊 Benchmark Mode: {'ENABLED' if benchmark_mode else 'disabled'}")

    comparison_results = {
        'mvp_available': MVP_AVAILABLE,
        'mvp_success': False,
        'mvp_time': 0,
        'mvp_details': {},
        'new_success': False,
        'new_time': 0,
        'new_details': {},
        'improvement': 0.0,
        'target_met': False,
        'regression_test_passed': False,
        'performance_grade': 'FAILED'
    }

    # Load and validate configuration
    config = load_and_validate_config(config_path)

    # Test MVP orchestrator (baseline)
    if MVP_AVAILABLE:
        logger.info("\n🔄 TESTING MVP ORCHESTRATOR (Baseline)...")
        mvp_monitor = PerformanceMonitor()
        mvp_monitor.start()

        try:
            # Create legacy configuration format
            legacy_config = {
                'target_growth_rate': config['simulation']['target_growth_rate'],
                'workforce': config['workforce'],
                'eligibility': config.get('eligibility', {}),
                'enrollment': config.get('enrollment', {}),
                'random_seed': config.get('random_seed', 42)
            }

            mvp_orchestrator = MultiYearSimulationOrchestrator(
                start_year=start_year,
                end_year=end_year,
                config=legacy_config,
                preserve_data=False
            )

            mvp_result = mvp_orchestrator.run_simulation(skip_breaks=True)
            mvp_perf = mvp_monitor.get_summary()

            comparison_results.update({
                'mvp_success': len(mvp_result['years_completed']) == (end_year - start_year + 1),
                'mvp_time': mvp_perf['total_time'],
                'mvp_details': {
                    'years_completed': mvp_result['years_completed'],
                    'peak_memory_mb': mvp_perf['peak_memory_mb'],
                    'avg_memory_mb': mvp_perf['avg_memory_mb']
                }
            })

            logger.info(f"✅ MVP orchestrator completed successfully")
            logger.info(f"   ⏱️  Time: {mvp_perf['total_time']:.2f}s")
            logger.info(f"   📊 Years: {len(mvp_result['years_completed'])}/{end_year - start_year + 1}")
            logger.info(f"   💾 Peak Memory: {mvp_perf['peak_memory_mb']:.1f} MB")

        except Exception as e:
            mvp_perf = mvp_monitor.get_summary()
            comparison_results.update({
                'mvp_success': False,
                'mvp_time': mvp_perf.get('total_time', 0),
                'mvp_details': {'error': str(e)}
            })

            logger.error(f"❌ MVP orchestrator failed: {e}")
            logger.error(f"   ⏱️  Time before failure: {mvp_perf.get('total_time', 0):.2f}s")
    else:
        logger.warning("⚠️  MVP orchestrator not available for comparison")

    # Test new orchestrator_dbt (optimized)
    logger.info("\n🚀 TESTING OPTIMIZED ORCHESTRATOR (Target)...")
    new_result = await run_enhanced_multi_year_simulation(
        start_year=start_year,
        end_year=end_year,
        optimization_level=OptimizationLevel.HIGH,
        max_workers=8,
        batch_size=2000,
        enable_compression=True,
        fail_fast=False,
        performance_mode=True,
        config_path=config_path
    )

    comparison_results.update({
        'new_success': new_result['success'],
        'new_time': new_result['total_execution_time'],
        'new_details': {
            'completed_years': new_result.get('completed_years', []),
            'performance_metrics': new_result.get('performance_metrics', {})
        }
    })

    # Calculate performance improvement and regression test results
    if comparison_results['mvp_success'] and comparison_results['new_success']:
        mvp_time = comparison_results['mvp_time']
        new_time = comparison_results['new_time']

        if mvp_time > 0:
            improvement = (mvp_time - new_time) / mvp_time
            speedup = mvp_time / new_time if new_time > 0 else 0

            comparison_results.update({
                'improvement': improvement,
                'speedup': speedup,
                'target_met': improvement >= 0.82,
                'regression_test_passed': improvement >= 0.82
            })

            # Performance grading
            if improvement >= 0.90:
                grade = "🏆 OUTSTANDING"
            elif improvement >= 0.82:
                grade = "✅ TARGET MET"
            elif improvement >= 0.50:
                grade = "⚠️  GOOD"
            elif improvement >= 0.20:
                grade = "🔍 NEEDS IMPROVEMENT"
            else:
                grade = "❌ POOR"

            comparison_results['performance_grade'] = grade

    # Comprehensive results reporting
    logger.info("\n🎯 PERFORMANCE COMPARISON RESULTS:")
    logger.info("=" * 60)

    if MVP_AVAILABLE:
        logger.info(f"📊 MVP Orchestrator (Baseline):")
        logger.info(f"   Success: {'✅ YES' if comparison_results['mvp_success'] else '❌ NO'}")
        logger.info(f"   Time: {comparison_results['mvp_time']:.2f}s")
        if comparison_results['mvp_details'].get('peak_memory_mb'):
            logger.info(f"   Peak Memory: {comparison_results['mvp_details']['peak_memory_mb']:.1f} MB")

    logger.info(f"\n🚀 Optimized Orchestrator (Target):")
    logger.info(f"   Success: {'✅ YES' if comparison_results['new_success'] else '❌ NO'}")
    logger.info(f"   Time: {comparison_results['new_time']:.2f}s")

    if comparison_results['improvement'] > 0:
        logger.info(f"\n🏅️  PERFORMANCE METRICS:")
        logger.info(f"   Performance Improvement: {comparison_results['improvement']:.1%}")
        logger.info(f"   Speedup Factor: {comparison_results.get('speedup', 0):.1f}x")
        logger.info(f"   Target Achievement (82%): {'✅ SUCCESS' if comparison_results['target_met'] else '❌ FAILED'}")
        logger.info(f"   Performance Grade: {comparison_results['performance_grade']}")
        logger.info(f"   Regression Test: {'✅ PASSED' if comparison_results['regression_test_passed'] else '❌ FAILED'}")
    else:
        logger.warning("   ⚠️  Cannot calculate improvement - baseline or target failed")

    # Benchmark mode detailed reporting
    if benchmark_mode:
        logger.info("\n📊 DETAILED BENCHMARK REPORT:")
        logger.info("=" * 60)

        if MVP_AVAILABLE and comparison_results['mvp_success']:
            logger.info(f"MVP Details: {json.dumps(comparison_results['mvp_details'], indent=2)}")

        logger.info(f"New System Details: {json.dumps(comparison_results['new_details'], indent=2)}")

    return comparison_results


def parse_arguments() -> argparse.Namespace:
    """Parse command line arguments with comprehensive options."""
    parser = argparse.ArgumentParser(
        description="Multi-Year Simulation CLI with 82% performance improvement and comprehensive testing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Required arguments for simulation
    parser.add_argument(
        '--start-year',
        type=int,
        help='Start year for simulation (e.g., 2025)'
    )
    parser.add_argument(
        '--end-year',
        type=int,
        help='End year for simulation (e.g., 2029)'
    )

    # Optimization settings
    parser.add_argument(
        '--optimization',
        choices=['high', 'medium', 'low', 'fallback'],
        default='high',
        help='Optimization level (default: high)'
    )
    parser.add_argument(
        '--max-workers',
        type=int,
        default=4,
        help='Maximum concurrent workers (default: 4)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=1000,
        help='Batch size for processing (default: 1000)'
    )

    # Feature flags
    parser.add_argument(
        '--enable-compression',
        action='store_true',
        help='Enable state compression for memory efficiency'
    )
    parser.add_argument(
        '--fail-fast',
        action='store_true',
        help='Stop on first year failure (default: continue)'
    )
    parser.add_argument(
        '--performance-mode',
        action='store_true',
        help='Enable detailed performance monitoring and reporting'
    )

    # Operational modes
    parser.add_argument(
        '--foundation-only',
        action='store_true',
        help='Run foundation setup only (for performance testing)'
    )
    parser.add_argument(
        '--compare-mvp',
        action='store_true',
        help='Compare performance with existing MVP orchestrator'
    )
    parser.add_argument(
        '--test-config',
        action='store_true',
        help='Test configuration compatibility with both systems'
    )
    parser.add_argument(
        '--benchmark',
        action='store_true',
        help='Run in comprehensive benchmark mode with detailed reporting'
    )

    # Configuration
    parser.add_argument(
        '--config',
        type=str,
        help='Path to simulation configuration file (YAML)'
    )
    parser.add_argument(
        '--log-file',
        type=str,
        help='Path to log file (default: console only)'
    )

    # Logging options
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    parser.add_argument(
        '--structured-logs',
        action='store_true',
        help='Use structured logging format'
    )

    return parser.parse_args()


async def main():
    """Main CLI function with comprehensive error handling and reporting."""
    args = parse_arguments()

    # Setup logging
    logger = setup_comprehensive_logging(
        args.verbose,
        args.log_file,
        args.structured_logs
    )

    logger.info("🎯 PlanWise Navigator - Production Multi-Year Simulation CLI")
    logger.info("🚀 Optimized orchestrator_dbt with 82% performance improvement target")
    logger.info("=" * 70)

    # Parse optimization level
    optimization_map = {
        'high': OptimizationLevel.HIGH,
        'medium': OptimizationLevel.MEDIUM,
        'low': OptimizationLevel.LOW,
        'fallback': OptimizationLevel.FALLBACK
    }
    optimization_level = optimization_map[args.optimization]

    start_time = time.time()

    try:
        if args.test_config:
            # Configuration compatibility test
            logger.info("🔧 CONFIGURATION COMPATIBILITY TEST MODE")
            result = test_configuration_compatibility(args.config)

            logger.info("\n📋 COMPATIBILITY TEST RESULTS:")
            logger.info(f"   Configuration Valid: {'✅ YES' if result['config_valid'] else '❌ NO'}")
            logger.info(f"   New System Compatible: {'✅ YES' if result['new_system_compatible'] else '❌ NO'}")
            logger.info(f"   Legacy Compatible: {'✅ YES' if result['legacy_compatible'] else '❌ NO'}")

            if result['issues']:
                logger.warning("\n⚠️  Issues Found:")
                for issue in result['issues']:
                    logger.warning(f"   • {issue}")

            if result['recommendations']:
                logger.info("\n💡 Recommendations:")
                for rec in result['recommendations']:
                    logger.info(f"   • {rec}")

            success = result['config_valid'] and result['new_system_compatible']

        elif args.foundation_only:
            # Foundation setup benchmark
            logger.info("🚀 FOUNDATION SETUP BENCHMARK MODE")
            result = await run_foundation_benchmark(
                optimization_level=optimization_level,
                config_path=args.config,
                benchmark_mode=args.benchmark
            )

            success = result['success']

        elif args.compare_mvp:
            # MVP comparison with regression testing
            if not args.start_year or not args.end_year:
                logger.error("❌ --start-year and --end-year required for MVP comparison")
                sys.exit(1)

            logger.info("🏁 MVP PERFORMANCE COMPARISON MODE")
            result = await run_comprehensive_performance_comparison(
                start_year=args.start_year,
                end_year=args.end_year,
                config_path=args.config,
                benchmark_mode=args.benchmark
            )

            success = result['new_success'] and (result['mvp_success'] or not MVP_AVAILABLE)

        else:
            # Multi-year simulation
            if not args.start_year or not args.end_year:
                logger.error("❌ --start-year and --end-year required for simulation")
                sys.exit(1)

            logger.info("🎯 MULTI-YEAR SIMULATION MODE")
            result = await run_enhanced_multi_year_simulation(
                start_year=args.start_year,
                end_year=args.end_year,
                optimization_level=optimization_level,
                max_workers=args.max_workers,
                batch_size=args.batch_size,
                enable_compression=args.enable_compression,
                fail_fast=args.fail_fast,
                performance_mode=args.performance_mode or args.benchmark,
                config_path=args.config
            )

            success = result['success']

        total_time = time.time() - start_time

        if success:
            logger.info(f"\n🎉 CLI execution COMPLETED successfully in {total_time:.2f}s")
            logger.info("=" * 70)
            sys.exit(0)
        else:
            logger.error(f"\n💥 CLI execution FAILED after {total_time:.2f}s")
            logger.error("=" * 70)
            sys.exit(1)

    except KeyboardInterrupt:
        total_time = time.time() - start_time
        logger.info(f"\n⚡ Interrupted by user after {total_time:.2f}s")
        sys.exit(130)

    except Exception as e:
        total_time = time.time() - start_time
        logger.error(f"\n💥 CLI execution failed with exception after {total_time:.2f}s: {e}")

        if args.verbose:
            logger.error("🔍 Full traceback:")
            logger.error(traceback.format_exc())

        logger.error("=" * 70)
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
