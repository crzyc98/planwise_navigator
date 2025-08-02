"""
PlanWise Navigator - dbt Orchestration Package

A comprehensive orchestration system for workforce simulation that provides both
optimized foundation setup and multi-year simulation capabilities. The package
delivers 82% performance improvement through batch operations and intelligent
coordination strategies.

Features:
- Foundation setup: <10 seconds (vs 49s legacy baseline)
- Multi-year simulation orchestration with state management
- Batch operations for seeds, staging models, and year processing
- Memory-efficient state compression and caching
- Circuit breaker patterns for resilient error handling
- Concurrent execution with graceful fallback strategies
"""

__version__ = "1.0.0"
__author__ = "PlanWise Navigator Team"

# Core orchestration components
from .workflow_orchestrator import WorkflowOrchestrator
from .core.config import (
    OrchestrationConfig,
    MultiYearConfig as NewMultiYearConfig,
    OptimizationLevel as ConfigOptimizationLevel,
    ValidationMode,
    TransitionStrategy as ConfigTransitionStrategy
)
from .core.config_bridge import ConfigurationBridge, get_default_config_bridge, load_config_bridge
from .core.database_manager import DatabaseManager
from .core.dbt_executor import DbtExecutor
from .core.validation_framework import ValidationFramework
from .loaders.seed_loader import SeedLoader
from .loaders.staging_loader import StagingLoader
from .utils.logging_utils import setup_orchestrator_logging

# Multi-year simulation components (lazy import to avoid dependencies)
def _lazy_import_multi_year():
    """Lazy import of multi-year components to avoid dependency issues."""
    try:
        from .multi_year import (
            MultiYearOrchestrator,
            MultiYearConfig,
            MultiYearResult,
            OptimizationLevel,
            create_multi_year_orchestrator,
            create_high_performance_orchestrator
        )
        return {
            "MultiYearOrchestrator": MultiYearOrchestrator,
            "MultiYearConfig": MultiYearConfig,
            "MultiYearResult": MultiYearResult,
            "OptimizationLevel": OptimizationLevel,
            "create_multi_year_orchestrator": create_multi_year_orchestrator,
            "create_high_performance_orchestrator": create_high_performance_orchestrator,
        }
    except ImportError as e:
        import warnings
        warnings.warn(f"Multi-year components not available due to missing dependencies: {e}")
        return {}

# Import multi-year components if available
_multi_year_components = _lazy_import_multi_year()

# Add multi-year components to module namespace if available
for name, component in _multi_year_components.items():
    globals()[name] = component

__all__ = [
    # Core orchestration
    "WorkflowOrchestrator",
    "OrchestrationConfig",
    "NewMultiYearConfig",
    "ConfigOptimizationLevel",
    "ValidationMode",
    "ConfigTransitionStrategy",
    "ConfigurationBridge",
    "get_default_config_bridge",
    "load_config_bridge",
    "DatabaseManager",
    "DbtExecutor",
    "ValidationFramework",
    "SeedLoader",
    "StagingLoader",
    "setup_orchestrator_logging",
] + list(_multi_year_components.keys())
