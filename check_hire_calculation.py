#!/usr/bin/env python3
"""Check the hire calculation breakdown."""

import duckdb

conn = duckdb.connect('simulation.duckdb')

print('=== WORKFORCE NEEDS BY LEVEL ===')
result = conn.execute('''
SELECT level_id, hires_needed, new_hire_avg_compensation
FROM int_workforce_needs_by_level
WHERE simulation_year = 2025
ORDER BY level_id
''').fetchall()

total_hires = 0
for level_id, hires, comp in result:
    print(f'Level {level_id}: {hires} hires needed (avg comp: ${comp:,.0f})')
    total_hires += hires

print(f'\nTOTAL HIRES FROM LEVEL BREAKDOWN: {total_hires}')

# Also check the base workforce needs
wn_result = conn.execute('SELECT total_hires_needed FROM int_workforce_needs WHERE simulation_year = 2025').fetchone()
print(f'TOTAL HIRES FROM WORKFORCE NEEDS: {wn_result[0] if wn_result else "NOT FOUND"}')

# Check if there's duplication in the fct_yearly_events
print('\n=== CHECKING FCT_YEARLY_EVENTS ===')
try:
    events_result = conn.execute('''
    SELECT event_type, COUNT(*) as count
    FROM fct_yearly_events
    WHERE simulation_year = 2025
    GROUP BY event_type
    ORDER BY count DESC
    ''').fetchall()

    for event_type, count in events_result:
        print(f'{event_type}: {count}')
except Exception as e:
    print(f'Table fct_yearly_events not found or error: {e}')

conn.close()
