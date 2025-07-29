#!/usr/bin/env python3
import duckdb

conn = duckdb.connect('/Users/nicholasamaral/planwise_navigator/simulation.duckdb')

# Test 1: Check if promotion events now match workforce snapshot level_id
print("=== Test 1: Promotion Level ID Validation ===")
result = conn.execute("""
SELECT
    p.employee_id,
    p.simulation_year,
    p.event_details,
    p.level_id as promotion_target_level,
    w.level_id as workforce_snapshot_level
FROM fct_yearly_events p
JOIN fct_workforce_snapshot w
    ON p.employee_id = w.employee_id
    AND p.simulation_year = w.simulation_year
WHERE p.event_type = 'promotion'
    AND w.level_id != p.level_id
    AND w.employment_status = 'active'
    AND p.employee_id = 'EMP_000003'
ORDER BY p.simulation_year
""").fetchall()

print(f"Found {len(result)} mismatches - should be 0:")
for row in result:
    print(f"  {row}")

# Test 2: Check EMP_000003 progression
print("\n=== Test 2: EMP_000003 Level Progression ===")
result2 = conn.execute("""
SELECT
    simulation_year,
    level_id,
    current_compensation,
    employment_status
FROM fct_workforce_snapshot
WHERE employee_id = 'EMP_000003'
ORDER BY simulation_year
""").fetchall()

print("EMP_000003 workforce progression:")
for row in result2:
    print(f"  Year {row[0]}: Level {row[1]}, Comp ${row[2]:,.2f}, Status {row[3]}")

# Test 3: Check promotion events for EMP_000003
print("\n=== Test 3: EMP_000003 Promotion Events ===")
result3 = conn.execute("""
SELECT
    simulation_year,
    event_details,
    level_id,
    compensation_amount
FROM fct_yearly_events
WHERE employee_id = 'EMP_000003'
    AND event_type = 'promotion'
ORDER BY simulation_year
""").fetchall()

print("EMP_000003 promotion events:")
for row in result3:
    print(f"  Year {row[0]}: {row[1]}, Target Level {row[2]}, Comp ${row[3]:,.2f}")

conn.close()
