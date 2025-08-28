#!/usr/bin/env python3
"""
Adaptive Memory Management System for PlanWise Navigator

Story S063-08: Implements real-time memory monitoring with adaptive batch size
adjustment, dynamic garbage collection, automatic fallback mechanisms, and
comprehensive performance analysis for single-threaded workforce simulation
environments.

Features:
- Real-time memory monitoring with configurable thresholds
- Adaptive batch size adjustment based on memory pressure
- Dynamic garbage collection with smart triggering
- Automatic fallback to smaller batch sizes
- Memory profiling hooks for performance analysis
- Optimization recommendations based on usage patterns
- Single-threaded optimization for work laptop environments
"""

from __future__ import annotations

import gc
import json
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import psutil

from .logger import ProductionLogger


class MemoryPressureLevel(Enum):
    """Memory pressure levels for adaptive management"""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    CRITICAL = "critical"


class OptimizationLevel(Enum):
    """Optimization levels for memory management"""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    FALLBACK = "fallback"


@dataclass
class MemorySnapshot:
    """Point-in-time memory usage snapshot"""
    timestamp: datetime
    rss_mb: float
    vms_mb: float
    percent: float
    available_mb: float
    pressure_level: MemoryPressureLevel
    gc_collections: int
    batch_size: int
    operation: Optional[str] = None


@dataclass
class BatchSizeConfig:
    """Batch size configuration for different optimization levels"""
    low: int = 250
    medium: int = 500
    high: int = 1000
    fallback: int = 100

    def get_size(self, level: OptimizationLevel) -> int:
        """Get batch size for optimization level"""
        return {
            OptimizationLevel.LOW: self.low,
            OptimizationLevel.MEDIUM: self.medium,
            OptimizationLevel.HIGH: self.high,
            OptimizationLevel.FALLBACK: self.fallback
        }[level]


@dataclass
class MemoryThresholds:
    """Memory pressure thresholds in MB"""
    moderate_mb: float = 2000.0  # 2GB
    high_mb: float = 3000.0      # 3GB
    critical_mb: float = 3500.0  # 3.5GB
    gc_trigger_mb: float = 2500.0  # 2.5GB
    fallback_trigger_mb: float = 3200.0  # 3.2GB


@dataclass
class AdaptiveConfig:
    """Configuration for adaptive memory management"""
    enabled: bool = True
    monitoring_interval_seconds: float = 1.0
    history_size: int = 100
    thresholds: MemoryThresholds = field(default_factory=MemoryThresholds)
    batch_sizes: BatchSizeConfig = field(default_factory=BatchSizeConfig)
    auto_gc_enabled: bool = True
    fallback_enabled: bool = True
    profiling_enabled: bool = False

    # Recommendation engine settings
    recommendation_window_minutes: int = 5
    min_samples_for_recommendation: int = 10

    # Memory leak detection
    leak_detection_enabled: bool = True
    leak_threshold_mb: float = 800.0  # 800MB growth threshold (tuned for simulation workloads)
    leak_window_minutes: int = 15


class MemoryRecommendation:
    """Memory optimization recommendation"""

    def __init__(
        self,
        recommendation_type: str,
        description: str,
        action: str,
        priority: str = "medium",
        estimated_savings_mb: Optional[float] = None,
        confidence: float = 0.7
    ):
        self.type = recommendation_type
        self.description = description
        self.action = action
        self.priority = priority
        self.estimated_savings_mb = estimated_savings_mb
        self.confidence = confidence
        self.timestamp = datetime.utcnow()

    def to_dict(self) -> Dict[str, Any]:
        return {
            "type": self.type,
            "description": self.description,
            "action": self.action,
            "priority": self.priority,
            "estimated_savings_mb": self.estimated_savings_mb,
            "confidence": self.confidence,
            "timestamp": self.timestamp.isoformat()
        }


