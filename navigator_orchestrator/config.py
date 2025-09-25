#!/usr/bin/env python3
"""
Typed configuration models and loaders for Navigator Orchestrator.

Features
- Pydantic v2 models for simulation config (type safety)
- YAML loader with optional environment variable overrides
- dbt var mapping compatible with existing models
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError


def get_database_path() -> Path:
    """Get standardized database path with environment variable support.

    This function implements Epic E050 database standardization by:
    - Using DATABASE_PATH environment variable if set
    - Defaulting to 'dbt/simulation.duckdb' (standardized location)
    - Creating parent directory if it doesn't exist
    - Returning resolved absolute path

    Returns:
        Path: Absolute path to the simulation database
    """
    db_path = os.getenv('DATABASE_PATH', 'dbt/simulation.duckdb')
    path = Path(db_path)

    # Ensure directory exists
    path.parent.mkdir(parents=True, exist_ok=True)

    return path.resolve()


class SimulationSettings(BaseModel):
    start_year: int = Field(..., ge=2000)
    end_year: int = Field(..., ge=2000)
    random_seed: int = Field(default=42)
    target_growth_rate: float = Field(default=0.03, ge=-1, le=1)


class PromotionCompensationSettings(BaseModel):
    """Promotion compensation increase configuration"""
    base_increase_pct: float = Field(default=0.20, ge=0.0, le=1.0, description="Base (midpoint) promotion increase percentage")
    distribution_range: float = Field(default=0.05, ge=0.0, le=0.20, description="Distribution range around base (+/- range)")
    max_cap_pct: float = Field(default=0.30, ge=0.0, le=1.0, description="Maximum promotion increase percentage")
    max_cap_amount: int = Field(default=500000, ge=0, description="Maximum promotion increase amount in dollars")
    distribution_type: str = Field(default="uniform", description="Distribution type: uniform, normal, deterministic")
    level_overrides: Optional[Dict[int, float]] = Field(default=None, description="Level-specific base increase overrides")

    class Advanced(BaseModel):
        """Advanced promotion compensation configuration"""
        normal_std_dev: float = Field(default=0.02, ge=0.0, le=0.20, description="Standard deviation for normal distribution")
        market_adjustments: Optional[Dict[str, float]] = Field(default=None, description="Market adjustment factors")

    advanced: Advanced = Field(default_factory=lambda: PromotionCompensationSettings.Advanced())


class CompensationSettings(BaseModel):
    cola_rate: float = Field(default=0.005, ge=0, le=1)
    merit_budget: float = Field(default=0.025, ge=0, le=1)
    promotion_compensation: PromotionCompensationSettings = Field(default_factory=PromotionCompensationSettings)


class WorkforceSettings(BaseModel):
    total_termination_rate: float = Field(default=0.12, ge=0, le=1)
    new_hire_termination_rate: float = Field(default=0.25, ge=0, le=1)


class OptOutRatesByAge(BaseModel):
    young: float = Field(default=0.10, ge=0, le=1)
    mid_career: float = Field(default=0.07, ge=0, le=1)
    mature: float = Field(default=0.05, ge=0, le=1)
    senior: float = Field(default=0.03, ge=0, le=1)


class OptOutRatesByIncome(BaseModel):
    low_income: float = Field(default=1.20, ge=0, le=5)
    moderate: float = Field(default=1.00, ge=0, le=5)
    high: float = Field(default=0.70, ge=0, le=5)
    executive: float = Field(default=0.50, ge=0, le=5)


class OptOutRatesSettings(BaseModel):
    by_age: OptOutRatesByAge = OptOutRatesByAge()
    by_income: OptOutRatesByIncome = OptOutRatesByIncome()


class AutoEnrollmentSettings(BaseModel):
    enabled: bool = True
    scope: Optional[str] = None
    hire_date_cutoff: Optional[str] = None
    window_days: int = 45
    default_deferral_rate: float = Field(default=0.06, ge=0, le=1)
    opt_out_grace_period: int = 30
    opt_out_rates: OptOutRatesSettings = OptOutRatesSettings()


class ProactiveEnrollmentSettings(BaseModel):
    enabled: bool = True

    class TimingWindow(BaseModel):
        min_days: int = 7
        max_days: int = 35

    timing_window: TimingWindow = TimingWindow()
    probability_by_demographics: Dict[str, float] = Field(default_factory=dict)


class EnrollmentTimingSettings(BaseModel):
    business_day_adjustment: bool = True


class EnrollmentSettings(BaseModel):
    auto_enrollment: AutoEnrollmentSettings = AutoEnrollmentSettings()
    proactive_enrollment: ProactiveEnrollmentSettings = ProactiveEnrollmentSettings()
    timing: EnrollmentTimingSettings = EnrollmentTimingSettings()


class EligibilitySettings(BaseModel):
    waiting_period_days: Optional[int] = None


class PlanEligibilitySettings(BaseModel):
    minimum_age: Optional[int] = None


class EmployerMatchEligibilitySettings(BaseModel):
    """Employer match eligibility requirements configuration"""
    minimum_tenure_years: int = Field(default=0, ge=0, description="Minimum years of service")
    require_active_at_year_end: bool = Field(default=True, description="Must be active on Dec 31")
    minimum_hours_annual: int = Field(default=1000, ge=0, description="Minimum hours worked annually")
    allow_new_hires: bool = Field(default=True, description="Allow new hires to qualify")
    allow_terminated_new_hires: bool = Field(default=False, description="Allow new-hire terminations to qualify")
    allow_experienced_terminations: bool = Field(default=False, description="Allow experienced terminations to qualify")


class EmployerMatchSettings(BaseModel):
    """Employer match configuration with eligibility requirements"""
    active_formula: str = Field(default="simple_match", description="Active match formula name")
    apply_eligibility: bool = Field(default=False, description="Apply eligibility filtering to match calculations")
    eligibility: EmployerMatchEligibilitySettings = Field(default_factory=EmployerMatchEligibilitySettings)
    formulas: Optional[Dict[str, Any]] = Field(default=None, description="Match formula definitions")


class AdaptiveMemoryThresholds(BaseModel):
    """Memory pressure thresholds in MB for adaptive management"""
    moderate_mb: float = Field(default=2000.0, ge=500.0, description="Moderate pressure threshold in MB")
    high_mb: float = Field(default=3000.0, ge=1000.0, description="High pressure threshold in MB")
    critical_mb: float = Field(default=3500.0, ge=1500.0, description="Critical pressure threshold in MB")
    gc_trigger_mb: float = Field(default=2500.0, ge=1000.0, description="Garbage collection trigger threshold in MB")
    fallback_trigger_mb: float = Field(default=3200.0, ge=1500.0, description="Fallback mode trigger threshold in MB")


class AdaptiveBatchSizes(BaseModel):
    """Batch size configuration for different optimization levels"""
    low: int = Field(default=250, ge=50, le=1000, description="Low optimization batch size")
    medium: int = Field(default=500, ge=100, le=2000, description="Medium optimization batch size")
    high: int = Field(default=1000, ge=200, le=5000, description="High optimization batch size")
    fallback: int = Field(default=100, ge=25, le=500, description="Fallback mode batch size")


class AdaptiveMemorySettings(BaseModel):
    """Adaptive memory management configuration"""
    enabled: bool = Field(default=True, description="Enable adaptive memory management")
    monitoring_interval_seconds: float = Field(default=1.0, ge=0.1, le=60.0, description="Memory monitoring interval in seconds")
    history_size: int = Field(default=100, ge=10, le=1000, description="Memory history buffer size")

    thresholds: AdaptiveMemoryThresholds = Field(default_factory=AdaptiveMemoryThresholds, description="Memory pressure thresholds")
    batch_sizes: AdaptiveBatchSizes = Field(default_factory=AdaptiveBatchSizes, description="Adaptive batch size configuration")

    auto_gc_enabled: bool = Field(default=True, description="Enable automatic garbage collection")
    fallback_enabled: bool = Field(default=True, description="Enable automatic fallback to smaller batch sizes")
    profiling_enabled: bool = Field(default=False, description="Enable memory profiling hooks")

    # Recommendation engine settings
    recommendation_window_minutes: int = Field(default=5, ge=1, le=60, description="Recommendation analysis window in minutes")
    min_samples_for_recommendation: int = Field(default=10, ge=5, le=100, description="Minimum samples needed for recommendations")

    # Memory leak detection
    leak_detection_enabled: bool = Field(default=True, description="Enable memory leak detection")
    leak_threshold_mb: float = Field(default=800.0, ge=100.0, description="Memory leak detection threshold in MB")
    leak_window_minutes: int = Field(default=15, ge=5, le=60, description="Memory leak detection window in minutes")


class CPUMonitoringThresholds(BaseModel):
    """CPU monitoring threshold configuration"""
    moderate_percent: float = Field(default=70.0, ge=0.0, le=100.0, description="Moderate CPU usage threshold percentage")
    high_percent: float = Field(default=85.0, ge=0.0, le=100.0, description="High CPU usage threshold percentage")
    critical_percent: float = Field(default=95.0, ge=0.0, le=100.0, description="Critical CPU usage threshold percentage")


class CPUMonitoringSettings(BaseModel):
    """CPU monitoring configuration for Story S067-03"""
    enabled: bool = Field(default=True, description="Enable CPU monitoring")
    monitoring_interval_seconds: float = Field(default=1.0, ge=0.1, le=60.0, description="CPU monitoring interval in seconds")
    history_size: int = Field(default=100, ge=10, le=1000, description="CPU history buffer size")

    thresholds: CPUMonitoringThresholds = Field(default_factory=CPUMonitoringThresholds, description="CPU pressure thresholds")


class ResourceManagerSettings(BaseModel):
    """Advanced resource management configuration for Story S067-03"""
    enabled: bool = Field(default=False, description="Enable advanced resource management")

    # Memory monitoring settings
    memory_monitoring: AdaptiveMemorySettings = Field(
        default_factory=AdaptiveMemorySettings,
        description="Memory monitoring configuration"
    )

    # CPU monitoring settings
    cpu_monitoring: CPUMonitoringSettings = Field(
        default_factory=CPUMonitoringSettings,
        description="CPU monitoring configuration"
    )

    # Adaptive thread adjustment settings
    adaptive_scaling_enabled: bool = Field(default=True, description="Enable adaptive thread count scaling")
    min_threads: int = Field(default=1, ge=1, le=16, description="Minimum thread count")
    max_threads: int = Field(default=8, ge=1, le=16, description="Maximum thread count")
    adjustment_cooldown_seconds: float = Field(default=30.0, ge=5.0, le=300.0, description="Cooldown period between thread adjustments")

    # Performance benchmarking
    benchmarking_enabled: bool = Field(default=False, description="Enable performance benchmarking")
    benchmark_thread_counts: List[int] = Field(default=[1, 2, 4, 6, 8], description="Thread counts to benchmark")

    # Resource cleanup settings
    auto_cleanup_enabled: bool = Field(default=True, description="Enable automatic resource cleanup")
    cleanup_threshold_mb: float = Field(default=2500.0, ge=1000.0, description="Memory threshold for triggering cleanup in MB")


class ModelParallelizationSettings(BaseModel):
    """Model-level parallelization configuration for sophisticated execution control"""
    enabled: bool = Field(default=False, description="Enable model-level parallelization")
    max_workers: int = Field(default=4, ge=1, le=16, description="Maximum parallel workers for model execution")
    memory_limit_mb: float = Field(default=4000.0, ge=1000.0, description="Memory limit for parallel execution in MB")
    enable_conditional_parallelization: bool = Field(default=False, description="Allow parallelization of conditional models")
    deterministic_execution: bool = Field(default=True, description="Ensure deterministic execution order")
    resource_monitoring: bool = Field(default=True, description="Enable resource monitoring during execution")

    class SafetySettings(BaseModel):
        """Safety settings for model parallelization"""
        fallback_on_resource_pressure: bool = Field(default=True, description="Fall back to sequential on resource pressure")
        validate_execution_safety: bool = Field(default=True, description="Validate execution safety before parallelization")
        abort_on_dependency_conflict: bool = Field(default=True, description="Abort if dependency conflicts detected")
        max_retries_per_model: int = Field(default=2, ge=1, le=5, description="Maximum retries per failed model")

    safety: SafetySettings = Field(default_factory=SafetySettings, description="Safety configuration")


class ThreadingSettings(BaseModel):
    """dbt threading configuration for Navigator Orchestrator"""
    enabled: bool = Field(default=True, description="Enable configurable threading support")
    thread_count: int = Field(default=1, ge=1, le=16, description="Number of threads for dbt execution (1-16)")
    mode: str = Field(default="selective", description="Threading mode: selective, aggressive, sequential")
    memory_per_thread_gb: float = Field(default=1.0, ge=0.25, le=8.0, description="Memory allocation per thread in GB")

    # Model-level parallelization settings
    parallelization: ModelParallelizationSettings = Field(
        default_factory=ModelParallelizationSettings,
        description="Model-level parallelization configuration"
    )

    # Advanced resource management (Story S067-03)
    resource_management: ResourceManagerSettings = Field(
        default_factory=ResourceManagerSettings,
        description="Advanced resource management configuration"
    )

    def validate_thread_count(self) -> None:
        """Validate thread count with clear error messages"""
        if self.thread_count < 1:
            raise ValueError("thread_count must be at least 1")
        if self.thread_count > 16:
            raise ValueError("thread_count cannot exceed 16 (hardware limitation)")

        # Warn about aggressive threading on limited memory
        total_memory_gb = self.thread_count * self.memory_per_thread_gb
        if total_memory_gb > 12.0:
            import warnings
            warnings.warn(f"High memory usage detected: {total_memory_gb:.1f}GB ({self.thread_count} threads × {self.memory_per_thread_gb:.1f}GB/thread). Consider reducing thread_count or memory_per_thread_gb for stability.")


class OrchestratorSettings(BaseModel):
    """Orchestrator configuration including threading support"""
    threading: ThreadingSettings = Field(default_factory=ThreadingSettings, description="dbt threading configuration")


class PolarsEventSettings(BaseModel):
    """Polars event generation configuration for E068G"""
    enabled: bool = Field(default=False, description="Enable Polars-based event generation")
    max_threads: int = Field(default=16, ge=1, le=32, description="Maximum threads for Polars operations")
    batch_size: int = Field(default=10000, ge=1000, le=50000, description="Batch size for employee processing")
    output_path: str = Field(default="data/parquet/events", description="Output directory for partitioned Parquet files")
    enable_compression: bool = Field(default=True, description="Enable zstd compression for Parquet files")
    compression_level: int = Field(default=6, ge=1, le=22, description="Compression level for zstd (1-22)")
    enable_profiling: bool = Field(default=False, description="Enable Polars query profiling")
    max_memory_gb: float = Field(default=8.0, ge=1.0, le=64.0, description="Maximum memory usage in GB")
    lazy_evaluation: bool = Field(default=True, description="Enable lazy evaluation for memory efficiency")
    streaming: bool = Field(default=True, description="Enable streaming mode")
    parallel_io: bool = Field(default=True, description="Enable parallel I/O operations")
    fallback_on_error: bool = Field(default=True, description="Fall back to SQL mode on Polars errors")


class EventGenerationSettings(BaseModel):
    """Event generation mode configuration supporting SQL and Polars"""
    mode: str = Field(default="sql", description="Event generation mode: 'sql' or 'polars'")
    polars: PolarsEventSettings = Field(default_factory=PolarsEventSettings, description="Polars-specific configuration")

    def validate_mode(self) -> None:
        """Validate event generation mode configuration"""
        valid_modes = {"sql", "polars"}
        if self.mode not in valid_modes:
            raise ValueError(f"Invalid event generation mode '{self.mode}'. Must be one of: {valid_modes}")

        if self.mode == "polars" and not self.polars.enabled:
            raise ValueError("Polars mode selected but polars.enabled is False")


class E068CThreadingSettings(BaseModel):
    """E068C Threading and parallelization configuration"""
    dbt_threads: int = Field(default=6, ge=1, le=16, description="Number of threads for dbt execution (E068C)")
    event_shards: int = Field(default=1, ge=1, le=8, description="Optional sharding for event generation (E068C)")
    max_parallel_years: int = Field(default=1, ge=1, le=5, description="Sequential year processing for determinism (E068C)")

    def validate_e068c_configuration(self) -> None:
        """Validate E068C threading configuration with clear error messages"""
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

        # Warn about high thread counts
        if self.dbt_threads > 8:
            import warnings
            warnings.warn(f"High dbt_threads count detected: {self.dbt_threads}. Consider reducing for stability on resource-constrained systems.")

        # Warn about event sharding without sufficient threads
        if self.event_shards > 1 and self.dbt_threads < self.event_shards:
            import warnings
            warnings.warn(f"Event sharding ({self.event_shards}) exceeds dbt_threads ({self.dbt_threads}). Consider increasing dbt_threads for optimal performance.")


class OptimizationSettings(BaseModel):
    """Performance optimization configuration"""
    level: str = Field(default="high", description="Optimization level: low, medium, high, fallback")
    max_workers: int = Field(default=4, ge=1, le=16, description="Maximum concurrent workers")
    batch_size: int = Field(default=1000, ge=50, le=10000, description="Default processing batch size")
    memory_limit_gb: Optional[float] = Field(default=8.0, ge=1.0, description="Memory limit in GB")

    # Event generation configuration
    event_generation: EventGenerationSettings = Field(default_factory=EventGenerationSettings, description="Event generation mode and settings")

    # E068C threading configuration
    e068c_threading: E068CThreadingSettings = Field(default_factory=E068CThreadingSettings, description="E068C threading and parallelization settings")

    # Adaptive memory management
    adaptive_memory: AdaptiveMemorySettings = Field(default_factory=AdaptiveMemorySettings, description="Adaptive memory management settings")


class ProductionSafetySettings(BaseModel):
    """Production data safety and backup configuration"""

    # Database configuration
    db_path: str = Field(
        default_factory=lambda: str(get_database_path()),
        description="Path to simulation database"
    )

    # Backup configuration
    backup_enabled: bool = Field(default=True, description="Enable automatic backups")
    backup_dir: str = Field(default="backups", description="Backup directory path")
    backup_retention_days: int = Field(
        default=7, ge=1, description="Backup retention period"
    )
    backup_before_simulation: bool = Field(
        default=True, description="Create backup before each simulation"
    )

    # Verification settings
    verify_backups: bool = Field(default=True, description="Enable backup verification")
    max_backup_size_gb: float = Field(
        default=10.0, ge=0.1, description="Maximum backup size in GB"
    )

    # Logging configuration
    log_level: str = Field(default="INFO", description="Logging level")
    log_dir: str = Field(default="logs", description="Log directory path")

    # Safety checks
    require_backup_before_run: bool = Field(
        default=True, description="Require backup before simulation"
    )
    enable_emergency_backups: bool = Field(
        default=True, description="Create emergency backup on restore"
    )


class OrchestrationConfig(BaseModel):
    """Complete orchestration configuration including production safety"""

    model_config = ConfigDict(extra="allow")

    # Core simulation configuration
    simulation: SimulationSettings
    compensation: CompensationSettings
    workforce: WorkforceSettings = WorkforceSettings()
    enrollment: EnrollmentSettings = EnrollmentSettings()
    eligibility: EligibilitySettings = EligibilitySettings()
    plan_eligibility: PlanEligibilitySettings = PlanEligibilitySettings()
    employer_match: Optional[EmployerMatchSettings] = Field(default=None, description="Employer match configuration")

    # Performance optimization configuration
    optimization: OptimizationSettings = Field(default_factory=OptimizationSettings, description="Performance optimization settings")

    # Production safety configuration
    production_safety: ProductionSafetySettings = ProductionSafetySettings()

    # Enterprise identifiers
    scenario_id: Optional[str] = None
    plan_design_id: Optional[str] = None

    def require_identifiers(self) -> None:
        """Raise if scenario_id/plan_design_id are missing."""
        if not self.scenario_id or not self.plan_design_id:
            raise ValueError(
                "scenario_id and plan_design_id are required for orchestrator runs"
            )


class SimulationConfig(BaseModel):
    """Top-level config with backward compatible extras allowed."""

    model_config = ConfigDict(extra="allow")

    # Enterprise identifiers (encouraged by architecture; optional for back-compat)
    scenario_id: Optional[str] = None
    plan_design_id: Optional[str] = None

    simulation: SimulationSettings
    compensation: CompensationSettings
    workforce: WorkforceSettings = WorkforceSettings()
    enrollment: EnrollmentSettings = EnrollmentSettings()
    eligibility: EligibilitySettings = EligibilitySettings()
    plan_eligibility: PlanEligibilitySettings = PlanEligibilitySettings()
    employer_match: Optional[EmployerMatchSettings] = Field(default=None, description="Employer match configuration")

    # Performance optimization configuration (optional for backward compatibility)
    optimization: Optional[OptimizationSettings] = Field(default=None, description="Performance optimization settings")

    # Orchestrator configuration including threading support
    orchestrator: Optional[OrchestratorSettings] = Field(default=None, description="Orchestrator configuration including threading")

    def require_identifiers(self) -> None:
        """Raise if scenario_id/plan_design_id are missing."""
        if not self.scenario_id or not self.plan_design_id:
            raise ValueError(
                "scenario_id and plan_design_id are required for orchestrator runs"
            )

    def get_thread_count(self) -> int:
        """Get configured thread count with fallback to single-threaded execution"""
        # Check E068C threading configuration first
        if self.optimization and self.optimization.e068c_threading:
            return self.optimization.e068c_threading.dbt_threads
        # Fallback to orchestrator threading configuration
        elif self.orchestrator and self.orchestrator.threading.enabled:
            return self.orchestrator.threading.thread_count
        return 1

    def get_e068c_threading_config(self) -> E068CThreadingSettings:
        """Get E068C threading configuration with defaults"""
        if self.optimization and self.optimization.e068c_threading:
            return self.optimization.e068c_threading
        return E068CThreadingSettings()

    def get_event_shards(self) -> int:
        """Get configured event shards count"""
        if self.optimization and self.optimization.e068c_threading:
            return self.optimization.e068c_threading.event_shards
        return 1

    def get_max_parallel_years(self) -> int:
        """Get configured maximum parallel years"""
        if self.optimization and self.optimization.e068c_threading:
            return self.optimization.e068c_threading.max_parallel_years
        return 1

    def get_event_generation_mode(self) -> str:
        """Get configured event generation mode (sql or polars)"""
        if self.optimization and self.optimization.event_generation:
            return self.optimization.event_generation.mode
        return "sql"

    def get_polars_settings(self) -> PolarsEventSettings:
        """Get Polars event generation settings"""
        if self.optimization and self.optimization.event_generation:
            return self.optimization.event_generation.polars
        return PolarsEventSettings()

    def is_polars_mode_enabled(self) -> bool:
        """Check if Polars event generation mode is enabled and configured"""
        return (self.get_event_generation_mode() == "polars" and
                self.get_polars_settings().enabled)

    def validate_threading_configuration(self) -> None:
        """Validate threading configuration and log warnings"""
        # Validate E068C threading configuration first
        if self.optimization and self.optimization.e068c_threading:
            try:
                self.optimization.e068c_threading.validate_e068c_configuration()
            except ValueError as e:
                raise ValueError(f"Invalid E068C threading configuration: {e}")

        # Validate event generation configuration
        if self.optimization and self.optimization.event_generation:
            try:
                self.optimization.event_generation.validate_mode()
            except ValueError as e:
                raise ValueError(f"Invalid event generation configuration: {e}")

        # Validate legacy orchestrator threading configuration if present
        if self.orchestrator and self.orchestrator.threading.enabled:
            try:
                self.orchestrator.threading.validate_thread_count()
            except ValueError as e:
                raise ValueError(f"Invalid orchestrator threading configuration: {e}")

            # Additional compatibility checks
            thread_count = self.orchestrator.threading.thread_count
            mode = self.orchestrator.threading.mode

            if mode == "sequential" and thread_count > 1:
                import warnings
                warnings.warn(f"Threading mode is 'sequential' but thread_count is {thread_count}. Consider setting thread_count=1 or changing mode to 'selective'.")

            if mode == "aggressive" and thread_count == 1:
                import warnings
                warnings.warn(f"Threading mode is 'aggressive' but thread_count is 1. Consider increasing thread_count or changing mode to 'sequential'.")


def _lower_keys(d: Dict[str, Any]) -> Dict[str, Any]:
    return {k.lower(): v for k, v in d.items()}


def _apply_env_overrides(cfg: Dict[str, Any], env: Dict[str, str], prefix: str) -> None:
    """Apply simple env overrides using DOUBLE-UNDERSCORE path syntax.

    Example: NAV_SIMULATION__START_YEAR=2026 overrides simulation.start_year
    """
    plen = len(prefix)
    for key, value in env.items():
        if not key.startswith(prefix):
            continue
        path = key[plen:].lower().split("__")
        cur: Any = cfg
        for part in path[:-1]:
            if part not in cur or not isinstance(cur[part], dict):
                cur[part] = {}
            cur = cur[part]
        # Basic type coercion for ints/bools/floats
        leaf = path[-1]
        if value.lower() in {"true", "false"}:
            cur[leaf] = value.lower() == "true"
        else:
            try:
                if "." in value:
                    cur[leaf] = float(value)
                else:
                    cur[leaf] = int(value)
            except ValueError:
                cur[leaf] = value


def load_simulation_config(
    path: Path | str = Path("config/simulation_config.yaml"),
    *,
    env_overrides: bool = True,
    env: Optional[Dict[str, str]] = None,
    env_prefix: str = "NAV_",
) -> SimulationConfig:
    """Load YAML config and return a typed `SimulationConfig`.

    - Allows extra keys for backward compatibility with existing YAML
    - Optionally applies environment variable overrides
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Config file not found: {p}")

    with open(p, "r") as fh:
        raw = yaml.safe_load(fh) or {}

    # Normalize to lowercase keys at top level for resilience
    data = _lower_keys(raw)

    if env_overrides:
        import os as _os

        _apply_env_overrides(data, env or dict(_os.environ), env_prefix)

    try:
        return SimulationConfig(**data)
    except ValidationError as e:
        # Raise clear error for CLI consumption
        raise ValueError(f"Invalid simulation configuration: {e}") from e


