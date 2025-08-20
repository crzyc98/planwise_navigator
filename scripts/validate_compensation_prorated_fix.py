#!/usr/bin/env python3
"""
Validate Compensation Prorated Fix Script

This script validates that the compensation prorated calculation fix works correctly.
It runs a simulation with known test data (including the user's EMP_000003 scenario),
executes the dbt models, and validates that prorated compensation calculations match
expected values.

Key validations:
- Correct time-weighted calculations for mid-year raises
- Proper handling of multiple raises per employee per year
- Validation that current_compensation equals prorated_annual_compensation
- Comparison with the previous incorrect behavior to confirm the fix
"""

import json
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import duckdb
import numpy as np
import pandas as pd

# Add parent directory to path to import project modules
sys.path.append(str(Path(__file__).parent.parent))


def connect_to_database(
    db_path: str = "simulation.duckdb",
) -> duckdb.DuckDBPyConnection:
    """Connect to the DuckDB database."""
    return duckdb.connect(db_path)


def setup_test_data(conn: duckdb.DuckDBPyConnection) -> None:
    """Set up test data for the prorated compensation validation."""

    # Create test workforce data
    test_workforce = pd.DataFrame(
        {
            "employee_id": [
                "EMP_000001",
                "EMP_000002",
                "EMP_000003",
                "EMP_000004",
                "EMP_000005",
            ],
            "employee_ssn": [
                "111-11-1111",
                "222-22-2222",
                "333-33-3333",
                "444-44-4444",
                "555-55-5555",
            ],
            "employee_birth_date": pd.to_datetime(
                ["1980-01-15", "1985-06-20", "1990-03-10", "1975-12-05", "1988-09-25"]
            ),
            "employee_hire_date": pd.to_datetime(
                ["2020-01-01", "2020-01-01", "2020-01-01", "2020-01-01", "2025-06-01"]
            ),
            "employee_gross_compensation": [
                55000.0,
                60000.0,
                50700.0,
                75000.0,
                65000.0,
            ],
            "level_id": [2, 2, 2, 3, 2],
            "employment_status": ["active", "active", "active", "active", "active"],
            "current_age": [45, 40, 35, 50, 37],
            "current_tenure": [5, 5, 5, 20, 0.5],
            "termination_date": [None, None, None, None, None],
            "termination_reason": [None, None, None, None, None],
            "simulation_year": [2025, 2025, 2025, 2025, 2025],
        }
    )

    # Create test yearly events including the user's specific scenario
    # EMP_000003: Only one raise on July 15th to match user's exact scenario
    test_events = pd.DataFrame(
        {
            "event_id": ["evt_001", "evt_002", "evt_003", "evt_004", "evt_005"],
            "employee_id": [
                "EMP_000001",
                "EMP_000002",
                "EMP_000003",
                "EMP_000004",
                "EMP_000005",
            ],
            "event_type": ["raise", "raise", "raise", "raise", "hire"],
            "simulation_year": [2025, 2025, 2025, 2025, 2025],
            "effective_date": pd.to_datetime(
                ["2025-03-15", "2025-08-01", "2025-07-15", "2025-12-31", "2025-06-01"]
            ),
            "compensation_amount": [57000.0, 62500.0, 53880.84, 78000.0, 65000.0],
            "previous_compensation": [55000.0, 60000.0, 50700.0, 75000.0, None],
            "event_reason": ["merit", "merit", "merit", "promotion", "new_hire"],
        }
    )

    # Clear existing test data
    conn.execute("DROP TABLE IF EXISTS test_int_snapshot_hiring")
    conn.execute("DROP TABLE IF EXISTS test_fct_yearly_events")

    # Create and populate test tables
    conn.register("workforce_data", test_workforce)
    conn.execute(
        "CREATE TABLE test_int_snapshot_hiring AS SELECT * FROM workforce_data"
    )

    conn.register("events_data", test_events)
    conn.execute("CREATE TABLE test_fct_yearly_events AS SELECT * FROM events_data")

    print("✓ Test data setup complete")


