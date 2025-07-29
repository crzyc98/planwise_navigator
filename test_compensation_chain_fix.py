#!/usr/bin/env python3
"""
Test script to validate the compensation chain fix for EMP_000012 scenario.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from orchestrator_mvp.core.event_emitter import generate_promotion_events, generate_merit_events_with_promotion_awareness
from orchestrator_mvp.core.database_manager import get_connection

def test_compensation_chain_fix():
    """Test the compensation chain fix with a simulated scenario."""
    
    print("🧪 Testing Compensation Chain Fix")
    print("=" * 50)
    
    # Create test promotion events (simulating EMP_000012 scenario)
    test_promotion_events = [
        {
            'employee_id': 'EMP_000012',
            'employee_ssn': 'SSN-704012016',
            'event_type': 'promotion',
            'simulation_year': 2028,
            'effective_date': '2028-02-03',
            'event_details': 'level_2_to_3',
            'compensation_amount': 108688.5,  # Post-promotion salary
            'previous_compensation': 101913.12,  # Should be 2027 end salary, not baseline
            'level_id': 3,  # Promoted to level 3
            'employee_age': 43,
            'employee_tenure': 1,
            'age_band': '35-44',
            'tenure_band': '< 2',
            'event_probability': 0.046,
            'event_category': 'promotion',
            'event_sequence': 5
        }
    ]
    
    print("📋 Test Promotion Events:")
    for promo in test_promotion_events:
        print(f"   • {promo['employee_id']}: ${promo['previous_compensation']:,.2f} → ${promo['compensation_amount']:,.2f}")
    
    # Test the new merit generation function
    print("\n📋 Testing Merit Events with Promotion Awareness...")
    
    try:
        merit_events = generate_merit_events_with_promotion_awareness(
            simulation_year=2028,
            promotion_events=test_promotion_events,
            random_seed=42
        )
        
        print(f"✅ Generated {len(merit_events)} merit events")
        
        # Find EMP_000012's merit event
        emp_000012_merit = None
        for merit in merit_events:
            if merit['employee_id'] == 'EMP_000012':
                emp_000012_merit = merit
                break
        
        if emp_000012_merit:
            print(f"\n🎯 EMP_000012 Merit Event Analysis:")
            print(f"   • Previous compensation: ${emp_000012_merit['previous_compensation']:,.2f}")
            print(f"   • New compensation: ${emp_000012_merit['compensation_amount']:,.2f}")
            print(f"   • Level ID: {emp_000012_merit['level_id']}")
            
            # Validate the fix
            expected_previous = 108688.5  # Should use post-promotion salary
            actual_previous = emp_000012_merit['previous_compensation']
            
            if abs(actual_previous - expected_previous) < 0.01:
                print(f"   ✅ PASS: Merit event uses post-promotion salary!")
                print(f"   ✅ Compensation chain is correctly linked")
            else:
                print(f"   ❌ FAIL: Merit event uses wrong previous compensation")
                print(f"   ❌ Expected: ${expected_previous:,.2f}, Got: ${actual_previous:,.2f}")
        else:
            print(f"   ⚠️  Could not find EMP_000012 merit event (may not exist in test data)")
            
    except Exception as e:
        print(f"❌ Error testing merit events: {str(e)}")
        raise

if __name__ == "__main__":
    test_compensation_chain_fix()