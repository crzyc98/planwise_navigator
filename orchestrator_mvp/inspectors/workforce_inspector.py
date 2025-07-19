"""
Workforce snapshot inspector module for MVP orchestrator.

This module provides inspection and validation functions for the workforce
snapshot table, displaying comprehensive metrics and validation results.
"""

import duckdb
import pandas as pd
from typing import Dict, List, Optional

from ..core.database_manager import get_connection


def inspect_workforce_snapshot(
    simulation_year: int = 2025,
    db_path: str = "simulation.duckdb"
) -> None:
    """
    Inspect and validate the workforce snapshot table.

    Args:
        simulation_year: Year to inspect
        db_path: Path to the DuckDB database
    """
    print(f"\n📊 Inspecting Workforce Snapshot for Year {simulation_year}")
    print("=" * 60)

    conn = get_connection()

    try:
        # First check if the table exists
        tables = conn.execute(
            "SELECT table_name FROM information_schema.tables WHERE table_name = 'fct_workforce_snapshot'"
        ).fetchall()

        if not tables:
            print("❌ ERROR: fct_workforce_snapshot table does not exist!")
            print("   Please run the workforce snapshot generation first.")
            return

        # Validate data quality
        validation_results = validate_snapshot_data_quality(simulation_year, db_path)

        if validation_results["has_issues"]:
            print("\n⚠️  Data Quality Issues Found:")
            for issue in validation_results["issues"]:
                print(f"   - {issue}")
        else:
            print("\n✅ Data Quality: All checks passed")

        # Display workforce metrics
        display_workforce_metrics(simulation_year, db_path)

        # Show event application summary
        show_event_application_summary(simulation_year, db_path)

        # Validate growth target (read actual target from config)
        import os
        import yaml
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "test_config.yaml")
        try:
            with open(config_path, 'r') as f:
                config = yaml.safe_load(f)
            actual_target_rate = config['ops']['run_multi_year_simulation']['config']['target_growth_rate']
            validate_workforce_growth_target(simulation_year, db_path, actual_target_rate)
        except Exception as e:
            print(f"⚠️  Could not read target growth rate from config: {e}")
            validate_workforce_growth_target(simulation_year, db_path)  # fallback to default

        print("\n" + "=" * 60)
        print("✅ Workforce snapshot inspection complete\n")

    except Exception as e:
        print(f"\n❌ ERROR during inspection: {str(e)}")
    finally:
        conn.close()


def validate_snapshot_data_quality(
    simulation_year: int,
    db_path: str
) -> Dict[str, any]:
    """
    Check for data quality issues in the workforce snapshot.

    Args:
        simulation_year: Year to validate
        db_path: Path to the DuckDB database

    Returns:
        Dictionary with validation results
    """
    conn = get_connection()
    issues = []

    try:
        # Check for records in the snapshot
        record_count = conn.execute(f"""
            SELECT COUNT(*) as count
            FROM fct_workforce_snapshot
            WHERE simulation_year = {simulation_year}
        """).fetchone()[0]

        if record_count == 0:
            issues.append(f"No records found for simulation year {simulation_year}")
            return {"has_issues": True, "issues": issues}

        # Check for missing employee IDs
        null_ids = conn.execute(f"""
            SELECT COUNT(*) as count
            FROM fct_workforce_snapshot
            WHERE simulation_year = {simulation_year}
              AND employee_id IS NULL
        """).fetchone()[0]

        if null_ids > 0:
            issues.append(f"{null_ids} records with missing employee IDs")

        # Check for invalid status codes
        invalid_status = conn.execute(f"""
            SELECT employment_status, COUNT(*) as count
            FROM fct_workforce_snapshot
            WHERE simulation_year = {simulation_year}
              AND employment_status NOT IN ('active', 'terminated')
            GROUP BY employment_status
        """).fetchall()

        if invalid_status:
            for employment_status, count in invalid_status:
                issues.append(f"{count} records with invalid status: {employment_status}")

        # Check for negative or null salaries on active employees
        salary_issues = conn.execute(f"""
            SELECT
                SUM(CASE WHEN current_compensation IS NULL THEN 1 ELSE 0 END) as null_count,
                SUM(CASE WHEN current_compensation < 0 THEN 1 ELSE 0 END) as negative_count
            FROM fct_workforce_snapshot
            WHERE simulation_year = {simulation_year}
              AND employment_status = 'active'
        """).fetchone()

        if salary_issues[0] > 0:
            issues.append(f"{salary_issues[0]} active employees with null compensation")
        if salary_issues[1] > 0:
            issues.append(f"{salary_issues[1]} active employees with negative compensation")

        # Check for duplicate employee IDs
        duplicates = conn.execute(f"""
            SELECT employee_id, COUNT(*) as count
            FROM fct_workforce_snapshot
            WHERE simulation_year = {simulation_year}
            GROUP BY employee_id
            HAVING COUNT(*) > 1
        """).fetchall()

        if duplicates:
            issues.append(f"{len(duplicates)} duplicate employee IDs found")

        return {
            "has_issues": len(issues) > 0,
            "issues": issues,
            "record_count": record_count
        }
    finally:
        conn.close()


