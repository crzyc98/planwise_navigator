#!/usr/bin/env python3
"""
Single-Year MVP Orchestrator for PlanWise Navigator.

Focused orchestrator for running single-year simulations (default year 2025)
with step-by-step validation and interactive debugging capabilities.
"""

import os
import sys
import argparse

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
    display_header,
    display_completion_message
)
from orchestrator_mvp.core.simulation_checklist import SimulationChecklist, StepSequenceError
from orchestrator_mvp.core.workforce_snapshot import generate_workforce_snapshot
from orchestrator_mvp.inspectors.workforce_inspector import inspect_workforce_snapshot


def run_single_year_simulation(
    simulation_year: int = 2025,
    skip_breaks: bool = False,
    force_step: str = None
) -> None:
    """
    Run a single-year workforce simulation with checklist validation.

    Args:
        simulation_year: Year to simulate (default: 2025)
        skip_breaks: If True, skip all interactive prompts
        force_step: Override checklist validation for a specific step
    """
    display_header(f"SINGLE-YEAR SIMULATION ({simulation_year})")

    print(f"\nThis tool will run a complete single-year workforce simulation")
    print(f"for year {simulation_year} with step-by-step validation.")
    print(f"Each step will be validated to ensure proper sequencing.")

    if skip_breaks:
        print("\n⚡ Running in non-interactive mode (skipping all breaks)")

    if force_step:
        print(f"\n⚠️ WARNING: Force mode enabled for step '{force_step}' - checklist validation will be overridden")

    try:
        # Initialize checklist for single-year mode
        checklist = SimulationChecklist(simulation_year, simulation_year)

        # Step 1: Clear database (with checklist validation)
        try:
            checklist.assert_step_ready("pre_simulation")
        except StepSequenceError as e:
            if force_step != "pre_simulation":
                print(f"\n❌ {str(e)}")
                raise
            else:
                print(f"\n⚠️ Forcing step 'pre_simulation' - {str(e)}")

        prompt_user_continue("clear the database", skip_breaks)
        clear_database_and_setup()
        checklist.mark_step_complete("pre_simulation")

        # Step 2: Load seed data and create staging tables
        prompt_user_continue("load seed data", skip_breaks)
        load_seed_data()

        prompt_user_continue("create staging tables", skip_breaks)
        create_staging_tables()

        # Step 3: Build foundation models
        prompt_user_continue("build foundation models", skip_breaks)
        build_foundation_models()

        # Step 4: Inspect foundation data
        prompt_user_continue("inspect foundation data", skip_breaks)
        inspect_foundation_data()

        print("\n✨ Foundational data looks good!")
        print("Now let's build on top of it...")

        # Step 5: Mark year_transition complete for single-year mode
        # For single year (2025), mark year transition as complete (no transition needed from baseline)
        checklist.mark_step_complete("year_transition", simulation_year)

        # Step 6: Workforce baseline (with checklist validation)
        try:
            checklist.assert_step_ready("workforce_baseline", simulation_year)
        except StepSequenceError as e:
            if force_step != "workforce_baseline":
                print(f"\n❌ {str(e)}")
                raise
            else:
                print(f"\n⚠️ Forcing step 'workforce_baseline' - {str(e)}")

        checklist.mark_step_complete("workforce_baseline", simulation_year)

        # Step 7: Workforce requirements calculation (with checklist validation)
        try:
            checklist.assert_step_ready("workforce_requirements", simulation_year)
        except StepSequenceError as e:
            if force_step != "workforce_requirements":
                print(f"\n❌ {str(e)}")
                raise
            else:
                print(f"\n⚠️ Forcing step 'workforce_requirements' - {str(e)}")

        prompt_user_continue("calculate workforce requirements", skip_breaks)
        calc_result = show_workforce_calculation()
        checklist.mark_step_complete("workforce_requirements", simulation_year)

        # Step 8: Generate simulation events via dbt models (with checklist validation)
        try:
            checklist.assert_step_ready("event_generation", simulation_year)
        except StepSequenceError as e:
            if force_step != "event_generation":
                print(f"\n❌ {str(e)}")
                raise
            else:
                print(f"\n⚠️ Forcing step 'event_generation' - {str(e)}")

        prompt_user_continue("generate simulation events via dbt models", skip_breaks)
        generate_simulation_events_via_dbt(simulation_year)
        checklist.mark_step_complete("event_generation", simulation_year)

        # Step 9: Generate workforce snapshot (with checklist validation)
        try:
            checklist.assert_step_ready("workforce_snapshot", simulation_year)
        except StepSequenceError as e:
            if force_step != "workforce_snapshot":
                print(f"\n❌ {str(e)}")
                raise
            else:
                print(f"\n⚠️ Forcing step 'workforce_snapshot' - {str(e)}")

        prompt_user_continue("generate workforce snapshot", skip_breaks)
        snapshot_result = generate_workforce_snapshot(simulation_year=simulation_year)

        if not snapshot_result["success"]:
            print(f"\n❌ ERROR generating workforce snapshot: {snapshot_result.get('error', 'Unknown error')}")
            raise RuntimeError("Failed to generate workforce snapshot")

        checklist.mark_step_complete("workforce_snapshot", simulation_year)

        # Step 10: Inspect workforce snapshot (with checklist validation)
        try:
            checklist.assert_step_ready("validation_metrics", simulation_year)
        except StepSequenceError as e:
            if force_step != "validation_metrics":
                print(f"\n❌ {str(e)}")
                raise
            else:
                print(f"\n⚠️ Forcing step 'validation_metrics' - {str(e)}")

        prompt_user_continue("inspect workforce snapshot", skip_breaks)
        inspect_workforce_snapshot(simulation_year=simulation_year)
        checklist.mark_step_complete("validation_metrics", simulation_year)

        # Show final checklist status
        print(f"\n📋 Single-Year Checklist Status:")
        print(checklist.get_progress_summary())

        # Display completion message
        display_completion_message(is_multi_year=False)

    except KeyboardInterrupt:
        print("\n\n⚠️  Single-year simulation interrupted by user.")
        sys.exit(1)

    except StepSequenceError as e:
        print(f"\n\n❌ STEP SEQUENCE ERROR: {str(e)}")
        print("Use --force-step to override checklist validation if needed.")
        sys.exit(1)

    except Exception as e:
        print(f"\n\n❌ FATAL ERROR: {str(e)}")
        sys.exit(1)


