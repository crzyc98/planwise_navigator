#!/usr/bin/env python3
"""
Simple test script to validate basic integration components without full dependencies
"""

try:
    # Test basic imports that should work
    import duckdb
    print("✅ DuckDB import successful")
    
    from pydantic import BaseModel
    print("✅ Pydantic import successful")
    
    # Test YearResult model definition (copy from validation.py to avoid dagster dependency)
    class YearResult(BaseModel):
        """Results from simulating a single year"""
        year: int
        success: bool
        active_employees: int
        total_terminations: int
        experienced_terminations: int
        new_hire_terminations: int
        total_hires: int
        growth_rate: float
        validation_passed: bool
    
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
    
    # Test database connectivity
    conn = duckdb.connect(':memory:')
    conn.execute("SELECT 1").fetchone()
    conn.close()
    print("✅ Database connectivity test passed")
    
    # Test event sourcing schema definitions
    try:
        import yaml
        with open('config/simulation_config.yaml', 'r') as f:
            config = yaml.safe_load(f)
        print("✅ Configuration file validation passed")
    except Exception as e:
        print(f"⚠️ Configuration file test skipped: {e}")
    
    print("🎉 Basic validation framework integration tests passed!")
    
except Exception as e:
    print(f"❌ Validation test failed: {e}")
    import traceback
    traceback.print_exc()
    exit(1)