def to_dbt_vars(cfg: SimulationConfig) -> Dict[str, Any]:
    """Map typed config to dbt vars compatible with existing models.

    Mirrors the existing `extract_dbt_vars_from_config` behavior in a typed way.
    """
    dbt_vars: Dict[str, Any] = {}

    # Simulation bounds
    if cfg.simulation.start_year is not None:
        dbt_vars["start_year"] = int(cfg.simulation.start_year)
    if cfg.simulation.end_year is not None:
        dbt_vars["end_year"] = int(cfg.simulation.end_year)

    # Compensation
    if cfg.compensation.cola_rate is not None:
        dbt_vars["cola_rate"] = cfg.compensation.cola_rate
    if cfg.compensation.merit_budget is not None:
        dbt_vars["merit_budget"] = cfg.compensation.merit_budget

    # Eligibility and plan eligibility
    if cfg.eligibility.waiting_period_days is not None:
        dbt_vars["eligibility_waiting_days"] = cfg.eligibility.waiting_period_days
        dbt_vars["minimum_service_days"] = cfg.eligibility.waiting_period_days
    if cfg.plan_eligibility.minimum_age is not None:
        dbt_vars["minimum_age"] = cfg.plan_eligibility.minimum_age

    # Auto-enrollment
    auto = cfg.enrollment.auto_enrollment
    if auto.enabled is not None:
        dbt_vars["auto_enrollment_enabled"] = bool(auto.enabled)
    if auto.scope is not None:
        dbt_vars["auto_enrollment_scope"] = str(auto.scope)
    if auto.hire_date_cutoff:
        dbt_vars["auto_enrollment_hire_date_cutoff"] = str(auto.hire_date_cutoff)
    if auto.window_days is not None:
        dbt_vars["auto_enrollment_window_days"] = int(auto.window_days)
    if auto.default_deferral_rate is not None:
        dbt_vars["auto_enrollment_default_deferral_rate"] = float(
            auto.default_deferral_rate
        )
    if auto.opt_out_grace_period is not None:
        dbt_vars["auto_enrollment_opt_out_grace_period"] = int(
            auto.opt_out_grace_period
        )

    # Opt-out rates by age
    age_rates = auto.opt_out_rates.by_age
    dbt_vars["opt_out_rate_young"] = float(age_rates.young)
    dbt_vars["opt_out_rate_mid"] = float(age_rates.mid_career)
    dbt_vars["opt_out_rate_mature"] = float(age_rates.mature)
    dbt_vars["opt_out_rate_senior"] = float(age_rates.senior)

    # Opt-out rates by income (calculate absolute rates from base + multipliers)
    income_rates = auto.opt_out_rates.by_income
    # Use moderate rate as base (typically young segment rate * moderate multiplier)
    base_rate = float(age_rates.young)  # Use young as typical base case
    moderate_rate = base_rate * float(income_rates.moderate)

    dbt_vars["opt_out_rate_low_income"] = base_rate * float(income_rates.low_income)
    dbt_vars["opt_out_rate_moderate"] = moderate_rate
    dbt_vars["opt_out_rate_high"] = base_rate * float(income_rates.high)
    dbt_vars["opt_out_rate_executive"] = base_rate * float(income_rates.executive)

    # Proactive enrollment
    pro = cfg.enrollment.proactive_enrollment
    if pro.enabled is not None:
        dbt_vars["proactive_enrollment_enabled"] = bool(pro.enabled)
    tw = pro.timing_window
    if tw.min_days is not None:
        dbt_vars["proactive_enrollment_min_days"] = int(tw.min_days)
    if tw.max_days is not None:
        dbt_vars["proactive_enrollment_max_days"] = int(tw.max_days)
    probs = pro.probability_by_demographics or {}
    for key in ("young", "mid_career", "mature", "senior"):
        if key in probs:
            dbt_vars[f"proactive_enrollment_rate_{key}"] = float(probs[key])

    # Timing
    if cfg.enrollment.timing.business_day_adjustment is not None:
        dbt_vars["enrollment_business_day_adjustment"] = bool(
            cfg.enrollment.timing.business_day_adjustment
        )

    # Random seed
    if cfg.simulation.random_seed is not None:
        dbt_vars["random_seed"] = cfg.simulation.random_seed

    # Growth and workforce parameters (CRITICAL FIX)
    if cfg.simulation.target_growth_rate is not None:
        dbt_vars["target_growth_rate"] = cfg.simulation.target_growth_rate

    # Termination rates (CRITICAL FIX)
    if hasattr(cfg, "workforce") and cfg.workforce:
        if cfg.workforce.total_termination_rate is not None:
            dbt_vars["total_termination_rate"] = cfg.workforce.total_termination_rate
        if cfg.workforce.new_hire_termination_rate is not None:
            dbt_vars[
                "new_hire_termination_rate"
            ] = cfg.workforce.new_hire_termination_rate

    # Deferral auto-escalation (E035 - simplified)
    try:
        dae = getattr(cfg, "deferral_auto_escalation", None)
        if isinstance(dae, dict):
            if "enabled" in dae:
                dbt_vars["deferral_escalation_enabled"] = bool(dae["enabled"])
            if "effective_day" in dae and dae["effective_day"]:
                # MM-DD string
                dbt_vars["deferral_escalation_effective_mmdd"] = str(
                    dae["effective_day"]
                )
            if "increment_amount" in dae and dae["increment_amount"] is not None:
                dbt_vars["deferral_escalation_increment"] = float(
                    dae["increment_amount"]
                )
            if "maximum_rate" in dae and dae["maximum_rate"] is not None:
                dbt_vars["deferral_escalation_cap"] = float(dae["maximum_rate"])
            if "hire_date_cutoff" in dae and dae["hire_date_cutoff"]:
                dbt_vars["deferral_escalation_hire_date_cutoff"] = str(
                    dae["hire_date_cutoff"]
                )
            if "require_active_enrollment" in dae:
                dbt_vars["deferral_escalation_require_enrollment"] = bool(
                    dae["require_active_enrollment"]
                )
    except Exception:
        pass

    # Deferral baseline mode (Option A default: frozen)
    try:
        db = getattr(cfg, "deferral_baseline", None)
        if isinstance(db, dict) and "mode" in db and db["mode"]:
            dbt_vars["deferral_baseline_mode"] = str(db["mode"]).lower()
        else:
            dbt_vars["deferral_baseline_mode"] = "frozen"
    except Exception:
        dbt_vars["deferral_baseline_mode"] = "frozen"

    # Staging/setup parameters: support file paths and plan-year settings from setup
    try:
        setup = getattr(cfg, "setup", None)
        if isinstance(setup, dict):
            # census_parquet_path: make absolute relative to repo root if given as relative path
            cpp = setup.get("census_parquet_path")
            if cpp:
                cpp_path = Path(cpp)
                if not cpp_path.is_absolute():
                    # Repo root = navigator_orchestrator/.. (this file lives under navigator_orchestrator)
                    repo_root = Path(__file__).resolve().parent.parent
                    cpp_path = (repo_root / cpp_path).resolve()
                dbt_vars["census_parquet_path"] = str(cpp_path)

            # Optional plan-year & eligibility vars for staging models
            pysd = setup.get("plan_year_start_date")
            pyed = setup.get("plan_year_end_date")
            ew = setup.get("eligibility_waiting_period_days")
            if pysd:
                dbt_vars["plan_year_start_date"] = str(pysd)
            if pyed:
                dbt_vars["plan_year_end_date"] = str(pyed)
            if ew is not None:
                dbt_vars["eligibility_waiting_period_days"] = int(ew)

            # Optional contract enforcement toggle for portability
            enf = setup.get("enforce_contracts")
            if enf is not None:
                dbt_vars["enforce_contracts"] = bool(enf)
    except Exception:
        # Non-fatal: continue with defaults
        pass

    # Epic E058: Enhanced employer match configuration with eligibility
    # Generate nested employer_match variable structure for dbt models
    # Always provide employer_match variable with safe defaults for backward compatibility
    employer_match_defaults = {
        'apply_eligibility': False,
        'eligibility': {
            'minimum_tenure_years': 0,
            'require_active_at_year_end': True,
            'minimum_hours_annual': 1000,
            'allow_new_hires': True,
            'allow_terminated_new_hires': False,
            'allow_experienced_terminations': False
        }
    }

    try:
        # Handle both Pydantic model and dict (for backward compatibility)
        employer_match = cfg.employer_match
        if employer_match is not None:
            # Convert Pydantic model to dict if needed
            if hasattr(employer_match, 'model_dump'):
                employer_data = employer_match.model_dump()
            else:
                # Fallback for dict-based configuration (legacy)
                employer_data = employer_match if isinstance(employer_match, dict) else {}

            # Generate nested employer_match variable structure
            dbt_employer_match = {
                'apply_eligibility': employer_data.get('apply_eligibility', False),
                'eligibility': {
                    'minimum_tenure_years': employer_data.get('eligibility', {}).get('minimum_tenure_years', 0),
                    'require_active_at_year_end': employer_data.get('eligibility', {}).get('require_active_at_year_end', True),
                    'minimum_hours_annual': employer_data.get('eligibility', {}).get('minimum_hours_annual', 1000),
                    'allow_new_hires': employer_data.get('eligibility', {}).get('allow_new_hires', True),
                    'allow_terminated_new_hires': employer_data.get('eligibility', {}).get('allow_terminated_new_hires', False),
                    'allow_experienced_terminations': employer_data.get('eligibility', {}).get('allow_experienced_terminations', False)
                }
            }
            dbt_vars["employer_match"] = dbt_employer_match

            # Maintain backward compatibility with existing variables
            active_formula = employer_data.get("active_formula")
            formulas = employer_data.get("formulas")
            if active_formula is not None:
                dbt_vars["active_match_formula"] = str(active_formula)
            if formulas is not None:
                dbt_vars["match_formulas"] = formulas
        else:
            # Try to get legacy configuration from extra fields
            employer_legacy = getattr(cfg, "employer_match", None)
            if employer_legacy and isinstance(employer_legacy, dict):
                # Legacy dict-based configuration from extra fields
                dbt_employer_match = {
                    'apply_eligibility': employer_legacy.get('apply_eligibility', False),
                    'eligibility': {
                        'minimum_tenure_years': employer_legacy.get('eligibility', {}).get('minimum_tenure_years', 0),
                        'require_active_at_year_end': employer_legacy.get('eligibility', {}).get('require_active_at_year_end', True),
                        'minimum_hours_annual': employer_legacy.get('eligibility', {}).get('minimum_hours_annual', 1000),
                        'allow_new_hires': employer_legacy.get('eligibility', {}).get('allow_new_hires', True),
                        'allow_terminated_new_hires': employer_legacy.get('eligibility', {}).get('allow_terminated_new_hires', False),
                        'allow_experienced_terminations': employer_legacy.get('eligibility', {}).get('allow_experienced_terminations', False)
                    }
                }
                dbt_vars["employer_match"] = dbt_employer_match

                # Backward compatibility
                if "active_formula" in employer_legacy:
                    dbt_vars["active_match_formula"] = str(employer_legacy["active_formula"])
                if "formulas" in employer_legacy:
                    dbt_vars["match_formulas"] = employer_legacy["formulas"]
            else:
                # No employer_match configuration found - use safe defaults
                dbt_vars["employer_match"] = employer_match_defaults

    except Exception as e:
        # Non-fatal: fall back to model defaults, but log the error
        import traceback
        print(f"Warning: Error processing employer_match configuration: {e}")
        print(f"Traceback: {traceback.format_exc()}")
        # Always provide defaults
        dbt_vars["employer_match"] = employer_match_defaults

    # Epic E059: Promotion compensation configuration
    promotion = cfg.compensation.promotion_compensation
    dbt_vars["promotion_base_increase_pct"] = promotion.base_increase_pct
    dbt_vars["promotion_distribution_range"] = promotion.distribution_range
    dbt_vars["promotion_max_cap_pct"] = promotion.max_cap_pct
    dbt_vars["promotion_max_cap_amount"] = promotion.max_cap_amount
    dbt_vars["promotion_distribution_type"] = promotion.distribution_type
    dbt_vars["promotion_level_overrides"] = promotion.level_overrides or {}
    dbt_vars["promotion_normal_std_dev"] = promotion.advanced.normal_std_dev

    # Market adjustments (if configured)
    if promotion.advanced.market_adjustments:
        dbt_vars["promotion_market_adjustments"] = promotion.advanced.market_adjustments

    # E068C Threading configuration for dbt
    e068c_config = cfg.get_e068c_threading_config()
    dbt_vars["dbt_threads"] = e068c_config.dbt_threads
    dbt_vars["event_shards"] = e068c_config.event_shards
    dbt_vars["max_parallel_years"] = e068c_config.max_parallel_years

    # E068G Event generation mode configuration
    event_gen_mode = cfg.get_event_generation_mode()
    polars_settings = cfg.get_polars_settings()
    dbt_vars["event_generation_mode"] = event_gen_mode
    dbt_vars["polars_enabled"] = cfg.is_polars_mode_enabled()
    if event_gen_mode == "polars":
        dbt_vars["polars_output_path"] = polars_settings.output_path
        dbt_vars["polars_max_threads"] = polars_settings.max_threads

    # Employer core contribution configuration
    # Map YAML employer_core_contribution block to dbt vars
    # NOTE: int_employer_eligibility.sql reads nested employer_core_contribution.eligibility
    # Ensure we pass the nested structure (keep flat vars for backward compatibility)
    try:
        core_contrib = getattr(cfg, "employer_core_contribution", None)
        if core_contrib:
            # core_contrib is likely a dict due to extra=allow
            enabled = core_contrib.get("enabled")
            rate = core_contrib.get("contribution_rate")
            eligibility = core_contrib.get("eligibility") or {}

            # Flat vars (backward compatibility with older models/macros)
            if enabled is not None:
                dbt_vars["employer_core_enabled"] = bool(enabled)
            if rate is not None:
                dbt_vars["employer_core_contribution_rate"] = float(rate)

            if eligibility:
                min_tenure = eligibility.get("minimum_tenure_years")
                require_active = eligibility.get("require_active_at_year_end")
                min_hours = eligibility.get("minimum_hours_annual")
                allow_new_hires = eligibility.get("allow_new_hires")
                allow_terminated_new_hires = eligibility.get("allow_terminated_new_hires")
                allow_experienced_terminations = eligibility.get("allow_experienced_terminations")

                if min_tenure is not None:
                    dbt_vars["core_minimum_tenure_years"] = int(min_tenure)
                if require_active is not None:
                    dbt_vars["core_require_active_eoy"] = bool(require_active)
                if min_hours is not None:
                    dbt_vars["core_minimum_hours"] = int(min_hours)
                if allow_new_hires is not None:
                    dbt_vars["core_allow_new_hires"] = bool(allow_new_hires)
                if allow_terminated_new_hires is not None:
                    dbt_vars["core_allow_terminated_new_hires"] = bool(allow_terminated_new_hires)
                if allow_experienced_terminations is not None:
                    dbt_vars["core_allow_experienced_terminations"] = bool(allow_experienced_terminations)

            # Nested var (required by current int_employer_eligibility.sql)
            dbt_core_nested: Dict[str, Any] = {}
            if enabled is not None:
                dbt_core_nested["enabled"] = bool(enabled)
            if rate is not None:
                dbt_core_nested["contribution_rate"] = float(rate)

            nested_elig: Dict[str, Any] = {}
            for key in (
                "minimum_tenure_years",
                "require_active_at_year_end",
                "minimum_hours_annual",
                "allow_new_hires",
                "allow_terminated_new_hires",
                "allow_experienced_terminations",
            ):
                if key in eligibility and eligibility.get(key) is not None:
                    nested_elig[key] = eligibility.get(key)

            if nested_elig:
                dbt_core_nested["eligibility"] = nested_elig

            if dbt_core_nested:
                dbt_vars["employer_core_contribution"] = dbt_core_nested
    except Exception:
        # Non-fatal: fall back to model defaults
        pass

    return dbt_vars


