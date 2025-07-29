#!/usr/bin/env python3
import duckdb

conn = duckdb.connect('/Users/nicholasamaral/planwise_navigator/simulation.duckdb')

print("=== int_promotion_events for EMP_000003 ===")
result = conn.execute("""
SELECT
    employee_id,
    simulation_year,
    from_level,
    to_level,
    new_salary
FROM int_promotion_events
WHERE employee_id = 'EMP_000003'
ORDER BY simulation_year
""").fetchall()

for row in result:
    print(f"  Year {row[1]}: from_level={row[2]}, to_level={row[3]}, salary=${row[4]:,.2f}")

print("\n=== fct_yearly_events promotions for EMP_000003 ===")
result2 = conn.execute("""
SELECT
    employee_id,
    simulation_year,
    event_details,
    level_id,
    compensation_amount
FROM fct_yearly_events
WHERE employee_id = 'EMP_000003'
    AND event_type = 'promotion'
ORDER BY simulation_year
""").fetchall()

for row in result2:
    print(f"  Year {row[1]}: {row[2]}, level_id={row[3]}, comp=${row[4]:,.2f}")

conn.close()
