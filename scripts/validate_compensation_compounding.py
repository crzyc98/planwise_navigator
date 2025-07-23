#!/usr/bin/env python3
"""
Validate Compensation Compounding Script

This script validates that compensation raises are compounding correctly across
simulation years. It runs multi-year simulations and verifies that each year's
starting salary matches the previous year's ending salary (post-raise).
"""

import duckdb
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Tuple
import json
import sys

# Add parent directory to path to import project modules
sys.path.append(str(Path(__file__).parent.parent))


def connect_to_database(db_path: str = "simulation.duckdb") -> duckdb.DuckDBPyConnection:
    """Connect to the DuckDB database."""
    return duckdb.connect(db_path)


def run_validation_query(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """Run the main validation query to check compensation compounding."""
    query = """
    WITH employee_year_over_year AS (
        -- Track each employee's compensation progression year over year
        SELECT
            curr.employee_id,
            curr.simulation_year AS current_year,
            prev.simulation_year AS previous_year,
            prev.full_year_equivalent_compensation AS previous_year_ending_salary,
            curr.current_compensation AS current_year_starting_salary,
            curr.full_year_equivalent_compensation AS current_year_ending_salary,
            -- Calculate if compensation carried forward correctly
            CASE
                WHEN ABS(curr.current_compensation - prev.full_year_equivalent_compensation) < 0.01 THEN 'CORRECT'
                WHEN ABS(curr.current_compensation - prev.current_compensation) < 0.01 THEN 'INCORRECT_NO_COMPOUND'
                ELSE 'MISMATCH'
            END AS compounding_status,
            -- Calculate the discrepancy
            curr.current_compensation - prev.full_year_equivalent_compensation AS salary_discrepancy
        FROM fct_workforce_snapshot curr
        INNER JOIN fct_workforce_snapshot prev
            ON curr.employee_id = prev.employee_id
            AND curr.simulation_year = prev.simulation_year + 1
            AND prev.employment_status = 'active'
            AND curr.employment_status = 'active'
    )
    SELECT *
    FROM employee_year_over_year
    ORDER BY ABS(salary_discrepancy) DESC
    """

    return conn.execute(query).df()


def analyze_specific_employee(conn: duckdb.DuckDBPyConnection, starting_salary: float = 176000) -> pd.DataFrame:
    """Analyze a specific employee's compensation progression to verify compounding."""
    query = f"""
    WITH target_employees AS (
        -- Find employees starting near the target salary
        SELECT DISTINCT employee_id
        FROM fct_workforce_snapshot
        WHERE simulation_year = 2025
            AND ABS(current_compensation - {starting_salary}) < 1000
            AND employment_status = 'active'
        LIMIT 5
    ),
    employee_progression AS (
        SELECT
            ws.employee_id,
            ws.simulation_year,
            ws.current_compensation AS starting_salary,
            ws.full_year_equivalent_compensation AS ending_salary,
            events.raise_amount,
            events.raise_percentage,
            -- Calculate expected progression with 4.3% raises
            {starting_salary} * POWER(1.043, ws.simulation_year - 2025) AS expected_salary_4_3_pct
        FROM fct_workforce_snapshot ws
        INNER JOIN target_employees te ON ws.employee_id = te.employee_id
        LEFT JOIN (
            SELECT
                employee_id,
                simulation_year,
                SUM(CASE WHEN event_type = 'raise' THEN new_compensation - previous_compensation ELSE 0 END) AS raise_amount,
                AVG(CASE WHEN event_type = 'raise' THEN (new_compensation - previous_compensation) / previous_compensation * 100 ELSE 0 END) AS raise_percentage
            FROM fct_yearly_events
            WHERE event_type = 'raise'
            GROUP BY employee_id, simulation_year
        ) events ON ws.employee_id = events.employee_id AND ws.simulation_year = events.simulation_year
        WHERE ws.employment_status = 'active'
        ORDER BY ws.employee_id, ws.simulation_year
    )
    SELECT *
    FROM employee_progression
    """

    return conn.execute(query).df()


def calculate_compounding_metrics(validation_df: pd.DataFrame) -> Dict[str, any]:
    """Calculate summary metrics for compensation compounding validation."""
    total_records = len(validation_df)
    if total_records == 0:
        return {
            "total_validations": 0,
            "error_message": "No year-over-year data found. Run multi-year simulation first."
        }

    correct_count = len(validation_df[validation_df['compounding_status'] == 'CORRECT'])
    incorrect_count = len(validation_df[validation_df['compounding_status'] == 'INCORRECT_NO_COMPOUND'])
    mismatch_count = len(validation_df[validation_df['compounding_status'] == 'MISMATCH'])

    metrics = {
        "total_validations": total_records,
        "correct_compounding": correct_count,
        "correct_percentage": round(100 * correct_count / total_records, 2),
        "incorrect_no_compound": incorrect_count,
        "incorrect_percentage": round(100 * incorrect_count / total_records, 2),
        "mismatches": mismatch_count,
        "mismatch_percentage": round(100 * mismatch_count / total_records, 2),
        "avg_discrepancy": round(validation_df[validation_df['compounding_status'] != 'CORRECT']['salary_discrepancy'].abs().mean(), 2) if incorrect_count + mismatch_count > 0 else 0,
        "total_lost_compensation": round(validation_df[validation_df['compounding_status'] == 'INCORRECT_NO_COMPOUND']['salary_discrepancy'].sum(), 2)
    }

    return metrics


def generate_example_report(validation_df: pd.DataFrame, employee_df: pd.DataFrame) -> str:
    """Generate a detailed report with specific examples of compounding behavior."""
    report = []
    report.append("=" * 80)
    report.append("COMPENSATION COMPOUNDING VALIDATION REPORT")
    report.append("=" * 80)
    report.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")

    # Summary metrics
    metrics = calculate_compounding_metrics(validation_df)

    if metrics.get("error_message"):
        report.append(f"ERROR: {metrics['error_message']}")
        return "\n".join(report)

    report.append("SUMMARY METRICS:")
    report.append("-" * 40)
    report.append(f"Total Year-over-Year Validations: {metrics['total_validations']:,}")
    report.append(f"Correct Compounding: {metrics['correct_compounding']:,} ({metrics['correct_percentage']}%)")
    report.append(f"Incorrect (No Compound): {metrics['incorrect_no_compound']:,} ({metrics['incorrect_percentage']}%)")
    report.append(f"Mismatches: {metrics['mismatches']:,} ({metrics['mismatch_percentage']}%)")
    report.append(f"Average Discrepancy: ${metrics['avg_discrepancy']:,.2f}")
    report.append(f"Total Lost Compensation: ${metrics['total_lost_compensation']:,.2f}")
    report.append("")

    # Specific employee example
    if len(employee_df) > 0:
        report.append("EXAMPLE: $176,000 EMPLOYEE PROGRESSION")
        report.append("-" * 40)

        for employee_id in employee_df['employee_id'].unique()[:1]:  # Show first employee
            emp_data = employee_df[employee_df['employee_id'] == employee_id]
            report.append(f"Employee ID: {employee_id}")
            report.append("")
            report.append("Year | Starting Salary | Ending Salary | Raise % | Expected (4.3%) | Status")
            report.append("-" * 80)

            prev_ending = None
            for _, row in emp_data.iterrows():
                year = int(row['simulation_year'])
                starting = row['starting_salary']
                ending = row['ending_salary']
                expected = row['expected_salary_4_3_pct']
                raise_pct = row['raise_percentage'] if pd.notna(row['raise_percentage']) else 0

                # Check if starting matches previous ending
                if prev_ending is not None:
                    status = "✓ CORRECT" if abs(starting - prev_ending) < 0.01 else "✗ ERROR"
                else:
                    status = "BASELINE"

                report.append(f"{year} | ${starting:>13,.2f} | ${ending:>12,.2f} | {raise_pct:>6.1f}% | ${expected:>14,.2f} | {status}")
                prev_ending = ending

            report.append("")

    # Top discrepancies
    report.append("TOP 10 DISCREPANCIES:")
    report.append("-" * 40)

    top_errors = validation_df[validation_df['compounding_status'] != 'CORRECT'].nlargest(10, 'salary_discrepancy', keep='all')
    if len(top_errors) > 0:
        report.append("Employee ID | Year | Prev End Salary | Curr Start Salary | Discrepancy | Status")
        report.append("-" * 80)

        for _, row in top_errors.iterrows():
            report.append(f"{row['employee_id']} | {int(row['current_year'])} | ${row['previous_year_ending_salary']:,.2f} | ${row['current_year_starting_salary']:,.2f} | ${row['salary_discrepancy']:,.2f} | {row['compounding_status']}")
    else:
        report.append("No discrepancies found - all compensation is compounding correctly!")

    report.append("")
    report.append("=" * 80)

    return "\n".join(report)


def validate_multi_year_simulation(conn: duckdb.DuckDBPyConnection, start_year: int = 2025, end_year: int = 2029) -> bool:
    """
    Validate that a multi-year simulation has proper compensation compounding.
    Returns True if validation passes, False otherwise.
    """
    # Check if simulation data exists
    years_query = f"""
    SELECT DISTINCT simulation_year
    FROM fct_workforce_snapshot
    WHERE simulation_year BETWEEN {start_year} AND {end_year}
    ORDER BY simulation_year
    """

    years_df = conn.execute(years_query).df()

    if len(years_df) < 2:
        print(f"ERROR: Not enough simulation years found. Expected {start_year}-{end_year}, found: {years_df['simulation_year'].tolist()}")
        return False

    print(f"Found simulation data for years: {years_df['simulation_year'].tolist()}")

    # Run validation
    validation_df = run_validation_query(conn)
    employee_df = analyze_specific_employee(conn)

    # Generate and print report
    report = generate_example_report(validation_df, employee_df)
    print(report)

    # Determine pass/fail
    metrics = calculate_compounding_metrics(validation_df)

    if metrics.get("error_message"):
        return False

    # Pass if >95% correct compounding
    pass_threshold = 95.0
    passed = metrics['correct_percentage'] >= pass_threshold

    if passed:
        print(f"\n✓ VALIDATION PASSED: {metrics['correct_percentage']}% of employees have correct compensation compounding")
    else:
        print(f"\n✗ VALIDATION FAILED: Only {metrics['correct_percentage']}% of employees have correct compensation compounding (threshold: {pass_threshold}%)")

    return passed


def main():
    """Main execution function."""
    print("Starting Compensation Compounding Validation...")
    print("-" * 80)

    try:
        # Connect to database
        conn = connect_to_database()

        # Run validation
        passed = validate_multi_year_simulation(conn)

        # Exit with appropriate code
        sys.exit(0 if passed else 1)

    except Exception as e:
        print(f"ERROR: {e}")
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    main()
