"""
Data models for performance monitoring.

This module contains the dataclasses and enums used throughout
the monitoring package. It has no internal dependencies to serve
as a stable foundation layer.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, Optional


@dataclass
class PerformanceMetrics:
    """Container for performance metrics"""

    operation_name: str
    start_time: float
    end_time: Optional[float] = None
    duration_seconds: Optional[float] = None
    start_memory_mb: Optional[float] = None
    end_memory_mb: Optional[float] = None
    memory_delta_mb: Optional[float] = None
    peak_memory_mb: Optional[float] = None
    cpu_percent: Optional[float] = None
    status: str = "running"
    error_message: Optional[str] = None
    context: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary for logging"""
        return {
            "operation": self.operation_name,
            "duration_seconds": round(self.duration_seconds, 3)
            if self.duration_seconds
            else None,
            "memory_delta_mb": round(self.memory_delta_mb, 2)
            if self.memory_delta_mb
            else None,
            "peak_memory_mb": round(self.peak_memory_mb, 2)
            if self.peak_memory_mb
            else None,
            "cpu_percent": round(self.cpu_percent, 1) if self.cpu_percent else None,
            "status": self.status,
            "error": self.error_message,
            **self.context,
        }


class PerformanceLevel(Enum):
    """Performance assessment levels for DuckDB operations"""

    EXCELLENT = "excellent"
    GOOD = "good"
    MODERATE = "moderate"
    POOR = "poor"
    CRITICAL = "critical"


@dataclass
class PerformanceCheckpoint:
    """Performance metrics captured at a specific workflow stage"""

    stage_name: str
    timestamp: float
    elapsed_time: float
    memory_usage_gb: float
    memory_percent: float
    memory_available_gb: float
    disk_usage_gb: float
    database_size_gb: float
    cpu_percent: float
    cpu_count: int
    io_read_bytes: int
    io_write_bytes: int
    io_read_count: int
    io_write_count: int
    thread_count: int

    def to_dict(self) -> Dict[str, Any]:
        """Convert checkpoint to dictionary for serialization"""
        return asdict(self)


@dataclass
class PerformanceOptimization:
    """Performance optimization recommendation"""

    category: str
    severity: str
    description: str
    recommendation: str
    potential_improvement: str
    priority: int  # 1-5, 1 being highest priority
