#!/usr/bin/env python3
"""Debug the CROSS JOIN multiplication issue."""

import duckdb

conn = duckdb.connect('simulation.duckdb')

# Check how many records are in workforce_needs
print('=== DEBUGGING CROSS JOIN ISSUE ===')

# Check workforce_needs table
try:
    result = conn.execute('''
    SELECT COUNT(*) as record_count
    FROM int_workforce_needs
    WHERE simulation_year = 2025
    ''').fetchone()
    print(f'Records in int_workforce_needs for 2025: {result[0]}')

    # Get all records to see if there are duplicates
    all_records = conn.execute('''
    SELECT workforce_needs_id, scenario_id, total_hires_needed
    FROM int_workforce_needs
    WHERE simulation_year = 2025
    ''').fetchall()

    print('\nAll workforce_needs records:')
    for wn_id, scenario, hires in all_records:
        print(f'  ID: {wn_id}, Scenario: {scenario}, Hires: {hires}')

except Exception as e:
    print(f'Error querying int_workforce_needs: {e}')

# Let me run a test query to see what the CROSS JOIN would produce
print('\n=== SIMULATING CROSS JOIN EFFECT ===')

# First, let's see how many levels we have
level_result = conn.execute('''
SELECT COUNT(DISTINCT level_id)
FROM int_workforce_needs_by_level
WHERE simulation_year = 2025
''').fetchone()
print(f'Number of distinct levels: {level_result[0]}')

# Now let's see what happens with CROSS JOIN
print('\nIf we have:')
print(f'- 875 hires from level breakdown')
print(f'- {result[0]} records in workforce_needs')
print(f'- {level_result[0]} distinct levels')

# Check if there's multiplication happening
if result[0] > 1:
    print(f'\n⚠️  PROBLEM: workforce_needs has {result[0]} records!')
    print(f'   This would multiply every hire by {result[0]}')
    print(f'   875 hires × {result[0]} = {875 * result[0]} (close to 6,564?)')

# Let's also check if there are multiple scenario_ids causing duplication
scenario_result = conn.execute('''
SELECT scenario_id, COUNT(*) as count
FROM int_workforce_needs
WHERE simulation_year = 2025
GROUP BY scenario_id
''').fetchall()

print('\n=== SCENARIO BREAKDOWN ===')
for scenario, count in scenario_result:
    print(f'Scenario "{scenario}": {count} records')

conn.close()
