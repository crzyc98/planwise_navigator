# filename: streamlit_dashboard/test_compensation_interface.py
"""
Basic tests for the compensation tuning interface functionality.
Run this to verify the interface components work correctly.
"""

import sys
from pathlib import Path

# Add the parent directory to Python path for imports
sys.path.append(str(Path(__file__).parent))

def test_parameter_loading():
    """Test that parameter loading functions work"""
    print("🧪 Testing parameter loading...")

    try:
        # Import functions from compensation_tuning
        from compensation_tuning import load_current_parameters, validate_parameters

        # Test parameter loading
        params = load_current_parameters()
        if params:
            print("✅ Parameter loading successful")
            print(f"   Loaded {len(params)} years of parameters")
        else:
            print("⚠️  No parameters loaded - may be expected for new installation")

        # Test parameter validation
        test_params = {
            'cola_rate': {1: 0.04, 2: 0.04, 3: 0.04, 4: 0.04, 5: 0.04},
            'merit_base': {1: 0.045, 2: 0.05, 3: 0.055, 4: 0.06, 5: 0.065},
            'new_hire_salary_adjustment': {1: 1.15, 2: 1.15, 3: 1.15, 4: 1.15, 5: 1.15}
        }

        warnings, errors = validate_parameters(test_params)
        print(f"✅ Parameter validation working: {len(warnings)} warnings, {len(errors)} errors")

    except Exception as e:
        print(f"❌ Parameter testing failed: {e}")
        return False

    return True

def test_database_connection():
    """Test database connectivity"""
    print("🧪 Testing database connection...")

    try:
        from compensation_tuning import load_simulation_results

        # Test database loading
        results = load_simulation_results()
        if results:
            print("✅ Database connection successful")
            print(f"   Found data for {len(results['years'])} years")
        else:
            print("⚠️  No simulation results found - run a simulation first")

    except Exception as e:
        print(f"❌ Database testing failed: {e}")
        return False

    return True

def test_file_structure():
    """Test that required files exist"""
    print("🧪 Testing file structure...")

    required_files = [
        "compensation_tuning.py",
        "../dbt/seeds/comp_levers.csv",
        "../config/simulation_config.yaml"
    ]

    missing_files = []
    for file_path in required_files:
        if not Path(file_path).exists():
            missing_files.append(file_path)

    if missing_files:
        print(f"❌ Missing files: {', '.join(missing_files)}")
        return False
    else:
        print("✅ All required files present")
        return True

def test_imports():
    """Test that all required imports work"""
    print("🧪 Testing imports...")

    try:
        import streamlit as st
        import pandas as pd
        import plotly.express as px
        import plotly.graph_objects as go
        import numpy as np
        import duckdb
        import yaml

        print("✅ All imports successful")
        return True
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return False

def main():
    """Run all tests"""
    print("🔬 Running Compensation Tuning Interface Tests")
    print("=" * 50)

    tests = [
        ("File Structure", test_file_structure),
        ("Imports", test_imports),
        ("Parameter Loading", test_parameter_loading),
        ("Database Connection", test_database_connection)
    ]

    passed = 0
    total = len(tests)

    for test_name, test_func in tests:
        print(f"\n📋 {test_name}:")
        if test_func():
            passed += 1

    print("\n" + "=" * 50)
    print(f"🎯 Test Results: {passed}/{total} tests passed")

    if passed == total:
        print("🎉 All tests passed! The interface should work correctly.")
        print("\n🚀 To launch the interface, run:")
        print("   python launch_compensation_tuning.py")
        print("   or")
        print("   streamlit run compensation_tuning.py")
    else:
        print("⚠️  Some tests failed. Check the errors above.")

    return passed == total

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
