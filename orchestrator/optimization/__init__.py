"""
S047 Optimization Engine for PlanWise Navigator

Advanced compensation parameter optimization using SciPy algorithms.
Enables analysts to automatically find optimal parameter combinations
for complex multi-constraint scenarios.
"""

from .constraint_solver import CompensationOptimizer
from .objective_functions import ObjectiveFunctions
from .optimization_schemas import (
    OptimizationRequest,
    OptimizationResult,
    OptimizationError,
    PARAMETER_SCHEMA
)

__all__ = [
    "CompensationOptimizer",
    "ObjectiveFunctions",
    "OptimizationRequest",
    "OptimizationResult",
    "OptimizationError",
    "PARAMETER_SCHEMA"
]
