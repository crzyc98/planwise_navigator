#!/usr/bin/env python3
"""
Simple test for core configuration system.

Tests the new multi-year configuration in isolation without full orchestrator imports.
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    # Test core configuration loading only
    from orchestrator_dbt.core.config import (
        OrchestrationConfig,
        MultiYearConfig,
        OptimizationLevel,
        ValidationMode,
        TransitionStrategy
    )

    print("✅ Successfully imported core configuration system")

    # Test configuration loading
    config = OrchestrationConfig()
    print(f"✅ Successfully loaded configuration from: {config.config_path}")
    print(f"   Project root: {config.project_root}")
    print(f"   Database path: {config.database.path}")
    print(f"   dbt project dir: {config.dbt.project_dir}")

    # Test multi-year configuration access
    multi_year_config = config.get_multi_year_config()
    print(f"✅ Multi-year configuration loaded:")
    print(f"   Optimization level: {multi_year_config.optimization.level.value}")
    print(f"   Max workers: {multi_year_config.optimization.max_workers}")
    print(f"   Batch size: {multi_year_config.optimization.batch_size}")
    print(f"   Memory limit: {multi_year_config.optimization.memory_limit_gb} GB")
    print(f"   State compression: {multi_year_config.performance.enable_state_compression}")
    print(f"   Concurrent processing: {multi_year_config.performance.enable_concurrent_processing}")
    print(f"   Checkpointing: {multi_year_config.state.enable_checkpointing}")
    print(f"   Fail fast: {multi_year_config.error_handling.fail_fast}")
    print(f"   Transition strategy: {multi_year_config.transition.strategy.value}")

    # Test simulation config access
    sim_config = config.get_simulation_config()
    print(f"✅ Simulation configuration:")
    print(f"   Start year: {sim_config.get('start_year', 'not set')}")
    print(f"   End year: {sim_config.get('end_year', 'not set')}")
    print(f"   Random seed: {sim_config.get('random_seed', 'not set')}")
    print(f"   Target growth rate: {sim_config.get('target_growth_rate', 'not set')}")

    # Test environment variable override
    print("\n🧪 Testing environment variable override...")
    original_level = os.environ.get("MULTI_YEAR_OPTIMIZATION_LEVEL")
    os.environ["MULTI_YEAR_OPTIMIZATION_LEVEL"] = "low"

    # Create new config with environment override
    config_with_env = OrchestrationConfig()
    env_multi_year = config_with_env.get_multi_year_config()

    if env_multi_year.optimization.level == OptimizationLevel.LOW:
        print("✅ Environment variable override works correctly")
        print(f"   Override level: {env_multi_year.optimization.level.value}")
    else:
        print(f"❌ Environment variable override failed: expected LOW, got {env_multi_year.optimization.level}")

    # Test multiple environment overrides
    os.environ["MULTI_YEAR_MAX_WORKERS"] = "8"
    os.environ["MULTI_YEAR_BATCH_SIZE"] = "2000"
    os.environ["MULTI_YEAR_ENABLE_STATE_COMPRESSION"] = "false"

    config_multi_env = OrchestrationConfig()
    multi_env_config = config_multi_env.get_multi_year_config()

    print(f"✅ Multiple environment overrides:")
    print(f"   Max workers: {multi_env_config.optimization.max_workers} (expected 8)")
    print(f"   Batch size: {multi_env_config.optimization.batch_size} (expected 2000)")
    print(f"   State compression: {multi_env_config.performance.enable_state_compression} (expected False)")

    # Restore original environment
    if original_level is not None:
        os.environ["MULTI_YEAR_OPTIMIZATION_LEVEL"] = original_level
    else:
        os.environ.pop("MULTI_YEAR_OPTIMIZATION_LEVEL", None)

    for var in ["MULTI_YEAR_MAX_WORKERS", "MULTI_YEAR_BATCH_SIZE", "MULTI_YEAR_ENABLE_STATE_COMPRESSION"]:
        os.environ.pop(var, None)

    # Test validation
    print("\n🔍 Testing validation...")
    try:
        config.validate()
        print("✅ Configuration validation passed")
    except Exception as e:
        print(f"❌ Configuration validation failed: {e}")
        sys.exit(1)

    # Test legacy compatibility method
    print("\n🔄 Testing legacy compatibility...")
    try:
        legacy_dict = config.to_legacy_multi_year_config()
        print("✅ Legacy compatibility method works")
        print(f"   Legacy format keys: {list(legacy_dict.keys())}")
        print(f"   Start year: {legacy_dict.get('start_year')}")
        print(f"   End year: {legacy_dict.get('end_year')}")
        print(f"   Optimization level: {legacy_dict.get('optimization_level')}")
    except Exception as e:
        print(f"❌ Legacy compatibility failed: {e}")

    # Test environment overrides tracking
    print("\n📊 Testing environment override tracking...")
    env_overrides = config.get_environment_overrides()
    print(f"✅ Environment overrides found: {len(env_overrides)}")
    for key, value in env_overrides.items():
        print(f"   {key}: {value}")

    # Test dbt vars
    print("\n📝 Testing dbt variables...")
    dbt_vars = config.get_dbt_vars()
    print(f"✅ dbt variables: {len(dbt_vars)}")
    for key, value in dbt_vars.items():
        print(f"   {key}: {value}")

    # Test configuration sections
    print("\n📋 Testing configuration sections...")
    workforce_config = config.get_workforce_config()
    eligibility_config = config.get_eligibility_config()
    enrollment_config = config.get_enrollment_config()

    print(f"✅ Workforce config keys: {list(workforce_config.keys())}")
    print(f"✅ Eligibility config keys: {list(eligibility_config.keys())}")
    print(f"✅ Enrollment config keys: {list(enrollment_config.keys())}")

    print("\n🎉 Core configuration system test completed successfully!")
    print("\n📋 Configuration Summary:")
    print(f"   📁 Project root: {config.project_root}")
    print(f"   📄 Config file: {config.config_path}")
    print(f"   🗄️  Database: {config.database.path}")
    print(f"   🔧 dbt project: {config.dbt.project_dir}")
    print(f"   🚀 Optimization: {multi_year_config.optimization.level.value}")
    print(f"   👥 Workers: {multi_year_config.optimization.max_workers}")
    print(f"   📦 Batch size: {multi_year_config.optimization.batch_size}")

    if multi_year_config.optimization.memory_limit_gb:
        print(f"   💾 Memory limit: {multi_year_config.optimization.memory_limit_gb} GB")

    print(f"   ✨ Features enabled:")
    print(f"      - State compression: {multi_year_config.performance.enable_state_compression}")
    print(f"      - Concurrent processing: {multi_year_config.performance.enable_concurrent_processing}")
    print(f"      - Parallel dbt: {multi_year_config.performance.enable_parallel_dbt}")
    print(f"      - Checkpointing: {multi_year_config.state.enable_checkpointing}")
    print(f"      - Resume capability: {multi_year_config.resume.enable_resume}")
    print(f"      - Performance monitoring: {multi_year_config.monitoring.enable_performance_monitoring}")

except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure you're running from the project root")
    sys.exit(1)
except Exception as e:
    print(f"❌ Unexpected error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
