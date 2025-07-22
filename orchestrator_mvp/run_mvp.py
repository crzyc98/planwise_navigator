#!/usr/bin/env python3
"""MVP Orchestrator for debugging dbt models.

Interactive script to clear the database, run dbt models one by one,
and inspect results with detailed validation.
"""

import os
import sys
import argparse

# Add current directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from .core import clear_database
from .loaders import run_dbt_model, run_dbt_seed
from .inspectors import inspect_stg_census_data
from .core.workforce_calculations import calculate_workforce_requirements_from_config
from .core.database_manager import get_connection
from .core.event_emitter import generate_and_store_all_events, validate_events_in_database
from .core.workforce_snapshot import generate_workforce_snapshot
from .inspectors.workforce_inspector import inspect_workforce_snapshot
import yaml


def show_workforce_calculation() -> None:
    """Display workforce calculation results using the real baseline data."""
    print("\n" + "="*60)
    print("📊 WORKFORCE CALCULATION RESULTS")
    print("="*60)

    try:
        # Get workforce count from int_baseline_workforce
        conn = get_connection()
        try:
            result = conn.execute("SELECT COUNT(*) FROM int_baseline_workforce WHERE employment_status = 'active'").fetchone()
            active_count = result[0]
            print(f"\n✅ Baseline workforce loaded: {active_count:,} active employees")
        finally:
            conn.close()

        # Load configuration
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "test_config.yaml")
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        workforce_config = config['workforce']
        workforce_config['target_growth_rate'] = config['ops']['run_multi_year_simulation']['config']['target_growth_rate']

        # Calculate workforce requirements
        calc_result = calculate_workforce_requirements_from_config(active_count, workforce_config)

        print("\n📋 SIMULATION PARAMETERS:")
        print(f"   • Target growth rate: {workforce_config['target_growth_rate']:.1%}")
        print(f"   • Total termination rate: {workforce_config['total_termination_rate']:.1%}")
        print(f"   • New hire termination rate: {workforce_config['new_hire_termination_rate']:.1%}")

        print("\n📊 NEXT YEAR REQUIREMENTS:")
        print(f"   • Starting workforce: {calc_result['current_workforce']:,}")
        print(f"   • Terminations needed: {calc_result['experienced_terminations']:,}")
        print(f"   • Gross hires needed: {calc_result['total_hires_needed']:,}")
        print(f"   • Expected new hire terminations: {calc_result['expected_new_hire_terminations']:,}")
        print(f"   • Net workforce growth: +{calc_result['net_hiring_impact']:,}")

        print("\n🧮 CALCULATION FORMULAS:")
        for formula_name, formula in calc_result['formula_details'].items():
            print(f"   • {formula_name}: {formula}")

        print("\n✅ Workforce calculation completed successfully!")

        # Return the calculation result for use in event generation
        return calc_result

    except Exception as e:
        print(f"\n❌ ERROR in workforce calculation: {str(e)}")
        raise


def generate_simulation_events(calc_result: dict) -> None:
    """Generate simulation events based on workforce calculations."""
    print("\n" + "="*60)
    print("🎯 SIMULATION EVENT GENERATION")
    print("="*60)

    try:
        # Load configuration to get new_hire_termination_rate
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "test_config.yaml")
        with open(config_path, 'r') as f:
            config = yaml.safe_load(f)

        # Add new_hire_termination_rate to calc_result if not present
        if 'new_hire_termination_rate' not in calc_result:
            calc_result['new_hire_termination_rate'] = config['workforce']['new_hire_termination_rate']

        simulation_year = 2025  # Default simulation year

        print(f"\n📋 EVENT GENERATION PARAMETERS:")
        print(f"   • Experienced terminations: {calc_result['experienced_terminations']:,}")
        print(f"   • Total hires needed: {calc_result['total_hires_needed']:,}")
        print(f"   • Expected new hire terminations: {calc_result['expected_new_hire_terminations']:,}")
        print(f"   • Simulation year: {simulation_year}")
        print(f"   • Random seed: 42 (for reproducibility)")

        # Generate all events (terminations, hires, new hire terminations)
        generate_and_store_all_events(
            calc_result=calc_result,
            simulation_year=simulation_year,
            random_seed=42
        )

        # Validate events
        print(f"\n🔍 Validating all generated events...")
        validate_events_in_database(simulation_year=simulation_year)

        print(f"\n✅ Event generation completed successfully!")

    except Exception as e:
        print(f"\n❌ ERROR in event generation: {str(e)}")
        raise


