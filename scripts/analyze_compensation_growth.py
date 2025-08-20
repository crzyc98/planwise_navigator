#!/usr/bin/env python3
"""
from navigator_orchestrator.config import get_database_path
Compensation Growth Analysis Script
Quick analysis tool for analysts to check simulation results
"""

from datetime import datetime
from pathlib import Path

import duckdb
import pandas as pd


def main():
    # Connect to database
    db_path = Path(__file__).parent.parent / str(get_database_path())
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
    if len(growth_df[growth_df["simulation_year"] == 2026]) > 0:
        target = 2.0
        actual = growth_df[growth_df["simulation_year"] == 2026][
            "yoy_growth_pct"
        ].values[0]
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
    cola_rate = param_df[param_df["parameter_name"] == "cola_rate"][
        "parameter_value"
    ].iloc[0]
    print(f"COLA Rate: {cola_rate*100:.1f}%")

    print("\nMerit Rates by Level:")
    merit_df = param_df[param_df["parameter_name"] == "merit_base"]
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
        year_data = cohort_df[cohort_df["simulation_year"] == year]
        if len(year_data) == 2:
            print(f"\nYear {year}:")
            for _, row in year_data.iterrows():
                print(
                    f"  {row['cohort']}: {row['count']:,} employees @ ${row['avg_comp']:,.0f}"
                )

            # Calculate gap
            existing = year_data[year_data["cohort"] == "Existing Employees"][
                "avg_comp"
            ].values[0]
            new_hire = year_data[year_data["cohort"] == "New Hires"]["avg_comp"].values[
                0
            ]
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

    # 5. Compensation Compounding Validation
    print("\n\nCOMPENSATION COMPOUNDING VALIDATION")
    print("-" * 70)

    compounding_results = analyze_compounding_behavior(conn)
    print(compounding_results)

    # 6. Quick Recommendations
    print("\n\nQUICK TUNING SUGGESTIONS")
    print("-" * 70)

    if "actual" in locals():
        if actual < target - 0.2:
            gap = target - actual
            print(f"To close the {gap:.1f}% gap, consider:")
            print(
                f"  • Increase COLA by {gap*0.6:.1f}% (to {(cola_rate + gap*0.006)*100:.1f}%)"
            )
            print(f"  • OR increase merit rates by {gap*0.8:.1f}% across all levels")
            print(f"  • OR reduce new hire volume by {gap*20:.0f} employees")
            print(f"  • OR increase new hire starting salaries by {gap*5:.0f}%")

    print("\n" + "=" * 70)
    print("For detailed parameter tuning, edit: dbt/seeds/comp_levers.csv")
    print("Then run: dbt seed --select comp_levers && dbt run --select stg_comp_levers")
    print("=" * 70)

    conn.close()


