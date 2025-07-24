#!/usr/bin/env python3
"""MVP Orchestrator for debugging dbt models.

Interactive script to clear the database, run dbt models one by one,
and inspect results with detailed validation.
"""

import os
import sys
import argparse

# Add parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator_mvp.core import clear_database
from orchestrator_mvp.loaders import run_dbt_model, run_dbt_seed
from orchestrator_mvp.inspectors import inspect_stg_census_data
from orchestrator_mvp.core.workforce_calculations import calculate_workforce_requirements_from_config
from orchestrator_mvp.core.database_manager import get_connection
from orchestrator_mvp.core.event_emitter import generate_and_store_all_events, validate_events_in_database
from orchestrator_mvp.core.workforce_snapshot import generate_workforce_snapshot
from orchestrator_mvp.inspectors.workforce_inspector import inspect_workforce_snapshot
from orchestrator_mvp.core.multi_year_simulation import run_multi_year_simulation
from orchestrator_mvp.core.multi_year_orchestrator import MultiYearSimulationOrchestrator
from orchestrator_mvp.core.simulation_checklist import SimulationChecklist, StepSequenceError
from orchestrator_mvp.inspectors.multi_year_inspector import (
    compare_year_over_year_metrics,
    validate_cumulative_growth,
    display_multi_year_summary
)
import yaml
import logging


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


def _validate_sequential_requirements(
    start_year: int, 
    end_year: int, 
    force_clear: bool, 
    preserve_data: bool
) -> None:
    """
    Validate sequential year execution requirements before starting multi-year simulation.
    
    Args:
        start_year: Starting year of simulation
        end_year: Ending year of simulation
        force_clear: Whether force clear mode is enabled
        preserve_data: Whether data preservation mode is enabled
        
    Raises:
        ValueError: If sequential requirements are not met
    """
    if force_clear:
        # Force clear mode bypasses sequential validation
        return
        
    if start_year == 2025:
        # Starting from baseline year, no previous dependencies
        return
        
    # Check if we're attempting to skip years
    conn = get_connection()
    try:
        # Check for gaps in previous years
        for check_year in range(2025, start_year):
            snapshot_check = """
                SELECT COUNT(*) FROM fct_workforce_snapshot 
                WHERE simulation_year = ? AND employment_status = 'active'
            """
            
            result = conn.execute(snapshot_check, [check_year]).fetchone()
            
            if not result or result[0] == 0:
                raise ValueError(
                    f"Sequential execution validation failed: Year {check_year} is missing or incomplete. "
                    f"Cannot start simulation from year {start_year} without completing year {check_year} first. "
                    f"Multi-year simulations must be run sequentially. "
                    f"Use --force-clear to start fresh from 2025, or complete year {check_year} first."
                )
        
        print(f"✅ Sequential validation passed: All years 2025-{start_year-1} are complete")
        
    except Exception as e:
        if "Sequential execution validation failed" in str(e):
            raise
        # Other database errors - warn but don't block
        print(f"⚠️ Could not validate sequential requirements: {str(e)}")
        print("Proceeding anyway - orchestrator will validate during execution")
    finally:
        conn.close()


