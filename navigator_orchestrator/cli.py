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

from .checkpoint_manager import CheckpointManager
from .config import load_simulation_config
from .dbt_runner import DbtRunner
from .pipeline_orchestrator import PipelineOrchestrator
from .recovery_orchestrator import RecoveryOrchestrator
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

    # Enhanced checkpoint and recovery integration
    checkpoint_manager = CheckpointManager(db_path=str(db_path))
    recovery_orchestrator = RecoveryOrchestrator(checkpoint_manager)

    start_year = args.start_year or (
        cfg.simulation.start_year if not args.years else _parse_years(args.years)[0]
    )
    end_year = args.end_year or (
        cfg.simulation.end_year if not args.years else _parse_years(args.years)[1]
    )

    # Calculate configuration hash for drift detection
    config_hash = recovery_orchestrator.calculate_config_hash(str(config_path))

    # Handle resume logic with enhanced recovery system
    actual_start_year = start_year
    if args.force_restart:
        print(f"🔄 Force restart: ignoring checkpoints, starting from {start_year}")
    elif args.resume:
        resume_year = recovery_orchestrator.resume_simulation(end_year, config_hash)
        if resume_year:
            actual_start_year = resume_year
            print(f"🔄 Resume mode: starting from year {actual_start_year}")
            if actual_start_year > end_year:
                print(f"✅ Simulation already complete through year {resume_year - 1}")
                return 0
        else:
            print(f"🔄 No valid checkpoint found, starting from {start_year}")

    # Show recovery status if verbose
    if args.verbose:
        status = recovery_orchestrator.get_recovery_status(config_hash)
        print(
            f"📊 Recovery status: {len(status.get('recommendations', []))} recommendations"
        )
        for rec in status.get("recommendations", []):
            print(f"   💡 {rec}")

    summary = orch.execute_multi_year_simulation(
        start_year=actual_start_year,
        end_year=end_year,
        resume_from_checkpoint=False,  # We handle resume logic above
        fail_on_validation_error=args.fail_on_validation_error,
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


def cmd_checkpoint(args: argparse.Namespace) -> int:
    config_path = (
        Path(args.config) if args.config else Path("config/simulation_config.yaml")
    )
    db_path = Path(args.database) if args.database else Path("dbt/simulation.duckdb")

    checkpoint_manager = CheckpointManager(db_path=str(db_path))
    recovery_orchestrator = RecoveryOrchestrator(checkpoint_manager)

    if args.action == "list":
        checkpoints = checkpoint_manager.list_checkpoints()
        if not checkpoints:
            print("No checkpoints found")
            return 0

        print(f"Found {len(checkpoints)} checkpoint(s):")
        for cp in checkpoints:
            status = "✅" if cp["integrity_valid"] else "⚠️"
            print(
                f"  {status} Year {cp['year']}: {cp['timestamp']} ({cp['format']}, {cp['file_size']} bytes)"
            )
        return 0

    elif args.action == "status":
        config_hash = recovery_orchestrator.calculate_config_hash(str(config_path))
        status = recovery_orchestrator.get_recovery_status(config_hash)

        print("🔍 Recovery Status:")
        print(f"  Checkpoints available: {status['checkpoints_available']}")
        print(f"  Total checkpoints: {status['total_checkpoints']}")
        if status["latest_checkpoint_year"]:
            print(
                f"  Latest checkpoint: Year {status['latest_checkpoint_year']} ({status['latest_checkpoint_timestamp']})"
            )
        if status["resumable_year"]:
            print(f"  Resumable from: Year {status['resumable_year']}")
        print(f"  Configuration compatible: {status['config_compatible']}")

        if status["recommendations"]:
            print("\n💡 Recommendations:")
            for rec in status["recommendations"]:
                print(f"  • {rec}")
        return 0

    elif args.action == "cleanup":
        keep_count = args.keep or 5
        removed = checkpoint_manager.cleanup_old_checkpoints(keep_count)
        print(
            f"🧹 Cleaned up {removed} old checkpoint file(s), keeping latest {keep_count}"
        )
        return 0

    elif args.action == "validate":
        validation = recovery_orchestrator.validate_recovery_environment()
        if validation["valid"]:
            print("✅ Recovery environment is valid")
        else:
            print("❌ Recovery environment has issues:")
            for issue in validation["issues"]:
                print(f"  • {issue}")

        if validation["warnings"]:
            print("\n⚠️ Warnings:")
            for warning in validation["warnings"]:
                print(f"  • {warning}")

        return 0 if validation["valid"] else 1

    else:
        # Legacy behavior - show last checkpoint
        checkpoints = checkpoint_manager.list_checkpoints()
        if not checkpoints:
            print("No checkpoints found")
            return 0

        latest = max(checkpoints, key=lambda x: x["year"])
        print(f"Last checkpoint: year={latest['year']} at {latest['timestamp']}")
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

    print(f"\n🎯 Batch execution completed:")
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
    pr.add_argument("--resume", action="store_true", help="Resume from last checkpoint")
    pr.add_argument(
        "--force-restart",
        action="store_true",
        help="Ignore checkpoints and start fresh",
    )
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

    # checkpoint
    pc = sub.add_parser(
        "checkpoint", help="Checkpoint management and recovery operations"
    )
    pc.add_argument("--config", "-c", help="Path to simulation config YAML")
    pc.add_argument("--database", help="Path to DuckDB database file")
    pc.add_argument(
        "action",
        nargs="?",
        default="show",
        choices=["list", "status", "cleanup", "validate", "show"],
        help="Checkpoint action: list, status, cleanup, validate, or show (default)",
    )
    pc.add_argument(
        "--keep",
        type=int,
        help="Number of checkpoints to keep when cleaning up (default: 5)",
    )
    pc.set_defaults(func=cmd_checkpoint)

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