def analyze_compounding_behavior(conn):
    """
    Analyze compensation compounding behavior to verify that employees start
    each year with their previous year's post-raise salary.
    """

    # Check if we have multi-year data
    years_query = """
    SELECT DISTINCT simulation_year
    FROM fct_workforce_snapshot
    ORDER BY simulation_year
    """
    years_df = conn.execute(years_query).df()

    if len(years_df) < 2:
        return "No multi-year data found. Run multi-year simulation to validate compounding."

    # Main compounding validation query
    compounding_query = """
    WITH employee_year_over_year AS (
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
    ),
    summary_stats AS (
        SELECT
            COUNT(*) AS total_employees_tracked,
            SUM(CASE WHEN compounding_status = 'CORRECT' THEN 1 ELSE 0 END) AS correct_compounding,
            SUM(CASE WHEN compounding_status = 'INCORRECT_NO_COMPOUND' THEN 1 ELSE 0 END) AS no_compounding,
            SUM(CASE WHEN compounding_status = 'MISMATCH' THEN 1 ELSE 0 END) AS mismatch,
            ROUND(100.0 * SUM(CASE WHEN compounding_status = 'CORRECT' THEN 1 ELSE 0 END) / COUNT(*), 1) AS correct_pct,
            AVG(CASE WHEN compounding_status != 'CORRECT' THEN ABS(salary_discrepancy) END) AS avg_discrepancy,
            SUM(CASE WHEN compounding_status = 'INCORRECT_NO_COMPOUND' THEN salary_discrepancy ELSE 0 END) AS total_lost_compensation
        FROM employee_year_over_year
    )
    SELECT * FROM summary_stats
    """

    summary_df = conn.execute(compounding_query).df()

    if len(summary_df) == 0 or summary_df["total_employees_tracked"].iloc[0] == 0:
        return "No year-over-year employee data found for compounding validation."

    # Format results
    row = summary_df.iloc[0]
    result = []
    result.append(
        f"Employees Tracked Across Years: {int(row['total_employees_tracked']):,}"
    )
    result.append(
        f"Correct Compounding: {int(row['correct_compounding']):,} ({row['correct_pct']:.1f}%)"
    )
    result.append(f"Incorrect (No Compound): {int(row['no_compounding']):,}")
    result.append(f"Mismatches: {int(row['mismatch']):,}")

    if pd.notna(row["avg_discrepancy"]):
        result.append(f"Average Discrepancy: ${row['avg_discrepancy']:,.2f}")

    if pd.notna(row["total_lost_compensation"]):
        result.append(
            f"Total Lost Compensation: ${row['total_lost_compensation']:,.2f}"
        )

    # Add status assessment
    if row["correct_pct"] >= 95:
        result.append(
            "\n✅ COMPOUNDING STATUS: EXCELLENT - Raises are compounding correctly"
        )
    elif row["correct_pct"] >= 90:
        result.append(
            "\n⚠️  COMPOUNDING STATUS: GOOD - Minor compounding issues detected"
        )
    else:
        result.append(
            "\n❌ COMPOUNDING STATUS: POOR - Significant compounding problems found"
        )
        result.append("   → Check int_workforce_previous_year_v2.sql implementation")

    # Show specific examples if there are issues
    if row["correct_pct"] < 100:
        examples_query = """
        WITH employee_year_over_year AS (
            SELECT
                curr.employee_id,
                curr.simulation_year AS current_year,
                prev.full_year_equivalent_compensation AS previous_year_ending_salary,
                curr.current_compensation AS current_year_starting_salary,
                CASE
                    WHEN ABS(curr.current_compensation - prev.full_year_equivalent_compensation) < 0.01 THEN 'CORRECT'
                    WHEN ABS(curr.current_compensation - prev.current_compensation) < 0.01 THEN 'INCORRECT_NO_COMPOUND'
                    ELSE 'MISMATCH'
                END AS compounding_status,
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
        WHERE compounding_status != 'CORRECT'
        ORDER BY ABS(salary_discrepancy) DESC
        LIMIT 5
        """

        examples_df = conn.execute(examples_query).df()

        if len(examples_df) > 0:
            result.append("\nTop Compounding Issues:")
            for _, example in examples_df.iterrows():
                result.append(
                    f"  Employee {example['employee_id']} (Year {int(example['current_year'])}): "
                    f"Expected ${example['previous_year_ending_salary']:,.2f}, "
                    f"Got ${example['current_year_starting_salary']:,.2f} "
                    f"(Diff: ${example['salary_discrepancy']:,.2f})"
                )

    # Check for $176k employee example mentioned in the plan
    example_176k_query = """
    WITH target_employee AS (
        SELECT DISTINCT employee_id
        FROM fct_workforce_snapshot
        WHERE simulation_year = 2025
            AND ABS(current_compensation - 176000) < 1000
            AND employment_status = 'active'
        LIMIT 1
    ),
    progression AS (
        SELECT
            ws.employee_id,
            ws.simulation_year,
            ws.current_compensation AS starting_salary,
            ws.full_year_equivalent_compensation AS ending_salary,
            176000 * POWER(1.043, ws.simulation_year - 2025) AS expected_starting_with_4_3_pct
        FROM fct_workforce_snapshot ws
        INNER JOIN target_employee te ON ws.employee_id = te.employee_id
        WHERE ws.employment_status = 'active'
        ORDER BY ws.simulation_year
    )
    SELECT * FROM progression
    """

    example_df = conn.execute(example_176k_query).df()

    if len(example_df) > 0:
        result.append(f"\nExample: Employee Starting Near $176,000:")
        for _, row in example_df.iterrows():
            year = int(row["simulation_year"])
            expected = row["expected_starting_with_4_3_pct"]
            actual = row["starting_salary"]
            status = "✓" if abs(actual - expected) < 100 else "✗"
            result.append(
                f"  {year}: Expected ${expected:,.2f}, Actual ${actual:,.2f} {status}"
            )

    return "\n".join(result)


if __name__ == "__main__":
    main()