def main(
    skip_breaks: bool = False,
    multi_year: bool = False,
    resume_from: int = None,
    validate_only: bool = False,
    force_step: str = None,
    preserve_data: bool = False,
    force_clear: bool = False,
    reset_year: int = None,
    validate_data: bool = False
) -> None:
    """Main orchestrator workflow.

    Args:
        skip_breaks: If True, skip all interactive prompts and run continuously
        multi_year: If True, run multi-year simulation mode
        resume_from: Optional year to resume multi-year simulation from
        validate_only: If True, only run validation checks without executing steps
        force_step: Override checklist validation for a specific step (with warning)
        preserve_data: If True, preserve existing multi-year simulation data
        force_clear: If True, clear all simulation data before starting
        reset_year: Clear data for a specific year only
        validate_data: Run data integrity checks before starting
    """
    print("\n" + "="*60)
    print("🚀 PLANWISE NAVIGATOR - MVP ORCHESTRATOR")
    print("="*60)

    if multi_year:
        print("\n🗓️ MULTI-YEAR SIMULATION MODE WITH CHECKLIST ENFORCEMENT")
        print("This tool will run a complete multi-year workforce simulation")
        print("using the configuration parameters from test_config.yaml")
        print("Each step will be validated to ensure proper sequencing.")
        if resume_from:
            print(f"📋 Resuming simulation from year {resume_from}")
        if validate_only:
            print("🔍 Validation-only mode: checking prerequisites without execution")
        if preserve_data:
            print("🔄 Data preservation mode: existing simulation data will be kept")
        if force_clear:
            print("🧹 Force clear mode: all simulation data will be cleared")
        if reset_year:
            print(f"🔄 Reset mode: clearing data for year {reset_year} only")
        if validate_data:
            print("📊 Data validation mode: checking data integrity before starting")
    else:
        print("\nThis tool will help you debug dbt models by running them")
        print("individually and inspecting the results at each step.")
        print("Single-year mode includes checklist validation for key steps.")

    if skip_breaks:
        print("\n⚡ Running in non-interactive mode (skipping all breaks)")

    if force_step:
        print(f"\n⚠️ WARNING: Force mode enabled for step '{force_step}' - checklist validation will be overridden")

    try:
        # Initialize checklist for single-year mode if not multi-year
        single_year_checklist = None
        if not multi_year:
            single_year_checklist = SimulationChecklist(2025, 2025)  # Single year checklist

        # Step 1: Clear database (with checklist validation)
        if not multi_year:
            try:
                single_year_checklist.assert_step_ready("pre_simulation")
            except StepSequenceError as e:
                if force_step != "pre_simulation":
                    print(f"\n❌ {str(e)}")
                    raise
                else:
                    print(f"\n⚠️ Forcing step 'pre_simulation' - {str(e)}")

        if not skip_breaks:
            input("\n📋 Press Enter to clear the database...")
        clear_database()

        if not multi_year:
            single_year_checklist.mark_step_complete("pre_simulation")

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

        # Step 6: Run int_baseline_workforce (with checklist validation)
        if not multi_year:
            try:
                single_year_checklist.assert_step_ready("workforce_baseline", 2025)
            except StepSequenceError as e:
                if force_step != "workforce_baseline":
                    print(f"\n❌ {str(e)}")
                    raise
                else:
                    print(f"\n⚠️ Forcing step 'workforce_baseline' - {str(e)}")

        if not skip_breaks:
            input("\n📋 Press Enter to run int_baseline_workforce model...")
        run_dbt_model("int_baseline_workforce")

        if not multi_year:
            single_year_checklist.mark_step_complete("workforce_baseline", 2025)

        # Step 6.5: Run int_workforce_previous_year for promotions
        if not skip_breaks:
            input("\n📋 Press Enter to run int_workforce_previous_year model...")
        run_dbt_model("int_workforce_previous_year")

        # Step 7: Show workforce calculation results (with checklist validation)
        if not multi_year:
            try:
                single_year_checklist.assert_step_ready("workforce_requirements", 2025)
            except StepSequenceError as e:
                if force_step != "workforce_requirements":
                    print(f"\n❌ {str(e)}")
                    raise
                else:
                    print(f"\n⚠️ Forcing step 'workforce_requirements' - {str(e)}")

        if not skip_breaks:
            input("\n📋 Press Enter to calculate workforce requirements...")
        calc_result = show_workforce_calculation()

        if not multi_year:
            single_year_checklist.mark_step_complete("workforce_requirements", 2025)

        # Step 8: Generate simulation events (with checklist validation)
        if not multi_year:
            try:
                single_year_checklist.assert_step_ready("event_generation", 2025)
            except StepSequenceError as e:
                if force_step != "event_generation":
                    print(f"\n❌ {str(e)}")
                    raise
                else:
                    print(f"\n⚠️ Forcing step 'event_generation' - {str(e)}")

        if not skip_breaks:
            input("\n📋 Press Enter to generate simulation events...")
        generate_simulation_events(calc_result)

        if not multi_year:
            single_year_checklist.mark_step_complete("event_generation", 2025)

        # Branch: Multi-year simulation or single-year mode
        if multi_year:
            # Load configuration for multi-year simulation
            config_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "test_config.yaml")
            with open(config_path, 'r') as f:
                raw_config = yaml.safe_load(f)

            start_year = raw_config['simulation']['start_year']
            end_year = raw_config['simulation']['end_year']

            # Flatten config for MultiYearSimulationOrchestrator
            config = {
                'target_growth_rate': raw_config['simulation']['target_growth_rate'],
                'random_seed': raw_config['simulation']['random_seed'],
                'workforce': raw_config['workforce']
            }

            # Handle data management options for multi-year simulation
            if reset_year is not None:
                print(f"\n🔄 RESET YEAR MODE: Clearing data for year {reset_year}")
                orchestrator = MultiYearSimulationOrchestrator(
                    start_year, end_year, config,
                    force_clear=False, preserve_data=True
                )
                orchestrator.clear_specific_years([reset_year])
                print(f"✅ Year {reset_year} data cleared successfully")
                return

            if validate_data:
                print(f"\n📊 DATA VALIDATION MODE")
                print(f"Checking data integrity for multi-year simulation ({start_year}-{end_year})")

                from orchestrator_mvp.core.multi_year_simulation import validate_multi_year_data_integrity
                validation_results = validate_multi_year_data_integrity(start_year, end_year)

                print(f"\n🔍 Validation Results:")
                print(f"   • Baseline available: {'✅' if validation_results['baseline_available'] else '❌'}")
                print(f"   • Existing years: {len(validation_results['existing_years'])}")
                print(f"   • Data gaps: {validation_results['data_gaps']}")
                print(f"   • Can proceed: {'✅' if validation_results['can_proceed'] else '❌'}")

                if validation_results['recommendations']:
                    print(f"\n💡 Recommendations:")
                    for rec in validation_results['recommendations']:
                        print(f"   • {rec}")

                print("\n✅ Data validation completed")
                return

            if validate_only:
                # Validation-only mode
                print(f"\n🔍 VALIDATION-ONLY MODE")
                print(f"Checking prerequisites for multi-year simulation ({start_year}-{end_year})")

                orchestrator = MultiYearSimulationOrchestrator(
                    start_year, end_year, config,
                    force_clear=force_clear, preserve_data=preserve_data
                )
                progress_summary = orchestrator.get_progress_summary()
                print(f"\n{progress_summary}")

                print("\n✅ Validation completed - no simulation executed")
                return

            if not skip_breaks:
                print(f"\n🗓️ Multi-year simulation configured for {start_year}-{end_year}")
                input(f"\n📋 Press Enter to run checklist-enforced multi-year simulation ({start_year}-{end_year})...")

            # Configure logging for multi-year simulation
            logging.basicConfig(level=logging.INFO, format='%(message)s')

            # Create checklist-enforced orchestrator with data management options
            try:
                # Validate sequential year execution requirements before starting
                _validate_sequential_requirements(start_year, end_year, force_clear, preserve_data)
                
                orchestrator = MultiYearSimulationOrchestrator(
                    start_year, end_year, config,
                    force_clear=force_clear, preserve_data=preserve_data
                )

                print(f"\n📋 Initial Progress Status:")
                print(orchestrator.get_progress_summary())

                # Validate conflicting options
                if force_clear and preserve_data:
                    raise ValueError("Cannot use --force-clear and --preserve-data together")

                # Run checklist-enforced multi-year simulation with enhanced error handling
                simulation_results = orchestrator.run_simulation(
                    skip_breaks=skip_breaks,
                    resume_from=resume_from
                )

                # Multi-year analysis
                print("\n" + "="*60)
                print("📊 MULTI-YEAR ANALYSIS")
                print("="*60)

                # Year-over-year comparison
                compare_year_over_year_metrics(start_year, end_year)

                # Growth validation
                target_growth = raw_config['simulation'].get('target_growth_rate', 0.03)
                validate_cumulative_growth(start_year, end_year, target_growth)

                # Comprehensive summary
                display_multi_year_summary(start_year, end_year)

                print(f"\n✅ Checklist-enforced multi-year simulation completed successfully!")
                print(f"Years simulated: {len(simulation_results['years_completed'])}/{simulation_results['end_year'] - simulation_results['start_year'] + 1}")
                print(f"Total runtime: {simulation_results['total_runtime_seconds']:.1f} seconds")

                # Show final progress summary
                print(f"\n📋 Final Progress Status:")
                print(orchestrator.get_progress_summary())

            except StepSequenceError as e:
                print(f"\n❌ Step sequence error in multi-year simulation: {str(e)}")
                print("Use --force-step to override checklist validation if needed.")
                raise
            except ValueError as e:
                error_msg = str(e).lower()
                if "circular dependency" in error_msg or "sequential" in error_msg or "helper model" in error_msg:
                    print(f"\n❌ Circular dependency or sequential execution error: {str(e)}")
                    print("\n💡 Troubleshooting guidance:")
                    print("   1. Multi-year simulations must be run sequentially (2025 → 2026 → 2027, etc.)")
                    print("   2. Each year depends on the previous year's completed workforce snapshot")
                    print("   3. Use --force-clear to start fresh from year 2025")
                    print("   4. Use --reset-year <YEAR> to clear a specific year and restart from there")
                    print("   5. Check that previous years completed successfully without errors")
                    print("\nFor more details, see docs/multi_year_simulation_checklist.md")
                else:
                    print(f"\n❌ Configuration or validation error: {str(e)}")
                raise
            except Exception as e:
                error_msg = str(e).lower()
                if "circular dependency" in error_msg or "workforce snapshot" in error_msg:
                    print(f"\n❌ Dependency resolution error: {str(e)}")
                    print("\n💡 This may be a circular dependency issue. Try running years sequentially.")
                else:
                    print(f"\n❌ Multi-year simulation failed: {str(e)}")
                raise

        else:
            # Single-year mode (with checklist validation)
            # Step 9: Generate workforce snapshot (with checklist validation)
            if not multi_year:
                try:
                    single_year_checklist.assert_step_ready("workforce_snapshot", 2025)
                except StepSequenceError as e:
                    if force_step != "workforce_snapshot":
                        print(f"\n❌ {str(e)}")
                        raise
                    else:
                        print(f"\n⚠️ Forcing step 'workforce_snapshot' - {str(e)}")

            if not skip_breaks:
                input("\n📋 Press Enter to generate workforce snapshot...")
            simulation_year = 2025
            snapshot_result = generate_workforce_snapshot(simulation_year=simulation_year)

            if not snapshot_result["success"]:
                print(f"\n❌ ERROR generating workforce snapshot: {snapshot_result.get('error', 'Unknown error')}")
                raise RuntimeError("Failed to generate workforce snapshot")

            if not multi_year:
                single_year_checklist.mark_step_complete("workforce_snapshot", 2025)

            # Step 10: Inspect workforce snapshot (with checklist validation)
            if not multi_year:
                try:
                    single_year_checklist.assert_step_ready("validation_metrics", 2025)
                except StepSequenceError as e:
                    if force_step != "validation_metrics":
                        print(f"\n❌ {str(e)}")
                        raise
                    else:
                        print(f"\n⚠️ Forcing step 'validation_metrics' - {str(e)}")

            if not skip_breaks:
                input("\n📋 Press Enter to inspect workforce snapshot...")
            inspect_workforce_snapshot(simulation_year=simulation_year)

            if not multi_year:
                single_year_checklist.mark_step_complete("validation_metrics", 2025)

                # Show final checklist status for single-year
                print(f"\n📋 Single-Year Checklist Status:")
                print(single_year_checklist.get_progress_summary())

        # Completion message
        print("\n" + "="*60)
        if multi_year:
            print("✅ CHECKLIST-ENFORCED MULTI-YEAR SIMULATION COMPLETED SUCCESSFULLY!")
        else:
            print("✅ CHECKLIST-ENFORCED MVP ORCHESTRATOR COMPLETED SUCCESSFULLY!")
        print("="*60)

        if multi_year:
            print("\nChecklist-enforced multi-year simulation artifacts created:")
            print("  • Workforce snapshots for each year")
            print("  • Event logs across all simulation years")
            print("  • Year-over-year analysis results")
            print("  • Growth validation reports")
            print("  • Complete step-by-step audit trail")
        else:
            print("\nChecklist-enforced single-year simulation completed:")
            print("  • All steps validated in proper sequence")
            print("  • Workforce snapshot generated and validated")
            print("  • Complete audit trail of step completion")
            print("\nYou can now:")
            print("  1. Run additional models with run_dbt_model()")
            print("  2. Create new inspector functions for other tables")
            print("  3. Query the database directly with DuckDB")
            print("  4. Analyze workforce snapshots with inspect_workforce_snapshot()")

        print("\nHappy debugging! 🎉")

    except KeyboardInterrupt:
        print("\n\n⚠️  Orchestrator interrupted by user.")
        sys.exit(1)

    except StepSequenceError as e:
        print(f"\n\n❌ STEP SEQUENCE ERROR: {str(e)}")
        print("Use --force-step to override checklist validation if needed.")
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
  # Run single-year simulation interactively (default)
  python -m orchestrator_mvp.run_mvp

  # Run single-year without breaks (non-interactive)
  python -m orchestrator_mvp.run_mvp --no-breaks
  python -m orchestrator_mvp.run_mvp -n

  # Run checklist-enforced multi-year simulation (interactive)
  python -m orchestrator_mvp.run_mvp --multi-year
  python -m orchestrator_mvp.run_mvp -m

  # Run multi-year simulation without breaks
  python -m orchestrator_mvp.run_mvp --multi-year --no-breaks
  python -m orchestrator_mvp.run_mvp -m -n

  # Resume multi-year simulation from year 2027
  python -m orchestrator_mvp.run_mvp --multi-year --resume-from 2027

  # Validate prerequisites without running simulation
  python -m orchestrator_mvp.run_mvp --multi-year --validate-only

  # Force a specific step (emergency override)
  python -m orchestrator_mvp.run_mvp --force-step workforce_snapshot

  # Data management options:
  # Run with data preservation (default)
  python -m orchestrator_mvp.run_mvp --multi-year --preserve-data

  # Clear all simulation data before starting
  python -m orchestrator_mvp.run_mvp --multi-year --force-clear

  # Clear data for a specific year only
  python -m orchestrator_mvp.run_mvp --multi-year --reset-year 2027

  # Validate data integrity before starting
  python -m orchestrator_mvp.run_mvp --multi-year --validate-data

