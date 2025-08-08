#!/usr/bin/env python3
"""Check if EMP_2024_000001 contributions are fixed."""

import duckdb

conn = duckdb.connect('/Users/nicholasamaral/planwise_navigator/simulation.duckdb')

# Check EMP_2024_000001 specifically
query = """
SELECT
    employee_id,
    simulation_year,
    current_deferral_rate,
    prorated_annual_contributions,
    irs_limited_annual_contributions,
    effective_deferral_rate,
    is_enrolled,
    deferral_rate_source,
    data_quality_flag
FROM int_employee_contributions
WHERE employee_id = 'EMP_2024_000001'
    AND simulation_year = 2025
"""

print("=== CHECKING EMP_2024_000001 AFTER FIX ===")
print()

result = conn.execute(query).fetchone()
if result:
    print(f"Employee ID: {result[0]}")
    print(f"Simulation Year: {result[1]}")
    print(f"Current Deferral Rate: {result[2]:.4f} ({result[2]*100:.2f}%)")
    print(f"Prorated Annual Contributions: ${result[3]:.2f}")
    print(f"IRS Limited Contributions: ${result[4]:.2f}")
    print(f"Effective Deferral Rate: {result[5]:.4f} ({result[5]*100:.2f}%)")
    print(f"Is Enrolled: {result[6]}")
    print(f"Deferral Rate Source: {result[7]}")
    print(f"Data Quality Flag: {result[8]}")

    if result[3] > 0 and result[2] == 0:
        print("\n❌ ISSUE STILL EXISTS: Employee has $0 deferral rate but positive contributions!")
    elif result[3] == 0 and result[2] == 0:
        print("\n✅ FIXED: Employee with 0% deferral rate correctly has $0 contributions!")
    else:
        print(f"\n✅ Employee has {result[2]*100:.2f}% deferral rate and ${result[3]:.2f} contributions (consistent)")
else:
    print("Employee EMP_2024_000001 not found in contributions table (may have been filtered out)")

# Check if employee exists in base data
query2 = """
SELECT
    employee_id,
    employee_deferral_rate
FROM stg_census_data
WHERE employee_id = 'EMP_2024_000001'
"""
result2 = conn.execute(query2).fetchone()
if result2:
    print(f"\nCensus data shows deferral rate: {result2[1]:.4f} ({result2[1]*100:.2f}%)")

# Check overall statistics
query3 = """
SELECT
    COUNT(*) as total,
    SUM(CASE WHEN current_deferral_rate = 0 AND prorated_annual_contributions > 0 THEN 1 ELSE 0 END) as zero_rate_with_contributions,
    SUM(CASE WHEN data_quality_flag = 'ZERO_DEFERRAL_WITH_CONTRIBUTIONS' THEN 1 ELSE 0 END) as flagged_issues
FROM int_employee_contributions
WHERE simulation_year = 2025
"""
result3 = conn.execute(query3).fetchone()
print(f"\n=== OVERALL STATISTICS ===")
print(f"Total employees: {result3[0]}")
print(f"Zero rate with contributions (actual): {result3[1]}")
print(f"Flagged as ZERO_DEFERRAL_WITH_CONTRIBUTIONS: {result3[2]}")

conn.close()
