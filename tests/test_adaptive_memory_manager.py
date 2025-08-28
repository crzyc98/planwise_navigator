#!/usr/bin/env python3
"""
Test Suite for Adaptive Memory Management System

Story S063-08: Tests for real-time memory monitoring, adaptive batch sizing,
dynamic garbage collection, and optimization recommendations.
"""

import gc
import tempfile
import time
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

# Import the modules we're testing
from navigator_orchestrator.adaptive_memory_manager import (
    AdaptiveConfig,
    AdaptiveMemoryManager,
    BatchSizeConfig,
    MemoryPressureLevel,
    MemoryRecommendation,
    MemorySnapshot,
    MemoryThresholds,
    OptimizationLevel,
    create_adaptive_memory_manager
)
from navigator_orchestrator.logger import ProductionLogger


class TestMemorySnapshot(unittest.TestCase):
    """Test MemorySnapshot dataclass functionality"""

    def test_memory_snapshot_creation(self):
        """Test creating a memory snapshot"""
        snapshot = MemorySnapshot(
            timestamp=datetime.utcnow(),
            rss_mb=1500.0,
            vms_mb=2000.0,
            percent=75.0,
            available_mb=1000.0,
            pressure_level=MemoryPressureLevel.MODERATE,
            gc_collections=5,
            batch_size=500,
            operation="test_operation"
        )

        self.assertEqual(snapshot.rss_mb, 1500.0)
        self.assertEqual(snapshot.pressure_level, MemoryPressureLevel.MODERATE)
        self.assertEqual(snapshot.operation, "test_operation")


class TestMemoryRecommendation(unittest.TestCase):
    """Test MemoryRecommendation functionality"""

    def test_recommendation_creation(self):
        """Test creating a memory recommendation"""
        recommendation = MemoryRecommendation(
            "test_type",
            "Test description",
            "Test action",
            priority="high",
            estimated_savings_mb=100.0,
            confidence=0.8
        )

        self.assertEqual(recommendation.type, "test_type")
        self.assertEqual(recommendation.priority, "high")
        self.assertEqual(recommendation.estimated_savings_mb, 100.0)
        self.assertEqual(recommendation.confidence, 0.8)

    def test_recommendation_to_dict(self):
        """Test recommendation serialization"""
        recommendation = MemoryRecommendation(
            "memory_leak",
            "Potential memory leak detected",
            "Consider profiling",
            priority="high"
        )

        result = recommendation.to_dict()

        self.assertIn("type", result)
        self.assertIn("description", result)
        self.assertIn("action", result)
        self.assertIn("priority", result)
        self.assertIn("timestamp", result)
        self.assertEqual(result["type"], "memory_leak")
        self.assertEqual(result["priority"], "high")


class TestBatchSizeConfig(unittest.TestCase):
    """Test BatchSizeConfig functionality"""

    def test_batch_size_defaults(self):
        """Test default batch sizes"""
        config = BatchSizeConfig()

        self.assertEqual(config.low, 250)
        self.assertEqual(config.medium, 500)
        self.assertEqual(config.high, 1000)
        self.assertEqual(config.fallback, 100)

    def test_get_size_for_level(self):
        """Test getting batch size for optimization level"""
        config = BatchSizeConfig(low=200, medium=400, high=800, fallback=50)

        self.assertEqual(config.get_size(OptimizationLevel.LOW), 200)
        self.assertEqual(config.get_size(OptimizationLevel.MEDIUM), 400)
        self.assertEqual(config.get_size(OptimizationLevel.HIGH), 800)
        self.assertEqual(config.get_size(OptimizationLevel.FALLBACK), 50)


class TestMemoryThresholds(unittest.TestCase):
    """Test MemoryThresholds functionality"""

    def test_threshold_defaults(self):
        """Test default memory thresholds"""
        thresholds = MemoryThresholds()

        self.assertEqual(thresholds.moderate_mb, 2000.0)
        self.assertEqual(thresholds.high_mb, 3000.0)
        self.assertEqual(thresholds.critical_mb, 3500.0)
        self.assertEqual(thresholds.gc_trigger_mb, 2500.0)
        self.assertEqual(thresholds.fallback_trigger_mb, 3200.0)


