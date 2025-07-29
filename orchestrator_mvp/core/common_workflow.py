"""
Common workflow functions shared between single-year and multi-year orchestrators.

This module contains shared functionality that both execution modes rely on,
including database setup, seed loading, foundation models, and validation.
"""

import os
import sys
import yaml
from typing import Dict, Any, Optional

# Add parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from orchestrator_mvp.core import clear_database
from orchestrator_mvp.loaders import run_dbt_model, run_dbt_model_with_vars, run_dbt_seed
from orchestrator_mvp.inspectors import inspect_stg_census_data
from orchestrator_mvp.core.workforce_calculations import calculate_workforce_requirements_from_config
from orchestrator_mvp.core.database_manager import get_connection
from orchestrator_mvp.core.event_emitter import validate_events_in_database


def clear_database_and_setup() -> None:
    """Clear database and perform initial setup."""
    print("\n" + "="*60)
    print("🧹 CLEARING DATABASE")
    print("="*60)
    clear_database()
    print("✅ Database cleared successfully")


def load_seed_data() -> None:
    """Load all required seed data for the simulation."""
    print("\n" + "="*60)
    print("📦 LOADING SEED DATA")
    print("="*60)

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

    print("Loading termination hazard configuration...")
    run_dbt_seed("config_termination_hazard_base")
    run_dbt_seed("config_termination_hazard_age_multipliers")
    run_dbt_seed("config_termination_hazard_tenure_multipliers")

    print("Loading raise configuration...")
    run_dbt_seed("config_raise_timing_distribution")
    run_dbt_seed("config_raises_hazard")

    print("✅ All seed data loaded successfully")


def create_staging_tables() -> None:
    """Create all staging tables from seed data."""
    print("\n" + "="*60)
    print("🏗️ CREATING STAGING TABLES")
    print("="*60)

    run_dbt_model("stg_config_job_levels")
    run_dbt_model("stg_config_cola_by_year")
    run_dbt_model("stg_comp_levers")

    print("Building termination hazard staging tables...")
    run_dbt_model("stg_config_termination_hazard_base")
    run_dbt_model("stg_config_termination_hazard_age_multipliers")
    run_dbt_model("stg_config_termination_hazard_tenure_multipliers")

    print("Building promotion hazard staging tables...")
    run_dbt_model("stg_config_promotion_hazard_base")
    run_dbt_model("stg_config_promotion_hazard_age_multipliers")
    run_dbt_model("stg_config_promotion_hazard_tenure_multipliers")

    print("✅ All staging tables created successfully")


def build_foundation_models() -> None:
    """Build foundation models required for simulation."""
    print("\n" + "="*60)
    print("🏛️ BUILDING FOUNDATION MODELS")
    print("="*60)

    print("Building census data model...")
    run_dbt_model("stg_census_data")

    print("Building baseline workforce...")
    run_dbt_model("int_baseline_workforce")

    print("Building previous year workforce...")
    run_dbt_model("int_workforce_previous_year")

    print("Building effective parameters...")
    run_dbt_model("int_effective_parameters")

    print("✅ Foundation models built successfully")


def inspect_foundation_data() -> None:
    """Inspect and validate foundation data."""
    print("\n" + "="*60)
    print("🔍 INSPECTING FOUNDATION DATA")
    print("="*60)

    inspect_stg_census_data()
    print("✅ Foundation data inspection completed")


def show_workforce_calculation() -> Dict[str, Any]:
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
        config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "config", "test_config.yaml")
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


