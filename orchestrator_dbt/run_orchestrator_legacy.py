#!/usr/bin/env python3
"""
CLI entry point for orchestrator_dbt setup workflow.

Provides command-line interface for running the complete setup workflow
with various options and configurations.
"""

import sys
import argparse
import logging
from pathlib import Path
from typing import Optional

# Add the parent directory to the Python path to enable imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from orchestrator_dbt.workflow_orchestrator import WorkflowOrchestrator
from orchestrator_dbt.core.workflow_orchestrator import WorkflowResult


def setup_logging(verbose: bool = False, quiet: bool = False) -> None:
    """
    Setup logging configuration.

    Args:
        verbose: Enable verbose (DEBUG) logging
        quiet: Enable quiet mode (ERROR only)
    """
    if quiet:
        level = logging.ERROR
    elif verbose:
        level = logging.DEBUG
    else:
        level = logging.INFO

    # Create formatter
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # Setup root logger
    logger = logging.getLogger()
    logger.setLevel(level)

    # Remove existing handlers
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)

    # Add console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)


def print_workflow_summary(result: WorkflowResult) -> None:
    """
    Print human-readable workflow summary.

    Args:
        result: WorkflowResult to summarize
    """
    print("\n" + "=" * 80)
    print("SETUP WORKFLOW SUMMARY")
    print("=" * 80)

    print(f"Overall Status: {'✅ SUCCESS' if result.success else '❌ FAILED'}")
    print(f"Steps Completed: {result.steps_completed}/{result.steps_total}")
    print(f"Completion Rate: {result.completion_rate:.1f}%")
    print(f"Total Runtime: {result.total_execution_time:.2f} seconds")

    print("\nStep Details:")
    print("-" * 40)

    for step in result.workflow_steps:
        status_icon = "✅" if step.success else "❌"
        print(f"{status_icon} {step.step_name:<30} ({step.execution_time:.2f}s)")
        if not step.success:
            print(f"   Error: {step.message}")

    # Print validation summary if available
    if result.final_validation:
        validation = result.final_validation
        print(f"\nValidation Results:")
        print("-" * 20)
        print(f"Checks Passed: {validation.passed_checks}/{validation.total_checks}")
        print(f"Success Rate: {validation.success_rate:.1f}%")

        if validation.critical_failures > 0:
            print(f"❌ Critical Failures: {validation.critical_failures}")

        if validation.warnings > 0:
            print(f"⚠️  Warnings: {validation.warnings}")

        # Show failed checks
        failed_checks = validation.get_failed_checks()
        if failed_checks:
            print("\nFailed Validation Checks:")
            for check in failed_checks:
                print(f"  ❌ {check.check_name}: {check.message}")

    print("=" * 80)


def run_status_check(orchestrator: WorkflowOrchestrator) -> int:
    """
    Run system status check.

    Args:
        orchestrator: WorkflowOrchestrator instance

    Returns:
        Exit code (0 for success, 1 for issues)
    """
    print("Checking system status...")

    status = orchestrator.get_system_status()

    print("\n" + "=" * 60)
    print("SYSTEM STATUS")
    print("=" * 60)

    # Core components
    print(f"Configuration: {'✅ Valid' if status['config_valid'] else '❌ Invalid'}")
    print(f"Database: {'✅ Accessible' if status['database_accessible'] else '❌ Inaccessible'}")
    print(f"dbt: {'✅ Available' if status['dbt_available'] else '❌ Unavailable'}")

    if status['dbt_available'] and 'dbt_version' in status:
        print(f"  Version: {status['dbt_version']}")
    elif 'dbt_error' in status:
        print(f"  Error: {status['dbt_error']}")

    # Seeds
    print(f"Seeds: {'✅ Available' if status['seeds_available'] else '❌ Not Found'}")
    if status['seeds_available']:
        print(f"  Count: {status['seeds_count']} seed files")

    # Staging models
    print(f"Staging Models: {'✅ Available' if status['staging_models_available'] else '❌ Not Found'}")
    if status['staging_models_available']:
        print(f"  Count: {status['staging_models_count']} staging models")

    # Database details
    if 'database_details' in status:
        db_details = status['database_details']
        print(f"\nDatabase Details:")
        print(f"  Total Tables: {db_details['total_tables']}")
        print(f"  Staging Tables: {db_details['staging_tables']}")
        print(f"  Fact Tables: {db_details['fact_tables']}")

    # Overall readiness
    ready = status['ready_for_setup']
    print(f"\nOverall Status: {'🟢 READY FOR SETUP' if ready else '🔴 NOT READY'}")

    if not ready:
        print("\nIssues to resolve:")
        if not status['database_accessible']:
            print("  ❌ Database connection issues")
        if not status['dbt_available']:
            print("  ❌ dbt not available or configured")
        if not status['seeds_available']:
            print("  ❌ No seed files found")
        if not status['staging_models_available']:
            print("  ❌ No staging models found")

    print("=" * 60)

    return 0 if ready else 1


def main() -> int:
    """
    Main CLI entry point.

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    parser = argparse.ArgumentParser(
        description="PlanWise Navigator - dbt Setup Orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                      # Run complete setup workflow
  %(prog)s --quick              # Run quick setup (foundation only)
  %(prog)s --status             # Check system status
  %(prog)s --config custom.yaml # Use custom configuration file
  %(prog)s --verbose            # Enable detailed logging
        """
    )

    parser.add_argument(
        "--config", "-c",
        type=Path,
        help="Path to configuration YAML file"
    )

    parser.add_argument(
        "--quick", "-q",
        action="store_true",
        help="Run quick setup (foundation models only)"
    )

    parser.add_argument(
        "--status", "-s",
        action="store_true",
        help="Check system status and readiness"
    )

    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Enable quiet mode (errors only)"
    )

    parser.add_argument(
        "--version",
        action="version",
        version="orchestrator_dbt 1.0.0"
    )

    args = parser.parse_args()

    # Setup logging
    setup_logging(verbose=args.verbose, quiet=args.quiet)

    logger = logging.getLogger(__name__)

    try:
        # Initialize orchestrator
        logger.info("Initializing PlanWise Navigator Setup Orchestrator...")
        orchestrator = WorkflowOrchestrator(config_path=args.config)

        # Handle different operations
        if args.status:
            return run_status_check(orchestrator)

        elif args.quick:
            logger.info("Starting quick setup workflow...")
            result = orchestrator.run_quick_setup()

        else:
            logger.info("Starting complete setup workflow...")
            result = orchestrator.run_complete_setup()

        # Print summary (unless in quiet mode)
        if not args.quiet:
            print_workflow_summary(result)

        # Return appropriate exit code
        return 0 if result.success else 1

    except KeyboardInterrupt:
        logger.error("Setup interrupted by user")
        return 130  # Standard exit code for SIGINT

    except Exception as e:
        logger.error(f"Setup failed with error: {e}")
        if args.verbose:
            logger.exception("Full error details:")
        return 1


if __name__ == "__main__":
    sys.exit(main())