class TestAdaptiveConfig(unittest.TestCase):
    """Test AdaptiveConfig functionality"""

    def test_config_defaults(self):
        """Test default adaptive configuration"""
        config = AdaptiveConfig()

        self.assertTrue(config.enabled)
        self.assertEqual(config.monitoring_interval_seconds, 1.0)
        self.assertEqual(config.history_size, 100)
        self.assertTrue(config.auto_gc_enabled)
        self.assertTrue(config.fallback_enabled)
        self.assertFalse(config.profiling_enabled)
        self.assertTrue(config.leak_detection_enabled)


class TestAdaptiveMemoryManager(unittest.TestCase):
    """Test AdaptiveMemoryManager functionality"""

    def setUp(self):
        """Set up test environment"""
        self.logger = Mock(spec=ProductionLogger)
        self.temp_dir = Path(tempfile.mkdtemp())

        self.config = AdaptiveConfig(
            enabled=True,
            monitoring_interval_seconds=0.1,  # Fast for testing
            history_size=10,
            thresholds=MemoryThresholds(
                moderate_mb=100.0,  # Low thresholds for testing
                high_mb=200.0,
                critical_mb=300.0,
                gc_trigger_mb=150.0,
                fallback_trigger_mb=250.0
            )
        )

        self.manager = AdaptiveMemoryManager(
            self.config,
            self.logger,
            reports_dir=self.temp_dir
        )

    def tearDown(self):
        """Clean up test environment"""
        if self.manager._monitoring_active:
            self.manager.stop_monitoring()

        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_initialization(self):
        """Test memory manager initialization"""
        self.assertIsNotNone(self.manager)
        self.assertEqual(self.manager.config, self.config)
        self.assertEqual(self.manager.logger, self.logger)
        self.assertFalse(self.manager._monitoring_active)
        self.assertEqual(len(self.manager._history), 0)

    def test_start_stop_monitoring(self):
        """Test starting and stopping memory monitoring"""
        self.assertFalse(self.manager._monitoring_active)

        self.manager.start_monitoring()
        self.assertTrue(self.manager._monitoring_active)
        self.assertIsNotNone(self.manager._monitoring_thread)

        # Wait a bit for monitoring to collect samples
        time.sleep(0.2)

        self.manager.stop_monitoring()
        self.assertFalse(self.manager._monitoring_active)

    @patch('psutil.Process')
    def test_memory_snapshot(self, mock_process_class):
        """Test taking memory snapshots"""
        # Mock process memory info
        mock_process = Mock()
        mock_memory_info = Mock()
        mock_memory_info.rss = 1024 * 1024 * 1500  # 1500 MB in bytes
        mock_memory_info.vms = 1024 * 1024 * 2000  # 2000 MB in bytes
        mock_process.memory_info.return_value = mock_memory_info
        mock_process_class.return_value = mock_process

        # Mock system memory
        with patch('psutil.virtual_memory') as mock_vm:
            mock_vm.return_value.percent = 60.0
            mock_vm.return_value.available = 1024 * 1024 * 1024 * 2  # 2GB available

            snapshot = self.manager._take_memory_snapshot("test_operation")

            self.assertEqual(snapshot.rss_mb, 1500.0)
            self.assertEqual(snapshot.vms_mb, 2000.0)
            self.assertEqual(snapshot.percent, 60.0)
            self.assertEqual(snapshot.operation, "test_operation")

    def test_pressure_level_calculation(self):
        """Test memory pressure level calculation"""
        # Test different pressure levels
        self.assertEqual(
            self.manager._calculate_pressure_level(50.0, 3000.0),
            MemoryPressureLevel.LOW
        )
        self.assertEqual(
            self.manager._calculate_pressure_level(150.0, 1500.0),
            MemoryPressureLevel.MODERATE
        )
        self.assertEqual(
            self.manager._calculate_pressure_level(250.0, 1200.0),
            MemoryPressureLevel.HIGH
        )
        self.assertEqual(
            self.manager._calculate_pressure_level(350.0, 400.0),
            MemoryPressureLevel.CRITICAL
        )

    @patch('gc.collect')
    def test_garbage_collection_trigger(self, mock_gc_collect):
        """Test automatic garbage collection triggering"""
        mock_gc_collect.return_value = 42  # Objects collected

        # Create snapshot that should trigger GC
        snapshot = MemorySnapshot(
            timestamp=datetime.utcnow(),
            rss_mb=160.0,  # Above gc_trigger_mb (150.0)
            vms_mb=200.0,
            percent=70.0,
            available_mb=1000.0,
            pressure_level=MemoryPressureLevel.MODERATE,
            gc_collections=5,
            batch_size=500
        )

        self.manager._trigger_garbage_collection(snapshot)

        mock_gc_collect.assert_called_once()
        self.assertEqual(self.manager._stats["total_gc_collections"], 1)

    def test_batch_size_adjustment(self):
        """Test adaptive batch size adjustment"""
        # Start with medium optimization level
        self.assertEqual(self.manager._current_optimization_level, OptimizationLevel.MEDIUM)
        self.assertEqual(self.manager._current_batch_size, 500)

        # Test adjustment to high pressure (should reduce batch size)
        high_pressure_snapshot = MemorySnapshot(
            timestamp=datetime.utcnow(),
            rss_mb=250.0,  # High pressure
            vms_mb=300.0,
            percent=80.0,
            available_mb=800.0,
            pressure_level=MemoryPressureLevel.HIGH,
            gc_collections=5,
            batch_size=500
        )

        self.manager._adjust_batch_size(high_pressure_snapshot)

        self.assertEqual(self.manager._current_optimization_level, OptimizationLevel.LOW)
        self.assertEqual(self.manager._current_batch_size, 250)
        self.assertEqual(self.manager._stats["batch_size_adjustments"], 1)

        # Test adjustment to critical pressure (should enable fallback)
        critical_pressure_snapshot = MemorySnapshot(
            timestamp=datetime.utcnow(),
            rss_mb=280.0,  # Above fallback trigger (250.0)
            vms_mb=350.0,
            percent=90.0,
            available_mb=400.0,
            pressure_level=MemoryPressureLevel.CRITICAL,
            gc_collections=6,
            batch_size=250
        )

        self.manager._adjust_batch_size(critical_pressure_snapshot)

        self.assertEqual(self.manager._current_optimization_level, OptimizationLevel.FALLBACK)
        self.assertEqual(self.manager._current_batch_size, 100)
        self.assertTrue(self.manager._fallback_active)
        self.assertEqual(self.manager._stats["automatic_fallbacks"], 1)

    def test_memory_leak_detection(self):
        """Test memory leak detection"""
        # Add some history with increasing memory usage
        base_time = datetime.utcnow()
        for i in range(5):
            snapshot = MemorySnapshot(
                timestamp=base_time + timedelta(minutes=i),
                rss_mb=1000.0 + (i * 150.0),  # Increasing memory usage
                vms_mb=1500.0,
                percent=70.0,
                available_mb=1000.0,
                pressure_level=MemoryPressureLevel.MODERATE,
                gc_collections=5,
                batch_size=500
            )
            self.manager._history.append(snapshot)

        # Current snapshot shows significant growth
        current_snapshot = MemorySnapshot(
            timestamp=base_time + timedelta(minutes=10),
            rss_mb=1600.0,  # 600MB growth from start
            vms_mb=1800.0,
            percent=80.0,
            available_mb=800.0,
            pressure_level=MemoryPressureLevel.HIGH,
            gc_collections=6,
            batch_size=500
        )

        self.manager._check_memory_leaks(current_snapshot)

        # Should detect memory leak and add recommendation
        self.assertTrue(len(self.manager._recommendations) > 0)
        leak_rec = self.manager._recommendations[0]
        self.assertEqual(leak_rec.type, "memory_leak")
        self.assertIn("leak", leak_rec.description.lower())

    def test_profiling_hooks(self):
        """Test memory profiling hooks"""
        hook_called = False
        hook_snapshot = None

        def test_hook(snapshot):
            nonlocal hook_called, hook_snapshot
            hook_called = True
            hook_snapshot = snapshot

        self.manager.add_profiling_hook(test_hook)

        # Enable profiling and take a snapshot
        self.manager.config.profiling_enabled = True
        snapshot = MemorySnapshot(
            timestamp=datetime.utcnow(),
            rss_mb=1000.0,
            vms_mb=1200.0,
            percent=70.0,
            available_mb=1000.0,
            pressure_level=MemoryPressureLevel.MODERATE,
            gc_collections=5,
            batch_size=500
        )

        # Process snapshot should call hooks
        self.manager._process_snapshot(snapshot)

        self.assertTrue(hook_called)
        self.assertEqual(hook_snapshot, snapshot)

    def test_memory_statistics(self):
        """Test memory statistics generation"""
        # Add some history
        for i in range(5):
            snapshot = MemorySnapshot(
                timestamp=datetime.utcnow(),
                rss_mb=1000.0 + (i * 50.0),
                vms_mb=1200.0,
                percent=70.0,
                available_mb=1000.0,
                pressure_level=MemoryPressureLevel.MODERATE,
                gc_collections=i,
                batch_size=500
            )
            self.manager._history.append(snapshot)

        # Add some stats
        self.manager._stats["total_gc_collections"] = 3
        self.manager._stats["batch_size_adjustments"] = 2

        stats = self.manager.get_memory_statistics()

        self.assertIn("current", stats)
        self.assertIn("trends", stats)
        self.assertIn("stats", stats)

        # Check current stats
        current = stats["current"]
        self.assertIn("memory_mb", current)
        self.assertIn("optimization_level", current)

        # Check trends
        trends = stats["trends"]
        self.assertIn("avg_memory_mb", trends)
        self.assertIn("peak_memory_mb", trends)

        # Check stats
        self.assertEqual(stats["stats"]["total_gc_collections"], 3)
        self.assertEqual(stats["stats"]["batch_size_adjustments"], 2)

    def test_recommendations_generation(self):
        """Test optimization recommendations generation"""
        # Create pattern that should generate recommendations
        base_time = datetime.utcnow() - timedelta(minutes=10)

        # High memory usage pattern
        for i in range(15):  # More than min_samples_for_recommendation
            snapshot = MemorySnapshot(
                timestamp=base_time + timedelta(minutes=i * 0.5),
                rss_mb=180.0,  # Consistently above moderate threshold
                vms_mb=220.0,
                percent=80.0,
                available_mb=800.0,
                pressure_level=MemoryPressureLevel.HIGH,
                gc_collections=i + 5,
                batch_size=500
            )
            self.manager._history.append(snapshot)

        # Force recommendation update
        self.manager._last_recommendation_time = base_time
        current_snapshot = MemorySnapshot(
            timestamp=datetime.utcnow(),
            rss_mb=190.0,
            vms_mb=230.0,
            percent=82.0,
            available_mb=750.0,
            pressure_level=MemoryPressureLevel.HIGH,
            gc_collections=20,
            batch_size=500
        )

        self.manager._update_recommendations(current_snapshot)

        recommendations = self.manager.get_recommendations()
        self.assertTrue(len(recommendations) > 0)

        # Should have high memory pattern recommendation
        high_memory_recs = [r for r in recommendations if r["type"] == "high_memory_pattern"]
        self.assertTrue(len(high_memory_recs) > 0)

    def test_export_memory_profile(self):
        """Test memory profile export"""
        # Add some test data
        snapshot = MemorySnapshot(
            timestamp=datetime.utcnow(),
            rss_mb=1000.0,
            vms_mb=1200.0,
            percent=70.0,
            available_mb=1000.0,
            pressure_level=MemoryPressureLevel.MODERATE,
            gc_collections=5,
            batch_size=500,
            operation="test"
        )
        self.manager._history.append(snapshot)

        # Add a recommendation
        self.manager._recommendations.append(
            MemoryRecommendation("test", "Test recommendation", "Test action")
        )

        # Export profile
        profile_path = self.manager.export_memory_profile()

        self.assertTrue(profile_path.exists())
        self.assertTrue(profile_path.name.startswith("memory_profile_"))
        self.assertTrue(profile_path.name.endswith(".json"))

        # Verify content
        import json
        with open(profile_path) as f:
            data = json.load(f)

        self.assertIn("metadata", data)
        self.assertIn("statistics", data)
        self.assertIn("history", data)
        self.assertIn("recommendations", data)

        # Verify history entry
        self.assertEqual(len(data["history"]), 1)
        history_entry = data["history"][0]
        self.assertEqual(history_entry["rss_mb"], 1000.0)
        self.assertEqual(history_entry["operation"], "test")

    def test_context_manager(self):
        """Test context manager functionality"""
        with AdaptiveMemoryManager(self.config, self.logger) as manager:
            self.assertTrue(manager._monitoring_active)
            # Wait briefly to ensure monitoring starts
            time.sleep(0.1)

        # After context manager exits, monitoring should be stopped
        self.assertFalse(manager._monitoring_active)


