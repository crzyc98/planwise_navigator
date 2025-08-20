#!/usr/bin/env python3
"""Check unexpected zero rate issues."""

import duckdb

conn = duckdb.connect("/Users/nicholasamaral/planwise_navigator/simulation.duckdb")

# Check employees with UNEXPECTED_ZERO_RATE
query = """
SELECT
    employee_id,
    current_deferral_rate,
    prorated_annual_contributions,
    is_enrolled,
    deferral_rate_source,
    employment_status
FROM int_employee_contributions
WHERE simulation_year = 2025
    AND data_quality_flag = 'UNEXPECTED_ZERO_RATE'
LIMIT 5
"""
results = conn.execute(query).fetchall()
print("Sample of employees with UNEXPECTED_ZERO_RATE:")
for row in results:
    print(
        f"  {row[0]}: rate={row[1]}, contributions=${row[2]:.2f}, enrolled={row[3]}, source={row[4]}, status={row[5]}"
    )

# Check if these are legitimate zero rates from census
query2 = """
SELECT
    COUNT(*) as count,
    AVG(prorated_annual_contributions) as avg_contributions
FROM int_employee_contributions
WHERE simulation_year = 2025
    AND data_quality_flag = 'UNEXPECTED_ZERO_RATE'
"""
result = conn.execute(query2).fetchone()
print(f"\nTotal UNEXPECTED_ZERO_RATE: {result[0]}, Avg contributions: ${result[1]:.2f}")

# Check if these employees have zero rate in census
query3 = """
SELECT
    COUNT(*) as zero_rate_in_census
FROM stg_census_data
WHERE employee_deferral_rate = 0
"""
result = conn.execute(query3).fetchone()
print(f"Employees with 0% rate in census: {result[0]}")

conn.close()
