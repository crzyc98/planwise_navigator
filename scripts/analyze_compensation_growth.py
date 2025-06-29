#!/usr/bin/env python3
"""
Compensation Growth Analysis Script
Quick analysis tool for analysts to check simulation results
"""

import duckdb
import pandas as pd
from datetime import datetime
from pathlib import Path

def main():
    # Connect to database
    db_path = Path(__file__).parent.parent / "simulation.duckdb"
    conn = duckdb.connect(str(db_path))

    print("=" * 70)
    print("COMPENSATION GROWTH ANALYSIS")
    print("=" * 70)
    print(f"Analysis Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")

    # 1. Overall Compensation Growth
    growth_query = """
    WITH yearly_comp AS (
        SELECT
            simulation_year,
            AVG(current_compensation) as avg_salary,
            COUNT(*) as employee_count
        FROM main.fct_workforce_snapshot
        WHERE employment_status = 'active'
        GROUP BY simulation_year
    ),
    growth_calc AS (
        SELECT
            simulation_year,
            avg_salary,
            employee_count,
            LAG(avg_salary) OVER (ORDER BY simulation_year) as prev_avg_salary,
            (avg_salary - LAG(avg_salary) OVER (ORDER BY simulation_year))
                / LAG(avg_salary) OVER (ORDER BY simulation_year) * 100 as yoy_growth_pct
        FROM yearly_comp
    )
    SELECT * FROM growth_calc ORDER BY simulation_year
    """

    growth_df = conn.execute(growth_query).df()
    print("YEAR-OVER-YEAR COMPENSATION GROWTH")
    print("-" * 70)
    print(growth_df.round(2).to_string(index=False))

    # Highlight target vs actual
    if len(growth_df[growth_df['simulation_year'] == 2026]) > 0:
        target = 2.0
        actual = growth_df[growth_df['simulation_year'] == 2026]['yoy_growth_pct'].values[0]
        print(f"\n2025-2026 Growth: {actual:.2f}% (Target: {target}%)")
        if abs(actual - target) <= 0.2:
            print("✅ Within target range!")
        else:
            print(f"❌ {actual - target:+.2f}% from target")

    # 2. Current Parameter Settings
    print("\n\nCURRENT COMPENSATION PARAMETERS")
    print("-" * 70)

    param_query = """
    SELECT
        parameter_name,
        job_level,
        parameter_value,
        fiscal_year
    FROM main.stg_comp_levers
    WHERE parameter_name IN ('cola_rate', 'merit_base')
        AND fiscal_year = 2025
    ORDER BY parameter_name, job_level
    """

    param_df = conn.execute(param_query).df()

    # Format parameters nicely
    cola_rate = param_df[param_df['parameter_name'] == 'cola_rate']['parameter_value'].iloc[0]
    print(f"COLA Rate: {cola_rate*100:.1f}%")

    print("\nMerit Rates by Level:")
    merit_df = param_df[param_df['parameter_name'] == 'merit_base']
    for _, row in merit_df.iterrows():
        print(f"  Level {row['job_level']}: {row['parameter_value']*100:.1f}%")

    # 3. New Hire Impact Analysis
    print("\n\nNEW HIRE DILUTION ANALYSIS")
    print("-" * 70)

    cohort_query = """
    WITH cohort_analysis AS (
        SELECT
            simulation_year,
            CASE
                WHEN simulation_year = YEAR(employee_hire_date) THEN 'New Hires'
                ELSE 'Existing Employees'
            END as cohort,
            COUNT(*) as count,
            AVG(current_compensation) as avg_comp
        FROM main.fct_workforce_snapshot
        WHERE employment_status = 'active'
            AND simulation_year IN (2025, 2026)
        GROUP BY 1, 2
    )
    SELECT * FROM cohort_analysis
    ORDER BY simulation_year, cohort DESC
    """

    cohort_df = conn.execute(cohort_query).df()

    for year in [2025, 2026]:
        year_data = cohort_df[cohort_df['simulation_year'] == year]
        if len(year_data) == 2:
            print(f"\nYear {year}:")
            for _, row in year_data.iterrows():
                print(f"  {row['cohort']}: {row['count']:,} employees @ ${row['avg_comp']:,.0f}")

            # Calculate gap
            existing = year_data[year_data['cohort'] == 'Existing Employees']['avg_comp'].values[0]
            new_hire = year_data[year_data['cohort'] == 'New Hires']['avg_comp'].values[0]
            gap = existing - new_hire
            gap_pct = gap / existing * 100
            print(f"  Compensation Gap: ${gap:,.0f} ({gap_pct:.1f}%)")

    # 4. Event Summary
    print("\n\nCOMPENSATION EVENTS SUMMARY (2026)")
    print("-" * 70)

    event_query = """
    SELECT
        event_type,
        COUNT(*) as count,
        AVG(compensation_amount) as avg_comp_at_event
    FROM main.fct_yearly_events
    WHERE simulation_year = 2026
    GROUP BY event_type
    ORDER BY count DESC
    """

    event_df = conn.execute(event_query).df()
    print(event_df.round(0).to_string(index=False))

    # 5. Quick Recommendations
    print("\n\nQUICK TUNING SUGGESTIONS")
    print("-" * 70)

    if 'actual' in locals():
        if actual < target - 0.2:
            gap = target - actual
            print(f"To close the {gap:.1f}% gap, consider:")
            print(f"  • Increase COLA by {gap*0.6:.1f}% (to {(cola_rate + gap*0.006)*100:.1f}%)")
            print(f"  • OR increase merit rates by {gap*0.8:.1f}% across all levels")
            print(f"  • OR reduce new hire volume by {gap*20:.0f} employees")
            print(f"  • OR increase new hire starting salaries by {gap*5:.0f}%")

    print("\n" + "=" * 70)
    print("For detailed parameter tuning, edit: dbt/seeds/comp_levers.csv")
    print("Then run: dbt seed --select comp_levers && dbt run --select stg_comp_levers")
    print("=" * 70)

    conn.close()

if __name__ == "__main__":
    main()
