"""
Setup Script for PlanWise Navigator Optimization Storage System
Initializes the database tables and validates the system setup.

Run this script to set up the optimization storage system:
python setup_optimization_storage.py
"""

import logging
import sys
from datetime import datetime
from pathlib import Path

# Add the streamlit_dashboard directory to the path
sys.path.insert(0, str(Path(__file__).parent))

try:
    from optimization_integration import (get_duckdb_integration,
                                          get_optimization_cache,
                                          validate_optimization_environment)
    from optimization_results_manager import get_optimization_results_manager
    from optimization_storage import (OptimizationStorageManager,
                                      get_optimization_storage)
except ImportError as e:
    print(f"Error importing optimization modules: {e}")
    print("Make sure you're running this from the streamlit_dashboard directory")
    sys.exit(1)

# Set up logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


def setup_database_tables():
    """Initialize the optimization storage database tables."""
    print("🔧 Setting up optimization storage database tables...")

    try:
        # Initialize the storage manager (this creates tables)
        storage = get_optimization_storage()
        print("✅ Storage manager initialized")

        # Test database connection
        db_integration = get_duckdb_integration()
        with db_integration.get_connection() as conn:
            # Test query
            result = conn.execute("SELECT COUNT(*) FROM optimization_runs").fetchone()
            print(
                f"✅ Database accessible, found {result[0]} existing optimization runs"
            )

        return True

    except Exception as e:
        print(f"❌ Failed to setup database tables: {e}")
        return False


def setup_cache_directory():
    """Set up the optimization cache directory."""
    print("📁 Setting up cache directory...")

    try:
        cache = get_optimization_cache()
        cache_stats = cache.get_cache_stats()
        print(f"✅ Cache directory created at: {cache_stats['cache_directory']}")
        return True

    except Exception as e:
        print(f"❌ Failed to setup cache directory: {e}")
        return False


def validate_system():
    """Validate the complete optimization system setup."""
    print("🔍 Validating optimization system...")

    try:
        validation = validate_optimization_environment()

        print("\n📊 System Validation Results:")
        print(
            f"  Database Accessible: {'✅' if validation['database_accessible'] else '❌'}"
        )
        print(f"  Tables Exist: {'✅' if validation['tables_exist'] else '❌'}")
        print(f"  Cache Operational: {'✅' if validation['cache_operational'] else '❌'}")
        print(
            f"  Storage Initialized: {'✅' if validation['storage_initialized'] else '❌'}"
        )

        if validation["warnings"]:
            print("\n⚠️  Warnings:")
            for warning in validation["warnings"]:
                print(f"    - {warning}")

        if validation["errors"]:
            print("\n❌ Errors:")
            for error in validation["errors"]:
                print(f"    - {error}")

        # Overall health check
        all_good = all(
            [
                validation["database_accessible"],
                validation["tables_exist"],
                validation["cache_operational"],
                validation["storage_initialized"],
            ]
        )

        if all_good:
            print("\n🎉 System validation PASSED - Optimization storage is ready!")
        else:
            print("\n⚠️  System validation FAILED - Some components need attention")

        return all_good

    except Exception as e:
        print(f"❌ Validation failed: {e}")
        return False


