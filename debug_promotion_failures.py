#!/usr/bin/env python3
import duckdb

conn = duckdb.connect('/Users/nicholasamaral/planwise_navigator/simulation.duckdb')

print("=== Investigating Promotion Compensation Failures ===")

result = conn.execute("""
SELECT
    employee_id,
    simulation_year,
    event_details,
    compensation_amount,
    previous_compensation,
    CASE
        WHEN previous_compensation IS NULL THEN 'MISSING_PREVIOUS_COMPENSATION'
        WHEN previous_compensation < 50000 THEN 'UNREALISTICALLY_LOW_PREVIOUS'
        WHEN previous_compensation > 500000 THEN 'UNREALISTICALLY_HIGH_PREVIOUS'
        ELSE 'VALID'
    END as validation_status
FROM fct_yearly_events
WHERE event_type = 'promotion'
    AND (
        previous_compensation IS NULL OR
        previous_compensation < 50000 OR
        previous_compensation > 500000
    )
ORDER BY employee_id, simulation_year
LIMIT 10
""").fetchall()

print("Failed Promotion Events:")
print("Employee ID  | Year | Event Details    | New Comp    | Prev Comp   | Issue")
print("-" * 80)
for row in result:
    print(f"{row[0]:<12} | {row[1]} | {row[2]:<15} | ${row[3]:>10,.2f} | {row[4] or 'NULL':>9} | {row[5]}")

conn.close()