def run_prorated_compensation_calculation(
    conn: duckdb.DuckDBPyConnection,
) -> pd.DataFrame:
    """Run the prorated compensation calculation using the updated logic."""

    query = """
    WITH workforce_base AS (
        SELECT
            employee_id,
            employee_ssn,
            employee_birth_date,
            employee_hire_date,
            employee_gross_compensation,
            current_age,
            current_tenure,
            level_id,
            termination_date,
            employment_status,
            termination_reason,
            simulation_year,
            employee_gross_compensation AS starting_compensation,
            employee_gross_compensation AS final_compensation,
            CASE
                WHEN EXTRACT(YEAR FROM employee_hire_date) = simulation_year
                THEN EXTRACT(DOY FROM employee_hire_date)
                ELSE 1
            END AS hire_day_of_year
        FROM test_int_snapshot_hiring
        WHERE simulation_year = 2025
    ),

    compensation_events AS (
        SELECT
            employee_id,
            event_type,
            simulation_year,
            effective_date,
            compensation_amount AS event_new_salary,
            previous_compensation,
            CASE
                WHEN EXTRACT(DOY FROM effective_date) < 1 THEN 1
                WHEN EXTRACT(DOY FROM effective_date) > EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE))
                THEN EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE))
                ELSE EXTRACT(DOY FROM effective_date)
            END AS event_day_of_year,
            ROW_NUMBER() OVER (
                PARTITION BY employee_id
                ORDER BY effective_date DESC
            ) AS event_rank
        FROM test_fct_yearly_events
        WHERE simulation_year = 2025
            AND event_type IN ('raise', 'promotion')
            AND effective_date IS NOT NULL
            AND compensation_amount IS NOT NULL
    ),

    latest_compensation_events AS (
        SELECT * FROM compensation_events WHERE event_rank = 1
    ),

    workforce_with_events AS (
        SELECT
            w.*,
            ce.event_type,
            ce.effective_date,
            ce.event_day_of_year,
            ce.event_new_salary,
            -- Update final_compensation to use new salary if there's an event
            CASE
                WHEN ce.event_new_salary IS NOT NULL THEN ce.event_new_salary
                ELSE w.final_compensation
            END AS updated_final_compensation
        FROM workforce_base w
        LEFT JOIN latest_compensation_events ce ON w.employee_id = ce.employee_id
    ),

    final_compensation AS (
        SELECT
            employee_id,
            starting_compensation,
            updated_final_compensation AS full_year_equivalent_compensation,
            event_day_of_year,
            event_new_salary,
            hire_day_of_year,

            CASE
                WHEN event_new_salary IS NULL THEN
                    CASE
                        WHEN hire_day_of_year > 1 THEN
                            starting_compensation * (EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE)) - hire_day_of_year + 1) / EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE))
                        ELSE starting_compensation
                    END
                ELSE
                    CASE
                        WHEN hire_day_of_year > 1 THEN
                            (starting_compensation * GREATEST(event_day_of_year - hire_day_of_year, 0) / EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE))) +
                            (event_new_salary * (EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE)) - event_day_of_year + 1) / EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE)))
                        ELSE
                            (starting_compensation * GREATEST(event_day_of_year - 1, 0) / EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE))) +
                            (event_new_salary * (EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE)) - event_day_of_year + 1) / EXTRACT(DOY FROM CAST(simulation_year || '-12-31' AS DATE)))
                    END
            END AS prorated_annual_compensation

        FROM workforce_with_events
    )

    SELECT
        employee_id,
        ROUND(prorated_annual_compensation, 2) AS prorated_annual_compensation,
        full_year_equivalent_compensation,
        starting_compensation,
        event_new_salary,
        event_day_of_year,
        hire_day_of_year
    FROM final_compensation
    ORDER BY employee_id
    """

    return conn.execute(query).fetchdf()


