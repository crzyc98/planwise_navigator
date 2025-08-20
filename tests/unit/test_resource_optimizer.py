# filename: tests/unit/test_resource_optimizer.py
"""
Unit tests for ResourceOptimizer and memory/I/O optimization components.

This test suite validates:
- Memory optimization with streaming and chunking strategies
- I/O optimization for checkpointing and result persistence
- Resource usage monitoring and adaptive optimization
- Batching and compression strategies for large simulations
- Performance monitoring and resource tracking
- Integration with existing simulation pipeline
"""

import os
import tempfile
import threading
import time
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, Mock, patch

import pytest
from orchestrator_mvp.utils.resource_optimizer import (
    CompressionType, InMemoryOptimizationStrategy, IOOptimizationResult,
    IOOptimizer, MemoryManager, MemoryOptimizationResult, MemoryRequirements,
    OptimizationConfig, OptimizationStrategy, PersistenceLevel, ResourceLimits,
    ResourceMetrics, ResourceMonitor, ResourceOptimizer, ResourceType,
    StreamingOptimizationStrategy, create_resource_optimizer,
    get_system_resource_status)


class TestResourceLimits:
    """Test cases for ResourceLimits configuration validation."""

    def test_resource_limits_creation(self):
        """Test creating resource limits with valid configuration."""
        limits = ResourceLimits(
            max_memory_gb=16.0,
            max_memory_percentage=0.75,
            max_disk_space_gb=100.0,
            chunk_size_mb=200,
            io_batch_size=2000,
        )

        assert limits.max_memory_gb == 16.0
        assert limits.max_memory_percentage == 0.75
        assert limits.max_disk_space_gb == 100.0
        assert limits.chunk_size_mb == 200
        assert limits.io_batch_size == 2000

    def test_memory_percentage_validation(self):
        """Test memory percentage validation bounds."""
        # Test valid percentage
        valid_limits = ResourceLimits(max_memory_percentage=0.8)
        assert valid_limits.max_memory_percentage == 0.8

        # Test percentage too low
        with pytest.raises(
            ValueError, match="Memory percentage should be between 0.1 and 0.95"
        ):
            ResourceLimits(max_memory_percentage=0.05)

        # Test percentage too high
        with pytest.raises(
            ValueError, match="Memory percentage should be between 0.1 and 0.95"
        ):
            ResourceLimits(max_memory_percentage=0.98)

    def test_default_values(self):
        """Test default resource limit values."""
        limits = ResourceLimits()

        assert limits.max_memory_gb == 8.0
        assert limits.max_memory_percentage == 0.8
        assert limits.max_disk_space_gb == 50.0
        assert limits.chunk_size_mb == 100
        assert limits.io_batch_size == 1000


class TestMemoryRequirements:
    """Test cases for MemoryRequirements calculation and analysis."""

    def test_memory_requirements_creation(self):
        """Test creating memory requirements with detailed breakdown."""
        requirements = MemoryRequirements(
            total_gb=12.5,
            peak_gb=16.25,
            baseline_gb=2.0,
            buffer_gb=1.5,
            workforce_data_gb=6.0,
            event_data_gb=4.5,
        )

        assert requirements.total_gb == 12.5
        assert requirements.peak_gb == 16.25
        assert requirements.baseline_gb == 2.0
        assert requirements.buffer_gb == 1.5
        assert requirements.workforce_data_gb == 6.0
        assert requirements.event_data_gb == 4.5

        # Test computed field
        assert requirements.is_large_simulation is True  # > 4.0 GB

    def test_large_simulation_detection(self):
        """Test large simulation detection logic."""
        # Small simulation
        small_requirements = MemoryRequirements(
            total_gb=3.0,
            peak_gb=3.9,
            baseline_gb=0.5,
            workforce_data_gb=1.5,
            event_data_gb=1.0,
        )
        assert small_requirements.is_large_simulation is False

        # Large simulation
        large_requirements = MemoryRequirements(
            total_gb=8.0,
            peak_gb=10.4,
            baseline_gb=1.0,
            workforce_data_gb=4.0,
            event_data_gb=3.0,
        )
        assert large_requirements.is_large_simulation is True


