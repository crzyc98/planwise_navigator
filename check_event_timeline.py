#!/usr/bin/env python3
"""Check when events were created."""

import duckdb
from datetime import datetime

conn = duckdb.connect('simulation.duckdb')

print('=== CHECKING EVENT CREATION TIMELINE ===')

# Check if fct_yearly_events exists and when records were created
try:
    result = conn.execute('''
    SELECT
        event_type,
        COUNT(*) as count,
        MIN(created_at) as earliest_created,
        MAX(created_at) as latest_created
    FROM fct_yearly_events
    WHERE simulation_year = 2025
    GROUP BY event_type
    ORDER BY count DESC
    ''').fetchall()

    print('\nEvent creation times:')
    for event_type, count, earliest, latest in result:
        print(f'{event_type}: {count} events')
        print(f'  Created between {earliest} and {latest}')

    # Get total time range
    total_result = conn.execute('''
    SELECT
        MIN(created_at) as earliest,
        MAX(created_at) as latest
    FROM fct_yearly_events
    WHERE simulation_year = 2025
    ''').fetchone()

    if total_result:
        earliest, latest = total_result
        print(f'\nAll events created between:')
        print(f'  {earliest} and {latest}')

        # Compare to current time
        now = datetime.now()
        if latest:
            latest_time = datetime.fromisoformat(str(latest).replace(' ', 'T'))
            time_diff = now - latest_time
            print(f'\nEvents were created {time_diff} ago')

except Exception as e:
    print(f'Error: {e}')
    print('fct_yearly_events table might not exist yet')

conn.close()