def display_workforce_metrics(
    simulation_year: int,
    db_path: str
) -> None:
    """
    Calculate and display key workforce metrics.

    Args:
        simulation_year: Year to analyze
        db_path: Path to the DuckDB database
    """
    print("\n📈 Workforce Metrics")
    print("-" * 40)

    conn = get_connection()

    try:
        # Headcount by status
        status_counts = conn.execute(f"""
            SELECT
                employment_status,
                COUNT(*) as count,
                ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER(), 2) as percentage
            FROM fct_workforce_snapshot
            WHERE simulation_year = {simulation_year}
            GROUP BY employment_status
            ORDER BY count DESC
        """).fetchall()

        print("\nHeadcount by Status:")
        for employment_status, count, pct in status_counts:
            print(f"   {employment_status:12} {count:7,} ({pct:5.1f}%)")

        # Compensation statistics for active employees
        comp_stats = conn.execute(f"""
            SELECT
                COUNT(*) as headcount,
                ROUND(SUM(current_compensation), 2) as total_comp,
                ROUND(AVG(current_compensation), 2) as avg_comp,
                ROUND(MIN(current_compensation), 2) as min_comp,
                ROUND(MAX(current_compensation), 2) as max_comp,
                ROUND(PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY current_compensation), 2) as median_comp
            FROM fct_workforce_snapshot
            WHERE simulation_year = {simulation_year}
              AND employment_status = 'active'
              AND current_compensation IS NOT NULL
        """).fetchone()

        if comp_stats and comp_stats[0] > 0:
            print("\nCompensation Statistics (Active Employees):")
            print(f"   Total Payroll:   ${comp_stats[1]:,.0f}")
            print(f"   Average Salary:  ${comp_stats[2]:,.0f}")
            print(f"   Median Salary:   ${comp_stats[5]:,.0f}")
            print(f"   Salary Range:    ${comp_stats[3]:,.0f} - ${comp_stats[4]:,.0f}")

        # Level distribution
        level_dist = conn.execute(f"""
            SELECT
                level_id,
                COUNT(*) as count,
                ROUND(AVG(current_compensation), 2) as avg_salary
            FROM fct_workforce_snapshot
            WHERE simulation_year = {simulation_year}
              AND employment_status = 'active'
            GROUP BY level_id
            ORDER BY level_id
        """).fetchall()

        if level_dist:
            print("\nHeadcount by Level:")
            for level_id, count, avg_sal in level_dist:
                print(f"   Level {level_id}: {count:6,} (avg: ${avg_sal:,.0f})")
    finally:
        conn.close()


