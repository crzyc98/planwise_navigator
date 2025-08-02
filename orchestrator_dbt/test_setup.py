#!/usr/bin/env python3
"""
Test script for orchestrator_dbt setup validation.

This script tests the basic functionality of the orchestrator_dbt package
without actually executing the full workflow.
"""

import sys
import logging
from pathlib import Path

# Add the project root to the path so we can import our modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from orchestrator_dbt import (
    WorkflowOrchestrator,
    OrchestrationConfig,
    setup_orchestrator_logging
)


def test_configuration_loading():
    """Test configuration loading."""
    print("🧪 Testing configuration loading...")

    try:
        config = OrchestrationConfig()
        print(f"✅ Configuration loaded successfully")
        print(f"   - Project root: {config.project_root_path}")
        print(f"   - Database path: {config.database.path}")
        print(f"   - dbt project: {config.dbt.project_dir}")
        return True
    except Exception as e:
        print(f"❌ Configuration loading failed: {e}")
        return False


def test_orchestrator_initialization():
    """Test orchestrator initialization."""
    print("\n🧪 Testing orchestrator initialization...")

    try:
        orchestrator = WorkflowOrchestrator()
        print(f"✅ Orchestrator initialized successfully")
        print(f"   - Config: {type(orchestrator.config).__name__}")
        print(f"   - Database Manager: {type(orchestrator.database_manager).__name__}")
        print(f"   - dbt Executor: {type(orchestrator.dbt_executor).__name__}")
        return True
    except Exception as e:
        print(f"❌ Orchestrator initialization failed: {e}")
        return False


def test_system_status():
    """Test system status check."""
    print("\n🧪 Testing system status check...")

    try:
        orchestrator = WorkflowOrchestrator()
        status = orchestrator.get_system_status()

        print(f"✅ System status check completed")
        print(f"   - Config valid: {status['config_valid']}")
        print(f"   - Database accessible: {status['database_accessible']}")
        print(f"   - dbt available: {status['dbt_available']}")
        print(f"   - Seeds available: {status['seeds_available']}")
        print(f"   - Staging models available: {status['staging_models_available']}")
        print(f"   - Ready for setup: {status['ready_for_setup']}")

        return True
    except Exception as e:
        print(f"❌ System status check failed: {e}")
        return False


def test_component_discovery():
    """Test component discovery."""
    print("\n🧪 Testing component discovery...")

    try:
        orchestrator = WorkflowOrchestrator()

        # Test seed discovery
        seeds = orchestrator.seed_loader.discover_seed_files()
        print(f"✅ Seed discovery: {len(seeds)} seeds found")
        if seeds:
            print(f"   - Examples: {seeds[:3]}")

        # Test staging model discovery
        models = orchestrator.staging_loader.discover_staging_models()
        print(f"✅ Staging model discovery: {len(models)} models found")
        if models:
            print(f"   - Examples: {models[:3]}")

        return True
    except Exception as e:
        print(f"❌ Component discovery failed: {e}")
        return False


def test_database_connection():
    """Test database connection."""
    print("\n🧪 Testing database connection...")

    try:
        orchestrator = WorkflowOrchestrator()

        # Test database connection and table listing
        with orchestrator.database_manager.get_connection() as conn:
            # Simple query to test connection
            result = conn.execute("SELECT 1 as test").fetchone()
            print(f"✅ Database connection successful: {result}")

        # Test table listing
        tables = orchestrator.database_manager.list_tables()
        print(f"✅ Table listing: {len(tables)} tables found")

        return True
    except Exception as e:
        print(f"❌ Database connection failed: {e}")
        return False


def test_dbt_availability():
    """Test dbt availability."""
    print("\n🧪 Testing dbt availability...")

    try:
        orchestrator = WorkflowOrchestrator()

        # Test dbt version
        version = orchestrator.dbt_executor.get_dbt_version()
        print(f"✅ dbt available: {version}")

        # Test model listing
        models = orchestrator.dbt_executor.list_models()
        print(f"✅ Model listing: {len(models)} models found")

        # Test seed listing
        seeds = orchestrator.dbt_executor.list_seeds()
        print(f"✅ Seed listing: {len(seeds)} seeds found")

        return True
    except Exception as e:
        print(f"❌ dbt availability test failed: {e}")
        return False


def main():
    """Run all tests."""
    print("🚀 Starting orchestrator_dbt setup validation tests")
    print("=" * 80)

    # Setup logging
    setup_orchestrator_logging(level="INFO")

    # Run tests
    tests = [
        ("Configuration Loading", test_configuration_loading),
        ("Orchestrator Initialization", test_orchestrator_initialization),
        ("System Status Check", test_system_status),
        ("Component Discovery", test_component_discovery),
        ("Database Connection", test_database_connection),
        ("dbt Availability", test_dbt_availability),
    ]

    passed = 0
    failed = 0

    for test_name, test_func in tests:
        try:
            if test_func():
                passed += 1
            else:
                failed += 1
        except Exception as e:
            print(f"❌ Test '{test_name}' crashed: {e}")
            failed += 1

    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    print(f"Tests Passed: {passed}")
    print(f"Tests Failed: {failed}")
    print(f"Success Rate: {(passed / (passed + failed) * 100):.1f}%")

    if failed == 0:
        print("\n🎉 All tests passed! The orchestrator_dbt package is ready for use.")
        return 0
    else:
        print(f"\n⚠️  {failed} test(s) failed. Please check the errors above.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
