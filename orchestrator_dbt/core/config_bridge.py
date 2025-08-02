"""
Configuration Bridge for Multi-Year Simulation

Provides seamless integration between different configuration systems:
- orchestrator_dbt.OrchestrationConfig (new structured config)
- orchestrator_dbt.multi_year.MultiYearConfig (legacy multi-year config)
- orchestrator_mvp configuration (simple path-based config)
- config.schema.SimulationConfig (Pydantic v1 validation)

This bridge ensures backward compatibility while enabling new multi-year features.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, Any, Optional, Union
from dataclasses import dataclass

from .config import (
    OrchestrationConfig,
    MultiYearConfig as NewMultiYearConfig,
    OptimizationLevel,
    ValidationMode,
    TransitionStrategy
)


@dataclass
class ConfigurationBridge:
    """
    Configuration bridge that provides unified access to all configuration systems.

    This class acts as a facade that:
    1. Loads configuration from the standard YAML file
    2. Provides access through multiple interfaces for backward compatibility
    3. Handles environment variable overrides consistently
    4. Validates configuration across all systems
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize configuration bridge.

        Args:
            config_path: Optional path to configuration YAML file.
                        Defaults to config/simulation_config.yaml
        """
        self.orchestration_config = OrchestrationConfig(config_path)
        self._legacy_multi_year_config: Optional['LegacyMultiYearConfig'] = None
        self._mvp_config: Optional[Dict[str, Any]] = None

    @property
    def orchestration(self) -> OrchestrationConfig:
        """Get orchestration configuration (new structured config)."""
        return self.orchestration_config

    @property
    def multi_year(self) -> NewMultiYearConfig:
        """Get new multi-year configuration."""
        return self.orchestration_config.multi_year

    def get_legacy_multi_year_config(self) -> 'LegacyMultiYearConfig':
        """Get legacy multi-year configuration for backward compatibility."""
        if self._legacy_multi_year_config is None:
            from ..multi_year.multi_year_orchestrator import MultiYearConfig as LegacyMultiYearConfig
            self._legacy_multi_year_config = LegacyMultiYearConfig.from_orchestration_config(
                self.orchestration_config
            )
        return self._legacy_multi_year_config

    def get_mvp_config(self) -> Dict[str, Any]:
        """Get orchestrator_mvp compatible configuration."""
        if self._mvp_config is None:
            self._mvp_config = {
                "DBT_PROJECT_DIR": self.orchestration_config.dbt.project_dir,
                "DUCKDB_PATH": self.orchestration_config.database.path,
                "SCHEMA_NAME": self.orchestration_config.database.schema_name,
                "PROJECT_ROOT": self.orchestration_config.project_root,
            }
        return self._mvp_config

    def get_simulation_parameters(self) -> Dict[str, Any]:
        """Get simulation parameters compatible with all systems."""
        simulation_config = self.orchestration_config.get_simulation_config()
        workforce_config = self.orchestration_config.get_workforce_config()

        return {
            # Core simulation parameters
            "start_year": simulation_config.get("start_year", 2025),
            "end_year": simulation_config.get("end_year", 2029),
            "random_seed": simulation_config.get("random_seed", 42),
            "target_growth_rate": simulation_config.get("target_growth_rate", 0.03),

            # Workforce parameters
            "total_termination_rate": workforce_config.get("total_termination_rate", 0.12),
            "new_hire_termination_rate": workforce_config.get("new_hire_termination_rate", 0.25),

            # Multi-year specific parameters
            "optimization_level": self.multi_year.optimization.level.value,
            "max_workers": self.multi_year.optimization.max_workers,
            "batch_size": self.multi_year.optimization.batch_size,
            "memory_limit_gb": self.multi_year.optimization.memory_limit_gb,
            "enable_state_compression": self.multi_year.performance.enable_state_compression,
            "enable_concurrent_processing": self.multi_year.performance.enable_concurrent_processing,
            "enable_checkpointing": self.multi_year.state.enable_checkpointing,
            "checkpoint_frequency": self.multi_year.state.checkpoint_frequency,
            "fail_fast": self.multi_year.error_handling.fail_fast,
            "max_retries": self.multi_year.error_handling.max_retries,
            "transition_strategy": self.multi_year.transition.strategy.value,
            "enable_performance_monitoring": self.multi_year.monitoring.enable_performance_monitoring,
        }

    def get_dbt_vars_extended(self) -> Dict[str, Any]:
        """Get extended dbt variables including multi-year parameters."""
        base_vars = self.orchestration_config.get_dbt_vars()

        # Add multi-year specific dbt variables
        multi_year_vars = {
            "multi_year_optimization_level": self.multi_year.optimization.level.value,
            "multi_year_enable_parallel_dbt": self.multi_year.performance.enable_parallel_dbt,
            "multi_year_batch_size": self.multi_year.optimization.batch_size,
            "multi_year_validation_mode": self.multi_year.error_handling.validation_mode.value,
            "multi_year_enable_checkpointing": self.multi_year.state.enable_checkpointing,
            "multi_year_compression_level": self.multi_year.state.compression_level,
        }

        return {**base_vars, **multi_year_vars}

    def get_environment_config(self) -> Dict[str, str]:
        """Get environment configuration suitable for subprocess calls."""
        env_config = {}

        # Database configuration
        env_config["DUCKDB_PATH"] = str(self.orchestration_config.database.path)
        env_config["DUCKDB_SCHEMA"] = self.orchestration_config.database.schema_name
        env_config["DUCKDB_TIMEOUT"] = str(self.orchestration_config.database.connection_timeout)

        # dbt configuration
        env_config["DBT_TARGET"] = self.orchestration_config.dbt.target
        env_config["DBT_THREADS"] = str(self.orchestration_config.dbt.threads)
        if self.orchestration_config.dbt.profiles_dir:
            env_config["DBT_PROFILES_DIR"] = str(self.orchestration_config.dbt.profiles_dir)

        # Multi-year configuration
        env_config["MULTI_YEAR_OPTIMIZATION_LEVEL"] = self.multi_year.optimization.level.value
        env_config["MULTI_YEAR_MAX_WORKERS"] = str(self.multi_year.optimization.max_workers)
        env_config["MULTI_YEAR_BATCH_SIZE"] = str(self.multi_year.optimization.batch_size)
        if self.multi_year.optimization.memory_limit_gb:
            env_config["MULTI_YEAR_MEMORY_LIMIT_GB"] = str(self.multi_year.optimization.memory_limit_gb)

        env_config["MULTI_YEAR_ENABLE_STATE_COMPRESSION"] = str(self.multi_year.performance.enable_state_compression).lower()
        env_config["MULTI_YEAR_ENABLE_CONCURRENT_PROCESSING"] = str(self.multi_year.performance.enable_concurrent_processing).lower()
        env_config["MULTI_YEAR_ENABLE_PARALLEL_DBT"] = str(self.multi_year.performance.enable_parallel_dbt).lower()
        env_config["MULTI_YEAR_CACHE_WORKFORCE_SNAPSHOTS"] = str(self.multi_year.performance.cache_workforce_snapshots).lower()

        env_config["MULTI_YEAR_ENABLE_CHECKPOINTING"] = str(self.multi_year.state.enable_checkpointing).lower()
        env_config["MULTI_YEAR_CHECKPOINT_FREQUENCY"] = str(self.multi_year.state.checkpoint_frequency)
        env_config["MULTI_YEAR_PRESERVE_INTERMEDIATE_STATES"] = str(self.multi_year.state.preserve_intermediate_states).lower()
        env_config["MULTI_YEAR_COMPRESSION_LEVEL"] = str(self.multi_year.state.compression_level)

        env_config["MULTI_YEAR_ENABLE_RESUME"] = str(self.multi_year.resume.enable_resume).lower()
        env_config["MULTI_YEAR_AUTO_RESUME_ON_FAILURE"] = str(self.multi_year.resume.auto_resume_on_failure).lower()
        env_config["MULTI_YEAR_CLEANUP_ON_SUCCESS"] = str(self.multi_year.resume.cleanup_on_success).lower()

        env_config["MULTI_YEAR_FAIL_FAST"] = str(self.multi_year.error_handling.fail_fast).lower()
        env_config["MULTI_YEAR_MAX_RETRIES"] = str(self.multi_year.error_handling.max_retries)
        env_config["MULTI_YEAR_RETRY_DELAY_SECONDS"] = str(self.multi_year.error_handling.retry_delay_seconds)
        env_config["MULTI_YEAR_VALIDATION_MODE"] = self.multi_year.error_handling.validation_mode.value

        env_config["MULTI_YEAR_TRANSITION_STRATEGY"] = self.multi_year.transition.strategy.value
        env_config["MULTI_YEAR_BATCH_WORKFORCE_UPDATES"] = str(self.multi_year.transition.batch_workforce_updates).lower()
        env_config["MULTI_YEAR_OPTIMIZE_EVENT_PROCESSING"] = str(self.multi_year.transition.optimize_event_processing).lower()

        env_config["MULTI_YEAR_ENABLE_PERFORMANCE_MONITORING"] = str(self.multi_year.monitoring.enable_performance_monitoring).lower()
        env_config["MULTI_YEAR_ENABLE_PROGRESS_REPORTING"] = str(self.multi_year.monitoring.enable_progress_reporting).lower()
        env_config["MULTI_YEAR_LOG_LEVEL"] = self.multi_year.monitoring.log_level
        env_config["MULTI_YEAR_ENABLE_MEMORY_PROFILING"] = str(self.multi_year.monitoring.enable_memory_profiling).lower()

        # Project configuration
        env_config["PLANWISE_PROJECT_ROOT"] = str(self.orchestration_config.project_root)

        return env_config

    def validate_all(self) -> None:
        """Validate configuration across all systems."""
        # Validate orchestration config (includes multi-year validation)
        self.orchestration_config.validate()

        # Additional cross-system validation
        simulation_config = self.orchestration_config.get_simulation_config()
        start_year = simulation_config.get("start_year")
        end_year = simulation_config.get("end_year")

        if start_year and end_year and start_year >= end_year:
            raise ValueError(f"start_year ({start_year}) must be less than end_year ({end_year})")

        # Validate that multi-year configuration is reasonable for the year range
        if start_year and end_year:
            year_range = end_year - start_year
            if year_range > 20:
                if self.multi_year.optimization.level == OptimizationLevel.LOW:
                    raise ValueError(
                        f"Year range of {year_range} is too large for LOW optimization level. "
                        "Consider using MEDIUM or HIGH optimization level for better performance."
                    )

        # Validate memory limits are reasonable
        if self.multi_year.optimization.memory_limit_gb:
            if self.multi_year.optimization.memory_limit_gb < 1.0:
                raise ValueError("memory_limit_gb should be at least 1.0 GB for reasonable performance")
            if self.multi_year.optimization.memory_limit_gb > 64.0:
                import warnings
                warnings.warn(
                    f"memory_limit_gb of {self.multi_year.optimization.memory_limit_gb} GB is very high. "
                    "Consider whether this is appropriate for your system."
                )

    def get_compatibility_report(self) -> Dict[str, Any]:
        """Generate a compatibility report showing configuration mappings."""
        return {
            "orchestration_config": {
                "project_root": str(self.orchestration_config.project_root),
                "config_path": str(self.orchestration_config.config_path),
                "database_path": str(self.orchestration_config.database.path),
                "dbt_project_dir": str(self.orchestration_config.dbt.project_dir),
            },
            "multi_year_config": {
                "optimization_level": self.multi_year.optimization.level.value,
                "max_workers": self.multi_year.optimization.max_workers,
                "batch_size": self.multi_year.optimization.batch_size,
                "memory_limit_gb": self.multi_year.optimization.memory_limit_gb,
                "enable_state_compression": self.multi_year.performance.enable_state_compression,
                "enable_concurrent_processing": self.multi_year.performance.enable_concurrent_processing,
                "enable_checkpointing": self.multi_year.state.enable_checkpointing,
                "fail_fast": self.multi_year.error_handling.fail_fast,
                "transition_strategy": self.multi_year.transition.strategy.value,
            },
            "legacy_compatibility": {
                "mvp_config_available": bool(self._mvp_config is not None),
                "legacy_multi_year_config_available": bool(self._legacy_multi_year_config is not None),
            },
            "environment_overrides": self.orchestration_config.get_environment_overrides(),
        }

    def __repr__(self) -> str:
        """String representation of configuration bridge."""
        return (
            f"ConfigurationBridge(\n"
            f"  project_root={self.orchestration_config.project_root},\n"
            f"  optimization_level={self.multi_year.optimization.level.value},\n"
            f"  max_workers={self.multi_year.optimization.max_workers},\n"
            f"  database_path={self.orchestration_config.database.path}\n"
            f")"
        )


def get_default_config_bridge() -> ConfigurationBridge:
    """Get default configuration bridge."""
    return ConfigurationBridge()


def load_config_bridge(config_path: Optional[str] = None) -> ConfigurationBridge:
    """
    Load configuration bridge from file.

    Args:
        config_path: Optional path to configuration file

    Returns:
        Loaded and validated configuration bridge
    """
    path = Path(config_path) if config_path else None
    return ConfigurationBridge(path)
