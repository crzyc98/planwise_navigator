"""Database cleanup utilities for simulation year-range management."""

import logging
from pathlib import Path

import duckdb

logger = logging.getLogger(__name__)

# Tables known to contain simulation_year data
TABLES_WITH_YEAR = [
    "fct_workforce_snapshot",
    "fct_yearly_events",
    "int_enrollment_state_accumulator",
    "int_deferral_rate_state_accumulator",
    "int_baseline_workforce",
    "int_employee_compensation_by_year",
    "int_employee_state_by_year",
    "int_workforce_snapshot_optimized",
]


def cleanup_years_outside_range(
    db_path: Path, start_year: int, end_year: int
) -> dict[str, int]:
    """
    Delete simulation data from years outside the configured range.

    This ensures that when a user reconfigures a scenario to a different
    year range, stale data from previous runs is removed.

    Args:
        db_path: Path to the DuckDB database file.
        start_year: First year to keep (inclusive).
        end_year: Last year to keep (inclusive).

    Returns:
        Dict mapping table name to number of deleted rows (only tables with deletions).
    """
    try:
        with duckdb.connect(str(db_path)) as conn:
            deleted_counts = _delete_outside_range(conn, start_year, end_year)

        if deleted_counts:
            logger.info(
                f"Cleaned up data outside year range {start_year}-{end_year}: "
                f"{deleted_counts}"
            )
        else:
            logger.debug(
                f"No stale data found outside year range {start_year}-{end_year}"
            )

    except (duckdb.Error, OSError):
        logger.exception("Failed to cleanup years outside range")
        return {}

    return deleted_counts


def _delete_outside_range(
    conn: duckdb.DuckDBPyConnection, start_year: int, end_year: int
) -> dict[str, int]:
    deleted_counts: dict[str, int] = {}
    conn.execute("BEGIN TRANSACTION")
    try:
        existing_tables = {row[0] for row in conn.execute("SHOW TABLES").fetchall()}
        for table in TABLES_WITH_YEAR:
            if table not in existing_tables:
                continue
            try:
                columns = {
                    row[0] for row in conn.execute(f"DESCRIBE {table}").fetchall()
                }
            except duckdb.CatalogException:
                logger.debug("Cleanup table %s disappeared", table)
                continue
            if "simulation_year" not in columns:
                continue
            deleted = conn.execute(
                f"DELETE FROM {table} WHERE simulation_year < ? OR simulation_year > ?",
                [start_year, end_year],
            ).fetchone()
            if deleted and deleted[0] > 0:
                deleted_counts[table] = deleted[0]
        conn.execute("COMMIT")
    except duckdb.Error:
        conn.execute("ROLLBACK")
        raise
    return deleted_counts
