"""
Database management operations for orchestrator_dbt.

Handles database connections, table clearing, and database state management
following the established patterns from orchestrator_mvp while extending
for setup-specific needs.
"""

from __future__ import annotations

import duckdb
import logging
from contextlib import contextmanager
from typing import List, Tuple, Dict, Any, Optional, Generator
from pathlib import Path

from .config import OrchestrationConfig


logger = logging.getLogger(__name__)


class DatabaseManager:
    """
    Database management operations for the dbt orchestrator.

    Provides connection management, table operations, and state validation
    with proper error handling and logging.
    """

    def __init__(self, config: OrchestrationConfig):
        """
        Initialize database manager with configuration.

        Args:
            config: Orchestration configuration containing database settings
        """
        self.config = config
        self.db_path = config.database.path
        self.schema_name = config.database.schema_name
        self.connection_timeout = config.database.connection_timeout

        # Ensure database directory exists
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def get_connection(self, read_only: bool = False) -> Generator[duckdb.DuckDBPyConnection, None, None]:
        """
        Create a managed connection to the DuckDB database.

        Args:
            read_only: Whether to open the connection in read-only mode

        Yields:
            DuckDB connection with proper cleanup
        """
        conn = None
        try:
            logger.debug(f"Connecting to database: {self.db_path}")
            conn = duckdb.connect(
                database=str(self.db_path),
                read_only=read_only
            )

            # Load extensions if available
            self._load_extensions(conn)

            # Note: DuckDB doesn't support lock_timeout configuration parameter
            # The connection_timeout is for our code logic, not a DuckDB setting

            yield conn

        except Exception as e:
            logger.error(f"Database connection error: {e}")
            if "Conflicting lock is held" in str(e):
                raise DatabaseLockError(
                    "Database is locked by another process. "
                    "Please close any open database connections in your IDE or other tools."
                ) from e
            raise DatabaseError(f"Failed to connect to database: {e}") from e

        finally:
            if conn:
                try:
                    conn.close()
                    logger.debug("Database connection closed")
                except Exception as e:
                    logger.warning(f"Error closing database connection: {e}")

    def _load_extensions(self, conn: duckdb.DuckDBPyConnection) -> None:
        """Load DuckDB extensions if available."""
        extensions = ["parquet", "json"]

        for ext in extensions:
            try:
                conn.execute(f"LOAD {ext};")
                logger.debug(f"Loaded {ext} extension")
            except Exception as e:
                logger.warning(f"Could not load {ext} extension: {e}")

    def list_tables(self, pattern: Optional[str] = None) -> List[str]:
        """
        Get a list of tables in the database.

        Args:
            pattern: Optional pattern to filter table names (e.g., "stg_")

        Returns:
            List of table names matching the pattern
        """
        with self.get_connection(read_only=True) as conn:
            query = f"""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = '{self.schema_name}'
                AND table_type = 'BASE TABLE'
                ORDER BY table_name
            """

            tables = conn.execute(query).fetchall()
            table_names = [table[0] for table in tables]

            if pattern:
                table_names = [name for name in table_names if pattern in name]

            logger.debug(f"Found {len(table_names)} tables" + (f" matching '{pattern}'" if pattern else ""))
            return table_names

    def table_exists(self, table_name: str) -> bool:
        """
        Check if a table exists in the database.

        Args:
            table_name: Name of the table to check

        Returns:
            True if table exists, False otherwise
        """
        with self.get_connection(read_only=True) as conn:
            query = f"""
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = '{self.schema_name}'
                AND table_name = '{table_name}'
            """

            count = conn.execute(query).fetchone()[0]
            return count > 0

    def get_table_row_count(self, table_name: str) -> int:
        """
        Get row count for a table.

        Args:
            table_name: Name of the table

        Returns:
            Number of rows in the table

        Raises:
            TableNotFoundError: If table does not exist
        """
        if not self.table_exists(table_name):
            raise TableNotFoundError(f"Table '{table_name}' does not exist")

        with self.get_connection(read_only=True) as conn:
            query = f"SELECT COUNT(*) FROM {self.schema_name}.{table_name}"
            count = conn.execute(query).fetchone()[0]

            logger.debug(f"Table {table_name} has {count:,} rows")
            return count

    def get_table_info(self, table_name: str) -> Dict[str, Any]:
        """
        Get detailed information about a table.

        Args:
            table_name: Name of the table

        Returns:
            Dictionary with table information
        """
        if not self.table_exists(table_name):
            raise TableNotFoundError(f"Table '{table_name}' does not exist")

        with self.get_connection(read_only=True) as conn:
            # Get row count
            row_count = conn.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]

            # Get column information
            columns_query = f"""
                SELECT column_name, data_type, is_nullable
                FROM information_schema.columns
                WHERE table_schema = '{self.schema_name}'
                AND table_name = '{table_name}'
                ORDER BY ordinal_position
            """
            columns = conn.execute(columns_query).fetchall()

            return {
                "table_name": table_name,
                "row_count": row_count,
                "column_count": len(columns),
                "columns": [
                    {
                        "name": col[0],
                        "type": col[1],
                        "nullable": col[2] == "YES"
                    }
                    for col in columns
                ]
            }

    def drop_foreign_key_constraints(self) -> List[Tuple[str, str]]:
        """
        Drop all foreign key constraints in the schema.

        Returns:
            List of (constraint_name, table_name) tuples that were dropped
        """
        dropped_constraints = []

        with self.get_connection() as conn:
            try:
                # Query for foreign key constraints (fixed for DuckDB)
                fk_query = f"""
                    SELECT DISTINCT constraint_name, table_name
                    FROM duckdb_constraints()
                    WHERE constraint_type = 'FOREIGN KEY'
                """

                constraints = conn.execute(fk_query).fetchall()
                logger.info(f"Found {len(constraints)} foreign key constraints to drop")

                for constraint_name, table_name in constraints:
                    try:
                        alter_query = f"ALTER TABLE {self.schema_name}.{table_name} DROP CONSTRAINT {constraint_name}"
                        conn.execute(alter_query)
                        dropped_constraints.append((constraint_name, table_name))
                        logger.debug(f"Dropped constraint {constraint_name} from {table_name}")
                    except Exception as e:
                        logger.warning(f"Could not drop constraint {constraint_name}: {e}")

            except Exception as e:
                logger.warning(f"Could not query foreign key constraints: {e}")

        logger.info(f"Successfully dropped {len(dropped_constraints)} foreign key constraints")
        return dropped_constraints

    def drop_tables_with_retry(self, tables: List[str], max_attempts: int = 5) -> Tuple[List[str], List[str]]:
        """
        Drop tables with retry logic for dependency resolution.

        Args:
            tables: List of table names to drop
            max_attempts: Maximum number of retry attempts

        Returns:
            Tuple of (successfully_dropped, failed_to_drop) table lists
        """
        successfully_dropped = []

        with self.get_connection() as conn:
            attempt = 0
            tables_to_retry = tables.copy()

            while tables_to_retry and attempt < max_attempts:
                attempt += 1
                failed_this_round = []

                logger.debug(f"Drop attempt {attempt}: trying to drop {len(tables_to_retry)} tables")

                for table in tables_to_retry:
                    try:
                        drop_query = f"DROP TABLE IF EXISTS {self.schema_name}.{table} CASCADE"
                        conn.execute(drop_query)
                        successfully_dropped.append(table)
                        logger.debug(f"Dropped table {table}")
                    except Exception as e:
                        if "is main key table" in str(e) or "depends on" in str(e):
                            failed_this_round.append(table)
                            logger.debug(f"Table {table} has dependencies, will retry")
                        else:
                            logger.error(f"Failed to drop {table}: {e}")
                            failed_this_round.append(table)

                tables_to_retry = failed_this_round

        logger.info(f"Successfully dropped {len(successfully_dropped)} tables, {len(tables_to_retry)} failed")
        return successfully_dropped, tables_to_retry

    def clear_tables(self, patterns: Optional[List[str]] = None) -> ClearTablesResult:
        """
        Clear tables from the database based on patterns.

        Args:
            patterns: List of patterns to match table names (e.g., ["stg_", "int_"])
                     If None, uses configuration defaults

        Returns:
            ClearTablesResult with operation details
        """
        if patterns is None:
            patterns = self.config.setup.clear_table_patterns

        logger.info(f"Starting table clearing with patterns: {patterns}")

        # Get all tables
        all_tables = self.list_tables()

        if not all_tables:
            logger.info("No tables found in database")
            return ClearTablesResult([], [], [], 0)

        # Filter tables by patterns
        tables_to_drop = []
        for table in all_tables:
            if any(pattern in table for pattern in patterns):
                tables_to_drop.append(table)

        if not tables_to_drop:
            logger.info(f"No tables found matching patterns: {patterns}")
            return ClearTablesResult([], [], all_tables, 0)

        logger.info(f"Found {len(tables_to_drop)} tables to drop out of {len(all_tables)} total")

        # Drop foreign key constraints first
        logger.info("Dropping foreign key constraints...")
        dropped_constraints = self.drop_foreign_key_constraints()

        # Drop tables with retry logic
        logger.info("Dropping tables...")
        successfully_dropped, failed_tables = self.drop_tables_with_retry(tables_to_drop)

        # Get remaining tables for verification
        remaining_tables = self.list_tables()

        result = ClearTablesResult(
            successfully_dropped=successfully_dropped,
            failed_to_drop=failed_tables,
            remaining_tables=remaining_tables,
            constraints_dropped=len(dropped_constraints)
        )

        if failed_tables:
            logger.warning(f"Failed to drop {len(failed_tables)} tables: {failed_tables}")
        else:
            logger.info("All targeted tables dropped successfully")

        return result

    def validate_database_state(self) -> DatabaseStateValidation:
        """
        Validate the current state of the database.

        Returns:
            DatabaseStateValidation with validation results
        """
        logger.info("Validating database state...")

        validation = DatabaseStateValidation()

        try:
            # Check database accessibility
            with self.get_connection(read_only=True) as conn:
                conn.execute("SELECT 1")
                validation.database_accessible = True

                # Check for required tables
                required_tables = self.config.validation.required_seed_tables
                existing_tables = self.list_tables()

                validation.required_tables_present = all(
                    table in existing_tables for table in required_tables
                )
                validation.missing_tables = [
                    table for table in required_tables
                    if table not in existing_tables
                ]

                # Get table statistics
                validation.total_tables = len(existing_tables)
                validation.staging_tables = len([t for t in existing_tables if t.startswith("stg_")])
                validation.intermediate_tables = len([t for t in existing_tables if t.startswith("int_")])
                validation.fact_tables = len([t for t in existing_tables if t.startswith("fct_")])

        except Exception as e:
            logger.error(f"Database state validation failed: {e}")
            validation.database_accessible = False
            validation.validation_error = str(e)

        validation.is_valid = (
            validation.database_accessible and
            validation.required_tables_present
        )

        logger.info(f"Database state validation: {'PASSED' if validation.is_valid else 'FAILED'}")
        return validation


