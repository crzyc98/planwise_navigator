#!/usr/bin/env python3
"""
Test script to validate that promotion events use current year compensation,
not baseline compensation from previous year.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator_mvp.core.event_emitter import generate_promotion_events_with_merit_awareness

def test_promotion_compensation_fix():
    """Test that promotion events use post-merit compensation correctly."""

    print("🧪 Testing Promotion Previous Compensation Fix")
    print("=" * 60)

    # Create simulated merit events for EMP_000012 showing 2027 -> 2028 progression
    print("📋 Step 1: Creating simulated merit events for 2028...")
    simulated_merit_events = [
        {
            'employee_id': 'EMP_000012',
            'employee_ssn': 'SSN-704012016',
            'event_type': 'raise',
            'simulation_year': 2028,
            'effective_date': '2028-07-15',
            'event_details': 'merit_2.3%_cola_2.5%',
            'compensation_amount': 113921.81,  # Current compensation after 2027 end
            'previous_compensation': 101913.12,  # 2027 end-of-year salary
            'level_id': 2
        }
    ]

    # Step 1 results
    emp_000012_merit = simulated_merit_events[0]
    print(f"✅ Simulated EMP_000012 merit event:")
    print(f"   • Previous: ${emp_000012_merit['previous_compensation']:,.2f}")
    print(f"   • New: ${emp_000012_merit['compensation_amount']:,.2f}")
    current_compensation = emp_000012_merit['compensation_amount']

    # Step 2: Generate promotion events with merit awareness
    print(f"\n📋 Step 2: Generating promotion events with merit awareness...")
    try:
        promotion_events = generate_promotion_events_with_merit_awareness(
            simulation_year=2028,
            merit_events=simulated_merit_events,
            random_seed=42
        )

        print(f"✅ Successfully generated promotion events with merit awareness")

        # Find EMP_000012's promotion event
        emp_000012_promotion = None
        for promo in promotion_events:
            if promo['employee_id'] == 'EMP_000012':
                emp_000012_promotion = promo
                break

        if emp_000012_promotion:
            print(f"\n🎯 EMP_000012 Promotion Event Analysis:")
            print(f"   • Previous compensation: ${emp_000012_promotion['previous_compensation']:,.2f}")
            print(f"   • New compensation: ${emp_000012_promotion['compensation_amount']:,.2f}")
            print(f"   • Level: {emp_000012_promotion['level_id']}")

            # Validate the fix
            expected_previous = current_compensation  # Should use current year compensation
            actual_previous = emp_000012_promotion['previous_compensation']

            if abs(actual_previous - expected_previous) < 0.01:
                print(f"   ✅ PASS: Promotion uses current year compensation!")
                print(f"   ✅ No longer using stale baseline compensation")
                print(f"   ✅ Compensation chain is correctly linked")
            else:
                print(f"   ❌ FAIL: Promotion uses wrong previous compensation")
                print(f"   ❌ Expected: ${expected_previous:,.2f}, Got: ${actual_previous:,.2f}")
                if actual_previous == 87300:
                    print(f"   ❌ Still using baseline compensation (87300) - not fixed!")

        else:
            print(f"   ⚠️  EMP_000012 did not get promoted in 2028")

    except Exception as e:
        print(f"❌ Error testing promotion events: {str(e)}")
        raise

if __name__ == "__main__":
    test_promotion_compensation_fix()
