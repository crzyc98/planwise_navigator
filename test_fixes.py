#!/usr/bin/env python3
"""
Test script to validate Story S037 fixes
Simulates 2025-2029 using our updated models
"""

import subprocess
import duckdb
import sys


def run_dbt_model(model_name, simulation_year=2025):
    """Run a specific dbt model for a given year"""
    cmd = [
        "venv/bin/dbt",
        "run",
        "--select",
        model_name,
        "--vars",
        f"{{simulation_year: {simulation_year}}}",
        "--project-dir",
        "dbt",
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, cwd=".")
    if result.returncode != 0:
        print(f"Error running {model_name}: {result.stderr}")
        return False
    return True


def clean_year_data(year):
    """Clean existing data for a specific year"""
    conn = duckdb.connect("simulation.duckdb")
    try:
        # Clean yearly events
        conn.execute("DELETE FROM fct_yearly_events WHERE simulation_year = ?", [year])
        # Clean workforce snapshot
        conn.execute(
            "DELETE FROM fct_workforce_snapshot WHERE simulation_year = ?", [year]
        )
        print(f"Cleaned data for year {year}")
    except Exception as e:
        print(f"Warning: Could not clean data for year {year}: {e}")
    finally:
        conn.close()


def run_year_simulation(year):
    """Run simulation for a specific year"""
    print(f"Running simulation for year {year}...")

    # Clean existing data
    clean_year_data(year)

    # Run models in sequence
    models = [
        "int_previous_year_workforce",
        "int_termination_events",
        "int_hiring_events",
        "int_new_hire_termination_events",
        "int_promotion_events",
        "int_merit_events",
        "fct_yearly_events",
        "fct_workforce_snapshot",
    ]

    for model in models:
        if not run_dbt_model(model, year):
            return False

    return True


def check_year_results(year):
    """Check results for a specific year"""
    conn = duckdb.connect("simulation.duckdb")
    try:
        # Get workforce count
        workforce_count = conn.execute(
            """
            SELECT COUNT(*)
            FROM fct_workforce_snapshot
            WHERE simulation_year = ? AND employment_status = 'active'
        """,
            [year],
        ).fetchone()[0]

        # Get events summary
        events = conn.execute(
            """
            SELECT event_type, COUNT(*) as count
            FROM fct_yearly_events
            WHERE simulation_year = ?
            GROUP BY event_type
            ORDER BY event_type
        """,
            [year],
        ).fetchall()

        print(f"Year {year}: {workforce_count} active employees")
        for event_type, count in events:
            print(f"  {event_type}: {count}")

        return workforce_count

    except Exception as e:
        print(f"Error checking year {year}: {e}")
        return 0
    finally:
        conn.close()


def main():
    """Test the simulation fixes"""
    print("Testing Story S037 fixes...")
    print("=" * 50)

    # Check baseline
    conn = duckdb.connect("simulation.duckdb")
    try:
        baseline_count = conn.execute(
            "SELECT COUNT(*) FROM int_baseline_workforce WHERE employment_status = 'active'"
        ).fetchone()[0]
        print(f"Baseline workforce: {baseline_count}")

        if baseline_count != 95:
            print(f"❌ Expected baseline of 95, got {baseline_count}")
            return 1
    except Exception as e:
        print(f"Error checking baseline: {e}")
        return 1
    finally:
        conn.close()

    # Run 2025 simulation
    if not run_year_simulation(2025):
        print("❌ Failed to run 2025 simulation")
        return 1

    workforce_2025 = check_year_results(2025)

    # Calculate expected growth
    baseline = 95
    growth_rate = (workforce_2025 - baseline) / baseline
    print(f"\n2025 growth rate from baseline: {growth_rate:.1%}")

    # Check if we have proper growth (should be ~3%)
    if 0.025 <= growth_rate <= 0.035:  # 2.5% to 3.5% tolerance
        print("✅ 2025 growth rate is within expected range")
        return 0
    else:
        print(
            f"❌ 2025 growth rate {growth_rate:.1%} is outside expected range (2.5%-3.5%)"
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
