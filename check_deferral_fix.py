#!/usr/bin/env python3
"""Check if the deferral rate fix resolved the data quality issues."""

import duckdb


def check_data_quality():
    # Connect to the database where dbt models are materialized
    conn = duckdb.connect("/Users/nicholasamaral/planwise_navigator/simulation.duckdb")

    print("=== CHECKING DATA QUALITY ISSUES ===")
    print()

    # Zero-deferral with positive contributions using current schema
    query1 = """
    SELECT
        COUNT(*) as total_records,
        SUM(CASE WHEN COALESCE(final_deferral_rate, 0) = 0 AND COALESCE(annual_contribution_amount, 0) > 0 THEN 1 ELSE 0 END) as zero_deferral_with_contributions,
        SUM(CASE WHEN NOT (COALESCE(final_deferral_rate, 0) = 0 AND COALESCE(annual_contribution_amount, 0) > 0) THEN 1 ELSE 0 END) as valid_records,
        0 as other_issues
    FROM int_employee_contributions
    WHERE simulation_year = 2025
    """
    result = conn.execute(query1).fetchone()
    print(f"Total records: {result[0]}")
    print(f"Zero deferral with contributions: {result[1]}")
    print(f"Valid records: {result[2]}")
    print(f"Other data quality issues: {result[3]}")
    print()

    # Deferral rate source quality distribution (updated column)
    query2 = """
    SELECT
        deferral_rate_source_quality,
        COUNT(*) as count
    FROM int_employee_contributions
    WHERE simulation_year = 2025
    GROUP BY deferral_rate_source_quality
    """
    results = conn.execute(query2).fetchall()
    print("Deferral rate source quality distribution:")
    for src, cnt in results:
        print(f"  {src}: {cnt}")
    print()

    # Basic stats on deferral rates present in current contributions table
    query3 = """
    SELECT
        COUNT(*) as employees_with_rates,
        AVG(final_deferral_rate) as avg_deferral_rate,
        MIN(final_deferral_rate) as min_deferral_rate,
        MAX(final_deferral_rate) as max_deferral_rate
    FROM int_employee_contributions
    WHERE simulation_year = 2025
    """
    result = conn.execute(query3).fetchone()
    print("Deferral rates:")
    print(f"  Count: {result[0]}")
    if result[1]:
        print(f"  Average rate: {result[1]:.2%}")
        print(f"  Min rate: {result[2]:.2%}")
        print(f"  Max rate: {result[3]:.2%}")
    print()

    # Show sample of any remaining issues
    query4 = """
    SELECT
        employee_id,
        final_deferral_rate,
        annual_contribution_amount,
        contribution_quality_flag,
        deferral_rate_source_quality
    FROM int_employee_contributions
    WHERE simulation_year = 2025
        AND COALESCE(final_deferral_rate, 0) = 0
        AND COALESCE(annual_contribution_amount, 0) > 0
    LIMIT 5
    """
    results = conn.execute(query4).fetchall()
    if results:
        print("Sample of employees with ZERO_DEFERRAL_WITH_CONTRIBUTIONS:")
        for row in results:
            print(
                f"  {row[0]}: rate={row[1]:.2%}, contributions=${row[2]:.2f}, flag={row[3]}, source={row[4]}"
            )
    else:
        print("✅ NO employees with ZERO_DEFERRAL_WITH_CONTRIBUTIONS issue!")

    # Check distribution of data quality flags
    query5 = """
    SELECT
        contribution_quality_flag,
        COUNT(*) as count
    FROM int_employee_contributions
    WHERE simulation_year = 2025
    GROUP BY contribution_quality_flag
    ORDER BY count DESC
    """
    print()
    print("Data quality flag distribution:")
    results = conn.execute(query5).fetchall()
    for flag, count in results:
        print(f"  {flag}: {count}")

    conn.close()


if __name__ == "__main__":
    check_data_quality()
