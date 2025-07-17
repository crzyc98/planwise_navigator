"""MVP Orchestrator Package.

A modular debugging toolkit for dbt models in PlanWise Navigator.

Structure:
- core/: Configuration and database operations
- loaders/: dbt model execution and data loading
- inspectors/: Data validation and inspection utilities
- run_mvp.py: Main interactive orchestration script
"""

__version__ = "0.1.0"
__author__ = "PlanWise Navigator Team"

# Import main functions for convenience
from .core import clear_database, list_tables, get_connection
from .loaders import run_dbt_model, run_staging_models, run_dbt_command
from .inspectors import inspect_stg_census_data

__all__ = [
    "clear_database",
    "list_tables",
    "get_connection",
    "run_dbt_model",
    "run_staging_models",
    "run_dbt_command",
    "inspect_stg_census_data",
]
