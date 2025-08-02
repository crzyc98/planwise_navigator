"""
Configuration management for orchestrator_dbt.

Provides configuration loading, validation, and access patterns for the dbt-based
orchestration system. Follows the established patterns from orchestrator_mvp while
extending for setup-specific needs.
"""

from __future__ import annotations

import os
import yaml
from pathlib import Path
from typing import Dict, Any, Optional, Literal, Union
from dataclasses import dataclass, field
from enum import Enum


class OptimizationLevel(Enum):
    """Optimization level for multi-year simulation."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    FALLBACK = "fallback"


class ValidationMode(Enum):
    """Validation mode for multi-year operations."""
    STRICT = "strict"
    WARNINGS = "warnings"
    DISABLED = "disabled"


class TransitionStrategy(Enum):
    """Strategy for year-to-year transitions."""
    OPTIMIZED = "optimized"
    CONSERVATIVE = "conservative"
    PARALLEL = "parallel"


@dataclass
class MultiYearOptimizationConfig:
    """Multi-year optimization configuration."""
    level: OptimizationLevel = OptimizationLevel.HIGH
    max_workers: int = 4
    batch_size: int = 1000
    memory_limit_gb: Optional[float] = 8.0


@dataclass
class MultiYearPerformanceConfig:
    """Multi-year performance configuration."""
    enable_state_compression: bool = True
    enable_concurrent_processing: bool = True
    enable_parallel_dbt: bool = True
    cache_workforce_snapshots: bool = True


@dataclass
class MultiYearStateConfig:
    """Multi-year state management configuration."""
    enable_checkpointing: bool = True
    checkpoint_frequency: int = 1
    preserve_intermediate_states: bool = False
    compression_level: int = 6


@dataclass
class MultiYearResumeConfig:
    """Multi-year resume configuration."""
    enable_resume: bool = True
    auto_resume_on_failure: bool = False
    cleanup_on_success: bool = True


@dataclass
class MultiYearErrorHandlingConfig:
    """Multi-year error handling configuration."""
    fail_fast: bool = False
    max_retries: int = 3
    retry_delay_seconds: int = 5
    validation_mode: ValidationMode = ValidationMode.STRICT


@dataclass
class MultiYearTransitionConfig:
    """Multi-year transition configuration."""
    strategy: TransitionStrategy = TransitionStrategy.OPTIMIZED
    batch_workforce_updates: bool = True
    optimize_event_processing: bool = True


@dataclass
class MultiYearMonitoringConfig:
    """Multi-year monitoring and logging configuration."""
    enable_performance_monitoring: bool = True
    enable_progress_reporting: bool = True
    log_level: str = "INFO"
    enable_memory_profiling: bool = False


@dataclass
class MultiYearConfig:
    """Complete multi-year simulation configuration."""
    optimization: MultiYearOptimizationConfig = field(default_factory=MultiYearOptimizationConfig)
    performance: MultiYearPerformanceConfig = field(default_factory=MultiYearPerformanceConfig)
    state: MultiYearStateConfig = field(default_factory=MultiYearStateConfig)
    resume: MultiYearResumeConfig = field(default_factory=MultiYearResumeConfig)
    error_handling: MultiYearErrorHandlingConfig = field(default_factory=MultiYearErrorHandlingConfig)
    transition: MultiYearTransitionConfig = field(default_factory=MultiYearTransitionConfig)
    monitoring: MultiYearMonitoringConfig = field(default_factory=MultiYearMonitoringConfig)

    def validate(self) -> None:
        """Validate multi-year configuration."""
        if self.optimization.max_workers < 1:
            raise ValueError("max_workers must be at least 1")

        if self.optimization.batch_size < 1:
            raise ValueError("batch_size must be at least 1")

        if self.optimization.memory_limit_gb is not None and self.optimization.memory_limit_gb <= 0:
            raise ValueError("memory_limit_gb must be positive")

        if not (1 <= self.state.compression_level <= 9):
            raise ValueError("compression_level must be between 1 and 9")

        if self.state.checkpoint_frequency < 1:
            raise ValueError("checkpoint_frequency must be at least 1")

        if self.error_handling.max_retries < 0:
            raise ValueError("max_retries must be non-negative")

        if self.error_handling.retry_delay_seconds < 0:
            raise ValueError("retry_delay_seconds must be non-negative")


@dataclass
class DatabaseConfig:
    """Database configuration settings."""
    path: Path
    schema_name: str = "main"
    connection_timeout: int = 30

    def validate(self) -> None:
        """Validate database configuration."""
        if not self.path.parent.exists():
            raise FileNotFoundError(f"Database directory does not exist: {self.path.parent}")


@dataclass
class DbtConfig:
    """dbt project configuration settings."""
    project_dir: Path
    profiles_dir: Optional[Path] = None
    target: str = "dev"
    threads: int = 4

    def validate(self) -> None:
        """Validate dbt configuration."""
        if not self.project_dir.exists():
            raise FileNotFoundError(f"dbt project directory not found: {self.project_dir}")

        dbt_project_yml = self.project_dir / "dbt_project.yml"
        if not dbt_project_yml.exists():
            raise FileNotFoundError(f"dbt_project.yml not found: {dbt_project_yml}")


@dataclass
class SetupConfig:
    """Setup-specific configuration settings."""
    clear_tables: bool = True
    clear_table_patterns: list[str] = field(default_factory=lambda: ["stg_", "int_", "fct_", "dim_"])
    load_seeds: bool = True
    run_staging_models: bool = True
    validate_results: bool = True
    fail_on_validation_error: bool = True

    # Census-specific configuration
    census_parquet_path: Optional[str] = None
    plan_year_start_date: str = "2024-01-01"
    plan_year_end_date: str = "2024-12-31"
    eligibility_waiting_period_days: int = 30


@dataclass
class ValidationConfig:
    """Data validation configuration settings."""
    min_baseline_workforce_count: int = 1000
    max_workforce_variance: float = 0.05  # 5% variance tolerance
    required_seed_tables: list[str] = field(default_factory=lambda: [
        "comp_levers",
        "config_job_levels",
        "config_cola_by_year"
    ])
    required_staging_models: list[str] = field(default_factory=lambda: [
        "stg_census_data",
        "stg_config_job_levels",
        "stg_comp_levers"
    ])


class OrchestrationConfig:
    """
    Main configuration class for orchestrator_dbt.

    Manages loading and validation of configuration from YAML files,
    environment variables, and provides structured access to all settings.
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration.

        Args:
            config_path: Optional path to configuration YAML file.
                        Defaults to config/simulation_config.yaml
        """
        # Determine project root and config path
        self.project_root = self._get_project_root()
        self.config_path = config_path or (self.project_root / "config" / "simulation_config.yaml")

        # Load configuration
        self.raw_config = self._load_config()

        # Initialize structured configuration
        self.database = self._init_database_config()
        self.dbt = self._init_dbt_config()
        self.setup = self._init_setup_config()
        self.validation = self._init_validation_config()
        self.multi_year = self._init_multi_year_config()

        # Validate all configurations
        self.validate()

    def _get_project_root(self) -> Path:
        """Get the project root directory."""
        # Walk up from this file to find the project root
        current = Path(__file__).parent
        while current.parent != current:
            if (current / "dbt" / "dbt_project.yml").exists():
                return current
            current = current.parent

        # Fallback to environment or current working directory
        if "PLANWISE_PROJECT_ROOT" in os.environ:
            return Path(os.environ["PLANWISE_PROJECT_ROOT"])

        raise FileNotFoundError("Could not determine project root directory")

    def _resolve_census_path(self, census_path: Optional[str]) -> Optional[str]:
        """Resolve census parquet path to absolute path."""
        if not census_path:
            return None

        path = Path(census_path)
        if path.is_absolute():
            return str(path)
        else:
            # Resolve relative to project root
            resolved_path = self.project_root / path
            return str(resolved_path)

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from YAML file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        with open(self.config_path, 'r') as f:
            return yaml.safe_load(f)

    def _init_database_config(self) -> DatabaseConfig:
        """Initialize database configuration."""
        # Check for environment override
        db_path = os.environ.get("DUCKDB_PATH")
        if db_path:
            db_path = Path(db_path)
        else:
            db_path = self.project_root / "simulation.duckdb"

        return DatabaseConfig(
            path=db_path,
            schema_name=os.environ.get("DUCKDB_SCHEMA", "main"),
            connection_timeout=int(os.environ.get("DUCKDB_TIMEOUT", "30"))
        )

    def _init_dbt_config(self) -> DbtConfig:
        """Initialize dbt configuration."""
        dbt_dir = self.project_root / "dbt"
        profiles_dir = os.environ.get("DBT_PROFILES_DIR")

        return DbtConfig(
            project_dir=dbt_dir,
            profiles_dir=Path(profiles_dir) if profiles_dir else None,
            target=os.environ.get("DBT_TARGET", "dev"),
            threads=int(os.environ.get("DBT_THREADS", "4"))
        )

    def _init_setup_config(self) -> SetupConfig:
        """Initialize setup configuration from YAML and environment."""
        setup_config = self.raw_config.get("setup", {})

        return SetupConfig(
            clear_tables=setup_config.get("clear_tables", True),
            clear_table_patterns=setup_config.get("clear_table_patterns", ["stg_", "int_", "fct_", "dim_"]),
            load_seeds=setup_config.get("load_seeds", True),
            run_staging_models=setup_config.get("run_staging_models", True),
            validate_results=setup_config.get("validate_results", True),
            fail_on_validation_error=setup_config.get("fail_on_validation_error", True),

            # Census configuration
            census_parquet_path=self._resolve_census_path(setup_config.get("census_parquet_path") or os.environ.get("CENSUS_PARQUET_PATH")),
            plan_year_start_date=setup_config.get("plan_year_start_date", "2024-01-01"),
            plan_year_end_date=setup_config.get("plan_year_end_date", "2024-12-31"),
            eligibility_waiting_period_days=setup_config.get("eligibility_waiting_period_days", 30)
        )

    def _init_validation_config(self) -> ValidationConfig:
        """Initialize validation configuration."""
        validation_config = self.raw_config.get("validation", {})

        return ValidationConfig(
            min_baseline_workforce_count=validation_config.get("min_baseline_workforce_count", 1000),
            max_workforce_variance=validation_config.get("max_workforce_variance", 0.05),
            required_seed_tables=validation_config.get("required_seed_tables", [
                "comp_levers", "config_job_levels", "config_cola_by_year"
            ]),
            required_staging_models=validation_config.get("required_staging_models", [
                "stg_census_data", "stg_config_job_levels", "stg_comp_levers"
            ])
        )

    def _init_multi_year_config(self) -> MultiYearConfig:
        """Initialize multi-year configuration from YAML and environment."""
        multi_year_config = self.raw_config.get("multi_year", {})

        # Extract nested configuration sections
        optimization_config = multi_year_config.get("optimization", {})
        performance_config = multi_year_config.get("performance", {})
        state_config = multi_year_config.get("state", {})
        resume_config = multi_year_config.get("resume", {})
        error_handling_config = multi_year_config.get("error_handling", {})
        transition_config = multi_year_config.get("transition", {})
        monitoring_config = multi_year_config.get("monitoring", {})

        # Parse optimization configuration with environment overrides
        optimization = MultiYearOptimizationConfig(
            level=self._parse_enum(
                optimization_config.get("level", "high"),
                OptimizationLevel,
                os.environ.get("MULTI_YEAR_OPTIMIZATION_LEVEL")
            ),
            max_workers=int(os.environ.get("MULTI_YEAR_MAX_WORKERS",
                                        optimization_config.get("max_workers", 4))),
            batch_size=int(os.environ.get("MULTI_YEAR_BATCH_SIZE",
                                        optimization_config.get("batch_size", 1000))),
            memory_limit_gb=self._parse_optional_float(
                os.environ.get("MULTI_YEAR_MEMORY_LIMIT_GB", optimization_config.get("memory_limit_gb"))
            )
        )

        # Parse performance configuration
        performance = MultiYearPerformanceConfig(
            enable_state_compression=self._parse_bool(
                os.environ.get("MULTI_YEAR_ENABLE_STATE_COMPRESSION",
                             performance_config.get("enable_state_compression", True))
            ),
            enable_concurrent_processing=self._parse_bool(
                os.environ.get("MULTI_YEAR_ENABLE_CONCURRENT_PROCESSING",
                             performance_config.get("enable_concurrent_processing", True))
            ),
            enable_parallel_dbt=self._parse_bool(
                os.environ.get("MULTI_YEAR_ENABLE_PARALLEL_DBT",
                             performance_config.get("enable_parallel_dbt", True))
            ),
            cache_workforce_snapshots=self._parse_bool(
                os.environ.get("MULTI_YEAR_CACHE_WORKFORCE_SNAPSHOTS",
                             performance_config.get("cache_workforce_snapshots", True))
            )
        )

        # Parse state configuration
        state = MultiYearStateConfig(
            enable_checkpointing=self._parse_bool(
                os.environ.get("MULTI_YEAR_ENABLE_CHECKPOINTING",
                             state_config.get("enable_checkpointing", True))
            ),
            checkpoint_frequency=int(os.environ.get("MULTI_YEAR_CHECKPOINT_FREQUENCY",
                                                   state_config.get("checkpoint_frequency", 1))),
            preserve_intermediate_states=self._parse_bool(
                os.environ.get("MULTI_YEAR_PRESERVE_INTERMEDIATE_STATES",
                             state_config.get("preserve_intermediate_states", False))
            ),
            compression_level=int(os.environ.get("MULTI_YEAR_COMPRESSION_LEVEL",
                                                state_config.get("compression_level", 6)))
        )

        # Parse resume configuration
        resume = MultiYearResumeConfig(
            enable_resume=self._parse_bool(
                os.environ.get("MULTI_YEAR_ENABLE_RESUME",
                             resume_config.get("enable_resume", True))
            ),
            auto_resume_on_failure=self._parse_bool(
                os.environ.get("MULTI_YEAR_AUTO_RESUME_ON_FAILURE",
                             resume_config.get("auto_resume_on_failure", False))
            ),
            cleanup_on_success=self._parse_bool(
                os.environ.get("MULTI_YEAR_CLEANUP_ON_SUCCESS",
                             resume_config.get("cleanup_on_success", True))
            )
        )

        # Parse error handling configuration
        error_handling = MultiYearErrorHandlingConfig(
            fail_fast=self._parse_bool(
                os.environ.get("MULTI_YEAR_FAIL_FAST",
                             error_handling_config.get("fail_fast", False))
            ),
            max_retries=int(os.environ.get("MULTI_YEAR_MAX_RETRIES",
                                         error_handling_config.get("max_retries", 3))),
            retry_delay_seconds=int(os.environ.get("MULTI_YEAR_RETRY_DELAY_SECONDS",
                                                  error_handling_config.get("retry_delay_seconds", 5))),
            validation_mode=self._parse_enum(
                error_handling_config.get("validation_mode", "strict"),
                ValidationMode,
                os.environ.get("MULTI_YEAR_VALIDATION_MODE")
            )
        )

        # Parse transition configuration
        transition = MultiYearTransitionConfig(
            strategy=self._parse_enum(
                transition_config.get("strategy", "optimized"),
                TransitionStrategy,
                os.environ.get("MULTI_YEAR_TRANSITION_STRATEGY")
            ),
            batch_workforce_updates=self._parse_bool(
                os.environ.get("MULTI_YEAR_BATCH_WORKFORCE_UPDATES",
                             transition_config.get("batch_workforce_updates", True))
            ),
            optimize_event_processing=self._parse_bool(
                os.environ.get("MULTI_YEAR_OPTIMIZE_EVENT_PROCESSING",
                             transition_config.get("optimize_event_processing", True))
            )
        )

        # Parse monitoring configuration
        monitoring = MultiYearMonitoringConfig(
            enable_performance_monitoring=self._parse_bool(
                os.environ.get("MULTI_YEAR_ENABLE_PERFORMANCE_MONITORING",
                             monitoring_config.get("enable_performance_monitoring", True))
            ),
            enable_progress_reporting=self._parse_bool(
                os.environ.get("MULTI_YEAR_ENABLE_PROGRESS_REPORTING",
                             monitoring_config.get("enable_progress_reporting", True))
            ),
            log_level=os.environ.get("MULTI_YEAR_LOG_LEVEL",
                                   monitoring_config.get("log_level", "INFO")),
            enable_memory_profiling=self._parse_bool(
                os.environ.get("MULTI_YEAR_ENABLE_MEMORY_PROFILING",
                             monitoring_config.get("enable_memory_profiling", False))
            )
        )

        return MultiYearConfig(
            optimization=optimization,
            performance=performance,
            state=state,
            resume=resume,
            error_handling=error_handling,
            transition=transition,
            monitoring=monitoring
        )

    def _parse_bool(self, value: Union[bool, str, None]) -> bool:
        """Parse boolean value from environment variable or config."""
        if value is None:
            return False
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in ("true", "1", "yes", "on")
        return bool(value)

    def _parse_optional_float(self, value: Union[float, str, None]) -> Optional[float]:
        """Parse optional float value from environment variable or config."""
        if value is None or value == "":
            return None
        if isinstance(value, float):
            return value
        if isinstance(value, str):
            if value.lower() in ("null", "none", ""):
                return None
            return float(value)
        return float(value)

    def _parse_enum(self, value: str, enum_class: type, env_override: Optional[str] = None) -> Any:
        """Parse enum value with optional environment override."""
        actual_value = env_override if env_override else value
        if isinstance(actual_value, enum_class):
            return actual_value
        try:
            return enum_class(actual_value.lower())
        except (ValueError, AttributeError):
            # Try uppercase
            try:
                return enum_class(actual_value.upper())
            except (ValueError, AttributeError):
                # Fall back to default
                return list(enum_class)[0]

    def validate(self) -> None:
        """Validate all configuration settings."""
        self.database.validate()
        self.dbt.validate()
        self.multi_year.validate()

        # Additional orchestrator-specific validation
        if self.setup.census_parquet_path:
            census_path = Path(self.setup.census_parquet_path)
            if not census_path.exists():
                raise FileNotFoundError(f"Census parquet file not found: {census_path}")

    def get_dbt_vars(self) -> Dict[str, Any]:
        """Get dbt variables for model execution."""
        return {
            "census_parquet_path": self.setup.census_parquet_path,
            "plan_year_start_date": self.setup.plan_year_start_date,
            "plan_year_end_date": self.setup.plan_year_end_date,
            "eligibility_waiting_period_days": self.setup.eligibility_waiting_period_days,
        }

    def get_simulation_config(self) -> Dict[str, Any]:
        """Get simulation configuration for compatibility with existing orchestrators."""
        return self.raw_config.get("simulation", {})

    def get_workforce_config(self) -> Dict[str, Any]:
        """Get workforce configuration."""
        return self.raw_config.get("workforce", {})

    def get_eligibility_config(self) -> Dict[str, Any]:
        """Get eligibility configuration."""
        return self.raw_config.get("eligibility", {})

    def get_enrollment_config(self) -> Dict[str, Any]:
        """Get enrollment configuration."""
        return self.raw_config.get("enrollment", {})

    def get_multi_year_config(self) -> MultiYearConfig:
        """Get multi-year configuration."""
        return self.multi_year

    def get_ops_config(self) -> Dict[str, Any]:
        """Get Dagster ops configuration."""
        return self.raw_config.get("ops", {})

    def to_legacy_multi_year_config(self) -> Dict[str, Any]:
        """Convert to legacy MultiYearConfig format for backward compatibility."""
        return {
            "start_year": self.get_simulation_config().get("start_year", 2025),
            "end_year": self.get_simulation_config().get("end_year", 2029),
            "optimization_level": self.multi_year.optimization.level.value,
            "max_workers": self.multi_year.optimization.max_workers,
            "batch_size": self.multi_year.optimization.batch_size,
            "enable_state_compression": self.multi_year.performance.enable_state_compression,
            "enable_concurrent_processing": self.multi_year.performance.enable_concurrent_processing,
            "enable_validation": self.multi_year.error_handling.validation_mode != ValidationMode.DISABLED,
            "fail_fast": self.multi_year.error_handling.fail_fast,
            "transition_strategy": self.multi_year.transition.strategy.value,
            "performance_monitoring": self.multi_year.monitoring.enable_performance_monitoring,
            "memory_limit_gb": self.multi_year.optimization.memory_limit_gb,
        }

    def get_environment_overrides(self) -> Dict[str, str]:
        """Get current environment variable overrides for multi-year configuration."""
        env_vars = {}

        # Optimization overrides
        if "MULTI_YEAR_OPTIMIZATION_LEVEL" in os.environ:
            env_vars["MULTI_YEAR_OPTIMIZATION_LEVEL"] = os.environ["MULTI_YEAR_OPTIMIZATION_LEVEL"]
        if "MULTI_YEAR_MAX_WORKERS" in os.environ:
            env_vars["MULTI_YEAR_MAX_WORKERS"] = os.environ["MULTI_YEAR_MAX_WORKERS"]
        if "MULTI_YEAR_BATCH_SIZE" in os.environ:
            env_vars["MULTI_YEAR_BATCH_SIZE"] = os.environ["MULTI_YEAR_BATCH_SIZE"]
        if "MULTI_YEAR_MEMORY_LIMIT_GB" in os.environ:
            env_vars["MULTI_YEAR_MEMORY_LIMIT_GB"] = os.environ["MULTI_YEAR_MEMORY_LIMIT_GB"]

        # Performance overrides
        if "MULTI_YEAR_ENABLE_STATE_COMPRESSION" in os.environ:
            env_vars["MULTI_YEAR_ENABLE_STATE_COMPRESSION"] = os.environ["MULTI_YEAR_ENABLE_STATE_COMPRESSION"]
        if "MULTI_YEAR_ENABLE_CONCURRENT_PROCESSING" in os.environ:
            env_vars["MULTI_YEAR_ENABLE_CONCURRENT_PROCESSING"] = os.environ["MULTI_YEAR_ENABLE_CONCURRENT_PROCESSING"]
        if "MULTI_YEAR_ENABLE_PARALLEL_DBT" in os.environ:
            env_vars["MULTI_YEAR_ENABLE_PARALLEL_DBT"] = os.environ["MULTI_YEAR_ENABLE_PARALLEL_DBT"]
        if "MULTI_YEAR_CACHE_WORKFORCE_SNAPSHOTS" in os.environ:
            env_vars["MULTI_YEAR_CACHE_WORKFORCE_SNAPSHOTS"] = os.environ["MULTI_YEAR_CACHE_WORKFORCE_SNAPSHOTS"]

        # State management overrides
        if "MULTI_YEAR_ENABLE_CHECKPOINTING" in os.environ:
            env_vars["MULTI_YEAR_ENABLE_CHECKPOINTING"] = os.environ["MULTI_YEAR_ENABLE_CHECKPOINTING"]
        if "MULTI_YEAR_CHECKPOINT_FREQUENCY" in os.environ:
            env_vars["MULTI_YEAR_CHECKPOINT_FREQUENCY"] = os.environ["MULTI_YEAR_CHECKPOINT_FREQUENCY"]
        if "MULTI_YEAR_PRESERVE_INTERMEDIATE_STATES" in os.environ:
            env_vars["MULTI_YEAR_PRESERVE_INTERMEDIATE_STATES"] = os.environ["MULTI_YEAR_PRESERVE_INTERMEDIATE_STATES"]
        if "MULTI_YEAR_COMPRESSION_LEVEL" in os.environ:
            env_vars["MULTI_YEAR_COMPRESSION_LEVEL"] = os.environ["MULTI_YEAR_COMPRESSION_LEVEL"]

        # Resume overrides
        if "MULTI_YEAR_ENABLE_RESUME" in os.environ:
            env_vars["MULTI_YEAR_ENABLE_RESUME"] = os.environ["MULTI_YEAR_ENABLE_RESUME"]
        if "MULTI_YEAR_AUTO_RESUME_ON_FAILURE" in os.environ:
            env_vars["MULTI_YEAR_AUTO_RESUME_ON_FAILURE"] = os.environ["MULTI_YEAR_AUTO_RESUME_ON_FAILURE"]
        if "MULTI_YEAR_CLEANUP_ON_SUCCESS" in os.environ:
            env_vars["MULTI_YEAR_CLEANUP_ON_SUCCESS"] = os.environ["MULTI_YEAR_CLEANUP_ON_SUCCESS"]

        # Error handling overrides
        if "MULTI_YEAR_FAIL_FAST" in os.environ:
            env_vars["MULTI_YEAR_FAIL_FAST"] = os.environ["MULTI_YEAR_FAIL_FAST"]
        if "MULTI_YEAR_MAX_RETRIES" in os.environ:
            env_vars["MULTI_YEAR_MAX_RETRIES"] = os.environ["MULTI_YEAR_MAX_RETRIES"]
        if "MULTI_YEAR_RETRY_DELAY_SECONDS" in os.environ:
            env_vars["MULTI_YEAR_RETRY_DELAY_SECONDS"] = os.environ["MULTI_YEAR_RETRY_DELAY_SECONDS"]
        if "MULTI_YEAR_VALIDATION_MODE" in os.environ:
            env_vars["MULTI_YEAR_VALIDATION_MODE"] = os.environ["MULTI_YEAR_VALIDATION_MODE"]

        # Transition overrides
        if "MULTI_YEAR_TRANSITION_STRATEGY" in os.environ:
            env_vars["MULTI_YEAR_TRANSITION_STRATEGY"] = os.environ["MULTI_YEAR_TRANSITION_STRATEGY"]
        if "MULTI_YEAR_BATCH_WORKFORCE_UPDATES" in os.environ:
            env_vars["MULTI_YEAR_BATCH_WORKFORCE_UPDATES"] = os.environ["MULTI_YEAR_BATCH_WORKFORCE_UPDATES"]
        if "MULTI_YEAR_OPTIMIZE_EVENT_PROCESSING" in os.environ:
            env_vars["MULTI_YEAR_OPTIMIZE_EVENT_PROCESSING"] = os.environ["MULTI_YEAR_OPTIMIZE_EVENT_PROCESSING"]

        # Monitoring overrides
        if "MULTI_YEAR_ENABLE_PERFORMANCE_MONITORING" in os.environ:
            env_vars["MULTI_YEAR_ENABLE_PERFORMANCE_MONITORING"] = os.environ["MULTI_YEAR_ENABLE_PERFORMANCE_MONITORING"]
        if "MULTI_YEAR_ENABLE_PROGRESS_REPORTING" in os.environ:
            env_vars["MULTI_YEAR_ENABLE_PROGRESS_REPORTING"] = os.environ["MULTI_YEAR_ENABLE_PROGRESS_REPORTING"]
        if "MULTI_YEAR_LOG_LEVEL" in os.environ:
            env_vars["MULTI_YEAR_LOG_LEVEL"] = os.environ["MULTI_YEAR_LOG_LEVEL"]
        if "MULTI_YEAR_ENABLE_MEMORY_PROFILING" in os.environ:
            env_vars["MULTI_YEAR_ENABLE_MEMORY_PROFILING"] = os.environ["MULTI_YEAR_ENABLE_MEMORY_PROFILING"]

        return env_vars

    @property
    def project_root_path(self) -> Path:
        """Get the project root path."""
        return self.project_root

    def __repr__(self) -> str:
        """String representation of configuration."""
        return (
            f"OrchestrationConfig(\n"
            f"  project_root={self.project_root},\n"
            f"  config_path={self.config_path},\n"
            f"  database_path={self.database.path},\n"
            f"  dbt_project_dir={self.dbt.project_dir}\n"
            f")"
        )


def get_default_config() -> OrchestrationConfig:
    """Get default orchestration configuration."""
    return OrchestrationConfig()


def load_config(config_path: Optional[str] = None) -> OrchestrationConfig:
    """
    Load orchestration configuration from file.

    Args:
        config_path: Optional path to configuration file

    Returns:
        Loaded and validated configuration
    """
    path = Path(config_path) if config_path else None
    return OrchestrationConfig(path)
