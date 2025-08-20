#!/usr/bin/env python3
"""
from navigator_orchestrator.config import get_database_path
Debug script for investigating $25M compensation anomaly in workforce simulation.
Traces extreme salary values back through the event history to identify the root cause
of unrealistic compensation calculations.
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


def identify_extreme_salaries(conn, threshold=5000000):
    """Identify employees with extreme compensation values"""
    print(f"\n💰 IDENTIFYING EXTREME SALARIES (>${threshold:,})")
    print("=" * 70)

    query = """
    SELECT DISTINCT
        employee_id,
        simulation_year,
        employee_gross_compensation,
        employment_status,
        level_id
    FROM fct_workforce_snapshot
    WHERE employee_gross_compensation > ?
    ORDER BY employee_gross_compensation DESC, simulation_year DESC
    LIMIT 20
    """

    df = conn.execute(query, [threshold]).df()

    if df.empty:
        print(f"✅ No employees found with compensation above ${threshold:,}")
        return pd.DataFrame()
    else:
        print(f"🚨 Found {len(df)} extreme salary records:")
        for _, row in df.iterrows():
            print(
                f"  Employee {row['employee_id']}: ${row['employee_gross_compensation']:,.2f} "
                f"(Year {row['simulation_year']}, Level {row['level_id']}, Status: {row['employment_status']})"
            )
        return df


def trace_event_history(conn, employee_id, max_years=5):
    """Trace complete event history for a specific employee"""
    print(f"\n📈 EVENT HISTORY FOR EMPLOYEE: {employee_id}")
    print("=" * 70)

    query = """
    SELECT
        simulation_year,
        event_type,
        event_category,
        effective_date,
        employee_gross_compensation,
        level_id,
        additional_info
    FROM fct_yearly_events
    WHERE employee_id = ?
    ORDER BY simulation_year ASC, effective_date ASC
    LIMIT ?
    """

    df = conn.execute(
        query, [employee_id, max_years * 10]
    ).df()  # Assume max 10 events per year

    if df.empty:
        print(f"❌ No event history found for employee {employee_id}")
        return

    print("Event progression:")
    for _, row in df.iterrows():
        comp_str = (
            f"${row['employee_gross_compensation']:,.2f}"
            if pd.notna(row["employee_gross_compensation"])
            else "N/A"
        )
        level_str = f"L{row['level_id']}" if pd.notna(row["level_id"]) else "N/A"
        print(
            f"  {row['simulation_year']}: {row['event_type']} ({row['event_category']}) -> {comp_str} ({level_str})"
        )


def analyze_promotion_logic(conn, simulation_year=2025):
    """Analyze promotion calculation logic for unrealistic increases"""
    print(f"\n🔍 ANALYZING PROMOTION LOGIC FOR YEAR {simulation_year}")
    print("=" * 70)

    query = """
    SELECT
        employee_id,
        employee_gross_compensation as new_compensation,
        additional_info,
        level_id
    FROM fct_yearly_events
    WHERE simulation_year = ?
        AND UPPER(event_type) = 'PROMOTION'
    ORDER BY employee_gross_compensation DESC
    LIMIT 10
    """

    df = conn.execute(query, [simulation_year]).df()

    if df.empty:
        print(f"❌ No promotions found for year {simulation_year}")
        return

    print("Top promotion compensations:")
    for _, row in df.iterrows():
        print(
            f"  Employee {row['employee_id']}: ${row['new_compensation']:,.2f} (Level {row['level_id']})"
        )
        if pd.notna(row["additional_info"]):
            print(f"    Info: {row['additional_info']}")

    # Check for multiple promotions per employee
    multiple_promotions_query = """
    SELECT
        employee_id,
        COUNT(*) as promotion_count,
        MIN(employee_gross_compensation) as min_comp,
        MAX(employee_gross_compensation) as max_comp
    FROM fct_yearly_events
    WHERE simulation_year = ?
        AND UPPER(event_type) = 'PROMOTION'
    GROUP BY employee_id
    HAVING COUNT(*) > 1
    ORDER BY promotion_count DESC
    """

    multiple_df = conn.execute(multiple_promotions_query, [simulation_year]).df()

    if not multiple_df.empty:
        print("\n🚨 Employees with multiple promotions:")
        for _, row in multiple_df.iterrows():
            print(
                f"  Employee {row['employee_id']}: {row['promotion_count']} promotions "
                f"(${row['min_comp']:,.2f} -> ${row['max_comp']:,.2f})"
            )


def investigate_merit_cola_calculations(conn, simulation_year=2025):
    """Investigate merit and COLA calculation logic"""
    print(f"\n📊 ANALYZING MERIT/COLA CALCULATIONS FOR YEAR {simulation_year}")
    print("=" * 70)

    query = """
    SELECT
        employee_id,
        event_category,
        employee_gross_compensation,
        additional_info,
        level_id
    FROM fct_yearly_events
    WHERE simulation_year = ?
        AND UPPER(event_type) = 'RAISE'
    ORDER BY employee_gross_compensation DESC
    LIMIT 10
    """

    df = conn.execute(query, [simulation_year]).df()

    if df.empty:
        print(f"❌ No merit/COLA raises found for year {simulation_year}")
        return

    print("Top merit/COLA raises:")
    for _, row in df.iterrows():
        print(
            f"  Employee {row['employee_id']}: ${row['new_compensation']:,.2f} "
            f"({row['event_category']}, Level {row['level_id']})"
        )
        if pd.notna(row["additional_info"]):
            print(f"    Info: {row['additional_info']}")


def check_seed_data_configuration(conn):
    """Check configuration tables for unrealistic compensation ranges"""
    print(f"\n⚙️  CHECKING SEED DATA CONFIGURATION")
    print("=" * 70)

    # Check job levels configuration
    job_levels_query = """
    SELECT
        level_id,
        level_name,
        min_salary,
        max_salary,
        target_salary
    FROM stg_config_job_levels
    ORDER BY level_id
    """

    try:
        df = conn.execute(job_levels_query).df()
        print("Job level salary ranges:")
        for _, row in df.iterrows():
            print(
                f"  Level {row['level_id']} ({row['level_name']}): "
                f"${row['min_salary']:,.0f} - ${row['max_salary']:,.0f} "
                f"(Target: ${row['target_salary']:,.0f})"
            )

            if row["max_salary"] > 10000000:  # $10M threshold
                print(
                    f"    🚨 WARNING: Extremely high max salary for level {row['level_id']}"
                )

    except Exception as e:
        print(f"❌ Could not query job levels: {e}")

    # Check hazard table for merit percentages
    hazard_query = """
    SELECT
        level_id,
        merit_increase_pct,
        promotion_probability,
        termination_probability
    FROM dim_hazard_table
    ORDER BY level_id
    LIMIT 10
    """

    try:
        hazard_df = conn.execute(hazard_query).df()
        print("\nHazard table merit percentages:")
        for _, row in hazard_df.iterrows():
            print(
                f"  Level {row['level_id']}: Merit {row['merit_increase_pct']*100:.1f}% "
                f"Promo {row['promotion_probability']*100:.1f}% "
                f"Term {row['termination_probability']*100:.1f}%"
            )

            if row["merit_increase_pct"] > 0.5:  # >50% merit increase
                print(
                    f"    🚨 WARNING: Extremely high merit increase for level {row['level_id']}"
                )

    except Exception as e:
        print(f"❌ Could not query hazard table: {e}")


def validate_level_corrections(conn, simulation_year=2025):
    """Validate level correction logic in workforce snapshot"""
    print(f"\n🔧 VALIDATING LEVEL CORRECTIONS FOR YEAR {simulation_year}")
    print("=" * 70)

    query = """
    SELECT
        employee_id,
        level_id,
        employee_gross_compensation,
        employment_status
    FROM fct_workforce_snapshot
    WHERE simulation_year = ?
        AND employee_gross_compensation > 1000000
    ORDER BY employee_gross_compensation DESC
    LIMIT 10
    """

    df = conn.execute(query, [simulation_year]).df()

    if df.empty:
        print("✅ No employees with compensation > $1M found")
        return

    print("High-compensation employees in final snapshot:")
    for _, row in df.iterrows():
        print(
            f"  Employee {row['employee_id']}: ${row['employee_gross_compensation']:,.2f} "
            f"(Level {row['level_id']}, Status: {row['employment_status']})"
        )


def detect_compounding_issues(conn, simulation_year=2025):
    """Detect employees with multiple events that could compound salary increases"""
    print(f"\n🔍 DETECTING COMPOUNDING SALARY ISSUES FOR YEAR {simulation_year}")
    print("=" * 70)

    query = """
    SELECT
        employee_id,
        COUNT(*) as total_events,
        COUNT(CASE WHEN UPPER(event_type) = 'PROMOTION' THEN 1 END) as promotions,
        COUNT(CASE WHEN UPPER(event_type) = 'RAISE' THEN 1 END) as raises,
        MIN(employee_gross_compensation) as min_comp,
        MAX(employee_gross_compensation) as max_comp,
        MAX(employee_gross_compensation) - MIN(employee_gross_compensation) as comp_increase
    FROM fct_yearly_events
    WHERE simulation_year = ?
        AND UPPER(event_type) IN ('PROMOTION', 'RAISE')
    GROUP BY employee_id
    HAVING COUNT(*) > 1
    ORDER BY comp_increase DESC
    LIMIT 15
    """

    df = conn.execute(query, [simulation_year]).df()

    if df.empty:
        print("✅ No employees with multiple compensation events found")
        return

    print("Employees with multiple compensation events:")
    for _, row in df.iterrows():
        print(
            f"  Employee {row['employee_id']}: {row['total_events']} events "
            f"({row['promotions']} promotions, {row['raises']} raises)"
        )
        print(
            f"    Compensation change: ${row['min_comp']:,.2f} -> ${row['max_comp']:,.2f} "
            f"(+${row['comp_increase']:,.2f})"
        )


def main():
    print("💰 COMPENSATION ANOMALY INVESTIGATION")
    print("=" * 80)

    try:
        conn = connect_to_database()

        # Identify extreme salaries
        extreme_df = identify_extreme_salaries(conn)

        if not extreme_df.empty:
            # Trace history for top 3 extreme salary cases
            print(f"\n🔬 DETAILED ANALYSIS OF TOP CASES")
            print("=" * 80)

            top_cases = extreme_df.head(3)
            for _, row in top_cases.iterrows():
                trace_event_history(conn, row["employee_id"])
                print()

        # Analyze calculation logic components
        analyze_promotion_logic(conn)
        investigate_merit_cola_calculations(conn)
        check_seed_data_configuration(conn)
        validate_level_corrections(conn)
        detect_compounding_issues(conn)

        print(f"\n📋 SUMMARY")
        print("=" * 80)

        # Final summary query
        summary_query = """
        SELECT
            'Total employees' as metric,
            COUNT(DISTINCT employee_id) as value
        FROM fct_workforce_snapshot
        WHERE simulation_year = 2025

        UNION ALL

        SELECT
            'Employees > $1M' as metric,
            COUNT(DISTINCT employee_id) as value
        FROM fct_workforce_snapshot
        WHERE simulation_year = 2025 AND employee_gross_compensation > 1000000

        UNION ALL

        SELECT
            'Employees > $5M' as metric,
            COUNT(DISTINCT employee_id) as value
        FROM fct_workforce_snapshot
        WHERE simulation_year = 2025 AND employee_gross_compensation > 5000000

        UNION ALL

        SELECT
            'Max compensation' as metric,
            MAX(employee_gross_compensation) as value
        FROM fct_workforce_snapshot
        WHERE simulation_year = 2025
        """

        summary_df = conn.execute(summary_query).df()
        print("Key metrics:")
        for _, row in summary_df.iterrows():
            if "Max compensation" in row["metric"]:
                print(f"  {row['metric']}: ${row['value']:,.2f}")
            else:
                print(f"  {row['metric']}: {row['value']:,}")

        conn.close()

    except Exception as e:
        print(f"❌ Error during investigation: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
