#!/usr/bin/env python3
"""
Simple Multi-Year Simulation Runner

A clean, simple wrapper around the working orchestrator_dbt multi-year simulation system.
This script provides an easy-to-use interface for running multi-year workforce simulations.

Usage:
    # Basic simulation
    python scripts/run_multi_year_simulation.py --years 2025 2026 2027

    # High-performance simulation
    python scripts/run_multi_year_simulation.py --years 2025 2026 2027 2028 --optimization high --threads 8

    # Foundation setup only (for testing)
    python scripts/run_multi_year_simulation.py --foundation-only

Examples:
    # Run 3-year simulation
    python scripts/run_multi_year_simulation.py --years 2025 2026 2027

    # Run with custom config
    python scripts/run_multi_year_simulation.py --years 2025 2026 --config config/custom.yaml

    # Foundation setup test
    python scripts/run_multi_year_simulation.py --foundation-only --verbose
"""

import argparse
import asyncio
import sys
import subprocess
from pathlib import Path
from typing import List, Optional


def run_orchestrator_dbt_cli(
    start_year: int,
    end_year: int,
    optimization: str = "high",
    max_workers: int = 4,
    batch_size: int = 1000,
    enable_compression: bool = False,
    fail_fast: bool = False,
    foundation_only: bool = False,
    config_path: Optional[str] = None,
    verbose: bool = False
) -> int:
    """Run the orchestrator_dbt CLI with the specified parameters."""

    # Build the command
    cmd = [
        sys.executable, "-m", "orchestrator_dbt.cli.run_multi_year",
        "--start-year", str(start_year),
        "--end-year", str(end_year),
        "--optimization", optimization,
        "--max-workers", str(max_workers),
        "--batch-size", str(batch_size)
    ]

    # Add optional flags
    if enable_compression:
        cmd.append("--enable-compression")
    if fail_fast:
        cmd.append("--fail-fast")
    if foundation_only:
        cmd.append("--foundation-only")
    if config_path:
        cmd.extend(["--config", config_path])
    if verbose:
        cmd.append("--verbose")

    print(f"🚀 Running multi-year simulation: {start_year}-{end_year}")
    print(f"   Command: {' '.join(cmd)}")

    # Execute the command
    try:
        result = subprocess.run(cmd, check=False)
        return result.returncode
    except Exception as e:
        print(f"❌ Failed to run simulation: {e}")
        return 1


def validate_years(years: List[int]) -> tuple[int, int]:
    """Validate and return start and end years."""
    if len(years) < 1:
        raise ValueError("At least one year must be specified")

    years = sorted(years)
    start_year = years[0]
    end_year = years[-1]

    # Validate year range
    current_year = 2024  # Reasonable current year for simulation
    if start_year < 2020 or end_year > current_year + 20:
        raise ValueError(f"Years must be between 2020 and {current_year + 20}")

    return start_year, end_year


def main():
    """Main function."""
    parser = argparse.ArgumentParser(
        description="Simple Multi-Year Simulation Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    # Primary arguments
    parser.add_argument(
        "--years",
        nargs="+",
        type=int,
        help="Simulation years (e.g., --years 2025 2026 2027)"
    )

    # Optimization settings
    parser.add_argument(
        "--optimization",
        choices=["high", "medium", "low", "fallback"],
        default="high",
        help="Optimization level (default: high)"
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=4,
        help="Number of concurrent threads (default: 4)"
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=1000,
        help="Processing batch size (default: 1000)"
    )

    # Feature flags
    parser.add_argument(
        "--enable-compression",
        action="store_true",
        help="Enable state compression for memory efficiency"
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop on first year failure (default: continue)"
    )

    # Operation modes
    parser.add_argument(
        "--foundation-only",
        action="store_true",
        help="Run foundation setup only (for testing)"
    )

    # Configuration
    parser.add_argument(
        "--config",
        type=str,
        help="Path to simulation configuration file (YAML)"
    )

    # Logging
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Enable verbose logging"
    )

    args = parser.parse_args()

    try:
        if args.foundation_only:
            # Foundation setup only
            print("🏗️  Running foundation setup only...")
            return run_orchestrator_dbt_cli(
                start_year=2025,  # Dummy year for foundation test
                end_year=2025,
                optimization=args.optimization,
                max_workers=args.threads,
                batch_size=args.batch_size,
                enable_compression=args.enable_compression,
                fail_fast=args.fail_fast,
                foundation_only=True,
                config_path=args.config,
                verbose=args.verbose
            )

        elif args.years:
            # Multi-year simulation
            start_year, end_year = validate_years(args.years)

            print(f"🎯 Multi-year simulation: {start_year} to {end_year}")
            print(f"   Years to simulate: {sorted(args.years)}")

            return run_orchestrator_dbt_cli(
                start_year=start_year,
                end_year=end_year,
                optimization=args.optimization,
                max_workers=args.threads,
                batch_size=args.batch_size,
                enable_compression=args.enable_compression,
                fail_fast=args.fail_fast,
                foundation_only=False,
                config_path=args.config,
                verbose=args.verbose
            )

        else:
            print("❌ Either --years or --foundation-only must be specified")
            parser.print_help()
            return 1

    except ValueError as e:
        print(f"❌ Invalid arguments: {e}")
        return 1
    except KeyboardInterrupt:
        print("\n⚡ Interrupted by user")
        return 130
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
