# orchestrator/utils/cold_start_validation.py
from typing import Dict, Any, List
import pandas as pd
from dagster import AssetExecutionContext, asset, multi_asset
from orchestrator.resources import DuckDBResource

def validate_workforce_initialization(
    context: AssetExecutionContext,
    duckdb: DuckDBResource,
    simulation_year: int
) -> Dict[str, Any]:
    """Validate workforce initialization after all models have run"""

    validation_checks = []

    with duckdb.get_connection() as conn:
        # Check active employee count
        active_count = conn.execute("""
            SELECT COUNT(*) as count
            FROM fct_workforce_snapshot
            WHERE simulation_year = ? AND employment_status = 'active'
        """, [simulation_year]).fetchone()[0]

        validation_checks.append({
            "check_name": "active_employee_count",
            "passed": active_count > 0,
            "message": f"Active employees in year {simulation_year}: {active_count}"
        })

        # Check if workforce continuity is maintained
        if simulation_year > 1:
            continuity_check = conn.execute("""
                SELECT
                    COUNT(DISTINCT p.employee_id) as prev_year_active,
                    COUNT(DISTINCT c.employee_id) as curr_year_employees
                FROM fct_workforce_snapshot p
                LEFT JOIN fct_workforce_snapshot c ON p.employee_id = c.employee_id
                    AND c.simulation_year = ?
                WHERE p.simulation_year = ? - 1
                    AND p.employment_status = 'active'
            """, [simulation_year, simulation_year]).fetchone()

            continuity_ratio = continuity_check[1] / continuity_check[0] if continuity_check[0] > 0 else 0
            validation_checks.append({
                "check_name": "workforce_continuity",
                "passed": continuity_ratio > 0.5,  # At least 50% continuity expected
                "message": f"Workforce continuity: {continuity_ratio:.2%} of previous year active employees"
            })

        # Check simulation run log
        run_logged = conn.execute("""
            SELECT COUNT(*) FROM int_simulation_run_log
            WHERE simulation_year = ?
        """, [simulation_year]).fetchone()[0] > 0

        validation_checks.append({
            "check_name": "simulation_run_logged",
            "passed": run_logged,
            "message": f"Simulation year {simulation_year} logged: {run_logged}"
        })

    all_passed = all(check["passed"] for check in validation_checks)

    return {
        "simulation_year": simulation_year,
        "validation_status": "PASSED" if all_passed else "FAILED",
        "checks": validation_checks,
        "active_employee_count": active_count
    }

def check_schema_compatibility(
    context: AssetExecutionContext,
    duckdb: DuckDBResource
) -> bool:
    """Check if census and workforce snapshot schemas are compatible"""

    with duckdb.get_connection() as conn:
        census_columns = conn.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'stg_census_data'
            ORDER BY ordinal_position
        """).fetchall()

        snapshot_columns = conn.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'fct_workforce_snapshot'
            AND column_name IN (
                'employee_id', 'employee_hire_date', 'employee_termination_date',
                'current_compensation', 'level_id'
            )
            ORDER BY column_name
        """).fetchall()

        # Verify critical columns match
        census_dict = {col[0]: col[1] for col in census_columns}
        snapshot_dict = {col[0]: col[1] for col in snapshot_columns}

        required_columns = ['employee_id', 'employee_hire_date', 'current_compensation', 'level_id']

        for col in required_columns:
            if col not in census_dict:
                context.log.error(f"Missing required column '{col}' in census data")
                return False

            if col in snapshot_dict and census_dict[col] != snapshot_dict[col]:
                context.log.warning(
                    f"Data type mismatch for '{col}': census={census_dict[col]}, "
                    f"snapshot={snapshot_dict[col]}"
                )

        return True