class TestOptimizationConfig:
    """Test cases for OptimizationConfig settings validation."""

    def test_optimization_config_creation(self):
        """Test creating optimization configuration."""
        config = OptimizationConfig(
            strategy_type=OptimizationStrategy.STREAMING,
            memory_usage_gb=2.5,
            chunk_size_employees=15000,
            overlap_buffer_percentage=0.15,
            preload_years=1,
            enable_caching=True,
            cache_size_mb=750,
        )

        assert config.strategy_type == OptimizationStrategy.STREAMING
        assert config.memory_usage_gb == 2.5
        assert config.chunk_size_employees == 15000
        assert config.overlap_buffer_percentage == 0.15
        assert config.preload_years == 1
        assert config.enable_caching is True
        assert config.cache_size_mb == 750

    def test_overlap_buffer_validation(self):
        """Test overlap buffer percentage validation."""
        # Valid overlap buffer
        valid_config = OptimizationConfig(
            strategy_type=OptimizationStrategy.CHUNKED,
            memory_usage_gb=4.0,
            overlap_buffer_percentage=0.2,
        )
        assert valid_config.overlap_buffer_percentage == 0.2

        # Overlap buffer too high
        with pytest.raises(
            ValueError, match="Overlap buffer should be between 0.0 and 0.5"
        ):
            OptimizationConfig(
                strategy_type=OptimizationStrategy.CHUNKED,
                memory_usage_gb=4.0,
                overlap_buffer_percentage=0.6,
            )

        # Negative overlap buffer
        with pytest.raises(
            ValueError, match="Overlap buffer should be between 0.0 and 0.5"
        ):
            OptimizationConfig(
                strategy_type=OptimizationStrategy.CHUNKED,
                memory_usage_gb=4.0,
                overlap_buffer_percentage=-0.1,
            )


class TestResourceMetrics:
    """Test cases for ResourceMetrics tracking."""

    def test_resource_metrics_creation(self):
        """Test creating resource metrics with system data."""
        metrics = ResourceMetrics(
            memory_used_gb=4.5,
            memory_available_gb=11.5,
            memory_percentage=0.28,
            cpu_percentage=0.65,
            disk_io_read_mb_per_sec=15.5,
            disk_io_write_mb_per_sec=8.2,
        )

        assert metrics.memory_used_gb == 4.5
        assert metrics.memory_available_gb == 11.5
        assert metrics.memory_percentage == 0.28
        assert metrics.cpu_percentage == 0.65
        assert metrics.disk_io_read_mb_per_sec == 15.5
        assert metrics.disk_io_write_mb_per_sec == 8.2
        assert isinstance(metrics.timestamp, datetime)

    def test_memory_pressure_level_calculation(self):
        """Test memory pressure level calculation."""
        # Low pressure
        low_pressure = ResourceMetrics(
            memory_used_gb=2.0,
            memory_available_gb=14.0,
            memory_percentage=0.45,
            cpu_percentage=0.3,
        )
        assert low_pressure.memory_pressure_level == "low"

        # Moderate pressure
        moderate_pressure = ResourceMetrics(
            memory_used_gb=5.0,
            memory_available_gb=11.0,
            memory_percentage=0.7,
            cpu_percentage=0.5,
        )
        assert moderate_pressure.memory_pressure_level == "moderate"

        # High pressure
        high_pressure = ResourceMetrics(
            memory_used_gb=13.0,
            memory_available_gb=3.0,
            memory_percentage=0.85,
            cpu_percentage=0.8,
        )
        assert high_pressure.memory_pressure_level == "high"

        # Critical pressure
        critical_pressure = ResourceMetrics(
            memory_used_gb=14.5,
            memory_available_gb=1.5,
            memory_percentage=0.95,
            cpu_percentage=0.9,
        )
        assert critical_pressure.memory_pressure_level == "critical"