# Exception classes
class DatabaseError(Exception):
    """Base exception for database operations."""
    pass


class DatabaseLockError(DatabaseError):
    """Exception raised when database is locked by another process."""
    pass


class TableNotFoundError(DatabaseError):
    """Exception raised when a table is not found."""
    pass


# Result classes
class ClearTablesResult:
    """Result of table clearing operation."""

    def __init__(
        self,
        successfully_dropped: List[str],
        failed_to_drop: List[str],
        remaining_tables: List[str],
        constraints_dropped: int
    ):
        self.successfully_dropped = successfully_dropped
        self.failed_to_drop = failed_to_drop
        self.remaining_tables = remaining_tables
        self.constraints_dropped = constraints_dropped

        self.success = len(failed_to_drop) == 0
        self.total_dropped = len(successfully_dropped)
        self.total_failed = len(failed_to_drop)

    def __repr__(self) -> str:
        return (
            f"ClearTablesResult("
            f"dropped={self.total_dropped}, "
            f"failed={self.total_failed}, "
            f"remaining={len(self.remaining_tables)}, "
            f"constraints_dropped={self.constraints_dropped}"
            f")"
        )


class DatabaseStateValidation:
    """Result of database state validation."""

    def __init__(self):
        self.database_accessible: bool = False
        self.required_tables_present: bool = False
        self.missing_tables: List[str] = []
        self.total_tables: int = 0
        self.staging_tables: int = 0
        self.intermediate_tables: int = 0
        self.fact_tables: int = 0
        self.is_valid: bool = False
        self.validation_error: Optional[str] = None

    def __repr__(self) -> str:
        return (
            f"DatabaseStateValidation("
            f"valid={self.is_valid}, "
            f"accessible={self.database_accessible}, "
            f"required_tables={self.required_tables_present}, "
            f"total_tables={self.total_tables}"
            f")"
        )
