"""MVP Orchestrator Package.

A modular debugging toolkit for dbt models in PlanWise Navigator,
with comprehensive single-year and multi-year simulation capabilities.

Structure:
- core/: Configuration, database operations, and multi-year simulation
- loaders/: dbt model execution and data loading
- inspectors/: Data validation, inspection utilities, and multi-year analysis
- run_mvp.py: Main interactive orchestration script with multi-year mode
"""

__version__ = "0.1.0"
__author__ = "PlanWise Navigator Team"

# Import main functions for convenience
from .core import clear_database, list_tables, get_connection
from .loaders import run_dbt_model, run_staging_models, run_dbt_command
from .inspectors import inspect_stg_census_data
from .core.workforce_snapshot import generate_workforce_snapshot
from .inspectors.workforce_inspector import inspect_workforce_snapshot

# Multi-year simulation capabilities
from .core.multi_year_simulation import (
    run_multi_year_simulation,
    prepare_next_year_baseline,
    validate_year_transition
)
from .inspectors.multi_year_inspector import (
    compare_year_over_year_metrics,
    validate_cumulative_growth,
    display_multi_year_summary,
    analyze_workforce_aging,
    validate_event_consistency
)

__all__ = [
    # Core functionality
    "clear_database",
    "list_tables",
    "get_connection",
    "run_dbt_model",
    "run_staging_models",
    "run_dbt_command",
    "inspect_stg_census_data",
    "generate_workforce_snapshot",
    "inspect_workforce_snapshot",

    # Multi-year simulation
    "run_multi_year_simulation",
    "prepare_next_year_baseline",
    "validate_year_transition",

    # Multi-year analysis
    "compare_year_over_year_metrics",
    "validate_cumulative_growth",
    "display_multi_year_summary",
    "analyze_workforce_aging",
    "validate_event_consistency",
]