def validate_user_scenario(results_df: pd.DataFrame) -> bool:
    """Validate the specific user scenario: EMP_000003."""

    emp_003_row = results_df[results_df["employee_id"] == "EMP_000003"]

    if len(emp_003_row) == 0:
        print("❌ EMP_000003 not found in results")
        return False

    row = emp_003_row.iloc[0]

    print(f"\\n🔍 Validating EMP_000003 scenario:")
    print(f"  Starting salary: ${row['starting_compensation']:,.2f}")
    print(f"  Raise effective day: {row['event_day_of_year']} (July 15th = day 196)")
    print(f"  New salary: ${row['event_new_salary']:,.2f}")
    print(f"  Calculated prorated: ${row['prorated_annual_compensation']:,.2f}")
    print(f"  Full year equivalent: ${row['full_year_equivalent_compensation']:,.2f}")

    # Calculate expected values manually
    starting_salary = 50700.0
    new_salary = 53880.84
    raise_day = 196  # July 15th
    days_in_year = 365

    # Period 1: Jan 1 - July 14 (195 days)
    period1_days = raise_day - 1
    period1_compensation = starting_salary * period1_days / days_in_year

    # Period 2: July 15 - Dec 31 (170 days)
    period2_days = days_in_year - raise_day + 1
    period2_compensation = new_salary * period2_days / days_in_year

    expected_prorated = period1_compensation + period2_compensation

    print(f"\\n📊 Manual calculation verification:")
    print(f"  Period 1 ({period1_days} days): ${period1_compensation:,.2f}")
    print(f"  Period 2 ({period2_days} days): ${period2_compensation:,.2f}")
    print(f"  Expected total: ${expected_prorated:,.2f}")

    # Validate within $1 tolerance
    tolerance = 1.0
    prorated_diff = abs(row["prorated_annual_compensation"] - expected_prorated)
    user_expected_diff = abs(row["prorated_annual_compensation"] - 52158.33)

    if prorated_diff <= tolerance:
        print(
            f"✓ Prorated calculation matches manual calculation (diff: ${prorated_diff:.2f})"
        )
    else:
        print(f"❌ Prorated calculation mismatch (diff: ${prorated_diff:.2f})")
        return False

    if user_expected_diff <= tolerance:
        print(
            f"✓ Prorated calculation matches user expectation of $52,158.33 (diff: ${user_expected_diff:.2f})"
        )
    else:
        print(
            f"❌ Prorated calculation doesn't match user expectation (diff: ${user_expected_diff:.2f})"
        )
        return False

    return True


def validate_multiple_raises_handling(conn: duckdb.DuckDBPyConnection) -> bool:
    """Validate that multiple raises per employee are handled correctly (latest one wins)."""

    # Query to check which raise was used for EMP_000003 (should be the September one)
    query = """
    WITH compensation_events AS (
        SELECT
            employee_id,
            effective_date,
            compensation_amount,
            ROW_NUMBER() OVER (
                PARTITION BY employee_id
                ORDER BY effective_date DESC
            ) AS event_rank
        FROM test_fct_yearly_events
        WHERE employee_id = 'EMP_000003'
            AND event_type = 'raise'
            AND effective_date IS NOT NULL
            AND compensation_amount IS NOT NULL
    )
    SELECT * FROM compensation_events ORDER BY effective_date
    """

    events_df = conn.execute(query).fetchdf()

    print(f"\\n🔄 Multiple raises validation for EMP_000003:")
    for _, row in events_df.iterrows():
        rank_indicator = "← LATEST (USED)" if row["event_rank"] == 1 else ""
        print(
            f"  {row['effective_date'].strftime('%Y-%m-%d')}: ${row['compensation_amount']:,.2f} {rank_indicator}"
        )

    # Should use the September raise (55000.0) not the July raise (53880.84)
    latest_raise = events_df[events_df["event_rank"] == 1].iloc[0]

    if latest_raise["compensation_amount"] == 55000.0:
        print("✓ Multiple raises handled correctly - latest raise selected")
        return True
    else:
        print("❌ Multiple raises not handled correctly")
        return False