Note: Multi-year simulations must be run sequentially (2025 → 2026 → 2027, etc.)
Each year depends on the previous year's completed workforce snapshot.
Use --force-clear to start fresh from 2025, or --reset-year to clear a specific year.
"""
    )

    parser.add_argument(
        '--no-breaks', '-n',
        action='store_true',
        help='Skip all interactive prompts and run continuously'
    )

    parser.add_argument(
        '--multi-year', '-m',
        action='store_true',
        help='Run multi-year simulation mode using config/test_config.yaml settings'
    )

    parser.add_argument(
        '--resume-from',
        type=int,
        metavar='YEAR',
        help='Resume multi-year simulation from a specific year (requires --multi-year)'
    )

    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Run validation checks without executing steps (requires --multi-year)'
    )

    parser.add_argument(
        '--force-step',
        type=str,
        metavar='STEP',
        help='Override checklist validation for a specific step (with warning)'
    )

    parser.add_argument(
        '--preserve-data',
        action='store_true',
        help='Preserve existing multi-year simulation data (default behavior)'
    )

    parser.add_argument(
        '--force-clear',
        action='store_true',
        help='Clear all simulation data before starting (destructive)'
    )

    parser.add_argument(
        '--reset-year',
        type=int,
        metavar='YEAR',
        help='Clear data for a specific year only (requires --multi-year)'
    )

    parser.add_argument(
        '--validate-data',
        action='store_true',
        help='Run data integrity checks before starting (requires --multi-year)'
    )

    args = parser.parse_args()

    # Validate argument combinations
    if args.resume_from and not args.multi_year:
        parser.error("--resume-from requires --multi-year")

    if args.validate_only and not args.multi_year:
        parser.error("--validate-only requires --multi-year")

    if args.reset_year and not args.multi_year:
        parser.error("--reset-year requires --multi-year")

    if args.validate_data and not args.multi_year:
        parser.error("--validate-data requires --multi-year")

    if args.force_clear and args.preserve_data:
        parser.error("--force-clear and --preserve-data are mutually exclusive")

    # Run main with configuration flags
    main(
        skip_breaks=args.no_breaks,
        multi_year=args.multi_year,
        resume_from=args.resume_from,
        validate_only=args.validate_only,
        force_step=args.force_step,
        preserve_data=args.preserve_data,
        force_clear=args.force_clear,
        reset_year=args.reset_year,
        validate_data=args.validate_data
    )