def show_event_application_summary(
    simulation_year: int,
    db_path: str
) -> None:
    """
    Summarize how events were applied to create the snapshot.

    Args:
        simulation_year: Year to analyze
        db_path: Path to the DuckDB database
    """
    print("\n🔄 Event Application Summary")
    print("-" * 40)

    conn = get_connection()

    try:
        # Event counts by type
        event_summary = conn.execute(f"""
            SELECT
                event_type,
                COUNT(*) as event_count,
                COUNT(DISTINCT employee_id) as affected_employees
            FROM fct_yearly_events
            WHERE simulation_year = {simulation_year}
            GROUP BY event_type
            ORDER BY event_count DESC
        """).fetchall()

        if event_summary:
            print("\nEvents Applied:")
            total_events = 0
            for event_type, count, employees in event_summary:
                print(f"   {event_type:15} {count:6,} events affecting {employees:,} employees")
                total_events += count
            print(f"   {'Total':15} {total_events:6,} events")
        else:
            print("\n   No events found for this simulation year")

        # Net workforce change
        net_change = conn.execute(f"""
            WITH baseline AS (
                SELECT COUNT(*) as count FROM int_baseline_workforce
            ),
            current AS (
                SELECT COUNT(*) as count
                FROM fct_workforce_snapshot
                WHERE simulation_year = {simulation_year} AND employment_status = 'active'
            )
            SELECT
                b.count as baseline_count,
                c.count as current_count,
                c.count - b.count as net_change
            FROM baseline b, current c
        """).fetchone()

        if net_change:
            print(f"\nWorkforce Change:")
            print(f"   Baseline:    {net_change[0]:,} employees")
            print(f"   Current:     {net_change[1]:,} employees")
            print(f"   Net Change:  {net_change[2]:+,} ({net_change[2]/net_change[0]*100:+.1f}%)")
    finally:
        conn.close()


def validate_workforce_growth_target(
    simulation_year: int,
    db_path: str,
    target_growth_rate: float = 0.05
) -> None:
    """
    Compare actual workforce growth against target.

    Args:
        simulation_year: Year to validate
        db_path: Path to the DuckDB database
        target_growth_rate: Expected growth rate (default 5%)
    """
    print("\n🎯 Growth Target Validation")
    print("-" * 40)

    conn = get_connection()

    try:
        # Calculate actual growth
        growth_data = conn.execute(f"""
            WITH baseline AS (
                SELECT COUNT(*) as count FROM int_baseline_workforce
            ),
            current AS (
                SELECT COUNT(*) as count
                FROM fct_workforce_snapshot
                WHERE simulation_year = {simulation_year} AND employment_status = 'active'
            )
            SELECT
                b.count as baseline,
                c.count as current,
                ROUND((c.count - b.count) * 100.0 / b.count, 2) as actual_growth_pct
            FROM baseline b, current c
        """).fetchone()

        if growth_data:
            baseline, current, actual_growth = growth_data
            target_growth_pct = target_growth_rate * 100
            target_headcount = int(baseline * (1 + target_growth_rate))

            print(f"\nTarget Growth Rate: {target_growth_pct:.1f}%")
            print(f"Actual Growth Rate: {actual_growth:.1f}%")
            print(f"\nTarget Headcount:   {target_headcount:,}")
            print(f"Actual Headcount:   {current:,}")
            print(f"Variance:           {current - target_headcount:+,} ({(actual_growth - target_growth_pct):+.1f}%)")

            # Determine if target was met
            if abs(actual_growth - target_growth_pct) <= 0.5:
                print("\n✅ Growth target achieved (within 0.5% tolerance)")
            elif actual_growth > target_growth_pct:
                print(f"\n⚠️  Growth exceeded target by {actual_growth - target_growth_pct:.1f}%")
            else:
                print(f"\n❌ Growth missed target by {target_growth_pct - actual_growth:.1f}%")
    finally:
        conn.close()
