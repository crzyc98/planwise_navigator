"""
Workforce snapshot generation module for MVP orchestrator.

This module handles the generation of workforce snapshots by running the
fct_workforce_snapshot dbt model and applying all simulation events to
create year-end workforce state.
"""

import duckdb
import pandas as pd
from datetime import datetime
from typing import Dict, Optional, Tuple

from ..core.database_manager import get_connection
from ..loaders.staging_loader import run_dbt_model


def generate_workforce_snapshot(
    simulation_year: int = 2025,
    db_path: str = "simulation.duckdb"
) -> Dict[str, any]:
    """
    Generate workforce snapshot by running fct_workforce_snapshot dbt model.

    Args:
        simulation_year: Year to generate snapshot for
        db_path: Path to the DuckDB database

    Returns:
        Dictionary containing snapshot generation results
    """
    try:
        print(f"\n🔄 Generating workforce snapshot for year {simulation_year}...")

        # Get starting workforce count
        starting_count = get_starting_workforce(db_path)
        print(f"   Starting workforce: {starting_count:,} employees")

        # Run the fct_workforce_snapshot model with simulation year
        print(f"\n   Running fct_workforce_snapshot model...")
        result = apply_events_to_workforce(simulation_year)

        if not result["success"]:
            return {
                "success": False,
                "error": result.get("error", "Failed to run workforce snapshot model")
            }

        # Calculate workforce metrics
        metrics = calculate_workforce_metrics(simulation_year, db_path)

        # Validate workforce continuity
        validation = validate_workforce_continuity(simulation_year, db_path)

        return {
            "success": True,
            "simulation_year": simulation_year,
            "starting_workforce": starting_count,
            "metrics": metrics,
            "validation": validation
        }

    except Exception as e:
        return {
            "success": False,
            "error": f"Error generating workforce snapshot: {str(e)}"
        }


def get_starting_workforce(db_path: str) -> int:
    """
    Get the baseline workforce count from the database.

    Args:
        db_path: Path to the DuckDB database

    Returns:
        Number of active employees at baseline
    """
    conn = get_connection()

    try:
        # Check if int_baseline_workforce exists
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'int_baseline_workforce'"
        ).fetchall()

        if not tables:
            # Fallback to stg_census_data if baseline not yet created
            result = conn.execute(
                "SELECT COUNT(*) as count FROM stg_census_data WHERE status = 'Active'"
            ).fetchone()
        else:
            result = conn.execute(
                "SELECT COUNT(*) as count FROM int_baseline_workforce"
            ).fetchone()

        return result[0] if result else 0
    finally:
        conn.close()


def apply_events_to_workforce(simulation_year: int) -> Dict[str, any]:
    """
    Run the fct_workforce_snapshot dbt model to apply all events.

    Args:
        simulation_year: Year to run the snapshot for

    Returns:
        Dictionary with success status and any error messages
    """
    # Import here to avoid circular dependency
    from ..loaders.staging_loader import run_dbt_model_with_vars

    # Run the model with simulation year variable
    vars_dict = {"simulation_year": simulation_year}
    result = run_dbt_model_with_vars("fct_workforce_snapshot", vars_dict)

    return result


def calculate_workforce_metrics(
    simulation_year: int,
    db_path: str
) -> Dict[str, any]:
    """
    Calculate key workforce metrics from the snapshot.

    Args:
        simulation_year: Year of the snapshot
        db_path: Path to the DuckDB database

    Returns:
        Dictionary of workforce metrics
    """
    conn = get_connection()

    try:
        # Get workforce counts by status
        status_counts = conn.execute(f"""
            SELECT
                employment_status,
                COUNT(*) as count
            FROM fct_workforce_snapshot
            WHERE simulation_year = {simulation_year}
            GROUP BY employment_status
            ORDER BY count DESC
        """).fetchall()

        # Get total headcount and compensation
        totals = conn.execute(f"""
            SELECT
                COUNT(*) as total_headcount,
                SUM(current_compensation) as total_compensation,
                AVG(current_compensation) as avg_compensation,
                MIN(current_compensation) as min_compensation,
                MAX(current_compensation) as max_compensation
            FROM fct_workforce_snapshot
            WHERE simulation_year = {simulation_year}
              AND employment_status = 'active'
        """).fetchone()

        # Get event impact summary
        event_impact = conn.execute(f"""
            SELECT
                event_type,
                COUNT(*) as event_count
            FROM fct_yearly_events
            WHERE simulation_year = {simulation_year}
            GROUP BY event_type
            ORDER BY event_count DESC
        """).fetchall()

        # Calculate growth rate
        baseline_count = get_starting_workforce(db_path)
        current_active = next((c[1] for c in status_counts if c[0] == 'Active'), 0)
        growth_rate = ((current_active - baseline_count) / baseline_count * 100) if baseline_count > 0 else 0

        return {
            "status_counts": dict(status_counts),
            "total_headcount": totals[0] if totals else 0,
            "total_compensation": totals[1] if totals else 0,
            "avg_compensation": totals[2] if totals else 0,
            "min_compensation": totals[3] if totals else 0,
            "max_compensation": totals[4] if totals else 0,
            "event_counts": dict(event_impact),
            "growth_rate": growth_rate,
            "baseline_count": baseline_count,
            "current_active": current_active
        }
    finally:
        conn.close()


def validate_workforce_continuity(
    simulation_year: int,
    db_path: str
) -> Dict[str, any]:
    """
    Validate workforce continuity and data quality.

    Args:
        simulation_year: Year to validate
        db_path: Path to the DuckDB database

    Returns:
        Dictionary with validation results
    """
    conn = get_connection()
    validation_results = {
        "has_errors": False,
        "errors": [],
        "warnings": []
    }

    try:
        # Check for missing employees
        missing_check = conn.execute(f"""
            SELECT COUNT(*) as missing_count
            FROM int_baseline_workforce b
            LEFT JOIN fct_workforce_snapshot s
                ON b.employee_id = s.employee_id
                AND s.simulation_year = {simulation_year}
            WHERE s.employee_id IS NULL
        """).fetchone()

        if missing_check and missing_check[0] > 0:
            validation_results["has_errors"] = True
            validation_results["errors"].append(
                f"Found {missing_check[0]} employees missing from snapshot"
            )

        # Check for invalid status codes
        invalid_status = conn.execute(f"""
            SELECT DISTINCT employment_status
            FROM fct_workforce_snapshot
            WHERE simulation_year = {simulation_year}
              AND employment_status NOT IN ('active', 'terminated')
        """).fetchall()

        if invalid_status:
            validation_results["warnings"].append(
                f"Found invalid status codes: {[s[0] for s in invalid_status]}"
            )

        # Check for null salaries on active employees
        null_salary = conn.execute(f"""
            SELECT COUNT(*) as null_count
            FROM fct_workforce_snapshot
            WHERE simulation_year = {simulation_year}
              AND employment_status = 'active'
              AND current_compensation IS NULL
        """).fetchone()

        if null_salary and null_salary[0] > 0:
            validation_results["warnings"].append(
                f"Found {null_salary[0]} active employees with null salary"
            )

        # Check event application completeness
        event_check = conn.execute(f"""
            SELECT
                COUNT(*) as total_events,
                COUNT(DISTINCT employee_id) as affected_employees
            FROM fct_yearly_events
            WHERE simulation_year = {simulation_year}
        """).fetchone()

        if event_check:
            validation_results["event_application"] = {
                "total_events": event_check[0],
                "affected_employees": event_check[1]
            }

        return validation_results
    finally:
        conn.close()
