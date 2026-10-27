"""Performance, threading, and optimization settings.

E073: Config Module Refactoring - performance module.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

# =============================================================================
# Memory Management Settings
# =============================================================================


class AdaptiveMemoryThresholds(BaseModel):
    """Memory pressure thresholds in MB for adaptive management."""

    moderate_mb: float = Field(
        default=2000.0, ge=500.0, description="Moderate pressure threshold in MB"
    )
    high_mb: float = Field(
        default=3000.0, ge=1000.0, description="High pressure threshold in MB"
    )
    critical_mb: float = Field(
        default=3500.0, ge=1500.0, description="Critical pressure threshold in MB"
    )
    gc_trigger_mb: float = Field(
        default=2500.0,
        ge=1000.0,
        description="Garbage collection trigger threshold in MB",
    )
    fallback_trigger_mb: float = Field(
        default=3200.0, ge=1500.0, description="Fallback mode trigger threshold in MB"
    )


class AdaptiveBatchSizes(BaseModel):
    """Batch size configuration for different optimization levels."""

    low: int = Field(
        default=250, ge=50, le=1000, description="Low optimization batch size"
    )
    medium: int = Field(
        default=500, ge=100, le=2000, description="Medium optimization batch size"
    )
    high: int = Field(
        default=1000, ge=200, le=5000, description="High optimization batch size"
    )
    fallback: int = Field(
        default=100, ge=25, le=500, description="Fallback mode batch size"
    )


class AdaptiveMemorySettings(BaseModel):
    """Adaptive memory management configuration."""

    enabled: bool = Field(default=True, description="Enable adaptive memory management")
    monitoring_interval_seconds: float = Field(
        default=1.0,
        ge=0.1,
        le=60.0,
        description="Memory monitoring interval in seconds",
    )
    history_size: int = Field(
        default=100, ge=10, le=1000, description="Memory history buffer size"
    )

    thresholds: AdaptiveMemoryThresholds = Field(
        default_factory=AdaptiveMemoryThresholds,
        description="Memory pressure thresholds",
    )
    batch_sizes: AdaptiveBatchSizes = Field(
        default_factory=AdaptiveBatchSizes,
        description="Adaptive batch size configuration",
    )

    auto_gc_enabled: bool = Field(
        default=True, description="Enable automatic garbage collection"
    )
    fallback_enabled: bool = Field(
        default=True, description="Enable automatic fallback to smaller batch sizes"
    )
    profiling_enabled: bool = Field(
        default=False, description="Enable memory profiling hooks"
    )

    # Recommendation engine settings
    recommendation_window_minutes: int = Field(
        default=5, ge=1, le=60, description="Recommendation analysis window in minutes"
    )
    min_samples_for_recommendation: int = Field(
        default=10,
        ge=5,
        le=100,
        description="Minimum samples needed for recommendations",
    )

    # Memory leak detection
    leak_detection_enabled: bool = Field(
        default=True, description="Enable memory leak detection"
    )
    leak_threshold_mb: float = Field(
        default=800.0, ge=100.0, description="Memory leak detection threshold in MB"
    )
    leak_window_minutes: int = Field(
        default=15, ge=5, le=60, description="Memory leak detection window in minutes"
    )


# =============================================================================
# CPU Monitoring Settings
# =============================================================================


class CPUMonitoringThresholds(BaseModel):
    """CPU monitoring threshold configuration."""

    moderate_percent: float = Field(
        default=70.0,
        ge=0.0,
        le=100.0,
        description="Moderate CPU usage threshold percentage",
    )
    high_percent: float = Field(
        default=85.0,
        ge=0.0,
        le=100.0,
        description="High CPU usage threshold percentage",
    )
    critical_percent: float = Field(
        default=95.0,
        ge=0.0,
        le=100.0,
        description="Critical CPU usage threshold percentage",
    )


class CPUMonitoringSettings(BaseModel):
    """CPU monitoring configuration for Story S067-03."""

    monitoring_interval_seconds: float = Field(
        default=1.0, ge=0.1, le=60.0, description="CPU monitoring interval in seconds"
    )
    history_size: int = Field(
        default=100, ge=10, le=1000, description="CPU history buffer size"
    )

    thresholds: CPUMonitoringThresholds = Field(
        default_factory=CPUMonitoringThresholds, description="CPU pressure thresholds"
    )


# =============================================================================
# Resource Management Settings
# =============================================================================


class ResourceManagerSettings(BaseModel):
    """Advanced resource management configuration for Story S067-03."""

    memory_monitoring: AdaptiveMemorySettings = Field(
        default_factory=AdaptiveMemorySettings,
        description="Memory monitoring configuration",
    )

    cpu_monitoring: CPUMonitoringSettings = Field(
        default_factory=CPUMonitoringSettings,
        description="CPU monitoring configuration",
    )

    adaptive_scaling_enabled: bool = Field(
        default=True, description="Ignored; no engine consumer"
    )
    min_threads: int = Field(
        default=1, ge=1, le=16, description="Ignored; no engine consumer"
    )
    max_threads: int = Field(
        default=8, ge=1, le=16, description="Ignored; no engine consumer"
    )

    cleanup_threshold_mb: float = Field(
        default=2500.0,
        ge=1000.0,
        description="Ignored; no engine consumer",
    )


# =============================================================================
# Model Parallelization Settings
# =============================================================================


class ModelParallelizationSettings(BaseModel):
    """Model-level parallelization configuration for sophisticated execution control."""

    enabled: bool = Field(
        default=False, description="Enable model-level parallelization"
    )
    max_workers: int = Field(
        default=4,
        ge=1,
        le=16,
        description="Maximum parallel workers for model execution",
    )
    enable_conditional_parallelization: bool = Field(
        default=False, description="Allow parallelization of conditional models"
    )
    deterministic_execution: bool = Field(
        default=True, description="Ignored; no engine consumer"
    )

    class SafetySettings(BaseModel):
        """Safety settings for model parallelization."""

        validate_execution_safety: bool = Field(
            default=True, description="Validate execution safety before parallelization"
        )

    safety: SafetySettings = Field(
        default_factory=SafetySettings, description="Safety configuration"
    )


# =============================================================================
# Threading Settings
# =============================================================================


class ThreadingSettings(BaseModel):
    """dbt threading configuration for Navigator Orchestrator."""

    enabled: bool = Field(
        default=True, description="Enable configurable threading support"
    )
    thread_count: int = Field(
        default=1, ge=1, le=16, description="Number of threads for dbt execution (1-16)"
    )
    mode: str = Field(
        default="selective",
        description="Ignored; no engine consumer",
    )
    memory_per_thread_gb: float = Field(
        default=1.0, ge=0.25, le=8.0, description="Ignored; no engine consumer"
    )

    parallelization: ModelParallelizationSettings = Field(
        default_factory=ModelParallelizationSettings,
        description="Model-level parallelization configuration",
    )

    resource_management: ResourceManagerSettings = Field(
        default_factory=ResourceManagerSettings,
        description="Advanced resource management configuration",
    )

    def validate_thread_count(self) -> None:
        """Validate thread count with clear error messages."""
        if self.thread_count < 1:
            raise ValueError("thread_count must be at least 1")
        if self.thread_count > 16:
            raise ValueError("thread_count cannot exceed 16 (hardware limitation)")

        total_memory_gb = self.thread_count * self.memory_per_thread_gb
        if total_memory_gb > 12.0:
            import warnings

            warnings.warn(
                f"High memory usage detected: {total_memory_gb:.1f}GB ({self.thread_count} threads × {self.memory_per_thread_gb:.1f}GB/thread). Consider reducing thread_count or memory_per_thread_gb for stability."
            )


class OrchestratorSettings(BaseModel):
    """Orchestrator configuration including threading support."""

    threading: ThreadingSettings = Field(
        default_factory=ThreadingSettings, description="dbt threading configuration"
    )


# =============================================================================
# Legacy Polars Event Settings (kept for backward compatibility)
# =============================================================================


class PolarsEventSettings(BaseModel):
    """Legacy Polars settings - retained for backward compatibility.

    All simulations now use SQL mode. These settings are ignored but kept
    to prevent config parsing errors from existing configuration files.
    """

    compression_level: int = Field(default=6, ge=1, le=22, description="[DEPRECATED]")
    max_memory_gb: float = Field(
        default=8.0, ge=1.0, le=64.0, description="[DEPRECATED]"
    )
    lazy_evaluation: bool = Field(default=True, description="[DEPRECATED]")
    streaming: bool = Field(default=True, description="[DEPRECATED]")
    parallel_io: bool = Field(default=True, description="[DEPRECATED]")


class EventGenerationSettings(BaseModel):
    """Event generation configuration. All simulations use SQL mode."""

    mode: str = Field(default="sql", description="Ignored; no engine consumer")
    polars: PolarsEventSettings = Field(
        default_factory=PolarsEventSettings,
        description="[DEPRECATED] Legacy Polars settings",
    )

    def validate_mode(self) -> None:
        """Validate event generation mode - always SQL."""
        # Silently accept 'polars' for backward compatibility but mode is always 'sql'
        pass


# =============================================================================
# E068C Threading Settings
# =============================================================================


class E068CThreadingSettings(BaseModel):
    """E068C Threading and parallelization configuration."""

    dbt_threads: int = Field(
        default=6,
        ge=1,
        le=16,
        description="Number of threads for dbt execution (E068C)",
    )
    event_shards: int = Field(
        default=1,
        ge=1,
        le=8,
        description="Optional sharding for event generation (E068C)",
    )
    max_parallel_years: int = Field(
        default=1,
        ge=1,
        le=5,
        description="Sequential year processing for determinism (E068C)",
    )

    def validate_e068c_configuration(self) -> None:
        """Validate E068C threading configuration with clear error messages."""
        if self.dbt_threads < 1:
            raise ValueError("dbt_threads must be at least 1")
        if self.dbt_threads > 16:
            raise ValueError("dbt_threads cannot exceed 16 (hardware limitation)")
        if self.event_shards < 1:
            raise ValueError("event_shards must be at least 1")
        if self.event_shards > 8:
            raise ValueError("event_shards cannot exceed 8 (reasonable limit)")
        if self.max_parallel_years < 1:
            raise ValueError("max_parallel_years must be at least 1")

        if self.dbt_threads > 8:
            import warnings

            warnings.warn(
                f"High dbt_threads count detected: {self.dbt_threads}. Consider reducing for stability on resource-constrained systems."
            )

        if self.event_shards > 1 and self.dbt_threads < self.event_shards:
            import warnings

            warnings.warn(
                f"Event sharding ({self.event_shards}) exceeds dbt_threads ({self.dbt_threads}). Consider increasing dbt_threads for optimal performance."
            )


# =============================================================================
# Optimization Settings
# =============================================================================


class OptimizationSettings(BaseModel):
    """Performance optimization configuration."""

    execution_engine: Literal["dbt"] = Field(
        default="dbt",
        description="Supported transformation execution engine",
    )

    @field_validator("execution_engine", mode="before")
    @classmethod
    def reject_unsupported_execution_engine(cls, value: Any) -> Any:
        if value != "dbt":
            raise ValueError(
                "optimization.execution_engine supports only 'dbt'; "
                f"received {value!r}"
            )
        return value

    event_generation: EventGenerationSettings = Field(
        default_factory=EventGenerationSettings,
        description="Event generation mode and settings",
    )
    e068c_threading: E068CThreadingSettings = Field(
        default_factory=E068CThreadingSettings,
        description="E068C threading and parallelization settings",
    )
    adaptive_memory: AdaptiveMemorySettings = Field(
        default_factory=AdaptiveMemorySettings,
        description="Adaptive memory management settings",
    )