def create_sample_data():
    """Create sample optimization data for testing."""
    print("📝 Creating sample optimization data...")

    try:
        from optimization_storage import (OptimizationConfiguration,
                                          OptimizationEngine,
                                          OptimizationMetadata,
                                          OptimizationObjective,
                                          OptimizationResults, OptimizationRun,
                                          OptimizationStatus, OptimizationType)

        # Create sample metadata
        metadata = OptimizationMetadata(
            scenario_id="setup_test_scenario",
            optimization_type=OptimizationType.ADVANCED_SCIPY,
            optimization_engine=OptimizationEngine.SCIPY_SLSQP,
            status=OptimizationStatus.COMPLETED,
            description="Sample optimization run created during setup",
            tags=["setup", "test", "sample"],
            random_seed=42,
            max_evaluations=50,
            runtime_seconds=12.5,
            function_evaluations=45,
            converged=True,
        )

        # Create sample configuration
        configuration = OptimizationConfiguration(
            objectives=[
                OptimizationObjective(
                    name="cost",
                    weight=0.4,
                    direction="minimize",
                    description="Minimize total compensation costs",
                ),
                OptimizationObjective(
                    name="equity",
                    weight=0.3,
                    direction="minimize",
                    description="Minimize compensation variance",
                ),
                OptimizationObjective(
                    name="targets",
                    weight=0.3,
                    direction="minimize",
                    description="Meet workforce growth targets",
                ),
            ],
            initial_parameters={
                "merit_rate_level_1": 0.045,
                "merit_rate_level_2": 0.040,
                "cola_rate": 0.025,
                "new_hire_salary_adjustment": 1.15,
            },
        )

        # Create sample results
        results = OptimizationResults(
            objective_value=0.234567,
            objective_breakdown={"cost": 0.12, "equity": 0.08, "targets": 0.035},
            optimal_parameters={
                "merit_rate_level_1": 0.042,
                "merit_rate_level_2": 0.038,
                "cola_rate": 0.023,
                "new_hire_salary_adjustment": 1.12,
            },
            risk_level="MEDIUM",
            risk_assessment={
                "level": "MEDIUM",
                "factors": ["Standard parameter ranges"],
                "assessment_date": datetime.now().isoformat(),
            },
        )

        # Create and save the sample run
        sample_run = OptimizationRun(
            metadata=metadata, configuration=configuration, results=results
        )

        storage = get_optimization_storage()
        run_id = storage.save_run_with_session_cache(sample_run)

        print(f"✅ Created sample optimization run: {run_id}")
        return True

    except Exception as e:
        print(f"❌ Failed to create sample data: {e}")
        return False


def print_usage_instructions():
    """Print instructions for using the optimization system."""
    print("\n" + "=" * 80)
    print("🚀 OPTIMIZATION STORAGE SYSTEM SETUP COMPLETE!")
    print("=" * 80)

    print("\n📖 Usage Instructions:")
    print("\n1. 🧠 Advanced Optimization Interface:")
    print("   - Launch: streamlit run advanced_optimization.py")
    print("   - Features: SciPy-based multi-objective optimization")
    print("   - Results: Automatically saved to unified storage")

    print("\n2. 💰 Compensation Tuning Interface:")
    print("   - Launch: streamlit run compensation_tuning.py")
    print("   - Features: Manual parameter adjustment and simulation")
    print("   - Results: Automatically saved to unified storage")

    print("\n3. 📊 Optimization Dashboard:")
    print("   - Launch: streamlit run optimization_dashboard.py")
    print("   - Features: View, compare, export, and analyze all results")
    print("   - Analytics: Performance trends and parameter sensitivity")

    print("\n4. 🔧 Integration with Existing Code:")
    print("   - Import: from optimization_integration_patch import *")
    print("   - Use: enhanced_save_optimization_results()")
    print("   - Use: enhanced_load_optimization_results()")

    print("\n📁 Key Components:")
    print("   - Database: /Users/nicholasamaral/planwise_navigator/simulation.duckdb")
    print("   - Cache: /tmp/planwise_optimization_cache/")
    print("   - Storage Tables: optimization_runs, optimization_results, etc.")

    print("\n🔍 System Monitoring:")
    print("   - Health Check: validate_optimization_environment()")
    print("   - Cache Stats: get_optimization_cache().get_cache_stats()")
    print(
        "   - Recent Results: get_optimization_results_manager().get_recent_results()"
    )

    print("\n💡 Tips:")
    print("   - All optimization results are versioned and immutable")
    print("   - Export formats: JSON, CSV, Excel, Parquet, Pickle")
    print("   - Session state integration for immediate result access")
    print("   - Automatic risk assessment and parameter validation")
    print("   - Comparison tools for A/B testing parameter sets")

    print("\n" + "=" * 80)


def main():
    """Main setup function."""
    print("🎯 PlanWise Navigator Optimization Storage Setup")
    print("=" * 50)

    success_steps = 0
    total_steps = 4

    # Step 1: Setup database tables
    if setup_database_tables():
        success_steps += 1

    # Step 2: Setup cache directory
    if setup_cache_directory():
        success_steps += 1

    # Step 3: Validate system
    if validate_system():
        success_steps += 1

    # Step 4: Create sample data
    if create_sample_data():
        success_steps += 1

    print(f"\n📊 Setup Summary: {success_steps}/{total_steps} steps completed")

    if success_steps == total_steps:
        print("🎉 SETUP SUCCESSFUL!")
        print_usage_instructions()
        return 0
    else:
        print(f"⚠️  SETUP PARTIALLY COMPLETED ({success_steps}/{total_steps})")
        print("Some components may not work correctly.")
        return 1


if __name__ == "__main__":
    exit_code = main()
    sys.exit(exit_code)