def validate_production_configuration(config: OrchestrationConfig) -> None:
    """
    Validate production configuration for safety requirements

    Story S043-02: Configuration Management

    Args:
        config: Complete orchestration configuration

    Raises:
        ValueError: If configuration validation fails
        FileNotFoundError: If required files don't exist
    """
    safety = config.production_safety

    # Validate database path exists
    db_path = Path(safety.db_path)
    if not db_path.exists():
        raise FileNotFoundError(f"Database file not found: {db_path}")

    # Validate database is accessible
    try:
        import duckdb

        with duckdb.connect(str(db_path)) as conn:
            conn.execute("SELECT 1").fetchone()
    except Exception as e:
        raise ValueError(f"Database connection failed: {str(e)}")

    # Validate backup directory is writable
    backup_dir = Path(safety.backup_dir)
    backup_dir.mkdir(parents=True, exist_ok=True)

    # Test write permissions
    test_file = backup_dir / ".write_test"
    try:
        test_file.write_text("test")
        test_file.unlink()
    except Exception as e:
        raise ValueError(f"Backup directory not writable: {backup_dir} - {str(e)}")

    # Validate log directory is writable
    log_dir = Path(safety.log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)

    # Test log directory write permissions
    test_log = log_dir / ".write_test"
    try:
        test_log.write_text("test")
        test_log.unlink()
    except Exception as e:
        raise ValueError(f"Log directory not writable: {log_dir} - {str(e)}")

    # Validate disk space
    db_size = db_path.stat().st_size
    required_space = db_size * 2  # Database + backup + 100% buffer

    import shutil

    available_space = shutil.disk_usage(backup_dir).free

    if available_space < required_space:
        required_gb = required_space / (1024**3)
        available_gb = available_space / (1024**3)
        raise ValueError(
            f"Insufficient disk space. Required: {required_gb:.2f} GB, "
            f"Available: {available_gb:.2f} GB"
        )

    # Validate log level
    valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
    if safety.log_level.upper() not in valid_levels:
        raise ValueError(
            f"Invalid log level: {safety.log_level}. Must be one of {valid_levels}"
        )


