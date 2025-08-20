#!/usr/bin/env python3
"""
from navigator_orchestrator.config import get_database_path
Debug script for investigating Growth Variance issue in fct_workforce_snapshot.sql
Traces termination logic through the workforce snapshot model to identify where
termination events are not being properly applied to employee status.
"""

import sys
from pathlib import Path

import duckdb
import pandas as pd

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))


def connect_to_database():
    """Connect to the simulation database"""
    db_path = project_root / str(get_database_path())
    if not db_path.exists():
        print(f"❌ Database not found at {db_path}")
        sys.exit(1)
    return duckdb.connect(str(db_path))


def query_event_counts(conn, simulation_year=2025):
    """Query termination event counts by type and category"""
    print(f"\n📊 TERMINATION EVENT COUNTS FOR YEAR {simulation_year}")
    print("=" * 60)

    query = """
    SELECT
        event_type,
        event_category,
        COUNT(*) as event_count,
        COUNT(DISTINCT employee_id) as unique_employees
    FROM fct_yearly_events
    WHERE simulation_year = ?
        AND UPPER(event_type) = 'TERMINATION'
    GROUP BY event_type, event_category
    ORDER BY event_count DESC
    """

    df = conn.execute(query, [simulation_year]).df()

    if df.empty:
        print(f"⚠️  No termination events found for year {simulation_year}")
        return 0
    else:
        print(df.to_string(index=False))
        total_terminations = df["event_count"].sum()
        print(f"\n📈 Total termination events: {total_terminations}")
        return total_terminations


def query_workforce_snapshot_status(conn, simulation_year=2025):
    """Query employment status counts in workforce snapshot"""
    print(f"\n👥 WORKFORCE SNAPSHOT STATUS COUNTS FOR YEAR {simulation_year}")
    print("=" * 60)

    query = """
    SELECT
        employment_status,
        COUNT(*) as employee_count,
        AVG(employee_gross_compensation) as avg_compensation,
        MIN(employee_gross_compensation) as min_compensation,
        MAX(employee_gross_compensation) as max_compensation
    FROM fct_workforce_snapshot
    WHERE simulation_year = ?
    GROUP BY employment_status
    ORDER BY employee_count DESC
    """

    df = conn.execute(query, [simulation_year]).df()

    if df.empty:
        print(f"⚠️  No workforce snapshot found for year {simulation_year}")
        return 0
    else:
        print(df.to_string(index=False))
        terminated_count = df[df["employment_status"] == "terminated"][
            "employee_count"
        ].sum()
        print(f"\n📈 Terminated employees in snapshot: {terminated_count}")
        return terminated_count


def trace_termination_application(conn, simulation_year=2025):
    """Trace how termination events are applied in workforce snapshot"""
    print(f"\n🔍 TRACING TERMINATION APPLICATION LOGIC")
    print("=" * 60)

    # Get the base workforce count
    base_query = """
    SELECT COUNT(*) as base_workforce_count
    FROM int_workforce_previous_year_v2
    WHERE simulation_year = ?
    """
    base_count = (
        conn.execute(base_query, [simulation_year]).df().iloc[0]["base_workforce_count"]
    )
    print(f"Base workforce count: {base_count}")

    # Check the JOIN between base workforce and current year events
    join_query = """
    WITH base_workforce AS (
        SELECT employee_id, employment_status, employee_gross_compensation
        FROM int_workforce_previous_year_v2
        WHERE simulation_year = ?
    ),
    current_year_events AS (
        SELECT DISTINCT employee_id, event_type, event_category
        FROM fct_yearly_events
        WHERE simulation_year = ?
            AND UPPER(event_type) = 'TERMINATION'
    )
    SELECT
        COUNT(bw.employee_id) as base_employees,
        COUNT(cye.employee_id) as termination_events,
        COUNT(CASE WHEN cye.employee_id IS NOT NULL THEN 1 END) as successful_joins
    FROM base_workforce bw
    LEFT JOIN current_year_events cye ON bw.employee_id = cye.employee_id
    """

    join_df = conn.execute(join_query, [simulation_year, simulation_year]).df()
    print("\nJOIN Analysis:")
    print(join_df.to_string(index=False))

    # Check for specific termination logic issues
    termination_logic_query = """
    WITH base_workforce AS (
        SELECT employee_id, employment_status, employee_gross_compensation
        FROM int_workforce_previous_year_v2
        WHERE simulation_year = ?
    ),
    current_year_events AS (
        SELECT DISTINCT employee_id, event_type, event_category
        FROM fct_yearly_events
        WHERE simulation_year = ?
            AND UPPER(event_type) = 'TERMINATION'
    ),
    workforce_after_terminations AS (
        SELECT
            bw.employee_id,
            CASE
                WHEN cye.event_type IS NOT NULL THEN 'terminated'
                ELSE bw.employment_status
            END as employment_status,
            bw.employee_gross_compensation
        FROM base_workforce bw
        LEFT JOIN current_year_events cye ON bw.employee_id = cye.employee_id
    )
    SELECT
        employment_status,
        COUNT(*) as count_after_terminations
    FROM workforce_after_terminations
    GROUP BY employment_status
    ORDER BY count_after_terminations DESC
    """

    termination_df = conn.execute(
        termination_logic_query, [simulation_year, simulation_year]
    ).df()
    print("\nStatus after termination logic:")
    print(termination_df.to_string(index=False))


