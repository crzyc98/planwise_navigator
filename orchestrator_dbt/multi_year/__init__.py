"""
Multi-Year Simulation Orchestration Package

A comprehensive multi-year workforce simulation system that leverages the optimized
orchestrator_dbt foundation for 82% performance improvement. This package implements
the composite pattern to integrate existing optimized components with multi-year
simulation workflow management.

Architecture:
- MultiYearOrchestrator: Main coordinator using composite pattern
- YearProcessor: Individual year processing with batch operations
- SimulationState: State management with compression and caching
- YearTransition: Year-to-year coordination and data flow

Performance Features:
- Foundation setup: <10 seconds (vs 49s legacy)
- Batch operations for seeds and staging models
- Concurrent execution with graceful fallback
- Memory-efficient state management with compression
- Circuit breaker pattern for resilient error handling
"""

__version__ = "1.0.0"
__author__ = "PlanWise Navigator Team"

from .multi_year_orchestrator import (
    MultiYearOrchestrator,
    MultiYearResult,
    FoundationSetupResult,
    MultiYearConfig,
    OptimizationLevel,
    create_multi_year_orchestrator,
    create_high_performance_orchestrator
)
from .year_processor import (
    YearProcessor,
    YearResult,
    YearContext,
    ProcessingStrategy
)
from .simulation_state import (
    SimulationState,
    WorkforceState,
    StateManager,
    StateCompression
)
from .year_transition import (
    YearTransition,
    TransitionResult,
    TransitionContext,
    StateTransferStrategy
)

__all__ = [
    # Core orchestrator
    "MultiYearOrchestrator",
    "MultiYearResult",
    "FoundationSetupResult",
    "MultiYearConfig",
    "OptimizationLevel",
    "create_multi_year_orchestrator",
    "create_high_performance_orchestrator",

    # Year processing
    "YearProcessor",
    "YearResult",
    "YearContext",
    "ProcessingStrategy",

    # State management
    "SimulationState",
    "WorkforceState",
    "StateManager",
    "StateCompression",

    # Year transitions
    "YearTransition",
    "TransitionResult",
    "TransitionContext",
    "StateTransferStrategy"
]
