#!/usr/bin/env python3
"""
Verification Script: Multi-Year Events Accumulation

This script verifies that fct_yearly_events properly accumulates data across all simulation years.
Run this after a multi-year simulation to confirm all years are present.
"""

import sys
from pathlib import Path

import duckdb


def check_multi_year_events():
    """Check that fct_yearly_events contains data for all simulation years."""

    db_path = Path("simulation.duckdb")
    if not db_path.exists():
        print("❌ Database file 'simulation.duckdb' not found")
        return False

    try:
        conn = duckdb.connect(str(db_path))
        print("🔍 Checking fct_yearly_events multi-year accumulation...")
        print("=" * 60)

        # Check if table exists
        try:
            conn.execute("SELECT 1 FROM fct_yearly_events LIMIT 1")
        except:
            print("❌ Table fct_yearly_events does not exist")
            return False

        # Get events by year
        year_query = """
        SELECT
            simulation_year,
            COUNT(*) as event_count,
            COUNT(DISTINCT event_type) as unique_event_types,
            MIN(effective_date) as earliest_event,
            MAX(effective_date) as latest_event
        FROM fct_yearly_events
        GROUP BY simulation_year
        ORDER BY simulation_year
        """

        results = conn.execute(year_query).fetchall()

        if not results:
            print("⚠️ No data found in fct_yearly_events table")
            return False

        print("📊 Events by Simulation Year:")
        print(f"{'Year':<6} {'Events':<10} {'Types':<8} {'Date Range'}")
        print("-" * 50)

        total_events = 0
        years_found = []

        for year, count, types, min_date, max_date in results:
            years_found.append(year)
            total_events += count
            date_range = f"{min_date} to {max_date}" if min_date and max_date else "N/A"
            print(f"{year:<6} {count:<10,} {types:<8} {date_range}")

        print("-" * 50)
        print(f"TOTAL: {total_events:,} events across {len(years_found)} years")
        print(f"Years found: {', '.join(map(str, years_found))}")

        # Check event type distribution
        print("\n📋 Event Type Distribution:")
        type_query = """
        SELECT
            event_type,
            COUNT(*) as total_events,
            COUNT(DISTINCT simulation_year) as years_present
        FROM fct_yearly_events
        GROUP BY event_type
        ORDER BY total_events DESC
        """

        type_results = conn.execute(type_query).fetchall()

        for event_type, count, years_present in type_results:
            print(
                f"   {event_type:<20}: {count:>6,} events across {years_present} years"
            )

        # Validate data quality
        print("\n🔍 Data Quality Checks:")

        # Check for missing required fields
        dq_query = """
        SELECT
            COUNT(*) as total_records,
            COUNT(CASE WHEN employee_id IS NULL THEN 1 END) as missing_employee_id,
            COUNT(CASE WHEN simulation_year IS NULL THEN 1 END) as missing_year,
            COUNT(CASE WHEN event_type IS NULL THEN 1 END) as missing_event_type,
            COUNT(CASE WHEN effective_date IS NULL THEN 1 END) as missing_date
        FROM fct_yearly_events
        """

        dq_results = conn.execute(dq_query).fetchone()
        total, missing_id, missing_year, missing_type, missing_date = dq_results

        if (
            missing_id == 0
            and missing_year == 0
            and missing_type == 0
            and missing_date == 0
        ):
            print("   ✅ All required fields populated")
        else:
            print(f"   ⚠️ Data quality issues:")
            if missing_id > 0:
                print(f"      - {missing_id:,} records missing employee_id")
            if missing_year > 0:
                print(f"      - {missing_year:,} records missing simulation_year")
            if missing_type > 0:
                print(f"      - {missing_type:,} records missing event_type")
            if missing_date > 0:
                print(f"      - {missing_date:,} records missing effective_date")

        # Check for expected multi-year pattern
        if len(years_found) == 1:
            year = years_found[0]
            print(f"\n⚠️ WARNING: Only one year ({year}) found in fct_yearly_events")
            print("   This suggests:")
            print("   1. Multi-year simulation was not completed successfully")
            print("   2. Database was cleared after partial run")
            print("   3. Only single-year simulation was performed")
            print("\n💡 To run a proper multi-year simulation:")
            print("   python run_multi_year.py")
            return False
        else:
            print(f"\n✅ SUCCESS: Multi-year data found ({len(years_found)} years)")

            # Check for gaps in years
            min_year, max_year = min(years_found), max(years_found)
            expected_years = set(range(min_year, max_year + 1))
            actual_years = set(years_found)
            missing_years = expected_years - actual_years

            if missing_years:
                print(
                    f"   ⚠️ Missing years: {', '.join(map(str, sorted(missing_years)))}"
                )
            else:
                print(f"   ✅ Complete year sequence: {min_year} - {max_year}")

        return True

    except Exception as e:
        print(f"❌ Error accessing database: {e}")
        if "Conflicting lock" in str(e):
            print("\n💡 Database is locked by another application (likely VS Code)")
            print("   Close any database connections in your IDE and try again")
        return False

    finally:
        try:
            conn.close()
        except:
            pass


def main():
    """Main function."""
    print("🎯 Multi-Year Events Verification Tool")
    print("Checking if fct_yearly_events accumulates data across simulation years")
    print()

    success = check_multi_year_events()

    if success:
        print("\n✅ Verification completed successfully")
        sys.exit(0)
    else:
        print("\n❌ Verification failed - see issues above")
        sys.exit(1)


if __name__ == "__main__":
    main()
