#!/usr/bin/env python3
"""
Debug script for merit events compensation compounding.

This script traces the compensation values used in merit event generation
to identify where the compounding breaks down. It queries the database to
show the data flow from fct_workforce_snapshot through int_workforce_active_for_events
to int_merit_events for a sample of employees across multiple years.

Usage:
    python scripts/debug_merit_events_compensation.py
    python scripts/debug_merit_events_compensation.py --employee-id EMP123456
    python scripts/debug_merit_events_compensation.py --year 2026 --limit 10
"""

import argparse
import sys
from pathlib import Path
import pandas as pd
import duckdb
from typing import Optional, List

# Add project root to path for imports
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))

DB_PATH = project_root / "simulation.duckdb"


def get_database_connection():
    """Get DuckDB connection to the simulation database."""
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database file not found: {DB_PATH}")
    return duckdb.connect(str(DB_PATH))


def trace_compensation_flow(
    conn: duckdb.DuckDBPyConnection,
    employee_id: Optional[str] = None,
    year: Optional[int] = None,
    limit: int = 5
) -> pd.DataFrame:
    """
    Trace compensation data flow from workforce snapshot through to merit events.

    Args:
        conn: DuckDB connection
        employee_id: Optional specific employee to trace
        year: Optional specific year to examine
        limit: Maximum number of employees to trace

    Returns:
        DataFrame with detailed compensation flow data
    """
    where_clauses = []
    params = []

    if employee_id:
        where_clauses.append("ws.employee_id = ?")
        params.append(employee_id)

    if year:
        where_clauses.append("ws.simulation_year = ?")
        params.append(year)
    else:
        where_clauses.append("ws.simulation_year > 2025")  # Focus on subsequent years

    where_clause = " AND ".join(where_clauses) if where_clauses else "ws.simulation_year > 2025"

    query = f"""
    WITH compensation_flow AS (
        SELECT
            ws.employee_id,
            ws.simulation_year,

            -- Previous year data (what should be used as baseline)
            ws_prev.simulation_year AS prev_year,
            ws_prev.current_compensation AS prev_year_starting_compensation,
            ws_prev.full_year_equivalent_compensation AS prev_year_final_compensation,

            -- Current year starting data
            ws.current_compensation AS current_year_starting_compensation,

            -- int_workforce_active_for_events data (what merit events should see)
            awfe.employee_gross_compensation AS awfe_compensation,

            -- Merit event data (what was actually used)
            me.previous_salary AS merit_baseline_used,
            me.new_salary AS merit_new_salary,
            me.merit_percentage,

            -- Diagnostic flags
            CASE
                WHEN ws.current_compensation = ws_prev.full_year_equivalent_compensation THEN 'CORRECT'
                WHEN ws.current_compensation = ws_prev.current_compensation THEN 'NO_COMPOUND'
                ELSE 'MISMATCH'
            END AS year_transition_status,

            CASE
                WHEN ABS(awfe.employee_gross_compensation - ws_prev.full_year_equivalent_compensation) < 0.01 THEN 'CORRECT'
                WHEN ABS(awfe.employee_gross_compensation - ws_prev.current_compensation) < 0.01 THEN 'USING_STARTING'
                ELSE 'UNKNOWN_SOURCE'
            END AS awfe_source_status,

            CASE
                WHEN ABS(me.previous_salary - awfe.employee_gross_compensation) < 0.01 THEN 'CORRECT'
                WHEN ABS(me.previous_salary - ws.current_compensation) < 0.01 THEN 'USING_CURRENT_YEAR'
                ELSE 'UNKNOWN_BASELINE'
            END AS merit_baseline_status,

            -- Discrepancies
            ws.current_compensation - ws_prev.full_year_equivalent_compensation AS starting_comp_discrepancy,
            awfe.employee_gross_compensation - ws_prev.full_year_equivalent_compensation AS awfe_discrepancy,
            me.previous_salary - awfe.employee_gross_compensation AS merit_baseline_discrepancy

        FROM fct_workforce_snapshot ws
        LEFT JOIN fct_workforce_snapshot ws_prev
            ON ws.employee_id = ws_prev.employee_id
            AND ws_prev.simulation_year = ws.simulation_year - 1
            AND ws_prev.employment_status = 'active'
        LEFT JOIN int_workforce_active_for_events awfe
            ON ws.employee_id = awfe.employee_id
            AND ws.simulation_year = awfe.simulation_year
        LEFT JOIN (
            SELECT
                employee_id,
                simulation_year,
                previous_salary,
                new_salary,
                merit_percentage
            FROM fct_yearly_events
            WHERE event_category = 'RAISE'
        ) me
            ON ws.employee_id = me.employee_id
            AND ws.simulation_year = me.simulation_year
        WHERE {where_clause}
            AND ws.employment_status = 'active'
            AND ws_prev.employee_id IS NOT NULL  -- Ensure we have previous year data
        ORDER BY
            ws.simulation_year,
            ABS(COALESCE(starting_comp_discrepancy, 0)) DESC,
            ws.employee_id
        LIMIT {limit}
    )
    SELECT * FROM compensation_flow
    """

    return conn.execute(query, params).df()


