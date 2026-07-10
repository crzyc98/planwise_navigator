#!/usr/bin/env python3
"""
Data Cleanup Module

Provides centralized database cleanup operations for the PlanWise Navigator pipeline.
Supports year-specific cleanup, full database reset, and selective table clearing with
intelligent filtering to preserve seed data and configuration tables.

This module enables idempotent re-runs by removing stale data while preserving
essential baseline tables like seeds and staging data.
"""

from __future__ import annotations

import csv
import logging
from pathlib import Path
from typing import List, Set

from planalign_core.constants import (
    TABLE_FCT_WORKFORCE_SNAPSHOT,
    TABLE_FCT_YEARLY_EVENTS,
)
from planalign_orchestrator.utils import DatabaseConnectionManager

logger = logging.getLogger(__name__)


class DataCleanupManager:
    """Manages database cleanup operations with selective table filtering.

    Provides robust cleanup operations for:
    - Year-specific fact table cleanup for idempotent re-runs
    - Full year data removal including intermediate tables
    - Complete database reset while preserving seed tables
    - Intelligent table filtering based on configurable patterns

    The cleanup manager ensures data consistency during re-runs by removing
    stale computed data while preserving source data and configuration.

    Example:
        >>> from planalign_orchestrator.config import get_database_path
        >>> from planalign_orchestrator.utils import DatabaseConnectionManager
        >>> db_manager = DatabaseConnectionManager(get_database_path())
        >>> cleanup = DataCleanupManager(db_manager, verbose=True)
        >>> cleanup.clear_year_fact_rows(2025)  # Clear 2025 from fact tables
        >>> cleanup.clear_year_data(2025)       # Clear all 2025 data
        >>> cleanup.full_reset()                # Complete database reset
    """

    # Core fact tables that require year-specific cleanup for idempotency
    FACT_TABLES = [
        TABLE_FCT_YEARLY_EVENTS,
        TABLE_FCT_WORKFORCE_SNAPSHOT,
        "fct_employer_match_events",
    ]

    # Default table prefixes to clear (intermediate and fact tables)
    DEFAULT_CLEAR_PATTERNS = ["int_", "fct_"]

    # Table prefixes to preserve (seeds and staging data)
    PRESERVE_PATTERNS = ["seed_", "stg_"]

    def __init__(
        self,
        db_manager: DatabaseConnectionManager,
        verbose: bool = False,
        scenario_id: str | None = None,
        plan_design_id: str | None = None,
    ):
        """Initialize DataCleanupManager with database connection manager.

        Args:
            db_manager: Database connection manager for executing cleanup operations
            verbose: Enable verbose logging for cleanup operations
            scenario_id: Active scenario identifier for scoped cleanup
            plan_design_id: Active plan design identifier for scoped cleanup
        """
        self.db_manager = db_manager
        self.verbose = verbose
        self.scenario_id = scenario_id
        self.plan_design_id = plan_design_id

    def _year_scope(
        self, conn, table: str, year: int, *, critical: bool = False
    ) -> tuple[str, list[object]]:
        """Build a year filter scoped to the active scenario when supported.

        Falls back to ``"default"`` for unset scenario_id/plan_design_id, matching
        the same fallback dbt uses (``{{ var('scenario_id', 'default') }}``, see
        ``dbt/models/marts/fct_yearly_events.sql``) and the CLI export path
        (``planalign_orchestrator/config/export.py``). This keeps ordinary
        single-scenario runs (no explicit scenario_id) scoped consistently with
        what was actually written to the table, instead of treating the common
        case as "identifiers unavailable".
        """
        columns = {
            row[0]
            for row in conn.execute(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_schema = 'main' AND table_name = ?
                """,
                [table],
            ).fetchall()
        }
        scenario_id = self.scenario_id or "default"
        plan_design_id = self.plan_design_id or "default"

        predicates = ["simulation_year = ?"]
        parameters: list[object] = [year]
        has_scenario_column = "scenario_id" in columns
        has_plan_design_column = "plan_design_id" in columns
        if has_scenario_column:
            predicates.append("scenario_id = ?")
            parameters.append(scenario_id)
        if has_plan_design_column:
            predicates.append("plan_design_id = ?")
            parameters.append(plan_design_id)

        if critical and not (has_scenario_column and has_plan_design_column):
            logger.warning(
                "%s has no scenario_id/plan_design_id columns; year-only cleanup "
                "for simulation_year=%s may remove rows belonging to other "
                "scenarios/plan designs sharing this database. Schema migration "
                "is required to fully scope this table.",
                table,
                year,
            )

        return " AND ".join(predicates), parameters

    def _delete_year_rows(
        self, conn, table: str, year: int, *, critical: bool = False
    ) -> bool:
        """Delete year rows when the target table exists."""
        table_exists = conn.execute(
            """
            SELECT 1
            FROM information_schema.tables
            WHERE table_schema = 'main' AND table_name = ?
            LIMIT 1
            """,
            [table],
        ).fetchone()
        if not table_exists:
            return False

        where_clause, parameters = self._year_scope(
            conn, table, year, critical=critical
        )
        conn.execute(f"DELETE FROM {table} WHERE {where_clause}", parameters)
        return True

    def clear_year_fact_rows(self, year: int) -> None:
        """Clear current-year rows from core fact tables for idempotent re-runs.

        This operation removes data from the core fact tables (fct_yearly_events,
        fct_workforce_snapshot, fct_employer_match_events) for the specified year.
        It prevents duplicate events/snapshots when event sequencing changes between runs.

        Args:
            year: Simulation year to clear from fact tables

        Notes:
            - Only clears from FACT_TABLES list (see class constant)
            - Silently handles missing tables (table may not exist yet)
            - Uses transactional execution with retry logic
            - Essential for deterministic re-runs of event generation
        """

        def _run(conn):
            cleared_count = 0
            for table in self.FACT_TABLES:
                try:
                    table_cleared = self._delete_year_rows(
                        conn,
                        table,
                        year,
                        critical=table
                        in (TABLE_FCT_YEARLY_EVENTS, TABLE_FCT_WORKFORCE_SNAPSHOT),
                    )
                    if table_cleared:
                        cleared_count += 1
                except Exception:
                    # Table may not exist yet; silently continue
                    pass
            return cleared_count

        try:
            cleared = self.db_manager.execute_with_retry(_run)
            if cleared and self.verbose:
                logger.info("Cleared year %d rows from %d fact table(s)", year, cleared)
        except Exception as e:
            # Non-fatal error; log but continue
            if self.verbose:
                logger.warning("Error clearing year %d fact rows: %s", year, e)

    def clear_year_data(
        self, year: int, table_patterns: List[str] | None = None
    ) -> None:
        """Clear all data for a specific year from matching tables.

        Removes all rows with the specified simulation_year from tables matching
        the configured patterns (default: int_* and fct_* tables). This is more
        comprehensive than clear_year_fact_rows() and removes intermediate data.

        Args:
            year: Simulation year to clear
            table_patterns: List of table prefixes to clear (default: DEFAULT_CLEAR_PATTERNS)

        Notes:
            - Only clears tables with simulation_year column
            - Preserves seed and staging tables
            - Uses transactional execution for consistency
            - Controlled by setup.clear_tables configuration
        """
        patterns = table_patterns or self.DEFAULT_CLEAR_PATTERNS

        def _run(conn):
            # Get all tables in the database
            tables = [
                r[0]
                for r in conn.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'main'
                    ORDER BY table_name
                    """
                ).fetchall()
            ]

            cleared = 0
            for table in tables:
                # Check if table should be cleared
                if not self.should_clear_table(table, patterns):
                    continue

                # Check if table has simulation_year column
                has_year_col = conn.execute(
                    """
                    SELECT 1 FROM information_schema.columns
                    WHERE table_schema='main'
                      AND table_name = ?
                      AND column_name = 'simulation_year'
                    LIMIT 1
                    """,
                    [table],
                ).fetchone()

                if has_year_col:
                    if self._delete_year_rows(
                        conn,
                        table,
                        year,
                        critical=table
                        in (TABLE_FCT_YEARLY_EVENTS, TABLE_FCT_WORKFORCE_SNAPSHOT),
                    ):
                        cleared += 1

            return cleared

        cleared = self.db_manager.execute_with_retry(_run)
        if cleared and self.verbose:
            logger.info(
                "Cleared year %d data from %d table(s) matching patterns: %s",
                year,
                cleared,
                patterns,
            )

    def full_reset(self, table_patterns: List[str] | None = None) -> None:
        """Clear all rows from matching tables for complete database reset.

        Performs a comprehensive reset by removing all data from tables matching
        the configured patterns. Preserves seed tables and staging data to allow
        rebuilding the simulation from scratch.

        Args:
            table_patterns: List of table prefixes to clear (default: DEFAULT_CLEAR_PATTERNS)

        Notes:
            - Only clears BASE TABLE types (not views)
            - Preserves seed_ and stg_ tables
            - Uses transactional execution for consistency
            - Controlled by setup.clear_mode='all' configuration
            - Useful for clean simulation reruns and testing
        """
        patterns = table_patterns or self.DEFAULT_CLEAR_PATTERNS

        def _run(conn):
            # Get all base tables (exclude views)
            tables = [
                r[0]
                for r in conn.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                    """
                ).fetchall()
            ]

            cleared = 0
            for table in tables:
                # Check if table should be cleared
                if not self.should_clear_table(table, patterns):
                    continue

                try:
                    result = conn.execute(f"DELETE FROM {table}")
                    # Get row count if available
                    if hasattr(result, "fetchone"):
                        row_count = result.fetchone()
                        if row_count and self.verbose:
                            logger.info("Cleared all rows from %s", table)
                    cleared += 1
                except Exception as e:
                    # Log error but continue with other tables
                    if self.verbose:
                        logger.warning("Could not clear %s: %s", table, e)

            return cleared

        cleared = self.db_manager.execute_with_retry(_run)
        if cleared and self.verbose:
            logger.info(
                "Full reset: cleared all rows from %d table(s) matching patterns: %s",
                cleared,
                patterns,
            )

    def should_clear_table(
        self, table_name: str, patterns: List[str] | None = None
    ) -> bool:
        """Determine if a table should be cleared based on name patterns.

        Applies intelligent filtering to decide if a table should be included
        in cleanup operations. Tables are cleared if they match the specified
        patterns AND do not match any preserve patterns.

        Args:
            table_name: Name of the table to check
            patterns: List of prefixes to match for clearing (default: DEFAULT_CLEAR_PATTERNS)

        Returns:
            True if table should be cleared, False otherwise

        Notes:
            - Preserves seed tables (seed_*) and staging tables (stg_*)
            - Matches tables starting with specified patterns (int_*, fct_*)
            - Case-sensitive prefix matching
        """
        patterns = patterns or self.DEFAULT_CLEAR_PATTERNS

        # Check if table matches preserve patterns (never clear these)
        for preserve_pattern in self.PRESERVE_PATTERNS:
            if table_name.startswith(preserve_pattern):
                return False

        # Check if table matches clear patterns
        for pattern in patterns:
            if table_name.startswith(pattern):
                return True

        return False

    def get_clearable_tables(self, patterns: List[str] | None = None) -> List[str]:
        """Get list of tables that would be cleared by cleanup operations.

        Useful for previewing cleanup operations before execution or for
        validation and testing purposes.

        Args:
            patterns: List of prefixes to match (default: DEFAULT_CLEAR_PATTERNS)

        Returns:
            List of table names that match clear patterns

        Example:
            >>> cleanup.get_clearable_tables()
            ['int_baseline_workforce', 'fct_yearly_events', 'fct_workforce_snapshot']
        """
        patterns = patterns or self.DEFAULT_CLEAR_PATTERNS

        def _run(conn):
            tables = [
                r[0]
                for r in conn.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'main' AND table_type = 'BASE TABLE'
                    ORDER BY table_name
                    """
                ).fetchall()
            ]
            return [t for t in tables if self.should_clear_table(t, patterns)]

        return self.db_manager.execute_with_retry(_run)

    def _get_csv_headers(self, csv_path: Path) -> Set[str] | None:
        """Read CSV headers from a seed file.

        Returns:
            Set of column names, or None if the file could not be read.
        """
        try:
            with open(csv_path, "r", encoding="utf-8", newline="") as f:
                reader = csv.reader(f)
                return set(next(reader))
        except Exception as e:
            logger.warning(f"Could not read CSV headers from {csv_path}: {e}")
            return None

    def _get_table_columns(self, conn, table_name: str) -> Set[str] | None:
        """Get column names for a table from the database.

        Returns:
            Set of column names, or None if the query failed.
        """
        try:
            return {
                row[0]
                for row in conn.execute(
                    """
                    SELECT column_name
                    FROM information_schema.columns
                    WHERE table_schema = 'main' AND table_name = ?
                    """,
                    [table_name],
                ).fetchall()
            }
        except Exception as e:
            logger.warning(f"Could not get columns for table {table_name}: {e}")
            return None

    def _check_and_drop_mismatched_table(
        self, conn, csv_path: Path, table_name: str
    ) -> bool:
        """Compare CSV headers to table columns and drop if mismatched.

        Returns:
            True if the table was dropped, False otherwise.
        """
        csv_headers = self._get_csv_headers(csv_path)
        if csv_headers is None:
            return False

        table_columns = self._get_table_columns(conn, table_name)
        if table_columns is None:
            return False

        missing_columns = csv_headers - table_columns
        if not missing_columns:
            return False

        logger.info(
            f"Schema mismatch for {table_name}: "
            f"CSV has columns {missing_columns} not in table. Dropping table."
        )
        if self.verbose:
            logger.debug(
                "Dropping %s - schema mismatch (missing: %s)",
                table_name,
                ", ".join(sorted(missing_columns)),
            )

        try:
            conn.execute(f"DROP TABLE IF EXISTS {table_name}")
            return True
        except Exception as e:
            logger.error(f"Failed to drop table {table_name}: {e}")
            return False

    def drop_seed_tables_with_schema_mismatch(
        self, seeds_dir: Path | None = None
    ) -> List[str]:
        """Drop seed tables whose schema doesn't match the CSV headers.

        This prevents DuckDB CSV sniffing errors when seed files gain new columns.
        The table will be recreated with the correct schema by `dbt seed --full-refresh`.

        Args:
            seeds_dir: Path to dbt seeds directory. If None, uses default location.

        Returns:
            List of table names that were dropped due to schema mismatch.

        Example:
            >>> dropped = cleanup.drop_seed_tables_with_schema_mismatch()
            >>> if dropped:
            ...     print(f"Dropped {len(dropped)} tables with outdated schema")
        """
        if seeds_dir is None:
            project_root = Path(__file__).parent.parent.parent
            seeds_dir = project_root / "dbt" / "seeds"

        if not seeds_dir.exists():
            logger.warning(f"Seeds directory not found: {seeds_dir}")
            return []

        dropped_tables: List[str] = []

        def _run(conn):
            nonlocal dropped_tables

            existing_tables = {
                row[0]
                for row in conn.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'main'
                    """
                ).fetchall()
            }

            for csv_path in seeds_dir.glob("*.csv"):
                table_name = csv_path.stem
                if table_name not in existing_tables:
                    continue

                if self._check_and_drop_mismatched_table(conn, csv_path, table_name):
                    dropped_tables.append(table_name)

            return dropped_tables

        self.db_manager.execute_with_retry(_run)

        if dropped_tables and self.verbose:
            logger.info(
                "Dropped %d seed table(s) with schema mismatch: %s",
                len(dropped_tables),
                ", ".join(dropped_tables),
            )

        return dropped_tables
