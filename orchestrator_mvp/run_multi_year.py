#!/usr/bin/env python3
"""
Multi-Year MVP Orchestrator for PlanWise Navigator.

Focused orchestrator for running multi-year simulations with advanced
data management options and sequential year validation.
"""

import os
import sys
import argparse
import yaml
import logging

# Add parent directory to Python path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from orchestrator_mvp.core.common_workflow import (
    clear_database_and_setup,
    load_seed_data,
    create_staging_tables,
    build_foundation_models,
    inspect_foundation_data,
    show_workforce_calculation,
    generate_simulation_events_via_dbt,
    prompt_user_continue,
    load_config,
    display_header,
    display_completion_message
)
from orchestrator_mvp.core.multi_year_orchestrator import MultiYearSimulationOrchestrator
from orchestrator_mvp.core.simulation_checklist import StepSequenceError
from orchestrator_mvp.core.database_manager import get_connection
from orchestrator_mvp.inspectors.multi_year_inspector import (
    compare_year_over_year_metrics,
    validate_cumulative_growth,
    display_multi_year_summary
)


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


def run_multi_year_simulation(
    skip_breaks: bool = False,
    resume_from: int = None,
    validate_only: bool = False,
    preserve_data: bool = False,
    force_clear: bool = False,
    reset_year: int = None,
    validate_data: bool = False
) -> None:
    """
    Run a multi-year workforce simulation with advanced options.

    Args:
        skip_breaks: If True, skip all interactive prompts
        resume_from: Optional year to resume multi-year simulation from
        validate_only: If True, only run validation checks without executing steps
        preserve_data: If True, preserve existing multi-year simulation data
        force_clear: If True, clear all simulation data before starting
        reset_year: Clear data for a specific year only
        validate_data: Run data integrity checks before starting
    """
    display_header("MULTI-YEAR SIMULATION WITH CHECKLIST ENFORCEMENT")

    print("\nThis tool will run a complete multi-year workforce simulation")
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

    if skip_breaks:
        print("\n⚡ Running in non-interactive mode (skipping all breaks)")

    try:
        # Load configuration for multi-year simulation
        raw_config = load_config()
        start_year = raw_config['simulation']['start_year']
        end_year = raw_config['simulation']['end_year']

        # Flatten config for MultiYearSimulationOrchestrator
        config = {
            'target_growth_rate': raw_config['simulation']['target_growth_rate'],
            'random_seed': raw_config['simulation']['random_seed'],
            'workforce': raw_config['workforce'],
            'eligibility': raw_config.get('eligibility', {'waiting_period_days': 365})
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

        # Setup foundation for multi-year simulation
        if not skip_breaks:
            print(f"\n🗓️ Multi-year simulation configured for {start_year}-{end_year}")
            input(f"\n📋 Press Enter to run checklist-enforced multi-year simulation ({start_year}-{end_year})...")

        # If starting fresh, setup foundation
        if force_clear or start_year == 2025:
            print("\n🏗️ Setting up foundation for multi-year simulation...")

            clear_database_and_setup()
            load_seed_data()
            create_staging_tables()
            build_foundation_models()
            inspect_foundation_data()

            print("\n✨ Foundation setup completed!")
            print("Now running the multi-year orchestrator...")

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

            # Display completion message
            display_completion_message(is_multi_year=True)

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

    except KeyboardInterrupt:
        print("\n\n⚠️  Multi-year simulation interrupted by user.")
        sys.exit(1)

    except StepSequenceError as e:
        print(f"\n\n❌ STEP SEQUENCE ERROR: {str(e)}")
        print("Use --force-step to override checklist validation if needed.")
        sys.exit(1)

    except Exception as e:
        print(f"\n\n❌ FATAL ERROR: {str(e)}")
        sys.exit(1)


def main() -> None:
    """Main entry point for multi-year simulation."""
    parser = argparse.ArgumentParser(
        description="PlanWise Navigator Multi-Year Simulation - Run sequential multi-year workforce simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run multi-year simulation interactively
  python -m orchestrator_mvp.run_multi_year

  # Run multi-year simulation without breaks
  python -m orchestrator_mvp.run_multi_year --no-breaks
  python -m orchestrator_mvp.run_multi_year -n

  # Resume multi-year simulation from year 2027
  python -m orchestrator_mvp.run_multi_year --resume-from 2027

  # Validate prerequisites without running simulation
  python -m orchestrator_mvp.run_multi_year --validate-only

  # Data management options:
  # Run with data preservation (default)
  python -m orchestrator_mvp.run_multi_year --preserve-data

  # Clear all simulation data before starting
  python -m orchestrator_mvp.run_multi_year --force-clear

  # Clear data for a specific year only
  python -m orchestrator_mvp.run_multi_year --reset-year 2027

  # Validate data integrity before starting
  python -m orchestrator_mvp.run_multi_year --validate-data

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
        '--resume-from',
        type=int,
        metavar='YEAR',
        help='Resume multi-year simulation from a specific year'
    )

    parser.add_argument(
        '--validate-only',
        action='store_true',
        help='Run validation checks without executing steps'
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
        help='Clear data for a specific year only'
    )

    parser.add_argument(
        '--validate-data',
        action='store_true',
        help='Run data integrity checks before starting'
    )

    args = parser.parse_args()

    # Validate argument combinations
    if args.force_clear and args.preserve_data:
        parser.error("--force-clear and --preserve-data are mutually exclusive")

    # Run multi-year simulation
    run_multi_year_simulation(
        skip_breaks=args.no_breaks,
        resume_from=args.resume_from,
        validate_only=args.validate_only,
        preserve_data=args.preserve_data,
        force_clear=args.force_clear,
        reset_year=args.reset_year,
        validate_data=args.validate_data
    )


if __name__ == "__main__":
    main()
