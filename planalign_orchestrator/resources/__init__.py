"""
Resources package for PlanAlign Engine resource management.

Provides comprehensive resource management with memory/CPU monitoring,
adaptive thread scaling, and performance optimization.

Story S067-03: Intelligent memory management during multi-threaded execution.
"""

from .data_models import (
    MemoryUsageSnapshot,
    CPUUsageSnapshot,
    ResourcePressure,
    BenchmarkResult,
)
from .memory_monitor import MemoryMonitor
from .cpu_monitor import CPUMonitor
from .adaptive_scaling import AdaptiveThreadAdjuster
from .benchmarker import PerformanceBenchmarker
from .manager import ResourceManager

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
