#!/usr/bin/env python3
"""
Navigator Orchestrator CLI (argparse-based)

Provides subcommands to run simulations, validate config, and inspect checkpoints.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Optional

from .config import load_simulation_config
from .dbt_runner import DbtRunner
from .utils import DatabaseConnectionManager
from .registries import RegistryManager
from .validation import DataValidator, HireTerminationRatioRule, EventSequenceRule
from .pipeline import PipelineOrchestrator


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
    cfg = load_simulation_config(Path(args.config) if args.config else Path("config/simulation_config.yaml"))
    db = DatabaseConnectionManager(Path(args.database) if args.database else Path("dbt/simulation.duckdb"))
    runner = DbtRunner(threads=args.threads or 4, executable=("echo" if args.dry_run else "dbt"), verbose=bool(args.verbose))
    registries = RegistryManager(db)
    dv = _build_validator(db)
    orch = PipelineOrchestrator(cfg, db, runner, registries, dv, verbose=bool(args.verbose))

    start_year = args.start_year or (cfg.simulation.start_year if not args.years else _parse_years(args.years)[0])
    end_year = args.end_year or (cfg.simulation.end_year if not args.years else _parse_years(args.years)[1])

    summary = orch.execute_multi_year_simulation(
        start_year=start_year,
        end_year=end_year,
        resume_from_checkpoint=args.resume,
        fail_on_validation_error=args.fail_on_validation_error,
    )
    if args.verbose:
        print("Summary:", summary.growth_analysis)
    print("✅ Simulation completed")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    cfg = load_simulation_config(Path(args.config) if args.config else Path("config/simulation_config.yaml"))
    cfg_dict = cfg.model_dump()
    print("✅ Configuration parsed successfully")
    # Basic identifier hints
    if not (cfg.scenario_id and cfg.plan_design_id):
        print("ℹ️  Tip: Add scenario_id and plan_design_id for full traceability")
    return 0


def cmd_checkpoint(args: argparse.Namespace) -> int:
    cfg = load_simulation_config(Path(args.config) if args.config else Path("config/simulation_config.yaml"))
    db = DatabaseConnectionManager(Path(args.database) if args.database else Path("dbt/simulation.duckdb"))
    runner = DbtRunner(executable="echo")
    registries = RegistryManager(db)
    dv = _build_validator(db)
    orch = PipelineOrchestrator(cfg, db, runner, registries, dv)

    ckpt = orch._find_last_checkpoint()  # internal helper is fine for CLI display
    if not ckpt:
        print("No checkpoints found")
        return 0
    print(f"Last checkpoint: year={ckpt.year} stage={ckpt.stage.value} at {ckpt.timestamp}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="navigator", description="PlanWise Navigator Orchestrator CLI")
    sub = p.add_subparsers(dest="command", required=True)

    # run
    pr = sub.add_parser("run", help="Run multi-year simulation")
    pr.add_argument("--config", "-c", help="Path to simulation config YAML")
    pr.add_argument("--database", help="Path to DuckDB database file")
    pr.add_argument("--start-year", type=int, help="Simulation start year")
    pr.add_argument("--end-year", type=int, help="Simulation end year")
    pr.add_argument("--years", type=str, help="Year range, e.g., 2025-2027")
    pr.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    pr.add_argument("--dry-run", action="store_true", help="Skip dbt by echoing commands")
    pr.add_argument("--threads", type=int, help="dbt threads")
    pr.add_argument("--fail-on-validation-error", action="store_true")
    pr.add_argument("--verbose", "-v", action="store_true")
    pr.set_defaults(func=cmd_run)

    # validate
    pv = sub.add_parser("validate", help="Validate configuration")
    pv.add_argument("--config", "-c", help="Path to simulation config YAML")
    pv.set_defaults(func=cmd_validate)

    # checkpoint
    pc = sub.add_parser("checkpoint", help="Show last checkpoint")
    pc.add_argument("--config", "-c", help="Path to simulation config YAML")
    pc.add_argument("--database", help="Path to DuckDB database file")
    pc.set_defaults(func=cmd_checkpoint)

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