class TestCreateAdaptiveMemoryManager(unittest.TestCase):
    """Test factory function for creating adaptive memory managers"""

    def test_create_with_defaults(self):
        """Test creating manager with default settings"""
        manager = create_adaptive_memory_manager()

        self.assertIsInstance(manager, AdaptiveMemoryManager)
        self.assertEqual(manager._current_optimization_level, OptimizationLevel.MEDIUM)
        self.assertIsNotNone(manager.logger)

    def test_create_with_memory_limit(self):
        """Test creating manager with memory limit"""
        manager = create_adaptive_memory_manager(
            memory_limit_gb=2.0,
            optimization_level=OptimizationLevel.LOW
        )

        self.assertEqual(manager._current_optimization_level, OptimizationLevel.LOW)
        # Should have calculated thresholds based on 2GB limit
        self.assertEqual(manager.config.thresholds.moderate_mb, 1024.0)  # 50% of 2GB
        self.assertEqual(manager.config.thresholds.high_mb, 1536.0)      # 75% of 2GB

    def test_create_with_overrides(self):
        """Test creating manager with configuration overrides"""
        manager = create_adaptive_memory_manager(
            enabled=False,
            monitoring_interval_seconds=2.0,
            auto_gc_enabled=False
        )

        self.assertFalse(manager.config.enabled)
        self.assertEqual(manager.config.monitoring_interval_seconds, 2.0)
        self.assertFalse(manager.config.auto_gc_enabled)


