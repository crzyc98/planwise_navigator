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
        "fct_yearly_events",
        "fct_workforce_snapshot",
        "fct_employer_match_events",
    ]

    # Default table prefixes to clear (intermediate and fact tables)
    DEFAULT_CLEAR_PATTERNS = ["int_", "fct_"]

    # Table prefixes to preserve (seeds and staging data)
    PRESERVE_PATTERNS = ["seed_", "stg_"]

    def __init__(
        self,
        db_manager: DatabaseConnectionManager,
        verbose: bool = False
    ):
        """Initialize DataCleanupManager with database connection manager.

        Args:
            db_manager: Database connection manager for executing cleanup operations
            verbose: Enable verbose logging for cleanup operations
        """
        self.db_manager = db_manager
        self.verbose = verbose

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
                    result = conn.execute(
                        f"DELETE FROM {table} WHERE simulation_year = ?",
                        [year]
                    )
                    # Get row count if available
                    if hasattr(result, 'fetchone'):
                        row_count = result.fetchone()
                        if row_count and self.verbose:
                            print(f"  ✓ Cleared {row_count[0]} rows from {table}")
                    cleared_count += 1
                except Exception:
                    # Table may not exist yet; silently continue
                    pass
            return cleared_count

        try:
            cleared = self.db_manager.execute_with_retry(_run)
            if cleared and self.verbose:
                print(f"🧹 Cleared year {year} rows from {cleared} fact table(s)")
        except Exception as e:
            # Non-fatal error; log but continue
            if self.verbose:
                print(f"⚠️  Warning: Error clearing year {year} fact rows: {e}")

    def clear_year_data(
        self,
        year: int,
        table_patterns: List[str] | None = None
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
                    rows_deleted = conn.execute(
                        f"DELETE FROM {table} WHERE simulation_year = ?",
                        [year]
                    ).fetchone()
                    cleared += 1
                    if self.verbose and rows_deleted:
                        print(f"  ✓ Cleared {rows_deleted[0]} rows from {table}")

            return cleared

        cleared = self.db_manager.execute_with_retry(_run)
        if cleared and self.verbose:
            print(
                f"🧹 Cleared year {year} data from {cleared} table(s) "
                f"matching patterns: {patterns}"
            )

    def full_reset(
        self,
        table_patterns: List[str] | None = None
    ) -> None:
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
                    if hasattr(result, 'fetchone'):
                        row_count = result.fetchone()
                        if row_count and self.verbose:
                            print(f"  ✓ Cleared all rows from {table}")
                    cleared += 1
                except Exception as e:
                    # Log error but continue with other tables
                    if self.verbose:
                        print(f"⚠️  Warning: Could not clear {table}: {e}")

            return cleared

        cleared = self.db_manager.execute_with_retry(_run)
        if cleared and self.verbose:
            print(
                f"🧹 Full reset: cleared all rows from {cleared} table(s) "
                f"matching patterns: {patterns}"
            )

    def should_clear_table(
        self,
        table_name: str,
        patterns: List[str] | None = None
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

    def get_clearable_tables(
        self,
        patterns: List[str] | None = None
    ) -> List[str]:
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

    def drop_seed_tables_with_schema_mismatch(
        self,
        seeds_dir: Path | None = None
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
            # Default to dbt/seeds relative to project root
            project_root = Path(__file__).parent.parent.parent
            seeds_dir = project_root / "dbt" / "seeds"

        if not seeds_dir.exists():
            logger.warning(f"Seeds directory not found: {seeds_dir}")
            return []

        dropped_tables: List[str] = []

        def _run(conn):
            nonlocal dropped_tables

            # Get all existing tables
            existing_tables = {
                row[0]: row[0]
                for row in conn.execute(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'main'
                    """
                ).fetchall()
            }

            # Check each CSV file in seeds directory
            for csv_path in seeds_dir.glob("*.csv"):
                table_name = csv_path.stem  # e.g., config_irs_limits

                if table_name not in existing_tables:
                    continue  # Table doesn't exist, will be created fresh

                # Get CSV headers
                try:
                    with open(csv_path, 'r', encoding='utf-8', newline='') as f:
                        reader = csv.reader(f)
                        csv_headers = set(next(reader))
                except Exception as e:
                    logger.warning(f"Could not read CSV headers from {csv_path}: {e}")
                    continue

                # Get table columns
                try:
                    table_columns = {
                        row[0]
                        for row in conn.execute(
                            """
                            SELECT column_name
                            FROM information_schema.columns
                            WHERE table_schema = 'main' AND table_name = ?
                            """,
                            [table_name]
                        ).fetchall()
                    }
                except Exception as e:
                    logger.warning(f"Could not get columns for table {table_name}: {e}")
                    continue

                # Check for schema mismatch (missing columns in table)
                missing_columns = csv_headers - table_columns
                if missing_columns:
                    logger.info(
                        f"Schema mismatch for {table_name}: "
                        f"CSV has columns {missing_columns} not in table. Dropping table."
                    )
                    if self.verbose:
                        print(
                            f"  🔄 Dropping {table_name} - schema mismatch "
                            f"(missing: {', '.join(sorted(missing_columns))})"
                        )

                    try:
                        conn.execute(f"DROP TABLE IF EXISTS {table_name}")
                        dropped_tables.append(table_name)
                    except Exception as e:
                        logger.error(f"Failed to drop table {table_name}: {e}")

            return dropped_tables

        self.db_manager.execute_with_retry(_run)

        if dropped_tables and self.verbose:
            print(
                f"🧹 Dropped {len(dropped_tables)} seed table(s) with schema mismatch: "
                f"{', '.join(dropped_tables)}"
            )

        return dropped_tables
