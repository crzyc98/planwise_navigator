"""Simulation service using planalign CLI for execution.

DEPRECATION NOTICE:
    This module is a backward compatibility wrapper. For new code, import directly from:
    - planalign_api.services.simulation

Example:
    # Old way (still works):
    from planalign_api.services.simulation_service import SimulationService

    # New way (preferred):
    from planalign_api.services.simulation import SimulationService
"""

# Re-export all public symbols from the simulation package
from .simulation import (
    # Utilities
    IS_WINDOWS,
    create_subprocess,
    wait_subprocess,
    # Handlers
    export_results_to_excel,
    # Main service
    SimulationService,
)

# Also export helper functions with their original names for backward compatibility
_create_subprocess = create_subprocess
_wait_subprocess = wait_subprocess
_export_results_to_excel = export_results_to_excel

__all__ = [
    # Utilities
    "IS_WINDOWS",
    "create_subprocess",
    "wait_subprocess",
    "_create_subprocess",
    "_wait_subprocess",
    # Handlers
    "export_results_to_excel",
    "_export_results_to_excel",
    # Main service
    "SimulationService",
]