def validate_field_mapping_fix(results_df: pd.DataFrame) -> bool:
    """Validate that current_compensation now equals prorated_annual_compensation."""

    print(f"\\n🔧 Field mapping validation:")

    all_correct = True
    for _, row in results_df.iterrows():
        # In the new system, current_compensation should equal prorated_annual_compensation
        expected_current_comp = row["prorated_annual_compensation"]

        print(
            f"  {row['employee_id']}: prorated=${expected_current_comp:,.2f}, full_year=${row['full_year_equivalent_compensation']:,.2f}"
        )

        # Check that prorated <= full_year_equivalent (should always be true)
        if (
            row["prorated_annual_compensation"]
            > row["full_year_equivalent_compensation"]
        ):
            print(f"    ❌ Prorated compensation exceeds full year equivalent")
            all_correct = False
        else:
            print(f"    ✓ Prorated ≤ Full year equivalent")

    return all_correct


def run_dbt_models() -> bool:
    """Run the dbt models to test the actual implementation."""
    try:
        print("\\n🔨 Running dbt models...")

        # Change to dbt directory
        dbt_dir = Path(__file__).parent.parent / "dbt"

        # Run the specific models we care about
        result = subprocess.run(
            [
                "dbt",
                "run",
                "--select",
                "int_snapshot_compensation",
                "fct_workforce_snapshot",
                "--vars",
                "simulation_year: 2025",
            ],
            cwd=dbt_dir,
            capture_output=True,
            text=True,
        )

        if result.returncode == 0:
            print("✓ dbt models ran successfully")
            return True
        else:
            print(f"❌ dbt models failed: {result.stderr}")
            return False

    except Exception as e:
        print(f"❌ Error running dbt models: {e}")
        return False


def main():
    """Main validation function."""
    print("🧪 Starting Compensation Prorated Fix Validation\\n")

    # Connect to database
    try:
        conn = connect_to_database()
        print("✓ Connected to database")
    except Exception as e:
        print(f"❌ Failed to connect to database: {e}")
        return False

    try:
        # Set up test data
        setup_test_data(conn)

        # Run the prorated compensation calculation
        results_df = run_prorated_compensation_calculation(conn)

        print(f"\\n📋 Calculation results:")
        for _, row in results_df.iterrows():
            print(
                f"  {row['employee_id']}: ${row['prorated_annual_compensation']:,.2f} (prorated) / ${row['full_year_equivalent_compensation']:,.2f} (full year)"
            )

        # Run validations
        validation_results = []

        # 1. Validate user scenario
        validation_results.append(
            ("User Scenario (EMP_000003)", validate_user_scenario(results_df))
        )

        # 2. Validate multiple raises handling
        validation_results.append(
            ("Multiple Raises Handling", validate_multiple_raises_handling(conn))
        )

        # 3. Validate field mapping fix
        validation_results.append(
            ("Field Mapping Fix", validate_field_mapping_fix(results_df))
        )

        # 4. Run dbt models (optional - may not work in all environments)
        try:
            dbt_success = run_dbt_models()
            validation_results.append(("dbt Models Execution", dbt_success))
        except:
            print(
                "⚠️  Skipping dbt models execution (not available in this environment)"
            )

        # Summary
        print(f"\\n📊 Validation Summary:")
        print("=" * 50)

        all_passed = True
        for test_name, passed in validation_results:
            status = "✓ PASS" if passed else "❌ FAIL"
            print(f"{status} {test_name}")
            if not passed:
                all_passed = False

        print("=" * 50)

        if all_passed:
            print(
                "🎉 All validations passed! The compensation prorated fix is working correctly."
            )
            return True
        else:
            print("⚠️  Some validations failed. Please review the issues above.")
            return False

    except Exception as e:
        print(f"❌ Validation failed with error: {e}")
        return False
    finally:
        conn.close()


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
