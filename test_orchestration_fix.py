#!/usr/bin/env python3
"""
Test script for the orchestration fix in workforce_snapshot.py
"""

import sys
import os

# Add the project root to the Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from orchestrator_mvp.core.workforce_snapshot import apply_events_to_workforce

def test_orchestration_fix():
    """Test the updated apply_events_to_workforce function"""
    print("🧪 Testing orchestration fix for intermediate snapshot models...")

    try:
        # This should now build all intermediate models before fct_workforce_snapshot
        result = apply_events_to_workforce(simulation_year=2025)

        print(f"✅ Test result: Success = {result.get('success', False)}")
        if result.get('error'):
            print(f"❌ Error: {result['error']}")
        else:
            print("🎉 Orchestration fix working correctly!")

    except Exception as e:
        print(f"❌ Test failed with exception: {str(e)}")
        return False

    return result.get('success', False)

if __name__ == "__main__":
    success = test_orchestration_fix()
    sys.exit(0 if success else 1)