def load_orchestration_config(
    path: Path | str = Path("config/orchestration_config.yaml"),
    *,
    validate_production: bool = True,
    env_overrides: bool = True,
    env: Optional[Dict[str, str]] = None,
    env_prefix: str = "NAV_",
) -> OrchestrationConfig:
    """
    Load complete orchestration configuration with production safety validation

    Args:
        path: Path to configuration file
        validate_production: Enable production safety validation
        env_overrides: Enable environment variable overrides
        env: Environment variables (uses os.environ if None)
        env_prefix: Prefix for environment variable overrides

    Returns:
        Validated orchestration configuration

    Raises:
        FileNotFoundError: If config file doesn't exist
        ValueError: If configuration is invalid
    """
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"Configuration file not found: {p}")

    with open(p, "r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh) or {}

    # Normalize to lowercase keys at top level for resilience
    data = _lower_keys(raw)

    if env_overrides:
        _apply_env_overrides(data, env or dict(os.environ), env_prefix)

    try:
        config = OrchestrationConfig(**data)
    except ValidationError as e:
        raise ValueError(f"Invalid orchestration configuration: {e}") from e

    # Production safety validation
    if validate_production:
        validate_production_configuration(config)

    return config


def get_backup_configuration(config: OrchestrationConfig) -> "BackupConfiguration":
    """
    Extract backup configuration for BackupManager

    Args:
        config: Complete orchestration configuration

    Returns:
        BackupConfiguration object suitable for BackupManager initialization
    """
    # Import here to avoid circular imports
    from .backup_manager import BackupConfiguration

    safety = config.production_safety

    return BackupConfiguration(
        backup_dir=Path(safety.backup_dir),
        retention_days=safety.backup_retention_days,
        verify_backups=safety.verify_backups,
        max_backup_size_gb=safety.max_backup_size_gb,
    )


def create_example_orchestration_config() -> str:
    """
    Create example orchestration configuration with production safety settings

    Returns:
        YAML configuration string
    """
    return """# PlanWise Navigator Orchestration Configuration
# Epic E043: Production Data Safety & Backup System

# Core simulation settings
simulation:
  start_year: 2025
  end_year: 2029
  random_seed: 42
  target_growth_rate: 0.03

# Compensation parameters
compensation:
  cola_rate: 0.005
  merit_budget: 0.025

# Workforce modeling
workforce:
  total_termination_rate: 0.12
  new_hire_termination_rate: 0.25

# Production data safety settings
production_safety:
  # Database configuration
  db_path: "simulation.duckdb"

  # Backup settings
  backup_enabled: true
  backup_dir: "backups"
  backup_retention_days: 7
  backup_before_simulation: true
  verify_backups: true
  max_backup_size_gb: 10.0

  # Logging configuration
  log_level: "INFO"
  log_dir: "logs"

  # Safety requirements
  require_backup_before_run: true
  enable_emergency_backups: true

# Enterprise identifiers (optional)
scenario_id: "default"
plan_design_id: "standard_401k"

# Enrollment settings
enrollment:
  auto_enrollment:
    enabled: true
    scope: "all_eligible_employees"
    hire_date_cutoff: null
    window_days: 45
    default_deferral_rate: 0.06
    opt_out_grace_period: 30
    opt_out_rates:
      by_age:
        young: 0.10
        mid_career: 0.07
        mature: 0.05
        senior: 0.03
      by_income:
        low_income: 1.20
        moderate: 1.00
        high: 0.70
        executive: 0.50

# Plan eligibility
eligibility:
  waiting_period_days: null

plan_eligibility:
  minimum_age: null
"""
