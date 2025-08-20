#!/usr/bin/env python3
"""Verify employees with 0% deferral rates have $0 contributions."""

import duckdb

conn = duckdb.connect("/Users/nicholasamaral/planwise_navigator/simulation.duckdb")

print("=== VERIFYING ZERO DEFERRAL RATE HANDLING ===")
print()

# Check employees with 0% deferral rate
query1 = """
SELECT
    COUNT(*) as count,
    MAX(prorated_annual_contributions) as max_contributions,
    AVG(prorated_annual_contributions) as avg_contributions
FROM int_employee_contributions
WHERE simulation_year = 2025
    AND current_deferral_rate <= 0.001
"""
result = conn.execute(query1).fetchone()
print(f"Employees with ≤0.1% deferral rate:")
print(f"  Count: {result[0]}")
print(
    f"  Max contributions: ${result[1]:.2f}"
    if result[1]
    else "  Max contributions: $0.00"
)
print(
    f"  Avg contributions: ${result[2]:.2f}"
    if result[2]
    else "  Avg contributions: $0.00"
)
print()

# Sample employees with very low deferral rates
query2 = """
SELECT
    employee_id,
    current_deferral_rate,
    prorated_annual_contributions,
    effective_deferral_rate,
    is_enrolled,
    data_quality_flag
FROM int_employee_contributions
WHERE simulation_year = 2025
    AND current_deferral_rate <= 0.001
ORDER BY prorated_annual_contributions DESC
LIMIT 5
"""
results = conn.execute(query2).fetchall()
if results:
    print("Sample employees with ≤0.1% deferral rate:")
    for row in results:
        print(
            f"  {row[0]}: rate={row[1]:.4f}, contributions=${row[2]:.2f}, effective={row[3]:.4f}, enrolled={row[4]}, flag={row[5]}"
        )
else:
    print("No employees found with ≤0.1% deferral rate")

print()

# Check data quality flag distribution
query3 = """
SELECT
    data_quality_flag,
    COUNT(*) as count
FROM int_employee_contributions
WHERE simulation_year = 2025
GROUP BY data_quality_flag
ORDER BY count DESC
"""
print("Data quality flag distribution:")
results = conn.execute(query3).fetchall()
for flag, count in results:
    print(f"  {flag}: {count}")

print()

# Final validation
query4 = """
SELECT
    COUNT(*) as issues
FROM int_employee_contributions
WHERE simulation_year = 2025
    AND current_deferral_rate = 0
    AND prorated_annual_contributions > 0.01
"""
result = conn.execute(query4).fetchone()
if result[0] == 0:
    print("✅ SUCCESS: No employees with 0% deferral rate have contributions > $0.01")
else:
    print(
        f"❌ FAILURE: {result[0]} employees with 0% deferral rate have contributions > $0.01"
    )

conn.close()
