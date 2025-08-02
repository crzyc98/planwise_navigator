#!/usr/bin/env python3
"""
Test the fixed hiring events generation.
"""

import subprocess
import duckdb

# 1. Run just the hiring events model
print("🔧 Running int_hiring_events with fixes...")
cmd = [
    "/Users/nicholasamaral/planwise_navigator/venv/bin/dbt",
    "run",
    "--select", "int_hiring_events",
    "--vars", "simulation_year: 2025",
    "--project-dir", "/Users/nicholasamaral/planwise_navigator/dbt"
]

result = subprocess.run(cmd, capture_output=True, text=True)
if result.returncode != 0:
    print(f"❌ Failed to run int_hiring_events")
    print(f"Error: {result.stderr}")
    exit(1)
else:
    print("✅ int_hiring_events completed")

# 2. Check what it created directly
print("\n🔍 Checking hiring events in database...")

# The int_hiring_events model should insert into fct_yearly_events
conn = duckdb.connect('simulation.duckdb')

# Count hiring events
hire_result = conn.execute('''
SELECT COUNT(*) as hire_count
FROM fct_yearly_events
WHERE simulation_year = 2025 AND event_type = 'hire'
''').fetchone()

print(f"\n📊 HIRE EVENTS GENERATED: {hire_result[0]}")

# Also check workforce needs for comparison
wn_result = conn.execute('''
SELECT total_hires_needed
FROM int_workforce_needs
WHERE simulation_year = 2025
''').fetchone()

if wn_result:
    print(f"📊 WORKFORCE NEEDS TARGET: {wn_result[0]}")

    expected = wn_result[0]
    actual = hire_result[0]

    if 850 <= actual <= 900:  # Allow small rounding differences
        print(f"\n✅ SUCCESS: Generated {actual} hires (expected ~{expected})")
        print("🎉 THE 6.7x INFLATION HAS BEEN FIXED!")
    else:
        print(f"\n❌ ISSUE: Generated {actual} hires (expected ~{expected})")
        if actual > 5000:
            print("💥 Still showing massive inflation - fixes may not be applied correctly")
        else:
            print("⚠️  Different from expected but not inflated")

conn.close()
