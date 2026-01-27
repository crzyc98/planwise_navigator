"""
Data models for resource management.

This module contains the dataclasses used throughout the resources package.
It has no internal dependencies to serve as a stable foundation layer.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional, Tuple


@dataclass
class MemoryUsageSnapshot:
    """Snapshot of memory usage at a point in time."""

    timestamp: float
    rss_mb: float
    vms_mb: float
    percent: float
    available_mb: float
    thread_id: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CPUUsageSnapshot:
    """Snapshot of CPU usage at a point in time."""

    timestamp: float
    percent: float
    load_avg: Tuple[float, float, float]
    core_count: int
    context: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ResourcePressure:
    """Current resource pressure status."""

    memory_pressure: str  # "none", "moderate", "high", "critical"
    cpu_pressure: str  # "none", "moderate", "high", "critical"
    memory_usage_mb: float
    memory_percent: float
    cpu_percent: float
    recommended_action: str
    thread_count_adjustment: int = 0


@dataclass
class BenchmarkResult:
    """Result from performance benchmark."""

    thread_count: int
    execution_time: float
    memory_usage_mb: float
    cpu_utilization: float
    speedup: float
    efficiency: float
    success: bool
    error_message: Optional[str] = None