def analyze_merit_event_patterns(
    conn: duckdb.DuckDBPyConnection,
    year: Optional[int] = None
) -> pd.DataFrame:
    """
    Analyze merit event generation patterns to identify compounding issues.

    Args:
        conn: DuckDB connection
        year: Optional specific year to analyze

    Returns:
        DataFrame with merit event pattern analysis
    """
    where_clause = f"WHERE simulation_year = {year}" if year else "WHERE simulation_year > 2025"

    query = f"""
    WITH merit_patterns AS (
        SELECT
            simulation_year,
            COUNT(*) as total_merit_events,

            -- Baseline compensation statistics
            MIN(previous_salary) as min_baseline,
            MAX(previous_salary) as max_baseline,
            AVG(previous_salary) as avg_baseline,
            STDDEV(previous_salary) as stddev_baseline,

            -- Merit percentage statistics
            MIN(merit_percentage) as min_merit_pct,
            MAX(merit_percentage) as max_merit_pct,
            AVG(merit_percentage) as avg_merit_pct,

            -- Salary increase statistics
            MIN(new_salary - previous_salary) as min_increase,
            MAX(new_salary - previous_salary) as max_increase,
            AVG(new_salary - previous_salary) as avg_increase,

            -- Check for identical baselines (sign of non-compounding)
            COUNT(DISTINCT previous_salary) as unique_baselines,
            COUNT(*) - COUNT(DISTINCT previous_salary) as duplicate_baseline_count

        FROM fct_yearly_events
        {where_clause}
            AND event_category = 'RAISE'
        GROUP BY simulation_year
        ORDER BY simulation_year
    )
    SELECT
        *,
        -- Calculate metrics that indicate compounding issues
        CASE
            WHEN duplicate_baseline_count > (total_merit_events * 0.1) THEN 'HIGH_DUPLICATES'
            WHEN duplicate_baseline_count > 0 THEN 'SOME_DUPLICATES'
            ELSE 'NO_DUPLICATES'
        END as baseline_duplication_status,

        ROUND(100.0 * duplicate_baseline_count / total_merit_events, 2) as duplicate_baseline_pct

    FROM merit_patterns
    """

    return conn.execute(query).df()


def compare_year_over_year_merit_counts(conn: duckdb.DuckDBPyConnection) -> pd.DataFrame:
    """
    Compare merit event counts year over year to detect compounding issues.

    If compensation is properly compounding, merit event counts should vary
    between years as different employees become eligible at different rates.

    Args:
        conn: DuckDB connection

    Returns:
        DataFrame comparing merit counts across years
    """
    query = """
    WITH yearly_counts AS (
        SELECT
            simulation_year,
            COUNT(*) as merit_events,
            COUNT(DISTINCT employee_id) as unique_employees,
            AVG(merit_percentage) as avg_merit_pct,
            AVG(previous_salary) as avg_baseline_salary
        FROM fct_yearly_events
        WHERE event_category = 'RAISE'
        GROUP BY simulation_year
        ORDER BY simulation_year
    )
    SELECT
        *,
        merit_events - LAG(merit_events) OVER (ORDER BY simulation_year) as count_change_from_prev,
        ROUND(
            100.0 * (merit_events - LAG(merit_events) OVER (ORDER BY simulation_year)) /
            LAG(merit_events) OVER (ORDER BY simulation_year), 2
        ) as pct_change_from_prev,
        avg_baseline_salary - LAG(avg_baseline_salary) OVER (ORDER BY simulation_year) as baseline_salary_change
    FROM yearly_counts
    """

    return conn.execute(query).df()


