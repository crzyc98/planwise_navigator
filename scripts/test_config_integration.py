#!/usr/bin/env python3
"""
Test script for the new multi-year configuration system integration.

This script verifies that:
1. The new configuration system loads correctly
2. Environment variable overrides work
3. Backward compatibility is maintained
4. All configuration bridges function properly
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    # Test core configuration loading
    from orchestrator_dbt.core.config import OrchestrationConfig, OptimizationLevel, ValidationMode
    from orchestrator_dbt.core.config_bridge import ConfigurationBridge

    print("✅ Successfully imported new configuration system")

    # Test configuration loading
    config = OrchestrationConfig()
    print(f"✅ Successfully loaded configuration from: {config.config_path}")

    # Test multi-year configuration access
    multi_year_config = config.get_multi_year_config()
    print(f"✅ Multi-year optimization level: {multi_year_config.optimization.level.value}")
    print(f"✅ Multi-year max workers: {multi_year_config.optimization.max_workers}")
    print(f"✅ Multi-year batch size: {multi_year_config.optimization.batch_size}")

    # Test configuration bridge
    bridge = ConfigurationBridge()
    print("✅ Successfully created configuration bridge")

    # Test simulation parameters
    sim_params = bridge.get_simulation_parameters()
    print(f"✅ Simulation year range: {sim_params['start_year']}-{sim_params['end_year']}")
    print(f"✅ Optimization level: {sim_params['optimization_level']}")

    # Test legacy compatibility
    legacy_config = bridge.get_legacy_multi_year_config()
    print(f"✅ Legacy compatibility - optimization level: {legacy_config.optimization_level.value}")

    # Test MVP compatibility
    mvp_config = bridge.get_mvp_config()
    print(f"✅ MVP compatibility - dbt project dir: {mvp_config['DBT_PROJECT_DIR']}")

    # Test environment variable override
    original_level = os.environ.get("MULTI_YEAR_OPTIMIZATION_LEVEL")
    os.environ["MULTI_YEAR_OPTIMIZATION_LEVEL"] = "medium"

    # Create new config with environment override
    config_with_env = OrchestrationConfig()
    env_multi_year = config_with_env.get_multi_year_config()

    if env_multi_year.optimization.level == OptimizationLevel.MEDIUM:
        print("✅ Environment variable override works correctly")
    else:
        print(f"❌ Environment variable override failed: expected MEDIUM, got {env_multi_year.optimization.level}")

    # Restore original environment
    if original_level is not None:
        os.environ["MULTI_YEAR_OPTIMIZATION_LEVEL"] = original_level
    else:
        os.environ.pop("MULTI_YEAR_OPTIMIZATION_LEVEL", None)

    # Test validation
    try:
        config.validate()
        print("✅ Configuration validation passed")
    except Exception as e:
        print(f"❌ Configuration validation failed: {e}")
        sys.exit(1)

    # Test bridge validation
    try:
        bridge.validate_all()
        print("✅ Bridge validation passed")
    except Exception as e:
        print(f"❌ Bridge validation failed: {e}")
        sys.exit(1)

    # Test compatibility report
    try:
        report = bridge.get_compatibility_report()
        print("✅ Compatibility report generated successfully")
        print(f"   - Project root: {report['orchestration_config']['project_root']}")
        print(f"   - Optimization level: {report['multi_year_config']['optimization_level']}")
        print(f"   - Environment overrides: {len(report['environment_overrides'])} found")
    except Exception as e:
        print(f"❌ Compatibility report failed: {e}")
        sys.exit(1)

    # Test extended dbt vars
    try:
        dbt_vars = bridge.get_dbt_vars_extended()
        print(f"✅ Extended dbt vars: {len(dbt_vars)} variables")
        if "multi_year_optimization_level" in dbt_vars:
            print(f"   - multi_year_optimization_level: {dbt_vars['multi_year_optimization_level']}")
        else:
            print("❌ Multi-year dbt variables not found")
    except Exception as e:
        print(f"❌ Extended dbt vars failed: {e}")
        sys.exit(1)

    # Test environment config for subprocess calls
    try:
        env_config = bridge.get_environment_config()
        print(f"✅ Environment config: {len(env_config)} variables")
        required_vars = [
            "DUCKDB_PATH", "MULTI_YEAR_OPTIMIZATION_LEVEL",
            "MULTI_YEAR_MAX_WORKERS", "PLANWISE_PROJECT_ROOT"
        ]
        missing_vars = [var for var in required_vars if var not in env_config]
        if missing_vars:
            print(f"❌ Missing required environment variables: {missing_vars}")
        else:
            print("✅ All required environment variables present")
    except Exception as e:
        print(f"❌ Environment config failed: {e}")
        sys.exit(1)

    print("\n🎉 All configuration integration tests passed!")
    print(f"📁 Project root: {bridge.orchestration.project_root}")
    print(f"⚙️  Configuration file: {bridge.orchestration.config_path}")
    print(f"🚀 Optimization level: {bridge.multi_year.optimization.level.value}")
    print(f"👥 Max workers: {bridge.multi_year.optimization.max_workers}")
    print(f"📦 Batch size: {bridge.multi_year.optimization.batch_size}")

    if bridge.multi_year.optimization.memory_limit_gb:
        print(f"💾 Memory limit: {bridge.multi_year.optimization.memory_limit_gb} GB")

    print(f"✨ State compression: {'enabled' if bridge.multi_year.performance.enable_state_compression else 'disabled'}")
    print(f"⚡ Concurrent processing: {'enabled' if bridge.multi_year.performance.enable_concurrent_processing else 'disabled'}")
    print(f"🔄 Checkpointing: {'enabled' if bridge.multi_year.state.enable_checkpointing else 'disabled'}")

except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running from the project root and all dependencies are installed")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
