"""
Table Existence Checker for Self-Healing dbt Initialization.

Provides functionality to check if required database tables exist,
enabling automatic detection of when initialization is needed.

Usage:
    from planalign_orchestrator.self_healing import TableExistenceChecker
    from planalign_orchestrator.utils import DatabaseConnectionManager

    db_manager = DatabaseConnectionManager(db_path)
    checker = TableExistenceChecker(db_manager)

    if not checker.is_initialized():
        missing = checker.get_missing_tables()
        print(f"Missing {len(missing)} tables")
"""

from __future__ import annotations

from typing import Dict, List, Set

from planalign_orchestrator.self_healing.initialization_state import (
    RequiredTable,
    TableTier,
    REQUIRED_TABLES,
)
from planalign_orchestrator.utils import DatabaseConnectionManager


class TableExistenceChecker:
    """Checks for existence of required database tables.

    Uses the DatabaseConnectionManager to query the database and compare
    existing tables against the REQUIRED_TABLES registry.

    Attributes:
        db_manager: Database connection manager for queries

    Example:
        >>> checker = TableExistenceChecker(db_manager)
        >>> if not checker.is_initialized():
        ...     missing = checker.get_missing_tables()
        ...     for table in missing:
        ...         print(f"Missing: {table.name} ({table.tier.value})")
    """

    def __init__(self, db_manager: DatabaseConnectionManager) -> None:
        """Initialize checker with database connection manager.

        Args:
            db_manager: Connection manager for database access
        """
        self.db_manager = db_manager

    def get_existing_tables(self) -> Set[str]:
        """Query database for all existing table names.

        Returns:
            Set of table names in the 'main' schema

        Raises:
            DatabaseError: If database query fails

        Note:
            Uses information_schema.tables to list tables.
            Only returns tables from the 'main' schema.
        """
        def _query(conn):
            result = conn.execute("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'main'
                ORDER BY table_name
            """).fetchall()
            return {row[0] for row in result}

        return self.db_manager.execute_with_retry(_query)

    def get_missing_tables(self) -> List[RequiredTable]:
        """Compare required tables against existing tables.

        Returns:
            List of RequiredTable objects that don't exist in database

        Note:
            Uses REQUIRED_TABLES constant for comparison.
            Maintains original order from REQUIRED_TABLES.
        """
        existing = self.get_existing_tables()
        return [
            table for table in REQUIRED_TABLES
            if table.name not in existing
        ]

    def is_initialized(self) -> bool:
        """Check if all required tables exist.

        Returns:
            True if all REQUIRED_TABLES exist, False otherwise

        Note:
            This is a quick check - returns False as soon as
            any required table is found missing.
        """
        existing = self.get_existing_tables()
        return all(
            table.name in existing
            for table in REQUIRED_TABLES
        )

    def get_missing_by_tier(self) -> Dict[TableTier, List[RequiredTable]]:
        """Group missing tables by their initialization tier.

        Returns:
            Dict mapping TableTier to list of missing RequiredTable objects.
            Empty dict if no tables missing.

        Example:
            >>> missing_by_tier = checker.get_missing_by_tier()
            >>> if TableTier.SEED in missing_by_tier:
            ...     print(f"Missing {len(missing_by_tier[TableTier.SEED])} seed tables")
        """
        missing = self.get_missing_tables()
        if not missing:
            return {}

        result: Dict[TableTier, List[RequiredTable]] = {}
        for table in missing:
            if table.tier not in result:
                result[table.tier] = []
            result[table.tier].append(table)

        return result

    def get_initialization_summary(self) -> str:
        """Get a human-readable summary of initialization status.

        Returns:
            Summary string describing what tables exist and what's missing

        Example:
            >>> print(checker.get_initialization_summary())
            "Database initialized: 8/8 required tables exist"
        """
        existing = self.get_existing_tables()
        total = len(REQUIRED_TABLES)
        present = sum(1 for t in REQUIRED_TABLES if t.name in existing)

        if present == total:
            return f"Database initialized: {present}/{total} required tables exist"

        missing_by_tier = self.get_missing_by_tier()
        parts = [f"Database needs initialization: {present}/{total} tables exist"]

        for tier in [TableTier.SEED, TableTier.FOUNDATION]:
            if tier in missing_by_tier:
                tables = missing_by_tier[tier]
                names = ", ".join(t.name for t in tables)
                parts.append(f"  Missing {tier.value}: {names}")

        return "\n".join(parts)