def sample_employee_tracing(conn, simulation_year=2025, sample_size=3):
    """Trace specific employees through the termination logic"""
    print(f"\n🔬 SAMPLE EMPLOYEE TRACING")
    print("=" * 60)

    # Get sample employees who should be terminated
    sample_query = """
    SELECT DISTINCT employee_id
    FROM fct_yearly_events
    WHERE simulation_year = ?
        AND UPPER(event_type) = 'TERMINATION'
    LIMIT ?
    """

    sample_employees = conn.execute(sample_query, [simulation_year, sample_size]).df()

    if sample_employees.empty:
        print("❌ No terminated employees found to trace")
        return

    for _, row in sample_employees.iterrows():
        employee_id = row["employee_id"]
        print(f"\n--- Tracing Employee: {employee_id} ---")

        # Check in base workforce
        base_check = """
        SELECT employee_id, employment_status, employee_gross_compensation
        FROM int_workforce_previous_year_v2
        WHERE simulation_year = ? AND employee_id = ?
        """
        base_df = conn.execute(base_check, [simulation_year, employee_id]).df()

        if not base_df.empty:
            print(
                f"✅ Found in base workforce: status={base_df.iloc[0]['employment_status']}"
            )
        else:
            print("❌ NOT found in base workforce")
            continue

        # Check termination events
        event_check = """
        SELECT event_type, event_category, effective_date
        FROM fct_yearly_events
        WHERE simulation_year = ? AND employee_id = ? AND UPPER(event_type) = 'TERMINATION'
        """
        event_df = conn.execute(event_check, [simulation_year, employee_id]).df()

        if not event_df.empty:
            print(
                f"✅ Found termination event: category={event_df.iloc[0]['event_category']}"
            )
        else:
            print("❌ No termination event found")
            continue

        # Check final status in workforce snapshot
        final_check = """
        SELECT employment_status, employee_gross_compensation
        FROM fct_workforce_snapshot
        WHERE simulation_year = ? AND employee_id = ?
        """
        final_df = conn.execute(final_check, [simulation_year, employee_id]).df()

        if not final_df.empty:
            final_status = final_df.iloc[0]["employment_status"]
            print(f"📋 Final status in snapshot: {final_status}")
            if final_status != "terminated":
                print("🚨 ISSUE: Employee should be terminated but isn't!")
        else:
            print("❌ Employee not found in final snapshot")


def validate_join_conditions(conn, simulation_year=2025):
    """Validate JOIN conditions and data quality"""
    print(f"\n🔧 VALIDATING JOIN CONDITIONS AND DATA QUALITY")
    print("=" * 60)

    # Check for NULL employee IDs
    null_check_query = """
    SELECT
        'base_workforce' as source,
        COUNT(*) as total_records,
        COUNT(employee_id) as non_null_ids,
        COUNT(*) - COUNT(employee_id) as null_ids
    FROM int_workforce_previous_year_v2
    WHERE simulation_year = ?

    UNION ALL

    SELECT
        'termination_events' as source,
        COUNT(*) as total_records,
        COUNT(employee_id) as non_null_ids,
        COUNT(*) - COUNT(employee_id) as null_ids
    FROM fct_yearly_events
    WHERE simulation_year = ? AND UPPER(event_type) = 'TERMINATION'
    """

    null_df = conn.execute(null_check_query, [simulation_year, simulation_year]).df()
    print("NULL ID Analysis:")
    print(null_df.to_string(index=False))

    # Check for case sensitivity issues
    case_check_query = """
    SELECT
        event_type,
        COUNT(*) as count
    FROM fct_yearly_events
    WHERE simulation_year = ?
        AND (UPPER(event_type) = 'TERMINATION' OR LOWER(event_type) = 'termination')
    GROUP BY event_type
    """

    case_df = conn.execute(case_check_query, [simulation_year]).df()
    print("\nCase sensitivity check:")
    print(case_df.to_string(index=False))


def main():
    print("🔍 WORKFORCE TERMINATION LOGIC DEBUGGING")
    print("=" * 80)

    try:
        conn = connect_to_database()

        # Run all debugging steps
        event_count = query_event_counts(conn)
        snapshot_count = query_workforce_snapshot_status(conn)

        print(f"\n📊 VARIANCE ANALYSIS")
        print("=" * 60)
        variance = event_count - snapshot_count
        variance_pct = (variance / max(event_count, 1)) * 100 if event_count > 0 else 0
        print(f"Termination events: {event_count}")
        print(f"Terminated employees: {snapshot_count}")
        print(f"Variance: {variance} ({variance_pct:.1f}%)")

        if variance > 0:
            print(
                "🚨 ISSUE DETECTED: More termination events than terminated employees!"
            )
        else:
            print("✅ Termination counts match")

        trace_termination_application(conn)
        sample_employee_tracing(conn)
        validate_join_conditions(conn)

        conn.close()

    except Exception as e:
        print(f"❌ Error during debugging: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
