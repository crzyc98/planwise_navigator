"""Configuration module for PlanAlign Engine.

E073: Config Module Refactoring

This module provides a clean, modular configuration system. All models and
functions are re-exported here for backward compatibility with existing imports.

Submodules:
    - paths: Project root and database path utilities
    - simulation: Simulation and compensation settings
    - workforce: Workforce, enrollment, eligibility settings
    - performance: Threading, optimization, Polars settings
    - safety: Production safety and OrchestrationConfig
    - loader: SimulationConfig and config loading functions
    - export: to_dbt_vars and helper functions
"""

# Path utilities
from .paths import (
    get_project_root,
    get_database_path,
)

# Simulation settings
from .simulation import (
    SimulationSettings,
    CompensationSettings,
    PromotionCompensationSettings,
)

# Workforce settings
from .workforce import (
    WorkforceSettings,
    OptOutRatesByAge,
    OptOutRatesByIncome,
    OptOutRatesSettings,
    AutoEnrollmentSettings,
    ProactiveEnrollmentSettings,
    EnrollmentTimingSettings,
    EnrollmentSettings,
    EligibilitySettings,
    PlanEligibilitySettings,
    EmployerMatchEligibilitySettings,
    EmployerMatchSettings,
)

# Performance settings
from .performance import (
    AdaptiveMemoryThresholds,
    AdaptiveBatchSizes,
    AdaptiveMemorySettings,
    CPUMonitoringThresholds,
    CPUMonitoringSettings,
    ResourceManagerSettings,
    ModelParallelizationSettings,
    ThreadingSettings,
    OrchestratorSettings,
    PolarsEventSettings,
    EventGenerationSettings,
    E068CThreadingSettings,
    OptimizationSettings,
)

# Safety settings
from .safety import (
    ProductionSafetySettings,
    OrchestrationConfig,
    validate_production_configuration,
    get_backup_configuration,
)

# Loader functions
from .loader import (
    SimulationConfig,
    load_simulation_config,
    load_orchestration_config,
)

# Export functions
from .export import (
    to_dbt_vars,
    _export_simulation_vars,
    _export_enrollment_vars,
    _export_legacy_vars,
    _export_employer_match_vars,
    _export_compensation_vars,
    _export_threading_vars,
    _export_core_contribution_vars,
)

__all__ = [
    # Paths
    "get_project_root",
    "get_database_path",
    # Simulation
    "SimulationSettings",
    "CompensationSettings",
    "PromotionCompensationSettings",
    # Workforce
    "WorkforceSettings",
    "OptOutRatesByAge",
    "OptOutRatesByIncome",
    "OptOutRatesSettings",
    "AutoEnrollmentSettings",
    "ProactiveEnrollmentSettings",
    "EnrollmentTimingSettings",
    "EnrollmentSettings",
    "EligibilitySettings",
    "PlanEligibilitySettings",
    "EmployerMatchEligibilitySettings",
    "EmployerMatchSettings",
    # Performance
    "AdaptiveMemoryThresholds",
    "AdaptiveBatchSizes",
    "AdaptiveMemorySettings",
    "CPUMonitoringThresholds",
    "CPUMonitoringSettings",
    "ResourceManagerSettings",
    "ModelParallelizationSettings",
    "ThreadingSettings",
    "OrchestratorSettings",
    "PolarsEventSettings",
    "EventGenerationSettings",
    "E068CThreadingSettings",
    "OptimizationSettings",
    # Safety
    "ProductionSafetySettings",
    "OrchestrationConfig",
    "validate_production_configuration",
    "get_backup_configuration",
    # Loader
    "SimulationConfig",
    "load_simulation_config",
    "load_orchestration_config",
    # Export
    "to_dbt_vars",
]