def main(skip_breaks: bool = False) -> None:
    """Main orchestrator workflow.

    Args:
        skip_breaks: If True, skip all interactive prompts and run continuously
    """
    print("\n" + "="*60)
    print("🚀 PLANWISE NAVIGATOR - MVP ORCHESTRATOR")
    print("="*60)
    print("\nThis tool will help you debug dbt models by running them")
    print("individually and inspecting the results at each step.")

    if skip_breaks:
        print("\n⚡ Running in non-interactive mode (skipping all breaks)")

    try:
        # Step 1: Clear database
        if not skip_breaks:
            input("\n📋 Press Enter to clear the database...")
        clear_database()

        # Step 2: Run stg_census_data
        if not skip_breaks:
            input("\n📋 Press Enter to run stg_census_data model...")
        run_dbt_model("stg_census_data")

        # Step 3: Inspect census data
        if not skip_breaks:
            input("\n📋 Press Enter to inspect census data...")
        inspect_stg_census_data()

        print("\n✨ Foundational data looks good!")
        print("Now let's build on top of it...")

        # Step 4: Load required seed data
        if not skip_breaks:
            input("\n📋 Press Enter to load seed data...")
        print("Loading config_job_levels...")
        run_dbt_seed("config_job_levels")
        print("Loading comp_levers...")
        run_dbt_seed("comp_levers")
        print("Loading config_cola_by_year...")
        run_dbt_seed("config_cola_by_year")
        print("Loading promotion hazard configuration...")
        run_dbt_seed("config_promotion_hazard_base")
        run_dbt_seed("config_promotion_hazard_age_multipliers")
        run_dbt_seed("config_promotion_hazard_tenure_multipliers")

        # Step 5: Create staging tables
        if not skip_breaks:
            input("\n📋 Press Enter to create staging tables...")
        run_dbt_model("stg_config_job_levels")

        # Step 6: Run int_baseline_workforce
        if not skip_breaks:
            input("\n📋 Press Enter to run int_baseline_workforce model...")
        run_dbt_model("int_baseline_workforce")

        # Step 6.5: Run int_workforce_previous_year for promotions
        if not skip_breaks:
            input("\n📋 Press Enter to run int_workforce_previous_year model...")
        run_dbt_model("int_workforce_previous_year")

        # Step 7: Show workforce calculation results
        if not skip_breaks:
            input("\n📋 Press Enter to calculate workforce requirements...")
        calc_result = show_workforce_calculation()

        # Step 8: Generate simulation events
        if not skip_breaks:
            input("\n📋 Press Enter to generate simulation events...")
        generate_simulation_events(calc_result)

        # Step 9: Generate workforce snapshot
        if not skip_breaks:
            input("\n📋 Press Enter to generate workforce snapshot...")
        simulation_year = 2025
        snapshot_result = generate_workforce_snapshot(simulation_year=simulation_year)

        if not snapshot_result["success"]:
            print(f"\n❌ ERROR generating workforce snapshot: {snapshot_result.get('error', 'Unknown error')}")
            raise RuntimeError("Failed to generate workforce snapshot")

        # Step 10: Inspect workforce snapshot
        if not skip_breaks:
            input("\n📋 Press Enter to inspect workforce snapshot...")
        inspect_workforce_snapshot(simulation_year=simulation_year)

        # Completion message
        print("\n" + "="*60)
        print("✅ MVP ORCHESTRATOR COMPLETED SUCCESSFULLY!")
        print("="*60)
        print("\nYou can now:")
        print("  1. Run additional models with run_dbt_model()")
        print("  2. Create new inspector functions for other tables")
        print("  3. Query the database directly with DuckDB")
        print("  4. Analyze workforce snapshots with inspect_workforce_snapshot()")
        print("\nHappy debugging! 🎉")

    except KeyboardInterrupt:
        print("\n\n⚠️  Orchestrator interrupted by user.")
        sys.exit(1)

    except Exception as e:
        print(f"\n\n❌ FATAL ERROR: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="PlanWise Navigator MVP Orchestrator - Debug dbt models interactively",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run interactively (default)
  python -m orchestrator_mvp.run_mvp

  # Run without breaks (non-interactive)
  python -m orchestrator_mvp.run_mvp --no-breaks
  python -m orchestrator_mvp.run_mvp -n
"""
    )

    parser.add_argument(
        '--no-breaks', '-n',
        action='store_true',
        help='Skip all interactive prompts and run continuously'
    )

    args = parser.parse_args()

    # Run main with the skip_breaks flag
    main(skip_breaks=args.no_breaks)