class AdaptiveMemoryManager:
    """
    Adaptive Memory Management System

    Provides real-time memory monitoring, adaptive batch sizing, dynamic garbage
    collection, and optimization recommendations for single-threaded environments.
    """

    def __init__(
        self,
        config: AdaptiveConfig,
        logger: ProductionLogger,
        *,
        reports_dir: Path = Path("reports/memory")
    ):
        self.config = config
        self.logger = logger
        self.reports_dir = Path(reports_dir)
        self.reports_dir.mkdir(parents=True, exist_ok=True)

        # Memory monitoring state
        self._process = psutil.Process()
        self._monitoring_active = False
        self._monitoring_thread: Optional[threading.Thread] = None
        self._history: deque[MemorySnapshot] = deque(maxlen=config.history_size)

        # Adaptive state
        self._current_optimization_level = OptimizationLevel.MEDIUM
        self._current_batch_size = config.batch_sizes.get_size(self._current_optimization_level)
        self._fallback_active = False
        self._gc_count = 0

        # Profiling hooks
        self._profiling_hooks: List[Callable[[MemorySnapshot], None]] = []

        # Recommendations
        self._recommendations: List[MemoryRecommendation] = []
        self._last_recommendation_time = datetime.utcnow()

        # Statistics
        self._stats = {
            "total_gc_collections": 0,
            "automatic_fallbacks": 0,
            "batch_size_adjustments": 0,
            "memory_warnings": 0,
            "critical_events": 0
        }

        self.logger.info(
            f"Adaptive Memory Manager initialized - "
            f"thresholds: {config.thresholds.moderate_mb}/{config.thresholds.high_mb}/{config.thresholds.critical_mb}MB, "
            f"batch sizes: {config.batch_sizes.low}/{config.batch_sizes.medium}/{config.batch_sizes.high}/{config.batch_sizes.fallback}"
        )

    def start_monitoring(self) -> None:
        """Start background memory monitoring"""
        if self._monitoring_active or not self.config.enabled:
            return

        self._monitoring_active = True
        self._monitoring_thread = threading.Thread(
            target=self._monitoring_loop,
            daemon=True,
            name="AdaptiveMemoryMonitor"
        )
        self._monitoring_thread.start()
        self.logger.info("Started adaptive memory monitoring")

    def stop_monitoring(self) -> None:
        """Stop background memory monitoring"""
        self._monitoring_active = False
        if self._monitoring_thread:
            self._monitoring_thread.join(timeout=2.0)
            self._monitoring_thread = None
        self.logger.info("Stopped adaptive memory monitoring")

    def _monitoring_loop(self) -> None:
        """Background monitoring loop"""
        while self._monitoring_active:
            try:
                snapshot = self._take_memory_snapshot()
                self._process_snapshot(snapshot)
                time.sleep(self.config.monitoring_interval_seconds)
            except Exception as e:
                self.logger.warning(f"Memory monitoring error: {e}")
                time.sleep(self.config.monitoring_interval_seconds * 2)

    def _take_memory_snapshot(self, operation: Optional[str] = None) -> MemorySnapshot:
        """Take a memory usage snapshot"""
        try:
            # Process memory info
            memory_info = self._process.memory_info()
            rss_mb = memory_info.rss / 1024 / 1024
            vms_mb = memory_info.vms / 1024 / 1024

            # System memory info
            system_memory = psutil.virtual_memory()
            percent = system_memory.percent
            available_mb = system_memory.available / 1024 / 1024

            # Determine pressure level
            pressure_level = self._calculate_pressure_level(rss_mb, available_mb)

            # GC stats
            gc_collections = sum(gc.get_stats()[i]['collections'] for i in range(len(gc.get_stats())))

            snapshot = MemorySnapshot(
                timestamp=datetime.utcnow(),
                rss_mb=rss_mb,
                vms_mb=vms_mb,
                percent=percent,
                available_mb=available_mb,
                pressure_level=pressure_level,
                gc_collections=gc_collections,
                batch_size=self._current_batch_size,
                operation=operation
            )

            self._history.append(snapshot)
            return snapshot

        except Exception as e:
            self.logger.warning(f"Failed to take memory snapshot: {e}")
            # Return minimal snapshot
            return MemorySnapshot(
                timestamp=datetime.utcnow(),
                rss_mb=0.0,
                vms_mb=0.0,
                percent=0.0,
                available_mb=0.0,
                pressure_level=MemoryPressureLevel.LOW,
                gc_collections=0,
                batch_size=self._current_batch_size,
                operation=operation
            )

    def _calculate_pressure_level(self, rss_mb: float, available_mb: float) -> MemoryPressureLevel:
        """Calculate memory pressure level"""
        thresholds = self.config.thresholds

        if rss_mb >= thresholds.critical_mb or available_mb < 500:  # Less than 500MB available
            return MemoryPressureLevel.CRITICAL
        elif rss_mb >= thresholds.high_mb or available_mb < 1000:  # Less than 1GB available
            return MemoryPressureLevel.HIGH
        elif rss_mb >= thresholds.moderate_mb or available_mb < 2000:  # Less than 2GB available
            return MemoryPressureLevel.MODERATE
        else:
            return MemoryPressureLevel.LOW

    def _process_snapshot(self, snapshot: MemorySnapshot) -> None:
        """Process a memory snapshot and take adaptive actions"""
        # Trigger garbage collection if needed
        if (self.config.auto_gc_enabled and
            snapshot.rss_mb >= self.config.thresholds.gc_trigger_mb):
            self._trigger_garbage_collection(snapshot)

        # Adjust batch size based on pressure
        self._adjust_batch_size(snapshot)

        # Check for memory leaks
        if self.config.leak_detection_enabled:
            self._check_memory_leaks(snapshot)

        # Call profiling hooks
        if self.config.profiling_enabled:
            for hook in self._profiling_hooks:
                try:
                    hook(snapshot)
                except Exception as e:
                    self.logger.warning(f"Profiling hook error: {e}")

        # Generate recommendations
        self._update_recommendations(snapshot)

        # Log warnings for high pressure
        if snapshot.pressure_level in (MemoryPressureLevel.HIGH, MemoryPressureLevel.CRITICAL):
            self._log_memory_warning(snapshot)

    def _trigger_garbage_collection(self, snapshot: MemorySnapshot) -> None:
        """Trigger garbage collection with logging"""
        pre_gc_memory = snapshot.rss_mb

        # Force full garbage collection
        collected = gc.collect()
        self._stats["total_gc_collections"] += 1
        self._gc_count += 1

        # Take post-GC snapshot
        post_snapshot = self._take_memory_snapshot("post_gc")
        memory_freed = pre_gc_memory - post_snapshot.rss_mb

        self.logger.info(
            "Automatic garbage collection triggered",
            pre_gc_memory_mb=round(pre_gc_memory, 1),
            post_gc_memory_mb=round(post_snapshot.rss_mb, 1),
            memory_freed_mb=round(memory_freed, 1),
            objects_collected=collected,
            pressure_level=snapshot.pressure_level.value
        )

    def _adjust_batch_size(self, snapshot: MemorySnapshot) -> None:
        """Adjust batch size based on memory pressure"""
        old_level = self._current_optimization_level
        old_batch_size = self._current_batch_size

        # Determine optimal optimization level
        if snapshot.pressure_level == MemoryPressureLevel.CRITICAL:
            if self.config.fallback_enabled and snapshot.rss_mb >= self.config.thresholds.fallback_trigger_mb:
                new_level = OptimizationLevel.FALLBACK
                if not self._fallback_active:
                    self._fallback_active = True
                    self._stats["automatic_fallbacks"] += 1
            else:
                new_level = OptimizationLevel.LOW
        elif snapshot.pressure_level == MemoryPressureLevel.HIGH:
            new_level = OptimizationLevel.LOW
            self._fallback_active = False
        elif snapshot.pressure_level == MemoryPressureLevel.MODERATE:
            new_level = OptimizationLevel.MEDIUM
            self._fallback_active = False
        else:
            # Return to higher performance if memory pressure is low
            new_level = OptimizationLevel.HIGH
            self._fallback_active = False

        if new_level != old_level:
            self._current_optimization_level = new_level
            self._current_batch_size = self.config.batch_sizes.get_size(new_level)
            self._stats["batch_size_adjustments"] += 1

            self.logger.info(
                "Adaptive batch size adjustment",
                old_level=old_level.value,
                new_level=new_level.value,
                old_batch_size=old_batch_size,
                new_batch_size=self._current_batch_size,
                memory_mb=round(snapshot.rss_mb, 1),
                pressure_level=snapshot.pressure_level.value,
                fallback_active=self._fallback_active
            )

    def _check_memory_leaks(self, snapshot: MemorySnapshot) -> None:
        """Check for potential memory leaks with smarter detection"""
        if len(self._history) < 15:  # Need more history for reliable detection
            return

        # Look at memory growth over a longer window to detect true leaks
        window_minutes = self.config.leak_window_minutes
        cutoff_time = datetime.utcnow().timestamp() - (window_minutes * 60)

        recent_snapshots = [
            s for s in self._history
            if s.timestamp.timestamp() >= cutoff_time
        ]

        if len(recent_snapshots) < 10:
            return

        # Calculate memory growth trend
        start_memory = recent_snapshots[0].rss_mb
        current_memory = snapshot.rss_mb
        growth = current_memory - start_memory

        # More sophisticated leak detection
        # 1. Check if growth is consistently increasing (not just temporary spikes)
        midpoint_memory = recent_snapshots[len(recent_snapshots)//2].rss_mb
        early_growth = midpoint_memory - start_memory
        late_growth = current_memory - midpoint_memory

        # 2. Only report if growth is substantial AND consistent
        is_consistent_growth = early_growth > 0 and late_growth > 0
        is_substantial_growth = growth > self.config.leak_threshold_mb

        # 3. Don't report during active processing (when batch size adjustments are happening)
        recent_pressure_levels = [s.pressure_level for s in recent_snapshots[-5:]]
        is_under_pressure = any(level != MemoryPressureLevel.LOW for level in recent_pressure_levels)

        # Only report leak if all conditions are met and not under active memory pressure
        if is_substantial_growth and is_consistent_growth and not is_under_pressure:
            # Additional check: has a recommendation been made recently?
            recent_leak_recommendations = [
                r for r in self._recommendations[-5:]
                if r.type == "memory_leak"
            ]

            if not recent_leak_recommendations:  # Only report if no recent leak warnings
                recommendation = MemoryRecommendation(
                    "memory_leak",
                    f"Sustained memory growth detected: {growth:.1f}MB over {window_minutes} minutes",
                    f"Consider memory profiling and garbage collection optimization",
                    priority="medium",  # Reduced priority since it's smarter detection
                    estimated_savings_mb=growth * 0.5,
                    confidence=0.7
                )
                self._recommendations.append(recommendation)

                self.logger.warning(
                    f"Sustained memory growth detected: {growth:.1f}MB over {window_minutes} minutes "
                    f"({start_memory:.1f}MB -> {current_memory:.1f}MB)"
                )

    def _log_memory_warning(self, snapshot: MemorySnapshot) -> None:
        """Log memory pressure warnings"""
        self._stats["memory_warnings"] += 1
        if snapshot.pressure_level == MemoryPressureLevel.CRITICAL:
            self._stats["critical_events"] += 1

        self.logger.warning(
            f"Memory pressure: {snapshot.pressure_level.value} - "
            f"{snapshot.rss_mb:.1f}MB used ({snapshot.percent:.1f}%), "
            f"{snapshot.available_mb:.1f}MB available, batch_size={snapshot.batch_size}, "
            f"optimization_level={self._current_optimization_level.value}, "
            f"fallback_active={self._fallback_active}"
        )

    def _update_recommendations(self, snapshot: MemorySnapshot) -> None:
        """Update optimization recommendations based on patterns"""
        # Only generate recommendations periodically
        time_since_last = (datetime.utcnow() - self._last_recommendation_time).total_seconds()
        if time_since_last < self.config.recommendation_window_minutes * 60:
            return

        if len(self._history) < self.config.min_samples_for_recommendation:
            return

        # Analyze recent memory patterns
        recent_snapshots = list(self._history)[-self.config.min_samples_for_recommendation:]

        # Calculate statistics
        avg_memory = sum(s.rss_mb for s in recent_snapshots) / len(recent_snapshots)
        max_memory = max(s.rss_mb for s in recent_snapshots)
        pressure_counts = {}
        for s in recent_snapshots:
            pressure_counts[s.pressure_level] = pressure_counts.get(s.pressure_level, 0) + 1

        # Generate recommendations
        recommendations = []

        # High memory usage pattern
        if avg_memory > self.config.thresholds.moderate_mb:
            if pressure_counts.get(MemoryPressureLevel.HIGH, 0) > len(recent_snapshots) * 0.3:
                recommendations.append(
                    MemoryRecommendation(
                        "high_memory_pattern",
                        f"Consistent high memory usage detected (avg: {avg_memory:.1f}MB)",
                        "Consider reducing batch sizes permanently or optimizing data processing",
                        priority="high",
                        estimated_savings_mb=(avg_memory - self.config.thresholds.moderate_mb) * 0.5,
                        confidence=0.85
                    )
                )

        # Frequent garbage collection
        gc_frequency = sum(1 for s in recent_snapshots[1:]
                          if s.gc_collections > recent_snapshots[recent_snapshots.index(s)-1].gc_collections)
        if gc_frequency > len(recent_snapshots) * 0.5:
            recommendations.append(
                MemoryRecommendation(
                    "frequent_gc",
                    f"Frequent garbage collection detected ({gc_frequency} collections)",
                    "Consider optimizing object lifecycle management and reducing temporary allocations",
                    priority="medium",
                    estimated_savings_mb=200.0,
                    confidence=0.7
                )
            )

        # Memory efficiency recommendation
        if max_memory > self.config.thresholds.high_mb and not self._fallback_active:
            recommendations.append(
                MemoryRecommendation(
                    "enable_fallback",
                    f"Peak memory usage reached {max_memory:.1f}MB",
                    "Consider enabling permanent fallback mode for this workload",
                    priority="medium",
                    estimated_savings_mb=max_memory - self.config.batch_sizes.fallback * 2,
                    confidence=0.6
                )
            )

        # Add new recommendations
        self._recommendations.extend(recommendations)
        if recommendations:
            self._last_recommendation_time = datetime.utcnow()

            for rec in recommendations:
                self.logger.info(
                    f"Memory optimization recommendation: {rec.type}",
                    **rec.to_dict()
                )

    def get_current_batch_size(self) -> int:
        """Get current adaptive batch size"""
        return self._current_batch_size

    def get_current_optimization_level(self) -> OptimizationLevel:
        """Get current optimization level"""
        return self._current_optimization_level

    def force_memory_check(self, operation: Optional[str] = None) -> MemorySnapshot:
        """Force immediate memory check and return snapshot"""
        snapshot = self._take_memory_snapshot(operation)
        self._process_snapshot(snapshot)
        return snapshot

    def add_profiling_hook(self, hook: Callable[[MemorySnapshot], None]) -> None:
        """Add profiling hook for custom memory analysis"""
        self._profiling_hooks.append(hook)
        self.logger.info("Added memory profiling hook")

    def get_memory_statistics(self) -> Dict[str, Any]:
        """Get comprehensive memory statistics"""
        current_snapshot = self._take_memory_snapshot("statistics")

        # Calculate trends from history
        recent_history = list(self._history)[-20:] if len(self._history) >= 20 else list(self._history)

        if len(recent_history) >= 2:
            memory_trend = recent_history[-1].rss_mb - recent_history[0].rss_mb
            avg_memory = sum(s.rss_mb for s in recent_history) / len(recent_history)
            peak_memory = max(s.rss_mb for s in recent_history)
        else:
            memory_trend = 0.0
            avg_memory = current_snapshot.rss_mb
            peak_memory = current_snapshot.rss_mb

        return {
            "current": {
                "memory_mb": round(current_snapshot.rss_mb, 1),
                "available_mb": round(current_snapshot.available_mb, 1),
                "pressure_level": current_snapshot.pressure_level.value,
                "batch_size": current_snapshot.batch_size,
                "optimization_level": self._current_optimization_level.value,
                "fallback_active": self._fallback_active
            },
            "trends": {
                "avg_memory_mb": round(avg_memory, 1),
                "peak_memory_mb": round(peak_memory, 1),
                "memory_trend_mb": round(memory_trend, 1),
                "samples_count": len(self._history)
            },
            "stats": self._stats.copy(),
            "recommendations_count": len(self._recommendations),
            "monitoring_active": self._monitoring_active
        }

    def get_recommendations(self, *, recent_only: bool = True) -> List[Dict[str, Any]]:
        """Get optimization recommendations"""
        if recent_only:
            # Only return recommendations from last hour
            cutoff = datetime.utcnow().timestamp() - 3600
            recommendations = [
                r for r in self._recommendations
                if r.timestamp.timestamp() >= cutoff
            ]
        else:
            recommendations = self._recommendations

        return [r.to_dict() for r in recommendations]

    def export_memory_profile(self, filepath: Optional[Path] = None) -> Path:
        """Export detailed memory profile for analysis"""
        if filepath is None:
            timestamp = datetime.utcnow().strftime('%Y%m%d_%H%M%S')
            filepath = self.reports_dir / f"memory_profile_{timestamp}.json"

        profile_data = {
            "metadata": {
                "export_time": datetime.utcnow().isoformat(),
                "config": {
                    "thresholds_mb": {
                        "moderate": self.config.thresholds.moderate_mb,
                        "high": self.config.thresholds.high_mb,
                        "critical": self.config.thresholds.critical_mb
                    },
                    "batch_sizes": {
                        "low": self.config.batch_sizes.low,
                        "medium": self.config.batch_sizes.medium,
                        "high": self.config.batch_sizes.high,
                        "fallback": self.config.batch_sizes.fallback
                    },
                    "monitoring_interval_seconds": self.config.monitoring_interval_seconds,
                    "history_size": self.config.history_size
                }
            },
            "statistics": self.get_memory_statistics(),
            "history": [
                {
                    "timestamp": s.timestamp.isoformat(),
                    "rss_mb": round(s.rss_mb, 2),
                    "vms_mb": round(s.vms_mb, 2),
                    "percent": round(s.percent, 1),
                    "available_mb": round(s.available_mb, 1),
                    "pressure_level": s.pressure_level.value,
                    "gc_collections": s.gc_collections,
                    "batch_size": s.batch_size,
                    "operation": s.operation
                }
                for s in self._history
            ],
            "recommendations": self.get_recommendations(recent_only=False)
        }

        with open(filepath, 'w') as f:
            json.dump(profile_data, f, indent=2)

        self.logger.info(f"Memory profile exported to {filepath}")
        return filepath

    def reset_statistics(self) -> None:
        """Reset internal statistics"""
        self._stats = {
            "total_gc_collections": 0,
            "automatic_fallbacks": 0,
            "batch_size_adjustments": 0,
            "memory_warnings": 0,
            "critical_events": 0
        }
        self._recommendations.clear()
        self.logger.info("Memory management statistics reset")

    def __enter__(self):
        """Context manager entry"""
        self.start_monitoring()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        self.stop_monitoring()


def create_adaptive_memory_manager(
    optimization_level: OptimizationLevel = OptimizationLevel.MEDIUM,
    memory_limit_gb: Optional[float] = None,
    logger: Optional[ProductionLogger] = None,
    **config_overrides
) -> AdaptiveMemoryManager:
    """
    Factory function to create configured AdaptiveMemoryManager

    Args:
        optimization_level: Base optimization level
        memory_limit_gb: Memory limit in GB (used to calculate thresholds)
        logger: Production logger instance
        **config_overrides: Additional configuration overrides

    Returns:
        Configured AdaptiveMemoryManager instance
    """
    # Calculate thresholds based on memory limit
    if memory_limit_gb:
        moderate_mb = memory_limit_gb * 1024 * 0.5  # 50% of limit
        high_mb = memory_limit_gb * 1024 * 0.75     # 75% of limit
        critical_mb = memory_limit_gb * 1024 * 0.9   # 90% of limit
        gc_trigger_mb = memory_limit_gb * 1024 * 0.6  # 60% of limit
        fallback_trigger_mb = memory_limit_gb * 1024 * 0.8  # 80% of limit
    else:
        # Default thresholds for work laptops
        moderate_mb = 2000.0
        high_mb = 3000.0
        critical_mb = 3500.0
        gc_trigger_mb = 2500.0
        fallback_trigger_mb = 3200.0

    # Create configuration
    config = AdaptiveConfig(
        thresholds=MemoryThresholds(
            moderate_mb=moderate_mb,
            high_mb=high_mb,
            critical_mb=critical_mb,
            gc_trigger_mb=gc_trigger_mb,
            fallback_trigger_mb=fallback_trigger_mb
        ),
        **config_overrides
    )

    # Create logger if not provided
    if logger is None:
        from .logger import ProductionLogger
        logger = ProductionLogger("AdaptiveMemoryManager")

    return AdaptiveMemoryManager(config, logger)
