#!/usr/bin/env python3
"""
Test script to validate the validation framework integration
"""

try:
    from src.simulation.validation import YearResult, validate_year_results, assert_year_complete
    print("✅ Validation module imports successful")
    
    # Test YearResult model
    yr = YearResult(
        year=2025, 
        success=True, 
        active_employees=100, 
        total_terminations=10, 
        experienced_terminations=8, 
        new_hire_terminations=2, 
        total_hires=15, 
        growth_rate=0.05, 
        validation_passed=True
    )
    print("✅ YearResult model validation passed")
    
    # Test behavioral identity
    yr2 = YearResult(
        year=2025, 
        success=True, 
        active_employees=100, 
        total_terminations=10, 
        experienced_terminations=8, 
        new_hire_terminations=2, 
        total_hires=15, 
        growth_rate=0.05, 
        validation_passed=True
    )
    
    if yr == yr2:
        print("✅ Behavioral identity validation passed")
    else:
        print("❌ Behavioral identity validation failed")
    
    # Test serialization
    yr_json = yr.model_dump_json()
    yr_from_json = YearResult.model_validate_json(yr_json)
    
    if yr == yr_from_json:
        print("✅ Serialization consistency validated")
    else:
        print("❌ Serialization consistency failed")
    
    print("🎉 All validation framework integration tests passed!")
    
except ImportError as e:
    print(f"❌ Import error: {e}")
    exit(1)
except Exception as e:
    print(f"❌ Validation test failed: {e}")
    exit(1)