def main() -> None:
    """Main entry point for single-year simulation."""
    parser = argparse.ArgumentParser(
        description="PlanWise Navigator Single-Year Simulation - Run focused single-year workforce simulation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run single-year simulation interactively (default year 2025)
  python -m orchestrator_mvp.run_single_year

  # Run single-year without breaks (non-interactive)
  python -m orchestrator_mvp.run_single_year --no-breaks
  python -m orchestrator_mvp.run_single_year -n

  # Force a specific step (emergency override)
  python -m orchestrator_mvp.run_single_year --force-step workforce_snapshot

  # Run for a different year
  python -m orchestrator_mvp.run_single_year --year 2026

Note: Single-year simulations are independent and don't require previous years.
For sequential multi-year simulations, use run_multi_year.py instead.
"""
    )

    parser.add_argument(
        '--no-breaks', '-n',
        action='store_true',
        help='Skip all interactive prompts and run continuously'
    )

    parser.add_argument(
        '--year', '-y',
        type=int,
        default=2025,
        metavar='YEAR',
        help='Year to simulate (default: 2025)'
    )

    parser.add_argument(
        '--force-step',
        type=str,
        metavar='STEP',
        help='Override checklist validation for a specific step (with warning)'
    )

    args = parser.parse_args()

    # Run single-year simulation
    run_single_year_simulation(
        simulation_year=args.year,
        skip_breaks=args.no_breaks,
        force_step=args.force_step
    )


if __name__ == "__main__":
    main()
