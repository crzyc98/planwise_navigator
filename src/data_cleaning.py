"""
Data Cleaning and Preparation Functions

This module contains pure business logic functions for data cleaning, preparation,
and standardization. These functions handle core data quality operations that are
independent of the Dagster orchestration framework.

Functions:
    clean_duckdb_data: Remove simulation data for specified years
    clean_orphaned_data_outside_range: Clean data outside simulation range
"""

from typing import Dict, List
import duckdb
from pathlib import Path
from dagster import OpExecutionContext

# Database path configuration
PROJECT_ROOT = Path(__file__).parent.parent
DB_PATH = PROJECT_ROOT / "simulation.duckdb"


def clean_duckdb_data(context: OpExecutionContext, years: List[int]) -> Dict[str, int]:
    """
    Clean simulation data for specified years.

    Removes existing simulation data from fct_yearly_events and fct_workforce_snapshot
    tables for the specified years to ensure fresh start for simulation runs.

    Args:
        context: Dagster operation execution context
        years: List of simulation years to clean (e.g., [2025, 2026, 2027])

    Returns:
        Dict containing counts of deleted records per table

    Examples:
        Clean single year:
        >>> clean_duckdb_data(context, [2025])

        Clean multiple years:
        >>> clean_duckdb_data(context, [2025, 2026, 2027])
    """
    if not years:
        context.log.info("No years specified for cleaning")
        return {"fct_yearly_events": 0, "fct_workforce_snapshot": 0}

    results = {"fct_yearly_events": 0, "fct_workforce_snapshot": 0}

    year_range = f"{min(years)}-{max(years)}" if len(years) > 1 else str(years[0])
    context.log.info(f"Cleaning existing data for years {year_range}")

    conn = duckdb.connect(str(DB_PATH))

    try:
        # Clean yearly events for all specified years
        for year in years:
            try:
                # Execute DELETE operation
                conn.execute(
                    "DELETE FROM fct_yearly_events WHERE simulation_year = ?", [year]
                )
                # Note: DuckDB doesn't always return rowcount for DELETE operations
                # We'll count this as successful deletion
                results["fct_yearly_events"] += 1  # Count per year cleaned
            except Exception as e:
                context.log.warning(f"Error cleaning events for year {year}: {e}")

        # Clean workforce snapshots for all specified years
        for year in years:
            try:
                # Execute delete without assigning to unused cursor
                conn.execute(
                    "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?",
                    [year],
                )
                results["fct_workforce_snapshot"] += 1  # Count per year cleaned
            except Exception as e:
                context.log.warning(
                    f"Error cleaning workforce snapshot for year {year}: {e}"
                )
                # Don't fail the operation if table doesn't exist yet

        context.log.info(
            f"Cleaned simulation data for {len(years)} years: "
            f"events cleaned for {results['fct_yearly_events']} years, "
            f"snapshots cleaned for {results['fct_workforce_snapshot']} years"
        )

        # VERIFICATION: Check that we didn't accidentally delete data from other years
        if len(years) == 1 and years[0] > 2025:
            prev_year = years[0] - 1
            remaining_prev_count = conn.execute(
                "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ? AND employment_status = 'active'",
                [prev_year]
            ).fetchone()[0]
            context.log.info(f"✅ Verification: Year {prev_year} still has {remaining_prev_count} active employees after cleaning year {years[0]}")

    except Exception as e:
        context.log.warning(f"Error during data cleaning: {e}")
        # Don't re-raise - allow pipeline to continue with best effort
    finally:
        conn.close()

    return results


def clean_orphaned_data_outside_range(context: OpExecutionContext, simulation_range: List[int]) -> Dict[str, int]:
    """
    Clean orphaned simulation data OUTSIDE the specified year range.

    Provides a clean analyst experience by removing data from previous simulation runs
    that fall outside the current simulation range, while preserving year-to-year
    dependencies within the range.

    Args:
        context: Dagster operation execution context
        simulation_range: List of years in current simulation (e.g., [2025, 2026, 2027])

    Returns:
        Dict containing counts of orphaned records cleaned

    Examples:
        Clean orphaned data outside 2025-2026 range:
        >>> clean_orphaned_data_outside_range(context, [2025, 2026])
        # Removes years < 2025 OR > 2026, preserves 2025-2026 dependencies
    """
    if not simulation_range:
        context.log.info("No simulation range specified - no orphaned data cleanup")
        return {"fct_yearly_events": 0, "fct_workforce_snapshot": 0}

    min_year = min(simulation_range)
    max_year = max(simulation_range)
    range_str = f"{min_year}-{max_year}" if min_year != max_year else str(min_year)

    context.log.info(f"Cleaning orphaned data outside simulation range {range_str}")

    results = {"fct_yearly_events": 0, "fct_workforce_snapshot": 0}
    conn = duckdb.connect(str(DB_PATH))

    try:
        # Clean yearly events OUTSIDE the simulation range
        try:
            orphaned_events = conn.execute(
                "SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year < ? OR simulation_year > ?",
                [min_year, max_year]
            ).fetchone()[0]

            if orphaned_events > 0:
                conn.execute(
                    "DELETE FROM fct_yearly_events WHERE simulation_year < ? OR simulation_year > ?",
                    [min_year, max_year]
                )
                results["fct_yearly_events"] = orphaned_events
                context.log.info(f"Cleaned {orphaned_events} orphaned events outside range {range_str}")
            else:
                context.log.info(f"No orphaned events found outside range {range_str}")
        except Exception as e:
            context.log.warning(f"Error cleaning orphaned events: {e}")

        # Clean workforce snapshots OUTSIDE the simulation range
        try:
            orphaned_snapshots = conn.execute(
                "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year < ? OR simulation_year > ?",
                [min_year, max_year]
            ).fetchone()[0]

            if orphaned_snapshots > 0:
                conn.execute(
                    "DELETE FROM fct_workforce_snapshot WHERE simulation_year < ? OR simulation_year > ?",
                    [min_year, max_year]
                )
                results["fct_workforce_snapshot"] = orphaned_snapshots
                context.log.info(f"Cleaned {orphaned_snapshots} orphaned snapshots outside range {range_str}")
            else:
                context.log.info(f"No orphaned snapshots found outside range {range_str}")
        except Exception as e:
            context.log.warning(f"Error cleaning orphaned snapshots: {e}")

        # Log what we preserved
        kept_events = conn.execute(
            "SELECT COUNT(*) FROM fct_yearly_events WHERE simulation_year BETWEEN ? AND ?",
            [min_year, max_year]
        ).fetchone()[0]
        kept_snapshots = conn.execute(
            "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year BETWEEN ? AND ?",
            [min_year, max_year]
        ).fetchone()[0]

        context.log.info(f"Preserved {kept_events} events and {kept_snapshots} snapshots within range {range_str}")

    except Exception as e:
        context.log.warning(f"Error during orphaned data cleanup: {e}")
    finally:
        conn.close()

    return results