def export_detailed_employee_progression(
    conn: duckdb.DuckDBPyConnection,
    output_file: Optional[str] = None,
    limit: int = 20
) -> pd.DataFrame:
    """
    Export detailed compensation progression for specific employees.

    Args:
        conn: DuckDB connection
        output_file: Optional CSV file path to export results
        limit: Maximum number of employees to include

    Returns:
        DataFrame with detailed employee progression
    """
    query = f"""
    WITH employee_progression AS (
        SELECT
            ws.employee_id,
            ws.simulation_year,
            ws.current_compensation,
            ws.full_year_equivalent_compensation,

            -- Merit event data for this year
            me.previous_salary as merit_baseline,
            me.new_salary as merit_result,
            me.merit_percentage,

            -- Previous year comparison
            LAG(ws.full_year_equivalent_compensation) OVER (
                PARTITION BY ws.employee_id ORDER BY ws.simulation_year
            ) as prev_year_final_comp,

            -- Compounding validation
            ws.current_compensation - LAG(ws.full_year_equivalent_compensation) OVER (
                PARTITION BY ws.employee_id ORDER BY ws.simulation_year
            ) as compound_discrepancy

        FROM fct_workforce_snapshot ws
        LEFT JOIN (
            SELECT
                employee_id, simulation_year, previous_salary, new_salary, merit_percentage
            FROM fct_yearly_events
            WHERE event_category = 'RAISE'
        ) me ON ws.employee_id = me.employee_id AND ws.simulation_year = me.simulation_year
        WHERE ws.employment_status = 'active'
            AND ws.simulation_year BETWEEN 2025 AND 2028
    )
    SELECT
        employee_id,
        simulation_year,
        current_compensation,
        full_year_equivalent_compensation,
        merit_baseline,
        merit_result,
        merit_percentage,
        prev_year_final_comp,
        compound_discrepancy,

        -- Status flags
        CASE
            WHEN ABS(COALESCE(compound_discrepancy, 0)) < 0.01 THEN 'CORRECT'
            WHEN compound_discrepancy IS NULL THEN 'FIRST_YEAR'
            ELSE 'DISCREPANCY'
        END as compounding_status

    FROM employee_progression
    WHERE employee_id IN (
        SELECT employee_id
        FROM employee_progression
        WHERE simulation_year > 2025
            AND ABS(COALESCE(compound_discrepancy, 0)) > 100
        LIMIT {limit}
    )
    ORDER BY employee_id, simulation_year
    """

    df = conn.execute(query).df()

    if output_file:
        df.to_csv(output_file, index=False)
        print(f"Detailed employee progression exported to: {output_file}")

    return df


def main():
    """Main function to run merit events compensation debugging."""
    parser = argparse.ArgumentParser(description="Debug merit events compensation compounding")
    parser.add_argument("--employee-id", help="Specific employee ID to trace")
    parser.add_argument("--year", type=int, help="Specific year to examine")
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of employees to trace")
    parser.add_argument("--export", help="Export detailed results to CSV file")
    parser.add_argument("--patterns-only", action="store_true", help="Only show merit event patterns")

    args = parser.parse_args()

    try:
        conn = get_database_connection()

        print("🔍 Merit Events Compensation Debugging")
        print("=" * 50)

        if args.patterns_only:
            print("\n📊 Merit Event Patterns Analysis")
            patterns_df = analyze_merit_event_patterns(conn, args.year)
            print(patterns_df.to_string(index=False))

            print("\n📈 Year-over-Year Merit Count Comparison")
            yoy_df = compare_year_over_year_merit_counts(conn)
            print(yoy_df.to_string(index=False))

        else:
            print(f"\n🔄 Tracing Compensation Flow")
            if args.employee_id:
                print(f"   Employee: {args.employee_id}")
            if args.year:
                print(f"   Year: {args.year}")
            print(f"   Limit: {args.limit}")

            flow_df = trace_compensation_flow(conn, args.employee_id, args.year, args.limit)

            if flow_df.empty:
                print("❌ No data found matching the specified criteria")
                return

            print(f"\n📋 Found {len(flow_df)} employees to trace")

            # Display key columns in a readable format
            display_columns = [
                'employee_id', 'simulation_year', 'prev_year_final_compensation',
                'current_year_starting_compensation', 'awfe_compensation',
                'merit_baseline_used', 'merit_new_salary',
                'year_transition_status', 'awfe_source_status', 'merit_baseline_status'
            ]

            print("\n📊 Compensation Flow Summary:")
            for col in display_columns:
                if col in flow_df.columns:
                    continue
            print(flow_df[display_columns].to_string(index=False))

            # Show discrepancies
            print("\n⚠️ Discrepancy Analysis:")
            discrepancy_cols = [
                'employee_id', 'simulation_year',
                'starting_comp_discrepancy', 'awfe_discrepancy', 'merit_baseline_discrepancy'
            ]
            discrepancies = flow_df[discrepancy_cols]
            print(discrepancies.to_string(index=False))

            # Summary statistics
            print(f"\n📈 Status Summary:")
            print(f"Year Transition Status:")
            print(flow_df['year_transition_status'].value_counts().to_string())
            print(f"\nAWFE Source Status:")
            print(flow_df['awfe_source_status'].value_counts().to_string())
            print(f"\nMerit Baseline Status:")
            print(flow_df['merit_baseline_status'].value_counts().to_string())

        # Export detailed progression if requested
        if args.export:
            print(f"\n💾 Exporting detailed employee progression...")
            export_detailed_employee_progression(conn, args.export, args.limit * 2)

        print(f"\n✅ Analysis complete!")

    except Exception as e:
        print(f"❌ Error during analysis: {str(e)}")
        sys.exit(1)
    finally:
        if 'conn' in locals():
            conn.close()


if __name__ == "__main__":
    main()