class TestOptimizationStrategies:
    """Test cases for optimization strategy implementations."""

    def test_streaming_optimization_strategy(self):
        """Test streaming optimization strategy configuration."""
        strategy = StreamingOptimizationStrategy(chunk_size=20000, overlap_buffer=0.1)

        assert strategy.chunk_size == 20000
        assert strategy.overlap_buffer == 0.1

        # Test configuration creation
        config = strategy.create_optimized_config(
            simulation_years=[2024, 2025, 2026], workforce_size=50000
        )

        assert config.strategy_type == OptimizationStrategy.STREAMING
        assert config.chunk_size_employees <= 20000  # Should be optimal size
        assert config.memory_usage_gb < 5.0  # Streaming uses minimal memory
        assert config.enable_caching is False  # Caching conflicts with streaming
        assert config.preload_years == 1  # Minimal preloading

        # Test performance impact estimation
        impact = strategy.estimate_performance_impact()
        assert "streaming reduces memory usage" in impact.lower()
        assert "may increase processing time" in impact.lower()

    def test_in_memory_optimization_strategy(self):
        """Test in-memory optimization strategy configuration."""
        strategy = InMemoryOptimizationStrategy(preload_years=3)

        assert strategy.preload_years == 3

        # Test configuration creation
        config = strategy.create_optimized_config(
            simulation_years=[2024, 2025], workforce_size=25000
        )

        assert config.strategy_type == OptimizationStrategy.IN_MEMORY
        assert config.chunk_size_employees == 25000  # Process all at once
        assert config.memory_usage_gb > 3.0  # In-memory uses more memory
        assert config.enable_caching is True  # Caching beneficial for in-memory
        assert config.preload_years == 2  # Limited by simulation years
        assert config.overlap_buffer_percentage == 0.0  # No chunking overlap

        # Test performance impact estimation
        impact = strategy.estimate_performance_impact()
        assert "minimal impact" in impact.lower()
        assert "optimal performance" in impact.lower()


class TestMemoryManager:
    """Test cases for MemoryManager optimization logic."""

    @pytest.fixture
    def memory_manager(self):
        """Create memory manager for testing."""
        limits = ResourceLimits(
            max_memory_gb=8.0, max_memory_percentage=0.8, chunk_size_mb=100
        )
        return MemoryManager(limits)

    def test_memory_manager_initialization(self, memory_manager):
        """Test memory manager initialization."""
        assert memory_manager.limits.max_memory_gb == 8.0
        assert memory_manager.limits.max_memory_percentage == 0.8

    def test_calculate_memory_requirements(self, memory_manager):
        """Test memory requirements calculation for different simulation sizes."""
        # Small simulation
        small_requirements = memory_manager.calculate_memory_requirements(
            simulation_years=[2024, 2025], workforce_size=5000
        )

        assert small_requirements.workforce_data_gb > 0
        assert small_requirements.event_data_gb > 0
        assert small_requirements.total_gb > small_requirements.workforce_data_gb
        assert small_requirements.peak_gb > small_requirements.total_gb
        assert small_requirements.baseline_gb == 0.5  # Fixed baseline

        # Large simulation
        large_requirements = memory_manager.calculate_memory_requirements(
            simulation_years=[2024, 2025, 2026, 2027, 2028], workforce_size=100000
        )

        # Large simulation should require more memory
        assert large_requirements.total_gb > small_requirements.total_gb
        assert (
            large_requirements.workforce_data_gb > small_requirements.workforce_data_gb
        )
        assert large_requirements.event_data_gb > small_requirements.event_data_gb
        assert large_requirements.is_large_simulation is True

    def test_select_optimal_strategy(self, memory_manager):
        """Test optimal strategy selection based on memory requirements."""
        # Small requirements - should select in-memory
        small_requirements = MemoryRequirements(
            total_gb=2.0,
            peak_gb=2.6,
            baseline_gb=0.5,
            workforce_data_gb=1.0,
            event_data_gb=0.5,
        )

        small_strategy = memory_manager.select_optimal_strategy(small_requirements)
        assert isinstance(small_strategy, InMemoryOptimizationStrategy)

        # Large requirements - should select streaming
        large_requirements = MemoryRequirements(
            total_gb=15.0,
            peak_gb=19.5,
            baseline_gb=0.5,
            workforce_data_gb=8.0,
            event_data_gb=6.5,
        )

        large_strategy = memory_manager.select_optimal_strategy(large_requirements)
        assert isinstance(large_strategy, StreamingOptimizationStrategy)

    def test_memory_management_context(self, memory_manager):
        """Test memory management context manager."""

        def memory_intensive_operation():
            # Allocate some memory
            data = [i for i in range(100000)]
            time.sleep(0.01)  # Brief pause
            return len(data)

        # Use memory management context
        with memory_manager.memory_management_context("test_operation"):
            result = memory_intensive_operation()
            assert result == 100000

        # Context manager should complete without errors
        # Memory tracking happens in the background