def generate_simulation_events_via_dbt(simulation_year: int) -> None:
    """Generate simulation events using dbt models in proper calendar sequence."""
    print("\n" + "="*60)
    print("🎯 SIMULATION EVENT GENERATION VIA DBT MODELS")
    print("="*60)

    try:
        print(f"\n📋 EVENT GENERATION PARAMETERS:")
        print(f"   • Simulation year: {simulation_year}")
        print(f"   • Method: dbt models (calendar-sequenced)")
        print(f"   • Sequence: Promotion (Feb 1) → Raise (July 15) → Termination → Hiring")

        # Step 0: Build required dependencies first
        print(f"\n📋 Step 0: Building event generation dependencies...")
        print(f"   • Building foundation model: int_employee_compensation_by_year")
        result = run_dbt_model_with_vars("int_employee_compensation_by_year", {"simulation_year": simulation_year})
        if not result["success"]:
            raise RuntimeError(f"Foundation model build failed: {result.get('error', 'Unknown error')}")
        print(f"   ✅ Foundation model built")

        print(f"   • Building hazard models...")
        hazard_models = ["int_hazard_promotion", "int_hazard_termination", "int_hazard_merit"]
        for hazard_model in hazard_models:
            print(f"     ◦ Building {hazard_model}")
            # Hazard models don't use variables - build them without vars
            try:
                run_dbt_model(hazard_model)
                print(f"     ✅ {hazard_model} built successfully")
            except Exception as e:
                print(f"     ⚠️ Warning: {hazard_model} failed, continuing anyway: {str(e)}")
        print(f"   ✅ Hazard models built")

        # Step 1: Generate promotion events (February 1 - happens first in calendar year)
        print(f"\n📋 Step 1: Generating promotion events (February 1, {simulation_year})...")
        result = run_dbt_model_with_vars("int_promotion_events", {"simulation_year": simulation_year})
        if not result["success"]:
            raise RuntimeError(f"Promotion events generation failed: {result.get('error', 'Unknown error')}")
        print(f"   ✅ Promotion events generated")

        # Step 2: Generate raise events (July 15 - uses post-promotion compensation)
        print(f"\n📋 Step 2: Generating raise events (July 15, {simulation_year})...")
        result = run_dbt_model_with_vars("int_merit_events", {"simulation_year": simulation_year})
        if not result["success"]:
            print(f"   ⚠️ Warning: Raise events failed, continuing anyway: {result.get('error', 'Unknown error')}")
        else:
            print(f"   ✅ Raise events generated")

        # Step 3: Generate termination events
        print(f"\n📋 Step 3: Generating termination events...")
        result = run_dbt_model_with_vars("int_termination_events", {"simulation_year": simulation_year})
        if not result["success"]:
            print(f"   ⚠️ Warning: Termination events failed, continuing anyway: {result.get('error', 'Unknown error')}")
        else:
            print(f"   ✅ Termination events generated")

        # Step 4: Generate hiring events
        print(f"\n📋 Step 4: Generating hiring events...")
        result = run_dbt_model_with_vars("int_hiring_events", {"simulation_year": simulation_year})
        if not result["success"]:
            print(f"   ⚠️ Warning: Hiring events failed, continuing anyway: {result.get('error', 'Unknown error')}")
        else:
            print(f"   ✅ Hiring events generated")

        # Step 5: Generate new hire termination events
        print(f"\n📋 Step 5: Generating new hire termination events...")
        result = run_dbt_model_with_vars("int_new_hire_termination_events", {"simulation_year": simulation_year})
        if not result["success"]:
            print(f"   ⚠️ Warning: New hire termination events failed, continuing anyway: {result.get('error', 'Unknown error')}")
        else:
            print(f"   ✅ New hire termination events generated")

        # Step 6: Combine all events into fct_yearly_events
        print(f"\n📋 Step 6: Combining all events into fct_yearly_events...")
        result = run_dbt_model_with_vars("fct_yearly_events", {"simulation_year": simulation_year})
        if not result["success"]:
            raise RuntimeError(f"Event combination failed: {result.get('error', 'Unknown error')}")
        print(f"   ✅ All events combined")

        # Validate events in database
        print(f"\n🔍 Validating all generated events...")
        validate_events_in_database(simulation_year=simulation_year)

        print(f"\n✅ dbt-based event generation completed successfully!")

    except Exception as e:
        print(f"\n❌ ERROR in dbt event generation: {str(e)}")
        raise


def prompt_user_continue(message: str, skip_breaks: bool = False) -> None:
    """Prompt user to continue if not in skip_breaks mode."""
    if not skip_breaks:
        input(f"\n📋 Press Enter to {message}...")


def load_config() -> Dict[str, Any]:
    """Load simulation configuration from test_config.yaml."""
    config_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
        "config",
        "test_config.yaml"
    )
    with open(config_path, 'r') as f:
        return yaml.safe_load(f)


def display_header(title: str) -> None:
    """Display a formatted header."""
    print("\n" + "="*60)
    print(f"🚀 {title}")
    print("="*60)


def display_completion_message(is_multi_year: bool = False) -> None:
    """Display completion message based on execution mode."""
    print("\n" + "="*60)
    if is_multi_year:
        print("✅ MULTI-YEAR SIMULATION COMPLETED SUCCESSFULLY!")
        print("="*60)
        print("\nMulti-year simulation artifacts created:")
        print("  • Workforce snapshots for each year")
        print("  • Event logs across all simulation years")
        print("  • Year-over-year analysis results")
        print("  • Growth validation reports")
        print("  • Complete step-by-step audit trail")
    else:
        print("✅ SINGLE-YEAR SIMULATION COMPLETED SUCCESSFULLY!")
        print("="*60)
        print("\nSingle-year simulation completed:")
        print("  • All steps validated in proper sequence")
        print("  • Workforce snapshot generated and validated")
        print("  • Complete audit trail of step completion")
        print("\nYou can now:")
        print("  1. Run additional models with run_dbt_model()")
        print("  2. Create new inspector functions for other tables")
        print("  3. Query the database directly with DuckDB")
        print("  4. Analyze workforce snapshots with inspect_workforce_snapshot()")

    print("\nHappy debugging! 🎉")
