"""
Simulation package for PlanAlign Studio API.

Provides comprehensive simulation execution and management services
for the PlanAlign Studio web interface.
"""

from .subprocess_utils import (
    IS_WINDOWS,
    create_subprocess,
    wait_subprocess,
)
from .result_handlers import export_results_to_excel
from .service import SimulationService

__all__ = [
    # Utilities
    "IS_WINDOWS",
    "create_subprocess",
    "wait_subprocess",
    # Handlers
    "export_results_to_excel",
    # Main service
    "SimulationService",
]