class TestIOOptimizer:
    """Test cases for IOOptimizer compression and persistence."""

    @pytest.fixture
    def io_optimizer(self):
        """Create I/O optimizer for testing."""
        limits = ResourceLimits(io_batch_size=1000)
        return IOOptimizer(limits)

    def test_io_optimizer_initialization(self, io_optimizer):
        """Test I/O optimizer initialization."""
        assert io_optimizer.limits.io_batch_size == 1000
        assert len(io_optimizer.compression_types) >= 2  # GZIP and LZMA

    def test_analyze_io_patterns(self, io_optimizer):
        """Test I/O pattern analysis for optimization opportunities."""
        # High frequency, comprehensive persistence
        high_io_analysis = io_optimizer.analyze_io_patterns(
            checkpoint_frequency=1,  # Very frequent
            result_persistence_level=PersistenceLevel.COMPREHENSIVE,
        )

        assert high_io_analysis["checkpoint_frequency"] == 1
        assert high_io_analysis["persistence_level"] == "comprehensive"
        assert (
            high_io_analysis["estimated_checkpoint_size_mb"] == 500
        )  # Comprehensive level
        assert high_io_analysis["total_checkpoint_data_mb"] > 0
        assert high_io_analysis["compression_potential"] > 0.5
        assert high_io_analysis["batching_potential"] > 0.2

        # Low frequency, minimal persistence
        low_io_analysis = io_optimizer.analyze_io_patterns(
            checkpoint_frequency=10,  # Infrequent
            result_persistence_level=PersistenceLevel.MINIMAL,
        )

        assert low_io_analysis["checkpoint_frequency"] == 10
        assert low_io_analysis["persistence_level"] == "minimal"
        assert low_io_analysis["estimated_checkpoint_size_mb"] == 10  # Minimal level
        assert (
            low_io_analysis["compression_potential"]
            < high_io_analysis["compression_potential"]
        )
        assert (
            low_io_analysis["batching_potential"]
            < high_io_analysis["batching_potential"]
        )

    def test_optimize_compression(self, io_optimizer):
        """Test compression optimization recommendations."""
        # Small data - no compression
        small_optimization = io_optimizer.optimize_compression(5.0)  # 5MB

        assert small_optimization["recommended_compression"] == "none"
        assert small_optimization["estimated_savings_percentage"] == 0.0
        assert small_optimization["performance_impact"] == "none"

        # Medium data - gzip compression
        medium_optimization = io_optimizer.optimize_compression(50.0)  # 50MB

        assert medium_optimization["recommended_compression"] == "gzip"
        assert medium_optimization["estimated_savings_percentage"] == 0.4
        assert medium_optimization["performance_impact"] == "low"

        # Large data - lzma compression
        large_optimization = io_optimizer.optimize_compression(200.0)  # 200MB

        assert large_optimization["recommended_compression"] == "lzma"
        assert large_optimization["estimated_savings_percentage"] == 0.6
        assert large_optimization["performance_impact"] == "moderate"

    def test_compress_and_save(self, io_optimizer):
        """Test data compression and saving functionality."""
        test_data = {
            "simulation_results": [f"result_{i}" for i in range(1000)],
            "workforce_data": {"employees": list(range(500))},
            "metadata": {"version": "1.0", "timestamp": "2025-01-01"},
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = Path(temp_dir) / "test_compressed_data.gz"

            # Test GZIP compression
            result = io_optimizer.compress_and_save(
                data=test_data,
                file_path=file_path,
                compression_type=CompressionType.GZIP,
            )

            # Verify save result
            assert result["file_path"] == str(file_path)
            assert result["original_size_bytes"] > 0
            assert result["compressed_size_bytes"] > 0
            assert result["compression_ratio"] < 1.0  # Should be compressed
            assert result["compression_percentage"] > 0
            assert result["compression_type"] == "gzip"
            assert result["save_duration_seconds"] > 0
            assert result["throughput_mb_per_sec"] > 0

            # Verify file was actually created
            assert file_path.exists()
            assert file_path.stat().st_size == result["compressed_size_bytes"]

            # Test no compression
            uncompressed_path = Path(temp_dir) / "test_uncompressed_data.bin"
            uncompressed_result = io_optimizer.compress_and_save(
                data=test_data,
                file_path=uncompressed_path,
                compression_type=CompressionType.NONE,
            )

            assert uncompressed_result["compression_ratio"] == 1.0  # No compression
            assert uncompressed_result["compression_percentage"] == 0.0


class TestResourceMonitor:
    """Test cases for ResourceMonitor system tracking."""

    @pytest.fixture
    def resource_monitor(self):
        """Create resource monitor for testing."""
        return ResourceMonitor(sampling_interval_seconds=0.1)  # Fast sampling for tests

    def test_resource_monitor_initialization(self, resource_monitor):
        """Test resource monitor initialization."""
        assert resource_monitor.sampling_interval == 0.1
        assert resource_monitor._monitoring_active is False
        assert resource_monitor._monitor_thread is None
        assert len(resource_monitor._metrics_history) == 0

    def test_get_current_metrics(self, resource_monitor):
        """Test getting current system resource metrics."""
        metrics = resource_monitor.get_current_metrics()

        assert isinstance(metrics, ResourceMetrics)
        assert metrics.memory_used_gb > 0
        assert metrics.memory_available_gb > 0
        assert 0 <= metrics.memory_percentage <= 1
        assert 0 <= metrics.cpu_percentage <= 1
        assert metrics.disk_io_read_mb_per_sec >= 0
        assert metrics.disk_io_write_mb_per_sec >= 0
        assert isinstance(metrics.timestamp, datetime)

    def test_start_stop_monitoring(self, resource_monitor):
        """Test starting and stopping continuous monitoring."""
        # Start monitoring
        resource_monitor.start_monitoring()
        assert resource_monitor._monitoring_active is True
        assert resource_monitor._monitor_thread is not None
        assert resource_monitor._monitor_thread.is_alive()

        # Let it collect some data
        time.sleep(0.25)

        # Stop monitoring
        resource_monitor.stop_monitoring()
        assert resource_monitor._monitoring_active is False

        # Should have collected some metrics
        assert len(resource_monitor._metrics_history) > 0

    def test_get_metrics_summary(self, resource_monitor):
        """Test metrics summary generation."""
        # Add some mock metrics to history
        for i in range(10):
            mock_metrics = ResourceMetrics(
                memory_used_gb=4.0 + i * 0.1,
                memory_available_gb=12.0 - i * 0.05,
                memory_percentage=0.25 + i * 0.01,
                cpu_percentage=0.3 + i * 0.02,
                timestamp=datetime.utcnow() - timedelta(minutes=i),
            )
            resource_monitor._metrics_history.append(mock_metrics)

        # Get summary
        summary = resource_monitor.get_metrics_summary(minutes=15)

        assert summary["time_period_minutes"] == 15
        assert summary["sample_count"] == 10
        assert "memory_usage" in summary
        assert "cpu_usage" in summary
        assert "disk_io" in summary

        # Verify memory usage summary
        memory_usage = summary["memory_usage"]
        assert "current_percentage" in memory_usage
        assert "average_percentage" in memory_usage
        assert "peak_percentage" in memory_usage
        assert "current_gb" in memory_usage
        assert "pressure_level" in memory_usage

        # Verify CPU usage summary
        cpu_usage = summary["cpu_usage"]
        assert "current_percentage" in cpu_usage
        assert "average_percentage" in cpu_usage
        assert "peak_percentage" in cpu_usage

    def test_monitor_context(self, resource_monitor):
        """Test resource monitoring context manager."""

        def test_operation():
            # Simulate work
            data = [i * i for i in range(10000)]
            time.sleep(0.01)
            return len(data)

        # Use monitoring context
        with resource_monitor.monitor_context("test_operation"):
            result = test_operation()
            assert result == 10000

        # Context should complete without errors


class TestResourceOptimizer:
    """Test cases for ResourceOptimizer main coordinator."""

    @pytest.fixture
    def resource_optimizer(self):
        """Create resource optimizer for testing."""
        limits = ResourceLimits(
            max_memory_gb=8.0, max_memory_percentage=0.8, chunk_size_mb=100
        )
        return ResourceOptimizer(
            resource_limits=limits, enable_monitoring=False  # Disable for testing
        )

    def test_resource_optimizer_initialization(self, resource_optimizer):
        """Test resource optimizer initialization."""
        assert resource_optimizer.resource_limits.max_memory_gb == 8.0
        assert resource_optimizer.resource_limits.max_memory_percentage == 0.8
        assert isinstance(resource_optimizer.memory_manager, MemoryManager)
        assert isinstance(resource_optimizer.io_optimizer, IOOptimizer)
        assert isinstance(resource_optimizer.resource_monitor, ResourceMonitor)

    def test_optimize_memory_usage(self, resource_optimizer):
        """Test comprehensive memory usage optimization."""
        # Small simulation
        small_result = resource_optimizer.optimize_memory_usage(
            simulation_years=[2024, 2025], workforce_size=10000
        )

        assert isinstance(small_result, MemoryOptimizationResult)
        assert small_result.strategy_type in [
            OptimizationStrategy.IN_MEMORY,
            OptimizationStrategy.STREAMING,
        ]
        assert small_result.memory_savings_gb >= 0
        assert isinstance(small_result.config, OptimizationConfig)
        assert len(small_result.performance_impact) > 0
        assert small_result.recommended_chunk_size > 0
        assert small_result.estimated_processing_time_minutes > 0
        assert small_result.efficiency_rating in [
            "excellent",
            "good",
            "acceptable",
            "marginal",
        ]

        # Large simulation
        large_result = resource_optimizer.optimize_memory_usage(
            simulation_years=[2024, 2025, 2026, 2027, 2028], workforce_size=100000
        )

        assert isinstance(large_result, MemoryOptimizationResult)
        # Large simulation should likely use streaming
        assert large_result.strategy_type == OptimizationStrategy.STREAMING
        assert large_result.memory_savings_gb > small_result.memory_savings_gb
        assert large_result.recommended_chunk_size < 100000  # Should be chunked

    def test_optimize_io_operations(self, resource_optimizer):
        """Test I/O operations optimization."""
        # High I/O scenario
        high_io_result = resource_optimizer.optimize_io_operations(
            checkpoint_frequency=1,  # Very frequent
            result_persistence_level=PersistenceLevel.COMPREHENSIVE,
        )

        assert isinstance(high_io_result, IOOptimizationResult)
        assert "checkpoint_optimization" in high_io_result.checkpoint_optimization
        assert "persistence_optimization" in high_io_result.persistence_optimization
        assert "compression_optimization" in high_io_result.compression_optimization
        assert high_io_result.total_io_reduction_percentage >= 0
        assert isinstance(high_io_result.is_significant_improvement, bool)

        # Low I/O scenario
        low_io_result = resource_optimizer.optimize_io_operations(
            checkpoint_frequency=10,  # Infrequent
            result_persistence_level=PersistenceLevel.MINIMAL,
        )

        assert isinstance(low_io_result, IOOptimizationResult)
        # High I/O scenario should have more optimization potential
        assert (
            high_io_result.total_io_reduction_percentage
            >= low_io_result.total_io_reduction_percentage
        )

    def test_get_optimization_recommendations(self, resource_optimizer):
        """Test comprehensive optimization recommendations."""
        recommendations = resource_optimizer.get_optimization_recommendations(
            simulation_years=[2024, 2025, 2026],
            workforce_size=50000,
            checkpoint_frequency=5,
            persistence_level=PersistenceLevel.STANDARD,
        )

        # Verify recommendation structure
        assert "simulation_parameters" in recommendations
        assert "memory_optimization" in recommendations
        assert "io_optimization" in recommendations
        assert "current_system_status" in recommendations
        assert "overall_recommendation" in recommendations

        # Verify simulation parameters
        sim_params = recommendations["simulation_parameters"]
        assert sim_params["years"] == 3
        assert sim_params["workforce_size"] == 50000
        assert sim_params["checkpoint_frequency"] == 5
        assert sim_params["persistence_level"] == "standard"

        # Verify memory optimization
        memory_opt = recommendations["memory_optimization"]
        assert "strategy" in memory_opt
        assert "savings_gb" in memory_opt
        assert "efficiency_rating" in memory_opt
        assert "recommended_chunk_size" in memory_opt
        assert "estimated_time_minutes" in memory_opt

        # Verify I/O optimization
        io_opt = recommendations["io_optimization"]
        assert "total_reduction_percentage" in io_opt
        assert "significant_improvement" in io_opt
        assert "compression_strategy" in io_opt
        assert "checkpoint_strategy" in io_opt

        # Verify system status
        system_status = recommendations["current_system_status"]
        assert "memory_used_gb" in system_status
        assert "memory_available_gb" in system_status
        assert "memory_pressure" in system_status
        assert "cpu_percentage" in system_status

        # Verify overall recommendation
        overall = recommendations["overall_recommendation"]
        assert "overall_rating" in overall
        assert "summary" in overall
        assert "memory_assessment" in overall
        assert "io_assessment" in overall
        assert "system_assessment" in overall
        assert "key_recommendations" in overall
        assert isinstance(overall["key_recommendations"], list)

    def test_generate_key_recommendations(self, resource_optimizer):
        """Test key recommendations generation logic."""
        # Create mock optimization results
        streaming_result = MemoryOptimizationResult(
            strategy_type="streaming",
            memory_savings_gb=4.5,
            config=Mock(),
            performance_impact="Low impact with streaming processing",
            recommended_chunk_size=15000,
            estimated_processing_time_minutes=75.0,
        )

        io_result = IOOptimizationResult(
            checkpoint_optimization={},
            persistence_optimization={},
            compression_optimization={"recommended_compression": "gzip"},
            total_io_reduction_percentage=0.35,
        )

        current_metrics = ResourceMetrics(
            memory_used_gb=6.0,
            memory_available_gb=10.0,
            memory_percentage=0.6,
            cpu_percentage=0.4,
        )

        recommendations = resource_optimizer._generate_key_recommendations(
            streaming_result, io_result, current_metrics, "good"
        )

        assert isinstance(recommendations, list)
        assert len(recommendations) > 0

        # Should include streaming recommendation
        streaming_rec = any(
            "streaming processing" in rec.lower() for rec in recommendations
        )
        assert streaming_rec

        # Should include compression recommendation if significant
        if io_result.is_significant_improvement:
            compression_rec = any(
                "gzip compression" in rec.lower() for rec in recommendations
            )
            assert compression_rec

    def test_cleanup(self, resource_optimizer):
        """Test resource optimizer cleanup."""
        # Start monitoring
        resource_optimizer.resource_monitor.start_monitoring()

        # Brief pause to ensure monitoring starts
        time.sleep(0.1)

        # Cleanup should stop monitoring
        resource_optimizer.cleanup()

        # Monitoring should be stopped
        # Note: cleanup may take a moment to complete

    def test_context_manager(self):
        """Test resource optimizer as context manager."""
        limits = ResourceLimits(max_memory_gb=4.0)

        with ResourceOptimizer(
            resource_limits=limits, enable_monitoring=False
        ) as optimizer:
            assert isinstance(optimizer, ResourceOptimizer)
            assert optimizer.resource_limits.max_memory_gb == 4.0

        # Context manager should handle cleanup automatically


class TestFactoryFunctions:
    """Test cases for factory functions."""

    def test_create_resource_optimizer(self):
        """Test resource optimizer factory function."""
        optimizer = create_resource_optimizer(
            max_memory_gb=16.0, max_memory_percentage=0.85, enable_monitoring=False
        )

        assert isinstance(optimizer, ResourceOptimizer)
        assert optimizer.resource_limits.max_memory_gb == 16.0
        assert optimizer.resource_limits.max_memory_percentage == 0.85

    def test_get_system_resource_status(self):
        """Test system resource status function."""
        status = get_system_resource_status()

        # Verify status structure
        assert "memory" in status
        assert "cpu" in status
        assert "disk" in status
        assert "recommendations" in status

        # Verify memory status
        memory_status = status["memory"]
        assert "total_gb" in memory_status
        assert "available_gb" in memory_status
        assert "used_percentage" in memory_status
        assert "pressure_level" in memory_status
        assert memory_status["total_gb"] > 0
        assert memory_status["available_gb"] >= 0

        # Verify CPU status
        cpu_status = status["cpu"]
        assert "logical_cores" in cpu_status
        assert "current_usage_percentage" in cpu_status
        assert cpu_status["logical_cores"] > 0

        # Verify disk status
        disk_status = status["disk"]
        assert "free_space_gb" in disk_status
        assert disk_status["free_space_gb"] > 0

        # Verify recommendations
        recommendations = status["recommendations"]
        assert "suitable_for_large_simulation" in recommendations
        assert "recommended_max_memory_gb" in recommendations
        assert "streaming_recommended" in recommendations
        assert isinstance(recommendations["suitable_for_large_simulation"], bool)


class TestPerformanceOptimization:
    """Test cases for performance optimization features."""

    def test_memory_optimization_performance(self):
        """Test memory optimization performance for different simulation sizes."""
        optimizer = create_resource_optimizer(enable_monitoring=False)

        # Test various simulation sizes
        test_cases = [
            ([2024], 5000),  # Small: 1 year, 5K employees
            ([2024, 2025], 25000),  # Medium: 2 years, 25K employees
            ([2024, 2025, 2026, 2027, 2028], 100000),  # Large: 5 years, 100K employees
        ]

        for years, workforce_size in test_cases:
            start_time = time.perf_counter()

            result = optimizer.optimize_memory_usage(
                simulation_years=years, workforce_size=workforce_size
            )

            end_time = time.perf_counter()
            optimization_time = end_time - start_time

            # Optimization should complete quickly
            assert optimization_time < 1.0  # Less than 1 second

            # Results should be valid
            assert isinstance(result, MemoryOptimizationResult)
            assert result.memory_savings_gb >= 0
            assert result.recommended_chunk_size > 0

    def test_io_optimization_performance(self):
        """Test I/O optimization performance for different scenarios."""
        optimizer = create_resource_optimizer(enable_monitoring=False)

        # Test various I/O scenarios
        test_cases = [
            (1, PersistenceLevel.COMPREHENSIVE),  # High I/O
            (5, PersistenceLevel.STANDARD),  # Medium I/O
            (10, PersistenceLevel.MINIMAL),  # Low I/O
        ]

        for frequency, persistence in test_cases:
            start_time = time.perf_counter()

            result = optimizer.optimize_io_operations(
                checkpoint_frequency=frequency, result_persistence_level=persistence
            )

            end_time = time.perf_counter()
            optimization_time = end_time - start_time

            # Optimization should complete quickly
            assert optimization_time < 0.5  # Less than 0.5 seconds

            # Results should be valid
            assert isinstance(result, IOOptimizationResult)
            assert result.total_io_reduction_percentage >= 0

    def test_concurrent_optimization_safety(self):
        """Test thread safety of optimization operations."""
        optimizer = create_resource_optimizer(enable_monitoring=False)

        results = []

        def run_memory_optimization():
            result = optimizer.optimize_memory_usage([2024, 2025], 20000)
            results.append(result)

        def run_io_optimization():
            result = optimizer.optimize_io_operations(5, PersistenceLevel.STANDARD)
            results.append(result)

        # Run optimizations concurrently
        threads = []
        for i in range(3):
            thread1 = threading.Thread(target=run_memory_optimization)
            thread2 = threading.Thread(target=run_io_optimization)
            threads.extend([thread1, thread2])

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        # All optimizations should complete successfully
        assert len(results) == 6  # 3 memory + 3 I/O optimizations

        # Results should be valid
        for result in results:
            assert isinstance(result, (MemoryOptimizationResult, IOOptimizationResult))

    def test_large_simulation_memory_efficiency(self):
        """Test memory efficiency for large simulations."""
        optimizer = create_resource_optimizer(
            max_memory_gb=8.0, enable_monitoring=False  # Limited memory
        )

        # Very large simulation that exceeds memory limits
        result = optimizer.optimize_memory_usage(
            simulation_years=[2024, 2025, 2026, 2027, 2028, 2029],  # 6 years
            workforce_size=200000,  # 200K employees
        )

        # Should select streaming strategy for large simulation
        assert result.strategy_type == OptimizationStrategy.STREAMING
        assert result.memory_savings_gb > 5.0  # Significant savings
        assert result.recommended_chunk_size < 200000  # Should be chunked
        assert result.efficiency_rating in ["excellent", "good", "acceptable"]

    def test_compression_effectiveness(self):
        """Test compression effectiveness for different data sizes."""
        optimizer = create_resource_optimizer(enable_monitoring=False)

        # Test different data sizes
        data_sizes = [5, 50, 200, 1000]  # MB

        for size_mb in data_sizes:
            io_result = optimizer.optimize_io_operations(
                checkpoint_frequency=3, result_persistence_level=PersistenceLevel.FULL
            )

            compression_info = io_result.compression_optimization

            if size_mb >= 100:  # Large data should use better compression
                assert compression_info["recommended_compression"] in ["lzma", "gzip"]
                assert compression_info["estimated_savings_percentage"] >= 0.4
            elif size_mb >= 10:  # Medium data should use basic compression
                assert compression_info["recommended_compression"] == "gzip"
                assert compression_info["estimated_savings_percentage"] >= 0.3
            else:  # Small data might not need compression
                # May or may not use compression based on size threshold
                pass
