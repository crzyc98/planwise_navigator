#!/usr/bin/env python3
"""
Navigator Orchestrator CLI (argparse-based)

Provides subcommands to run simulations, validate config, and run batch scenarios.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from .config import load_simulation_config
from .dbt_runner import DbtRunner
from .pipeline_orchestrator import PipelineOrchestrator
from .registries import RegistryManager
from .scenario_batch_runner import ScenarioBatchRunner
from .utils import DatabaseConnectionManager
from .validation import (DataValidator, EventSequenceRule,
                         HireTerminationRatioRule)


def _parse_years(s: str) -> tuple[int, int]:
    try:
        start, end = s.split("-")
        return int(start), int(end)
    except Exception:
        raise argparse.ArgumentTypeError("Expected YEAR-YEAR format, e.g., 2025-2027")


def _build_validator(db: DatabaseConnectionManager) -> DataValidator:
    dv = DataValidator(db)
    dv.register_rule(HireTerminationRatioRule())
    dv.register_rule(EventSequenceRule())
    return dv


def cmd_run(args: argparse.Namespace) -> int:
    config_path = (
        Path(args.config) if args.config else Path("config/simulation_config.yaml")
    )
    cfg = load_simulation_config(config_path)
    db_path = Path(args.database) if args.database else Path("dbt/simulation.duckdb")
    db = DatabaseConnectionManager(db_path)

    # Extract threading configuration from config (with CLI override)
    if cfg.orchestrator:
        cfg.validate_threading_configuration()
    cfg.validate_eligibility_configuration()

    thread_count = args.threads if args.threads is not None else cfg.get_thread_count()
    threading_enabled = True
    threading_mode = "selective"

    if cfg.orchestrator and cfg.orchestrator.threading:
        threading_enabled = cfg.orchestrator.threading.enabled
        threading_mode = cfg.orchestrator.threading.mode

    runner = DbtRunner(
        threads=thread_count,
        executable=("echo" if args.dry_run else "dbt"),
        verbose=bool(args.verbose),
        threading_enabled=threading_enabled,
        threading_mode=threading_mode,
    )
    registries = RegistryManager(db)
    dv = _build_validator(db)
    orch = PipelineOrchestrator(
        cfg, db, runner, registries, dv, verbose=bool(args.verbose)
    )

    start_year = args.start_year or (
        cfg.simulation.start_year if not args.years else _parse_years(args.years)[0]
    )
    end_year = args.end_year or (
        cfg.simulation.end_year if not args.years else _parse_years(args.years)[1]
    )

    summary = orch.execute_multi_year_simulation(
        start_year=start_year,
        end_year=end_year,
        fail_on_validation_error=args.fail_on_validation_error,
        dry_run=args.dry_run,
    )
    if args.verbose:
        print("Summary:", summary.growth_analysis)
    print("✅ Simulation completed")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    cfg = load_simulation_config(
        Path(args.config) if args.config else Path("config/simulation_config.yaml")
    )
    if getattr(args, "enforce_identifiers", False):
        cfg.require_identifiers()
    cfg_dict = cfg.model_dump()
    print("✅ Configuration parsed successfully")
    # Basic identifier hints
    if not (cfg.scenario_id and cfg.plan_design_id):
        print("ℹ️  Tip: Add scenario_id and plan_design_id for full traceability")
    return 0


def cmd_batch(args: argparse.Namespace) -> int:
    """Execute batch scenario processing with Excel export."""
    scenarios_dir = Path(args.scenarios_dir) if args.scenarios_dir else Path("scenarios")
    output_dir = Path(args.output_dir) if args.output_dir else Path("outputs")
    base_config_path = Path(args.config) if args.config else Path("config/simulation_config.yaml")

    if not scenarios_dir.exists():
        print(f"❌ Scenarios directory not found: {scenarios_dir}")
        return 1

    # Validate base configuration exists
    if not base_config_path.exists():
        print(f"❌ Base configuration not found: {base_config_path}")
        return 1

    runner = ScenarioBatchRunner(scenarios_dir, output_dir, base_config_path)
    results = runner.run_batch(
        scenario_names=args.scenarios,
        export_format=args.export_format,
        threads=args.threads,
        optimization=args.optimization,
        clean_databases=args.clean
    )

    if not results:
        print("❌ No scenarios were processed")
        return 1

    # Report results
    successful = [name for name, result in results.items() if result.get("status") == "completed"]
    failed = [name for name, result in results.items() if result.get("status") == "failed"]

    print("\n🎯 Batch execution completed:")
    print(f"  ✅ Successful: {len(successful)} scenarios")
    if successful:
        print(f"     {', '.join(successful)}")
    print(f"  ❌ Failed: {len(failed)} scenarios")
    if failed:
        print(f"     {', '.join(failed)}")

    if successful:
        print(f"  📊 Outputs: {runner.batch_output_dir}")

    return 0 if not failed else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="navigator", description="PlanWise Navigator Orchestrator CLI"
    )
    sub = p.add_subparsers(dest="command", required=True)

    # run
    pr = sub.add_parser("run", help="Run multi-year simulation")
    pr.add_argument("--config", "-c", help="Path to simulation config YAML")
    pr.add_argument("--database", help="Path to DuckDB database file")
    pr.add_argument("--start-year", type=int, help="Simulation start year")
    pr.add_argument("--end-year", type=int, help="Simulation end year")
    pr.add_argument("--years", type=str, help="Year range, e.g., 2025-2027")
    pr.add_argument(
        "--dry-run", action="store_true", help="Skip dbt by echoing commands"
    )
    pr.add_argument("--threads", type=int, help="dbt threads")
    pr.add_argument("--fail-on-validation-error", action="store_true")
    pr.add_argument("--verbose", "-v", action="store_true")
    pr.set_defaults(func=cmd_run)

    # validate
    pv = sub.add_parser("validate", help="Validate configuration")
    pv.add_argument("--config", "-c", help="Path to simulation config YAML")
    pv.set_defaults(func=cmd_validate)

    # batch
    pb = sub.add_parser("batch", help="Run multiple scenarios with Excel export")
    pb.add_argument("--config", "-c", help="Base configuration file (default: config/simulation_config.yaml)")
    pb.add_argument("--scenarios-dir", help="Directory containing scenario YAML files (default: scenarios/)")
    pb.add_argument("--output-dir", help="Output directory for batch results (default: outputs/)")
    pb.add_argument("--scenarios", nargs="*", help="Specific scenario names to run (default: all)")
    pb.add_argument("--export-format", choices=["excel", "csv"], default="excel", help="Export format")
    pb.add_argument("--split-by-year", action="store_true", help="Split Workforce Snapshot into per-year sheets/files")
    pb.add_argument("--threads", type=int, default=1, help="Number of dbt threads for parallel execution (default: 1)")
    pb.add_argument("--optimization", choices=["low", "medium", "high"], default="medium", help="Optimization level (default: medium)")
    pb.add_argument("--clean", action="store_true", help="Delete DuckDB databases before running for a clean start")
    pb.set_defaults(func=cmd_batch)

    return p


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except Exception as e:
        print(f"❌ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
