"""
Performance Monitoring System for PlanAlign Engine

DEPRECATION NOTICE:
    This module is a backward compatibility wrapper. For new code, import directly from:
    - planalign_orchestrator.monitoring

Example:
    # Old way (still works):
    from planalign_orchestrator.performance_monitor import PerformanceMonitor

    # New way (preferred):
    from planalign_orchestrator.monitoring import PerformanceMonitor

Epic E068E: Engine & I/O Tuning - DuckDB Performance Monitoring
Target: 15-25% performance improvement through monitoring and optimization.
"""

# Re-export all public symbols from the monitoring package
from .monitoring import (
    PerformanceMetrics,
    PerformanceLevel,
    PerformanceCheckpoint,
    PerformanceOptimization,
    PerformanceMonitor,
    DuckDBPerformanceMonitor,
)

__all__ = [
    # Data models
    "PerformanceMetrics",
    "PerformanceLevel",
    "PerformanceCheckpoint",
    "PerformanceOptimization",
    # Monitor classes
    "PerformanceMonitor",
    "DuckDBPerformanceMonitor",
]
