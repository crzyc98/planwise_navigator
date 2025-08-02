#!/usr/bin/env python3
"""Check the int_hiring_events table content."""

import duckdb

conn = duckdb.connect('simulation.duckdb')

print('=== CHECKING INT_HIRING_EVENTS TABLE ===')

# Check if int_hiring_events table exists and has data
try:
    result = conn.execute('''
    SELECT COUNT(*) as count
    FROM int_hiring_events
    WHERE simulation_year = 2025
    ''').fetchone()

    print(f'Records in int_hiring_events: {result[0]}')

    if result[0] > 0:
        # Show sample records
        sample = conn.execute('''
        SELECT employee_id, level_id, compensation_amount, hire_date
        FROM int_hiring_events
        WHERE simulation_year = 2025
        LIMIT 5
        ''').fetchall()

        print('\nSample records:')
        for emp_id, level, comp, date in sample:
            print(f'  {emp_id}: Level {level}, ${comp:.0f}, {date}')

    # Check level breakdown
    level_breakdown = conn.execute('''
    SELECT level_id, COUNT(*) as count
    FROM int_hiring_events
    WHERE simulation_year = 2025
    GROUP BY level_id
    ORDER BY level_id
    ''').fetchall()

    if level_breakdown:
        print('\nBreakdown by level:')
        total = 0
        for level, count in level_breakdown:
            print(f'  Level {level}: {count} hires')
            total += count
        print(f'  TOTAL: {total} hires')

except Exception as e:
    print(f'Error: {e}')
    print('int_hiring_events table may not exist')

conn.close()
