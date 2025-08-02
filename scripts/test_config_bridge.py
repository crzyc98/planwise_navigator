#!/usr/bin/env python3
"""
Test script for the configuration bridge system.

Tests the ConfigurationBridge class which provides unified access to all configuration systems.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    # Test configuration bridge import
    from orchestrator_dbt.core.config_bridge import ConfigurationBridge, get_default_config_bridge, load_config_bridge

    print("✅ Successfully imported configuration bridge system")

    # Test bridge creation
    bridge = ConfigurationBridge()
    print("✅ Successfully created configuration bridge")

    # Test orchestration config access
    orchestration = bridge.orchestration
    print(f"✅ Orchestration config access:")
    print(f"   Project root: {orchestration.project_root}")
    print(f"   Database path: {orchestration.database.path}")

    # Test multi-year config access
    multi_year = bridge.multi_year
    print(f"✅ Multi-year config access:")
    print(f"   Optimization level: {multi_year.optimization.level.value}")
    print(f"   Max workers: {multi_year.optimization.max_workers}")

    # Test simulation parameters
    print("\n📊 Testing simulation parameters...")
    sim_params = bridge.get_simulation_parameters()
    print(f"✅ Simulation parameters ({len(sim_params)} parameters):")
    for key in ["start_year", "end_year", "optimization_level", "max_workers", "enable_state_compression"]:
        if key in sim_params:
            print(f"   {key}: {sim_params[key]}")

    # Test MVP config compatibility
    print("\n🔄 Testing MVP config compatibility...")
    mvp_config = bridge.get_mvp_config()
    print(f"✅ MVP config compatibility:")
    print(f"   DBT_PROJECT_DIR: {mvp_config['DBT_PROJECT_DIR']}")
    print(f"   DUCKDB_PATH: {mvp_config['DUCKDB_PATH']}")
    print(f"   PROJECT_ROOT: {mvp_config['PROJECT_ROOT']}")

    # Test extended dbt vars
    print("\n📝 Testing extended dbt variables...")
    dbt_vars = bridge.get_dbt_vars_extended()
    print(f"✅ Extended dbt variables ({len(dbt_vars)} variables):")

    # Show base dbt vars
    base_vars = ["census_parquet_path", "plan_year_start_date", "plan_year_end_date", "eligibility_waiting_period_days"]
    print("   Base dbt variables:")
    for var in base_vars:
        if var in dbt_vars:
            print(f"     {var}: {dbt_vars[var]}")

    # Show multi-year dbt vars
    multi_year_vars = ["multi_year_optimization_level", "multi_year_enable_parallel_dbt", "multi_year_batch_size"]
    print("   Multi-year dbt variables:")
    for var in multi_year_vars:
        if var in dbt_vars:
            print(f"     {var}: {dbt_vars[var]}")

    # Test environment config
    print("\n🌍 Testing environment configuration...")
    env_config = bridge.get_environment_config()
    print(f"✅ Environment configuration ({len(env_config)} variables):")

    # Show key environment variables
    key_vars = [
        "DUCKDB_PATH", "DBT_TARGET", "MULTI_YEAR_OPTIMIZATION_LEVEL",
        "MULTI_YEAR_MAX_WORKERS", "MULTI_YEAR_ENABLE_STATE_COMPRESSION",
        "PLANWISE_PROJECT_ROOT"
    ]
    for var in key_vars:
        if var in env_config:
            print(f"   {var}: {env_config[var]}")

    # Test validation
    print("\n🔍 Testing bridge validation...")
    try:
        bridge.validate_all()
        print("✅ Bridge validation passed")
    except Exception as e:
        print(f"❌ Bridge validation failed: {e}")
        sys.exit(1)

    # Test compatibility report
    print("\n📋 Testing compatibility report...")
    try:
        report = bridge.get_compatibility_report()
        print("✅ Compatibility report generated successfully")

        print("   Orchestration config:")
        for key, value in report["orchestration_config"].items():
            print(f"     {key}: {value}")

        print("   Multi-year config:")
        for key, value in report["multi_year_config"].items():
            print(f"     {key}: {value}")

        print("   Legacy compatibility:")
        for key, value in report["legacy_compatibility"].items():
            print(f"     {key}: {value}")

        env_overrides = report.get("environment_overrides", {})
        print(f"   Environment overrides: {len(env_overrides)} found")
        for key, value in env_overrides.items():
            print(f"     {key}: {value}")

    except Exception as e:
        print(f"❌ Compatibility report failed: {e}")
        sys.exit(1)

    # Test convenience functions
    print("\n🛠️  Testing convenience functions...")
    try:
        default_bridge = get_default_config_bridge()
        print("✅ get_default_config_bridge() works")

        loaded_bridge = load_config_bridge()
        print("✅ load_config_bridge() works")

        # Test with explicit path
        config_path = str(project_root / "config" / "simulation_config.yaml")
        explicit_bridge = load_config_bridge(config_path)
        print("✅ load_config_bridge(explicit_path) works")

    except Exception as e:
        print(f"❌ Convenience functions failed: {e}")
        sys.exit(1)

    # Test environment variable overrides with bridge
    print("\n🧪 Testing environment overrides with bridge...")
    original_level = os.environ.get("MULTI_YEAR_OPTIMIZATION_LEVEL")
    original_workers = os.environ.get("MULTI_YEAR_MAX_WORKERS")

    os.environ["MULTI_YEAR_OPTIMIZATION_LEVEL"] = "medium"
    os.environ["MULTI_YEAR_MAX_WORKERS"] = "6"

    env_bridge = ConfigurationBridge()
    env_sim_params = env_bridge.get_simulation_parameters()

    print(f"✅ Environment override test:")
    print(f"   Optimization level: {env_sim_params['optimization_level']} (expected: medium)")
    print(f"   Max workers: {env_sim_params['max_workers']} (expected: 6)")

    # Restore environment
    if original_level:
        os.environ["MULTI_YEAR_OPTIMIZATION_LEVEL"] = original_level
    else:
        os.environ.pop("MULTI_YEAR_OPTIMIZATION_LEVEL", None)

    if original_workers:
        os.environ["MULTI_YEAR_MAX_WORKERS"] = original_workers
    else:
        os.environ.pop("MULTI_YEAR_MAX_WORKERS", None)

    # Test string representation
    print(f"\n📄 Bridge string representation:")
    print(bridge)

    print("\n🎉 Configuration bridge test completed successfully!")
    print("\n📋 Bridge Summary:")
    print(f"   📁 Project root: {bridge.orchestration.project_root}")
    print(f"   📄 Config file: {bridge.orchestration.config_path}")
    print(f"   🚀 Optimization: {bridge.multi_year.optimization.level.value}")
    print(f"   👥 Max workers: {bridge.multi_year.optimization.max_workers}")
    print(f"   📦 Batch size: {bridge.multi_year.optimization.batch_size}")
    print(f"   💾 Memory limit: {bridge.multi_year.optimization.memory_limit_gb} GB")
    print(f"   🌍 Environment variables: {len(bridge.get_environment_config())}")
    print(f"   📝 dbt variables: {len(bridge.get_dbt_vars_extended())}")
    print(f"   ⚙️  Simulation parameters: {len(bridge.get_simulation_parameters())}")

except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running from the project root")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
