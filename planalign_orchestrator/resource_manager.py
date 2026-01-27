#!/usr/bin/env python3
"""
Advanced Memory Management & Optimization for Navigator Orchestrator

DEPRECATION NOTICE:
    This module is a backward compatibility wrapper. For new code, import directly from:
    - planalign_orchestrator.resources

Example:
    # Old way (still works):
    from planalign_orchestrator.resource_manager import ResourceManager

    # New way (preferred):
    from planalign_orchestrator.resources import ResourceManager

Story S067-03: Implementation of intelligent memory management during multi-threaded execution
to keep the system stable under varying load conditions.
"""

# Re-export all public symbols from the resources package
from .resources import (
    # Data models
    MemoryUsageSnapshot,
    CPUUsageSnapshot,
    ResourcePressure,
    BenchmarkResult,
    # Monitor classes
    MemoryMonitor,
    CPUMonitor,
    # Adaptive components
    AdaptiveThreadAdjuster,
    PerformanceBenchmarker,
    # Facade
    ResourceManager,
)

__all__ = [
    # Data models
    "MemoryUsageSnapshot",
    "CPUUsageSnapshot",
    "ResourcePressure",
    "BenchmarkResult",
    # Monitor classes
    "MemoryMonitor",
    "CPUMonitor",
    # Adaptive components
    "AdaptiveThreadAdjuster",
    "PerformanceBenchmarker",
    # Facade
    "ResourceManager",
]
