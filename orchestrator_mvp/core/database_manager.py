"""Database management operations.

Handles database connections, table clearing, and database state management.
"""

import duckdb
from typing import List, Tuple

from .config import DUCKDB_PATH, SCHEMA_NAME


def get_connection() -> duckdb.DuckDBPyConnection:
    """Create a connection to the DuckDB database."""
    if not DUCKDB_PATH.exists():
        raise FileNotFoundError(f"Database file not found at {DUCKDB_PATH}")

    return duckdb.connect(str(DUCKDB_PATH))


def list_tables() -> List[str]:
    """Get a list of all tables in the main schema."""
    conn = get_connection()

    try:
        tables_query = f"""
        SELECT table_name
        FROM information_schema.tables
        WHERE table_schema = '{SCHEMA_NAME}'
        AND table_type = 'BASE TABLE'
        ORDER BY table_name
        """

        tables = conn.execute(tables_query).fetchall()
        return [table[0] for table in tables]

    finally:
        conn.close()


def drop_foreign_key_constraints() -> List[Tuple[str, str]]:
    """Drop all foreign key constraints in the main schema.

    Returns:
        List of (constraint_name, table_name) tuples that were dropped
    """
    conn = get_connection()
    dropped_constraints = []

    try:
        fk_query = f"""
        SELECT DISTINCT constraint_name, table_name
        FROM duckdb_constraints()
        WHERE constraint_type = 'FOREIGN KEY'
        AND table_schema = '{SCHEMA_NAME}'
        """

        constraints = conn.execute(fk_query).fetchall()

        for constraint_name, table_name in constraints:
            try:
                alter_query = f"ALTER TABLE {SCHEMA_NAME}.{table_name} DROP CONSTRAINT {constraint_name}"
                conn.execute(alter_query)
                dropped_constraints.append((constraint_name, table_name))
            except Exception as e:
                print(f"  ⚠️  Could not drop constraint {constraint_name}: {str(e)}")

        return dropped_constraints

    except Exception as e:
        print(f"  ⚠️  Could not query foreign key constraints: {str(e)}")
        return []

    finally:
        conn.close()


def drop_tables_with_retry(tables: List[str], max_attempts: int = 5) -> Tuple[List[str], List[str]]:
    """Drop tables with retry logic for dependency resolution.

    Args:
        tables: List of table names to drop
        max_attempts: Maximum number of retry attempts

    Returns:
        Tuple of (successfully_dropped, failed_to_drop) table lists
    """
    conn = get_connection()
    successfully_dropped = []

    try:
        attempt = 0
        tables_to_retry = tables.copy()

        while tables_to_retry and attempt < max_attempts:
            attempt += 1
            failed_this_round = []

            for table in tables_to_retry:
                try:
                    drop_query = f"DROP TABLE IF EXISTS {SCHEMA_NAME}.{table} CASCADE"
                    conn.execute(drop_query)
                    successfully_dropped.append(table)
                except Exception as e:
                    if "is main key table" in str(e) or "depends on" in str(e):
                        failed_this_round.append(table)
                    else:
                        print(f"  ❌ Failed to drop {table}: {str(e)}")
                        failed_this_round.append(table)

            tables_to_retry = failed_this_round

        return successfully_dropped, tables_to_retry

    finally:
        conn.close()


def clear_database() -> None:
    """Drop all tables from the main schema in DuckDB."""
    print("\n" + "="*60)
    print("CLEARING DATABASE")
    print("="*60)

    # Get list of all tables
    tables = list_tables()

    if not tables:
        print("\nNo tables found in database.")
        return

    print(f"\nFound {len(tables)} tables to drop:")
    for table in tables:
        print(f"  - {table}")

    # Drop foreign key constraints first
    print("\nDropping foreign key constraints...")
    dropped_constraints = drop_foreign_key_constraints()

    if dropped_constraints:
        for constraint_name, table_name in dropped_constraints:
            print(f"  ✓ Dropped foreign key {constraint_name} from {table_name}")
    else:
        print("  ✓ No foreign key constraints found or dropped")

    # Drop tables with retry logic
    print("\nDropping tables...")
    successfully_dropped, failed_tables = drop_tables_with_retry(tables)

    for table in successfully_dropped:
        print(f"  ✓ Dropped {table}")

    # Handle remaining tables
    if failed_tables:
        print(f"\n⚠️  Could not drop {len(failed_tables)} tables:")
        for table in failed_tables:
            print(f"  - {table}")

        # Focus on dbt-managed tables
        dbt_failed_tables = [
            t for t in failed_tables
            if any(prefix in t for prefix in ['stg_', 'int_', 'fct_', 'dim_'])
        ]

        if dbt_failed_tables:
            print(f"\n⚠️  WARNING: {len(dbt_failed_tables)} dbt tables could not be dropped:")
            for table in dbt_failed_tables:
                print(f"  - {table}")
        else:
            print(f"\n✓ All dbt tables cleared! ({len(failed_tables)} non-dbt tables remain)")

    # Final verification
    remaining_tables = list_tables()

    if not remaining_tables:
        print("\n✅ Database completely cleared!")
    else:
        dbt_tables_remaining = [
            t for t in remaining_tables
            if any(prefix in t for prefix in ['stg_', 'int_', 'fct_', 'dim_'])
        ]

        if dbt_tables_remaining:
            print(f"\n⚠️  WARNING: {len(dbt_tables_remaining)} dbt tables still remain:")
            for table in dbt_tables_remaining:
                print(f"  - {table}")
        else:
            print(f"\n✓ All dbt tables cleared! ({len(remaining_tables)} non-dbt tables remain)")
