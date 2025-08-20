#!/usr/bin/env python3
"""
Validation script to test the deferral rate fix in int_employee_contributions model.
This script validates that the model correctly uses deferral rates from both:
1. Census data (existing employees)
2. Enrollment events (new hires and rate changes)
"""

import sys
from pathlib import Path

import duckdb


def get_connection():
    """Get database connection."""
    db_path = Path("simulation.duckdb")
    return duckdb.connect(str(db_path), read_only=True)


def validate_deferral_rates():
    """Validate that deferral rates are correctly sourced."""
    conn = get_connection()

    print("=" * 80)
    print("DEFERRAL RATE VALIDATION REPORT")
    print("=" * 80)

    # Check census deferral rates
    print("\n1. CENSUS DATA DEFERRAL RATES:")
    print("-" * 40)
    census_query = """
    SELECT
        COUNT(DISTINCT employee_id) AS total_employees,
        COUNT(DISTINCT CASE WHEN employee_deferral_rate > 0 THEN employee_id END) AS employees_with_deferral,
        COUNT(DISTINCT CASE WHEN employee_deferral_rate = 0 THEN employee_id END) AS employees_zero_deferral,
        COUNT(DISTINCT CASE WHEN employee_deferral_rate IS NULL THEN employee_id END) AS employees_null_deferral,
        AVG(CASE WHEN employee_deferral_rate > 0 THEN employee_deferral_rate END) AS avg_deferral_rate
    FROM stg_census_data
    """
    result = conn.execute(census_query).fetchone()
    print(f"  Total employees in census: {result[0]}")
    print(f"  Employees with positive deferral: {result[1]}")
    print(f"  Employees with zero deferral: {result[2]}")
    print(f"  Employees with null deferral: {result[3]}")
    print(
        f"  Average deferral rate (positive only): {result[4]:.2%}"
        if result[4]
        else "  No positive rates"
    )

    # Check enrollment event deferral rates
    print("\n2. ENROLLMENT EVENT DEFERRAL RATES (2025):")
    print("-" * 40)
    enrollment_query = """
    SELECT
        COUNT(DISTINCT employee_id) AS total_enrollments,
        COUNT(DISTINCT CASE WHEN employee_deferral_rate > 0 THEN employee_id END) AS positive_deferral,
        COUNT(DISTINCT CASE WHEN employee_deferral_rate = 0 THEN employee_id END) AS zero_deferral,
        AVG(CASE WHEN employee_deferral_rate > 0 THEN employee_deferral_rate END) AS avg_enrollment_rate
    FROM fct_yearly_events
    WHERE event_type IN ('enrollment', 'enrollment_change')
        AND simulation_year = 2025
        AND employee_deferral_rate IS NOT NULL
    """
    result = conn.execute(enrollment_query).fetchone()
    print(f"  Total enrollment events: {result[0]}")
    print(f"  Enrollments with positive deferral: {result[1]}")
    print(f"  Enrollments with zero deferral: {result[2]}")
    print(
        f"  Average enrollment deferral rate: {result[3]:.2%}"
        if result[3]
        else "  No rates"
    )

    # Check contribution calculations
    print("\n3. CONTRIBUTION CALCULATIONS (2025):")
    print("-" * 40)
    contrib_query = """
    SELECT
        COUNT(DISTINCT employee_id) AS total_contributors,
        COUNT(DISTINCT CASE WHEN current_deferral_rate > 0 THEN employee_id END) AS positive_rate_contributors,
        COUNT(DISTINCT CASE WHEN current_deferral_rate = 0 THEN employee_id END) AS zero_rate_contributors,
        COUNT(DISTINCT CASE WHEN current_deferral_rate = 0.05 THEN employee_id END) AS hardcoded_rate_count,
        COUNT(DISTINCT CASE WHEN deferral_rate_source = 'enrollment_event' THEN employee_id END) AS from_enrollment,
        COUNT(DISTINCT CASE WHEN deferral_rate_source = 'census_data' THEN employee_id END) AS from_census,
        COUNT(DISTINCT CASE WHEN deferral_rate_source = 'default_zero' THEN employee_id END) AS defaulted_zero
    FROM int_employee_contributions
    WHERE simulation_year = 2025
    """
    try:
        result = conn.execute(contrib_query).fetchone()
        print(f"  Total employees with contributions: {result[0]}")
        print(f"  Employees with positive deferral rate: {result[1]}")
        print(f"  Employees with zero deferral rate: {result[2]}")
        print(f"  Employees with 5% rate (potential hardcode): {result[3]}")
        print(f"  Deferral from enrollment events: {result[4]}")
        print(f"  Deferral from census data: {result[5]}")
        print(f"  Defaulted to zero: {result[6]}")
    except Exception as e:
        print(f"  ERROR: Could not query contributions - {e}")
        print(
            "  Model may need to be rebuilt with: dbt run --select int_employee_contributions"
        )

    # Critical validation: Zero deferral should mean zero contributions
    print("\n4. CRITICAL VALIDATION - ZERO DEFERRAL CONTRIBUTIONS:")
    print("-" * 40)
    zero_contrib_query = """
    SELECT
        COUNT(*) AS employees_with_issue,
        SUM(prorated_annual_contributions) AS total_incorrect_contributions
    FROM int_employee_contributions
    WHERE simulation_year = 2025
        AND current_deferral_rate = 0
        AND prorated_annual_contributions > 0
    """
    try:
        result = conn.execute(zero_contrib_query).fetchone()
        if result[0] > 0:
            print(
                f"  ❌ ISSUE FOUND: {result[0]} employees with 0% deferral have contributions!"
            )
            print(f"  Total incorrect contributions: ${result[1]:,.2f}")
        else:
            print("  ✅ PASSED: No employees with 0% deferral have contributions")
    except Exception as e:
        print(f"  ERROR: Could not validate - {e}")

    # Check for all hardcoded 5% rates
    print("\n5. HARDCODED 5% RATE CHECK:")
    print("-" * 40)
    hardcode_check_query = """
    SELECT
        COUNT(DISTINCT ec.employee_id) AS employees_at_5_percent,
        COUNT(DISTINCT CASE
            WHEN sc.employee_deferral_rate != 0.05
            AND fe.employee_deferral_rate != 0.05
            THEN ec.employee_id
        END) AS suspicious_5_percent
    FROM int_employee_contributions ec
    LEFT JOIN stg_census_data sc ON ec.employee_id = sc.employee_id
    LEFT JOIN (
        SELECT DISTINCT employee_id, employee_deferral_rate
        FROM fct_yearly_events
        WHERE event_type IN ('enrollment', 'enrollment_change')
            AND simulation_year = 2025
    ) fe ON ec.employee_id = fe.employee_id
    WHERE ec.simulation_year = 2025
        AND ec.current_deferral_rate = 0.05
    """
    try:
        result = conn.execute(hardcode_check_query).fetchone()
        print(f"  Employees with exactly 5% deferral: {result[0]}")
        if result[1] > 0:
            print(
                f"  ❌ SUSPICIOUS: {result[1]} employees have 5% but not from any source!"
            )
            print("     This suggests the hardcoded value is still being used")
        else:
            print("  ✅ All 5% rates are legitimate (from census or enrollment)")
    except Exception as e:
        print(f"  ERROR: Could not check hardcoded rates - {e}")

    conn.close()
    print("\n" + "=" * 80)
    print("VALIDATION COMPLETE")
    print("=" * 80)


if __name__ == "__main__":
    try:
        validate_deferral_rates()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