class TestMemoryPressureLevels(unittest.TestCase):
    """Test memory pressure level calculations and behaviors"""

    def setUp(self):
        """Set up test environment"""
        self.logger = Mock(spec=ProductionLogger)
        self.config = AdaptiveConfig(
            thresholds=MemoryThresholds(
                moderate_mb=1000.0,
                high_mb=2000.0,
                critical_mb=3000.0,
                gc_trigger_mb=1500.0,
                fallback_trigger_mb=2500.0
            )
        )
        self.manager = AdaptiveMemoryManager(self.config, self.logger)

    def test_low_pressure_behavior(self):
        """Test behavior under low memory pressure"""
        snapshot = MemorySnapshot(
            timestamp=datetime.utcnow(),
            rss_mb=500.0,  # Low memory usage
            vms_mb=600.0,
            percent=40.0,
            available_mb=3000.0,
            pressure_level=MemoryPressureLevel.LOW,
            gc_collections=5,
            batch_size=500
        )

        old_level = self.manager._current_optimization_level
        self.manager._adjust_batch_size(snapshot)

        # Should maintain or increase to high performance
        self.assertEqual(self.manager._current_optimization_level, OptimizationLevel.HIGH)
        self.assertFalse(self.manager._fallback_active)

    def test_critical_pressure_behavior(self):
        """Test behavior under critical memory pressure"""
        snapshot = MemorySnapshot(
            timestamp=datetime.utcnow(),
            rss_mb=2800.0,  # Above fallback trigger
            vms_mb=3200.0,
            percent=95.0,
            available_mb=200.0,
            pressure_level=MemoryPressureLevel.CRITICAL,
            gc_collections=10,
            batch_size=500
        )

        self.manager._adjust_batch_size(snapshot)

        # Should enable fallback mode
        self.assertEqual(self.manager._current_optimization_level, OptimizationLevel.FALLBACK)
        self.assertTrue(self.manager._fallback_active)
        self.assertEqual(self.manager._stats["automatic_fallbacks"], 1)


if __name__ == '__main__':
    # Run all tests
    unittest.main(verbosity=2)
