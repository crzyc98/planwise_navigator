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
from .db_cleanup import cleanup_years_outside_range
from .output_parser import SimulationOutputParser
from .results_reader import read_results
from .run_archiver import archive_run, prune_old_runs
from .service import SimulationService

__all__ = [
    # Utilities
    "IS_WINDOWS",
    "create_subprocess",
    "wait_subprocess",
    # Handlers
    "export_results_to_excel",
    # Extracted modules
    "cleanup_years_outside_range",
    "SimulationOutputParser",
    "read_results",
    "archive_run",
    "prune_old_runs",
    # Main service
    "SimulationService",
]
