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
        starting_count = get_starting_workforce(db_path, simulation_year)
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


def get_starting_workforce(db_path: str, simulation_year: int = 2025) -> int:
    """
    Get the starting workforce count for multi-year simulation support with circular dependency validation.

    For year 1 (baseline): uses int_baseline_workforce
    For subsequent years: validates helper model readiness and uses previous year's workforce snapshot

    Args:
        db_path: Path to the DuckDB database
        simulation_year: Year to get starting workforce for

    Returns:
        Number of active employees to start with

    Raises:
        ValueError: If helper model data is missing for subsequent years
    """
    conn = get_connection()

    try:
        # For the first simulation year (assume 2025), use baseline workforce
        if simulation_year == 2025:
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
                    "SELECT COUNT(*) as count FROM int_baseline_workforce WHERE employment_status = 'active'"
                ).fetchone()
        else:
            # For subsequent years, validate helper model readiness first
            previous_year = simulation_year - 1

            # Check if the new helper model can access required data
            helper_check = conn.execute(
                "SELECT COUNT(*) as count FROM fct_workforce_snapshot WHERE simulation_year = ? AND employment_status = 'active'",
                [previous_year]
            ).fetchone()

            if not helper_check or helper_check[0] == 0:
                raise ValueError(
                    f"Circular dependency helper model validation failed: "
                    f"No active employees found in year {previous_year} workforce snapshot. "
                    f"Cannot proceed with year {simulation_year}. "
                    f"Please ensure year {previous_year} completed successfully before running year {simulation_year}."
                )

            print(f"   ✅ Helper model validation: {helper_check[0]:,} employees available from year {previous_year}")
            result = helper_check

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

    # For years after 2025, build the circular dependency helper model first
    if simulation_year > 2025:
        print(f"   Preparing previous year workforce data for year {simulation_year} using helper model...")

        # First, validate the helper model can be built
        try:
            from ..core.database_manager import get_connection
            conn = get_connection()
            try:
                previous_year = simulation_year - 1
                verify_source_query = "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ? AND employment_status = 'active'"
                verify_source_result = conn.execute(verify_source_query, [previous_year]).fetchone()

                if not verify_source_result or verify_source_result[0] == 0:
                    return {
                        "success": False,
                        "error": f"Circular dependency issue: No source data found in fct_workforce_snapshot for year {previous_year}. "
                               f"Multi-year simulations must be run sequentially. Please complete year {previous_year} first."
                    }
                print(f"   ✅ Helper model validation: Found {verify_source_result[0]:,} active employees from year {previous_year}")
            finally:
                conn.close()
        except Exception as e:
            return {
                "success": False,
                "error": f"Could not validate helper model readiness: {str(e)}"
            }

        # Run the circular dependency helper model instead of int_workforce_previous_year_v2
        helper_vars = {"simulation_year": simulation_year}
        helper_result = run_dbt_model_with_vars("int_active_employees_prev_year_snapshot", helper_vars, full_refresh=True)

        if not helper_result.get("success", False):
            return {
                "success": False,
                "error": f"Failed to build circular dependency helper model: {helper_result.get('error', 'Unknown error')}. "
                       f"This model is required to break the circular dependency in multi-year simulations."
            }

        print(f"   ✅ Circular dependency helper model built successfully for year {simulation_year}")

    # Run the model with simulation year variable
    print(f"   🔄 Running fct_workforce_snapshot for year {simulation_year}...")
    vars_dict = {"simulation_year": simulation_year}
    result = run_dbt_model_with_vars("fct_workforce_snapshot", vars_dict)
    print(f"   🔍 DEBUG: fct_workforce_snapshot result: {result.get('success', False)} - {result.get('error', 'No error')}")

    # Verify that the data was actually written and helper model validation
    if result.get("success", False):
        try:
            from ..core.database_manager import get_connection
            conn = get_connection()
            try:
                verify_query = "SELECT COUNT(*) FROM fct_workforce_snapshot WHERE simulation_year = ?"
                verify_result = conn.execute(verify_query, [simulation_year]).fetchone()

                if verify_result and verify_result[0] > 0:
                    print(f"   ✅ Verified: {verify_result[0]:,} records written for year {simulation_year}")

                    # For subsequent years, also verify helper model was created successfully
                    if simulation_year > 2025:
                        helper_verify_query = "SELECT COUNT(*) FROM int_active_employees_prev_year_snapshot WHERE simulation_year = ?"
                        helper_verify_result = conn.execute(helper_verify_query, [simulation_year]).fetchone()

                        if helper_verify_result and helper_verify_result[0] > 0:
                            print(f"   ✅ Helper model verified: {helper_verify_result[0]:,} records for circular dependency resolution")
                        else:
                            print(f"   ⚠️ Helper model validation warning: No data found in int_active_employees_prev_year_snapshot")
                else:
                    print(f"   ❌ Verification failed: No data found for year {simulation_year}")
                    return {
                        "success": False,
                        "error": f"Workforce snapshot generation failed - no data written for year {simulation_year}"
                    }
            finally:
                conn.close()
        except Exception as e:
            print(f"   ⚠️ Could not verify data: {str(e)}")

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
        baseline_count = get_starting_workforce(db_path, simulation_year)
        current_active = next((c[1] for c in status_counts if c[0] == 'active'), 0)

        # For year-over-year growth calculation
        if simulation_year > 2025:
            previous_year = simulation_year - 1
            previous_active_result = conn.execute(f"""
                SELECT COUNT(*) as count
                FROM fct_workforce_snapshot
                WHERE simulation_year = {previous_year}
                  AND employment_status = 'active'
            """).fetchone()
            previous_active = previous_active_result[0] if previous_active_result else baseline_count
            growth_rate = ((current_active - previous_active) / previous_active * 100) if previous_active > 0 else 0
        else:
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
            "current_active": current_active,
            "simulation_year": simulation_year
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
        # Check for missing employees (different logic for multi-year)
        if simulation_year == 2025:
            # For first year, check against baseline
            missing_check = conn.execute(f"""
                SELECT COUNT(*) as missing_count
                FROM int_baseline_workforce b
                LEFT JOIN fct_workforce_snapshot s
                    ON b.employee_id = s.employee_id
                    AND s.simulation_year = {simulation_year}
                WHERE s.employee_id IS NULL
                  AND b.employment_status = 'active'
            """).fetchone()
        else:
            # For subsequent years, check for year transition continuity
            previous_year = simulation_year - 1
            missing_check = conn.execute(f"""
                SELECT COUNT(*) as missing_count
                FROM fct_workforce_snapshot prev
                LEFT JOIN fct_workforce_snapshot curr
                    ON prev.employee_id = curr.employee_id
                    AND curr.simulation_year = {simulation_year}
                WHERE prev.simulation_year = {previous_year}
                  AND prev.employment_status = 'active'
                  AND curr.employee_id IS NULL
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

        # Add year transition validation for multi-year scenarios
        if simulation_year > 2025:
            previous_year = simulation_year - 1

            # Check for proper age/tenure progression
            age_tenure_check = conn.execute(f"""
                SELECT COUNT(*) as inconsistent_count
                FROM fct_workforce_snapshot prev
                JOIN fct_workforce_snapshot curr
                    ON prev.employee_id = curr.employee_id
                WHERE prev.simulation_year = {previous_year}
                  AND curr.simulation_year = {simulation_year}
                  AND prev.employment_status = 'active'
                  AND curr.employment_status = 'active'
                  AND (curr.current_age <= prev.current_age OR curr.current_tenure <= prev.current_tenure)
            """).fetchone()

            if age_tenure_check and age_tenure_check[0] > 0:
                validation_results["warnings"].append(
                    f"Found {age_tenure_check[0]} employees with inconsistent age/tenure progression"
                )

            validation_results["year_transition"] = {
                "from_year": previous_year,
                "to_year": simulation_year,
                "validated": True
            }

        return validation_results
    finally:
        conn.close()
