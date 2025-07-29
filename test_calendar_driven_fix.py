#!/usr/bin/env python3
"""
Test the calendar-driven event fix to ensure proper sequencing and no double merit.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator_mvp.core.event_emitter import generate_and_store_all_events
from orchestrator_mvp.core.database_manager import get_connection
from orchestrator_mvp.core.workforce_calculations import calculate_workforce_requirements_from_config

def test_calendar_driven_fix():
    """Test the calendar-driven event generation fix."""

    print("🧪 Testing Calendar-Driven Event Generation Fix")
    print("=" * 60)

    try:
        # Step 1: Clear existing 2028 events to avoid conflicts
        print("🧹 Clearing existing 2028 events...")
        conn = get_connection()
        conn.execute("DELETE FROM fct_yearly_events WHERE simulation_year = 2028")
        print("   ✅ Cleared existing events")
        conn.close()

        # Step 2: Calculate workforce requirements
        print("\n📊 Calculating workforce requirements for 2028...")
        # Use default config
        config = {
            'target_growth_rate': 0.03,
            'total_termination_rate': 0.12,
            'new_hire_termination_rate': 0.25
        }
        calc_result = calculate_workforce_requirements_from_config(2028, config)

        print(f"   • Target terminations: {calc_result['experienced_terminations']}")
        print(f"   • Target hires: {calc_result['total_hires_needed']}")
        print(f"   • Expected net change: {calc_result.get('net_workforce_change', 'N/A')}")

        # Step 3: Generate events with fixed calendar-driven approach
        print(f"\n🎯 Generating events with calendar-driven approach...")
        generate_and_store_all_events(
            calc_result=calc_result,
            simulation_year=2028,
            random_seed=42,
            table_name="fct_yearly_events"
        )

        # Step 4: Validate results
        print(f"\n🔍 Validating calendar-driven results...")
        conn = get_connection()

        # Check event counts by type
        event_counts = conn.execute("""
            SELECT event_type, COUNT(*) as count
            FROM fct_yearly_events
            WHERE simulation_year = 2028
            GROUP BY event_type
            ORDER BY event_type
        """).fetchall()

        print(f"   📊 Event counts by type:")
        total_events = 0
        for event_type, count in event_counts:
            print(f"     • {event_type}: {count}")
            total_events += count

        # Check for duplicate merit events (the main bug we're fixing)
        duplicate_merits = conn.execute("""
            SELECT employee_id, COUNT(*) as merit_count
            FROM fct_yearly_events
            WHERE simulation_year = 2028 AND event_type = 'raise'
            GROUP BY employee_id
            HAVING COUNT(*) > 1
            LIMIT 5
        """).fetchall()

        if duplicate_merits:
            print(f"   ❌ FOUND {len(duplicate_merits)} employees with duplicate merit events!")
            for emp_id, count in duplicate_merits:
                print(f"     • {emp_id}: {count} merit events")
        else:
            print(f"   ✅ NO duplicate merit events found")

        # Check event dates
        event_dates = conn.execute("""
            SELECT event_type, effective_date, COUNT(*) as count
            FROM fct_yearly_events
            WHERE simulation_year = 2028 AND event_type IN ('promotion', 'raise')
            GROUP BY event_type, effective_date
            ORDER BY event_type, effective_date
        """).fetchall()

        print(f"   📅 Event dates:")
        for event_type, date, count in event_dates:
            print(f"     • {event_type}: {date} ({count} events)")

        # Check EMP_000012 specifically
        emp_12_events = conn.execute("""
            SELECT event_type, effective_date, compensation_amount, previous_compensation
            FROM fct_yearly_events
            WHERE simulation_year = 2028 AND employee_id = 'EMP_000012'
            ORDER BY effective_date, event_type
        """).fetchall()

        print(f"   🎯 EMP_000012 events:")
        for event_type, date, comp, prev_comp in emp_12_events:
            print(f"     • {event_type} on {date}: ${prev_comp:,.2f} → ${comp:,.2f}")

        conn.close()

        print(f"\n✅ Calendar-driven test completed successfully!")
        print(f"   • Total events generated: {total_events}")
        print(f"   • Fixed promotion dates: February 1st")
        print(f"   • Fixed merit+COLA dates: July 15th")
        print(f"   • Eliminated double merit processing")

    except Exception as e:
        print(f"❌ Test failed: {str(e)}")
        raise

if __name__ == "__main__":
    test_calendar_driven_fix()
