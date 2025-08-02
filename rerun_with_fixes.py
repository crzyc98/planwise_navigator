#!/usr/bin/env python3
"""
Re-run the simulation with the fixed dbt models.

This script:
1. Clears the incorrect event data that was generated before fixes
2. Re-runs the 2025 simulation with the corrected models
3. Validates the results match expected 873 hires
"""

import subprocess
import duckdb
import sys

def clear_event_data():
    """Clear the incorrect event data from before fixes."""
    print("🧹 Clearing incorrect event data...")

    conn = duckdb.connect('simulation.duckdb')
    try:
        # Clear events table
        conn.execute("DELETE FROM fct_yearly_events WHERE simulation_year = 2025")
        print("✅ Cleared fct_yearly_events for 2025")

        # Clear workforce snapshot
        conn.execute("DELETE FROM fct_workforce_snapshot WHERE simulation_year = 2025")
        print("✅ Cleared fct_workforce_snapshot for 2025")

    except Exception as e:
        print(f"⚠️  Warning during cleanup: {e}")
    finally:
        conn.close()

def run_dbt_models():
    """Run the event generation models with fixes applied."""
    print("\n🔧 Running dbt models with fixes...")

    models_to_run = [
        "int_workforce_needs",
        "int_workforce_needs_by_level",
        "int_termination_events",
        "int_hiring_events",
        "int_new_hire_termination_events",
        "int_promotion_events",
        "int_merit_events",
        "int_enrollment_events",
        "fct_yearly_events",
        "fct_workforce_snapshot"
    ]

    for model in models_to_run:
        print(f"\n  Running {model}...")
        cmd = [
            "/Users/nicholasamaral/planwise_navigator/venv/bin/dbt",
            "run",
            "--select", model,
            "--vars", "simulation_year: 2025",
            "--project-dir", "/Users/nicholasamaral/planwise_navigator/dbt"
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"❌ Failed to run {model}")
            print(f"Error: {result.stderr}")
            return False
        else:
            print(f"✅ {model} completed")

    return True

def validate_results():
    """Validate that the fixes produced correct results."""
    print("\n🔍 Validating results...")

    conn = duckdb.connect('simulation.duckdb')

    # Check workforce needs
    wn_result = conn.execute('''
    SELECT total_hires_needed
    FROM int_workforce_needs
    WHERE simulation_year = 2025
    ''').fetchone()

    if wn_result:
        print(f"\n📊 Workforce needs calculation: {wn_result[0]} hires")

    # Check actual events created
    events_result = conn.execute('''
    SELECT event_type, COUNT(*) as count
    FROM fct_yearly_events
    WHERE simulation_year = 2025
    GROUP BY event_type
    ORDER BY count DESC
    ''').fetchall()

    print("\n📊 Events generated:")
    hire_count = 0
    for event_type, count in events_result:
        print(f"  {event_type}: {count}")
        if event_type == 'hire':
            hire_count = count

    # Validate hire count
    print(f"\n🎯 VALIDATION RESULT:")
    if 850 <= hire_count <= 900:  # Allow small rounding differences
        print(f"✅ SUCCESS: {hire_count} hires generated (expected ~873)")
        return True
    else:
        print(f"❌ FAILURE: {hire_count} hires generated (expected ~873)")
        return False

    conn.close()

def main():
    """Main execution flow."""
    print("🚀 RE-RUNNING SIMULATION WITH FIXES")
    print("=" * 50)

    # Step 1: Clear old data
    clear_event_data()

    # Step 2: Run dbt models
    if not run_dbt_models():
        print("\n💥 Failed to run dbt models")
        return 1

    # Step 3: Validate results
    if validate_results():
        print("\n🎉 SIMULATION COMPLETED SUCCESSFULLY WITH FIXES!")
        print("   The 6.7x inflation has been resolved.")
        return 0
    else:
        print("\n💥 Validation failed - fixes may not be working correctly")
        return 1

if __name__ == "__main__":
    sys.exit(main())
