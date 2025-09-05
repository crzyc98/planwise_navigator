#!/usr/bin/env python3
"""
Hybrid Pipeline Demonstration Script (E068G)

This script demonstrates the hybrid pipeline integration that supports both
SQL-based (traditional dbt models) and Polars-based (bulk factory) event generation.

Usage:
    python scripts/run_hybrid_pipeline.py --mode sql --years 2025 2026
    python scripts/run_hybrid_pipeline.py --mode polars --years 2025 2026 2027
    python scripts/run_hybrid_pipeline.py --mode comparison --years 2025 2026
"""

import argparse
import sys
import time
from pathlib import Path

# Add the parent directory to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from navigator_orchestrator import create_orchestrator
from navigator_orchestrator.config import load_simulation_config


def run_single_mode(mode: str, config_path: str, years: list, verbose: bool = True):
    """Run pipeline in a single mode (SQL or Polars)."""

    print(f"\n{'='*60}")
    print(f"RUNNING HYBRID PIPELINE IN {mode.upper()} MODE")
    print(f"{'='*60}")
    print(f"Years: {', '.join(map(str, years))}")
    print(f"Config: {config_path}")

    # Load configuration
    config = load_simulation_config(config_path)

    # Override event generation mode
    if not hasattr(config, 'optimization') or not config.optimization:
        print("❌ Error: Configuration missing optimization section")
        return False

    config.optimization.event_generation.mode = mode
    if mode == "polars":
        config.optimization.event_generation.polars.enabled = True

    # Validate threading configuration
    try:
        config.validate_threading_configuration()
    except ValueError as e:
        print(f"❌ Configuration validation error: {e}")
        return False

    # Create and run orchestrator
    start_time = time.time()

    try:
        orchestrator = create_orchestrator(config, verbose=verbose)

        summary = orchestrator.execute_multi_year_simulation(
            start_year=min(years),
            end_year=max(years),
            fail_on_validation_error=False
        )

        duration = time.time() - start_time

        print(f"\n✅ {mode.upper()} pipeline completed successfully!")
        print(f"⏱️  Total execution time: {duration:.1f}s")
        print(f"📊 Completed years: {len(summary.completed_years) if hasattr(summary, 'completed_years') else 'N/A'}")

        # Display mode-specific performance info
        if hasattr(summary, 'threading_config'):
            thread_config = summary.threading_config
            print(f"🧵 Threading config: {thread_config.get('dbt_threads', 'N/A')} dbt threads")
            print(f"🔄 Event generation mode: {thread_config.get('event_generation_mode', 'N/A')}")
            if thread_config.get('polars_enabled'):
                print(f"🚀 Polars mode enabled: {thread_config.get('polars_enabled', False)}")

        # Performance assessment for Polars mode
        if mode == "polars" and duration <= 60:
            print("🎯 PERFORMANCE TARGET MET: ≤60s for multi-year generation")
        elif mode == "polars":
            print(f"⏰ Performance target missed: {duration:.1f}s (target: ≤60s)")

        return True

    except Exception as e:
        duration = time.time() - start_time
        print(f"\n❌ {mode.upper()} pipeline failed after {duration:.1f}s")
        print(f"Error: {e}")
        return False


def run_comparison_mode(config_path: str, years: list, verbose: bool = True):
    """Run both SQL and Polars modes for performance comparison."""

    print(f"\n{'='*60}")
    print("RUNNING HYBRID PIPELINE PERFORMANCE COMPARISON")
    print(f"{'='*60}")
    print(f"Years: {', '.join(map(str, years))}")
    print(f"Config: {config_path}")
    print("This will run both SQL and Polars modes and compare performance.")

    results = {}

    # Run SQL mode
    print(f"\n🔄 Step 1/2: Running SQL mode...")
    sql_success = run_single_mode("sql", config_path, years, verbose=False)

    if sql_success:
        results["sql"] = "✅ Success"
    else:
        results["sql"] = "❌ Failed"

    # Add a brief pause between runs
    time.sleep(2)

    # Run Polars mode
    print(f"\n🔄 Step 2/2: Running Polars mode...")
    polars_success = run_single_mode("polars", config_path, years, verbose=False)

    if polars_success:
        results["polars"] = "✅ Success"
    else:
        results["polars"] = "❌ Failed"

    # Display comparison summary
    print(f"\n{'='*60}")
    print("PERFORMANCE COMPARISON SUMMARY")
    print(f"{'='*60}")

    for mode, result in results.items():
        print(f"{mode.upper()} Mode: {result}")

    if sql_success and polars_success:
        print("\n💡 Both modes completed successfully!")
        print("📊 Check the hybrid performance reports for detailed metrics:")
        print("   - reports/hybrid_performance/")
        print("   - Look for performance comparison and recommendations")
    elif sql_success or polars_success:
        print("\n⚠️  One mode succeeded, one failed.")
        print("💡 This might indicate environment or configuration issues.")
    else:
        print("\n❌ Both modes failed.")
        print("💡 Check configuration and dependencies.")

    return sql_success or polars_success


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Hybrid Pipeline Demonstration (E068G)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run SQL mode for 2 years
  python scripts/run_hybrid_pipeline.py --mode sql --years 2025 2026

  # Run Polars mode for multiple years (performance target: ≤60s)
  python scripts/run_hybrid_pipeline.py --mode polars --years 2025 2026 2027

  # Compare both modes
  python scripts/run_hybrid_pipeline.py --mode comparison --years 2025 2026

  # Use custom configuration
  python scripts/run_hybrid_pipeline.py --mode polars --config config/custom.yaml --years 2025
        """
    )

    parser.add_argument(
        '--mode',
        choices=['sql', 'polars', 'comparison'],
        required=True,
        help='Execution mode: sql, polars, or comparison'
    )

    parser.add_argument(
        '--years',
        type=int,
        nargs='+',
        required=True,
        help='Simulation years to process (e.g., 2025 2026 2027)'
    )

    parser.add_argument(
        '--config',
        default='config/hybrid_simulation_config.yaml',
        help='Path to simulation configuration file'
    )

    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    # Validate configuration file exists
    config_path = Path(args.config)
    if not config_path.exists():
        print(f"❌ Configuration file not found: {config_path}")
        print("💡 Try using the default: config/hybrid_simulation_config.yaml")
        return 1

    # Validate years
    if min(args.years) < 2020 or max(args.years) > 2050:
        print("❌ Invalid year range. Years must be between 2020 and 2050.")
        return 1

    # Sort years for consistent processing
    years = sorted(args.years)

    print("🚀 PlanWise Navigator Hybrid Pipeline (E068G)")
    print(f"Mode: {args.mode}")
    print(f"Years: {years}")
    print(f"Configuration: {config_path}")

    # Run the appropriate mode
    if args.mode == 'comparison':
        success = run_comparison_mode(str(config_path), years, args.verbose)
    else:
        success = run_single_mode(args.mode, str(config_path), years, args.verbose)

    if success:
        print(f"\n🎉 Hybrid pipeline execution completed successfully!")
        return 0
    else:
        print(f"\n💥 Hybrid pipeline execution failed.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
