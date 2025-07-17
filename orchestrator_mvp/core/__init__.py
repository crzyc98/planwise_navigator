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
]
