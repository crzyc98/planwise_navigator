"""Core infrastructure for MVP orchestrator.

Contains configuration management and database operations.
"""

from .config import DUCKDB_PATH, DBT_PROJECT_DIR, SCHEMA_NAME, PROJECT_ROOT
from .database_manager import (
    get_connection,
    list_tables,
    drop_foreign_key_constraints,
    drop_tables_with_retry,
    clear_database,
)
from .event_emitter import (
    generate_experienced_termination_events,
    generate_and_store_termination_events,
    validate_events_in_database,
)
from .simulation_checklist import (
    SimulationChecklist,
    StepSequenceError,
    SimulationStep
)
from .multi_year_orchestrator import MultiYearSimulationOrchestrator

__all__ = [
    "DUCKDB_PATH",
    "DBT_PROJECT_DIR",
    "SCHEMA_NAME",
    "PROJECT_ROOT",
    "get_connection",
    "list_tables",
    "drop_foreign_key_constraints",
    "drop_tables_with_retry",
    "clear_database",
    "generate_experienced_termination_events",
    "generate_and_store_termination_events",
    "validate_events_in_database",
    "SimulationChecklist",
    "StepSequenceError",
    "SimulationStep",
    "MultiYearSimulationOrchestrator",
]
