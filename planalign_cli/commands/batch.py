"""
Batch command for Fidelity PlanAlign Engine CLI

Run multiple scenarios with Excel export and enhanced progress tracking.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

from ..integration.orchestrator_wrapper import OrchestratorWrapper
from ..ui.progress import (
    create_batch_progress,
    show_error_message,
)
from ..utils.config_helpers import find_default_config, find_scenarios_directory
from planalign_core.constants import DATABASE_FILENAME, STATUS_COMPLETED, STATUS_FAILED

console = Console()
batch_command = typer.Typer()


@batch_command.callback()
def batch_main():
    """📊 Run multiple scenarios with Excel export."""
    pass


@batch_command.command("run")
def run_batch(
    scenarios: Optional[list[str]] = typer.Option(
        None, "--scenarios", help="Specific scenario names to run"
    ),
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Base configuration file"
    ),
    scenarios_dir: Optional[str] = typer.Option(
        None, "--scenarios-dir", help="Directory containing scenario YAML files"
    ),
    output_dir: Optional[str] = typer.Option(
        None, "--output-dir", help="Output directory for batch results"
    ),
    export_format: str = typer.Option(
        "excel", "--export-format", help="Export format (excel, csv)"
    ),
    threads: int = typer.Option(1, "--threads", help="Number of dbt threads"),
    optimization: str = typer.Option(
        "medium", "--optimization", help="Optimization level (low, medium, high)"
    ),
    clean: bool = typer.Option(
        False,
        "--clean",
        help="Delete DuckDB databases before running for a clean start",
    ),
    parallel: Optional[int] = typer.Option(
        None,
        "--parallel",
        "-p",
        min=1,
        help=(
            "Worker processes to run scenarios across. Default: sized from "
            "available memory (~1.5 GiB/worker) and CPU count. Use 1 to force "
            "serial execution."
        ),
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Show detailed output"),
    seeds: Optional[int] = typer.Option(
        None, "--seeds", min=1, help="Run an isolated ensemble per scenario"
    ),
    seed_list: Optional[str] = typer.Option(
        None, "--seed-list", help="Comma-separated explicit ensemble seeds"
    ),
    attribution: bool = typer.Option(
        False, "--attribution", help="Measure one-factor-at-a-time variance attribution"
    ),
    attribution_seeds: Optional[int] = typer.Option(
        None, "--attribution-seeds", min=1, help="Headline seed subset for attribution"
    ),
    min_seeds: int = typer.Option(10, "--min-seeds", min=1),
    discard_seed_dbs: bool = typer.Option(False, "--discard-seed-dbs"),
    threshold: Optional[list[str]] = typer.Option(
        None, "--threshold", help="Repeatable ensemble threshold in metric:value form"
    ),
):
    """Run multiple scenarios with Excel export."""
    try:
        # Handle comma-separated scenario names for user convenience
        if scenarios and len(scenarios) == 1 and "," in scenarios[0]:
            scenarios = [s.strip() for s in scenarios[0].split(",")]

        console.print("📊 [bold blue]Starting batch scenario processing[/bold blue]")

        # Setup paths
        base_config_path = Path(config) if config else find_default_config()
        scenarios_path = (
            Path(scenarios_dir) if scenarios_dir else find_scenarios_directory()
        )
        output_path = Path(output_dir) if output_dir else Path("var/outputs")

        if not scenarios_path.exists():
            show_error_message(f"Scenarios directory not found: {scenarios_path}")
            raise typer.Exit(1)

        # Create wrapper and batch runner
        wrapper = OrchestratorWrapper(
            base_config_path, Path("dbt") / DATABASE_FILENAME, verbose=verbose
        )
        batch_runner = wrapper.create_batch_runner(scenarios_path, output_path)

        if seeds is not None or seed_list is not None or attribution or threshold:
            results = _run_ensemble_batch(
                batch_runner,
                scenarios=scenarios,
                seeds=seeds,
                seed_list=seed_list,
                attribution=attribution,
                attribution_seeds=attribution_seeds,
                min_seeds=min_seeds,
                discard_seed_dbs=discard_seed_dbs,
                parallel=parallel,
                threshold=threshold,
                export_format=export_format,
            )
            if not results:
                show_error_message("No scenarios were processed")
                raise typer.Exit(1)
            exit_code = _report_batch_results(results, batch_runner)
            if exit_code:
                raise typer.Exit(exit_code)
            return

        # Determine scenario count for progress tracking
        available_scenario_files = list(scenarios_path.glob("*.yaml"))
        if scenarios:
            scenario_count = len(scenarios)
            console.print(
                f"🎯 [blue]Running {scenario_count} specified scenarios: {', '.join(scenarios)}[/blue]"
            )
        else:
            scenario_count = len(available_scenario_files)
            console.print(
                f"🎯 [blue]Running all {scenario_count} available scenarios[/blue]"
            )

        # Execute batch processing with enhanced progress tracking
        with create_batch_progress(scenario_count) as (progress, main_task):
            progress.update(main_task, description="📊 Starting batch processing...")

            # Show status before starting
            console.print(f"⚙️  [dim]Configuration: {base_config_path}[/dim]")
            console.print(f"📁 [dim]Scenarios: {scenarios_path}[/dim]")
            console.print(f"📊 [dim]Export format: {export_format}[/dim]")
            console.print("")

            # Execute the batch run
            try:
                results = batch_runner.run_batch(
                    scenario_names=scenarios,
                    export_format=export_format,
                    threads=threads,
                    optimization=optimization,
                    clean_databases=clean,
                    parallel=parallel,
                    on_event=_make_progress_handler(progress, main_task),
                )
                progress.update(
                    main_task,
                    completed=scenario_count,
                    description="✅ Batch processing complete",
                )
            except KeyboardInterrupt:
                progress.update(main_task, description="⚠️  Interrupted")
                raise
            except Exception:
                progress.update(main_task, description="❌ Batch processing failed")
                raise

        if not results:
            show_error_message("No scenarios were processed")
            raise typer.Exit(1)

        exit_code = _report_batch_results(results, batch_runner)
        if exit_code:
            raise typer.Exit(exit_code)

    except typer.Exit:
        raise
    except Exception as e:
        show_error_message(f"Batch processing failed: {e}")
        raise typer.Exit(1)


def _make_progress_handler(progress, main_task):
    """Drive the Rich bar from pool events.

    The pool delivers events on this process's thread, so updates are safe and
    ordered here even while N workers run — the workers themselves never touch
    the terminal.
    """
    from planalign_orchestrator.run_pool import EventKind

    running: set[str] = set()

    def handle(event) -> None:
        if event.kind is EventKind.JOB_STARTED:
            running.add(event.job_name)
        else:
            running.discard(event.job_name)
            progress.advance(main_task)
            icon = "✅" if event.kind is EventKind.JOB_COMPLETED else "❌"
            console.print(
                f"  {icon} [dim]{event.job_name}"
                f" ({event.duration_seconds or 0:.1f}s)[/dim]"
            )
        if running:
            active = ", ".join(sorted(running))
            progress.update(main_task, description=f"📊 Running: {active}")

    return handle


def _report_batch_results(results: dict, batch_runner) -> int:
    """Report batch processing results and return exit code."""
    successful = [
        name
        for name, result in results.items()
        if result.get("status") == STATUS_COMPLETED
    ]
    failed = [
        name
        for name, result in results.items()
        if result.get("status") == STATUS_FAILED
    ]

    console.print("\n🎯 [bold blue]Batch execution completed[/bold blue]")
    budget = getattr(batch_runner, "worker_budget", None)
    if budget is not None:
        console.print(f"  ⚡ Fan-out: [dim]{budget.describe()}[/dim]")
    console.print(f"  ✅ Successful: {len(successful)} scenarios")
    if successful:
        console.print(f"     [dim]{', '.join(successful)}[/dim]")

    console.print(f"  ❌ Failed: {len(failed)} scenarios")
    if failed:
        console.print(f"     [dim red]{', '.join(failed)}[/dim red]")

    if successful:
        console.print(f"  📊 Outputs: [dim]{batch_runner.batch_output_dir}[/dim]")

    return 0 if not failed else 1


# Default command
@batch_command.command(name="", hidden=True)
def default(
    scenarios: Optional[list[str]] = typer.Option(None, "--scenarios"),
    config: Optional[str] = typer.Option(None, "--config", "-c"),
    scenarios_dir: Optional[str] = typer.Option(None, "--scenarios-dir"),
    output_dir: Optional[str] = typer.Option(None, "--output-dir"),
    export_format: str = typer.Option("excel", "--export-format"),
    threads: int = typer.Option(1, "--threads"),
    optimization: str = typer.Option("medium", "--optimization"),
    clean: bool = typer.Option(False, "--clean"),
    parallel: Optional[int] = typer.Option(None, "--parallel", "-p", min=1),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    seeds: Optional[int] = typer.Option(None, "--seeds", min=1),
    seed_list: Optional[str] = typer.Option(None, "--seed-list"),
    attribution: bool = typer.Option(False, "--attribution"),
    attribution_seeds: Optional[int] = typer.Option(None, "--attribution-seeds", min=1),
    min_seeds: int = typer.Option(10, "--min-seeds", min=1),
    discard_seed_dbs: bool = typer.Option(False, "--discard-seed-dbs"),
    threshold: Optional[list[str]] = typer.Option(None, "--threshold"),
):
    """Default batch command."""
    run_batch(
        scenarios=scenarios,
        config=config,
        scenarios_dir=scenarios_dir,
        output_dir=output_dir,
        export_format=export_format,
        threads=threads,
        optimization=optimization,
        clean=clean,
        parallel=parallel,
        verbose=verbose,
        seeds=seeds,
        seed_list=seed_list,
        attribution=attribution,
        attribution_seeds=attribution_seeds,
        min_seeds=min_seeds,
        discard_seed_dbs=discard_seed_dbs,
        threshold=threshold,
    )


def _run_ensemble_batch(
    batch_runner,
    *,
    scenarios: Optional[list[str]],
    seeds: Optional[int],
    seed_list: Optional[str],
    attribution: bool,
    attribution_seeds: Optional[int],
    min_seeds: int,
    discard_seed_dbs: bool,
    parallel: Optional[int],
    threshold: Optional[list[str]],
    export_format: str,
) -> dict:
    """Run the same ensemble semantics independently for every batch scenario."""
    from planalign_ensemble.models import EnsembleSpec, Threshold
    from planalign_ensemble.planner import plan_ensemble
    from planalign_ensemble.report import (
        EnsembleProgressReporter,
        print_attribution_tables,
        print_distribution_tables,
        print_ensemble_plan,
    )
    from planalign_ensemble.runner import run_ensemble
    from planalign_orchestrator.run_pool import resolve_worker_count

    from .simulate import _ensemble_exit_code, _parse_seed_list, _parse_threshold

    if seeds is not None and seed_list is not None:
        raise ValueError("--seeds and --seed-list cannot be used together")
    if attribution_seeds is not None and not attribution:
        raise ValueError("--attribution-seeds requires --attribution")
    explicit_seeds = _parse_seed_list(seed_list) if seed_list is not None else None
    seed_count = seeds if seeds is not None else len(explicit_seeds or ())
    if seed_count < 1:
        raise ValueError("ensemble options require --seeds or --seed-list")
    discovered = batch_runner._discover_scenarios(scenarios)
    _validate_requested_scenarios(batch_runner, scenarios, discovered)
    results: dict = {}
    for name, config_path in discovered.items():
        config = batch_runner._load_merged_config(config_path)
        configured_thresholds = tuple(
            Threshold(metric=item.metric, value=item.value, label=item.label)
            for item in config.ensemble.thresholds
        )
        cli_thresholds = tuple(_parse_threshold(value) for value in (threshold or ()))
        spec = EnsembleSpec(
            scenario_id=config.scenario_id or name,
            seed_count=seed_count,
            base_seed=config.simulation.random_seed,
            seed_list=explicit_seeds,
            start_year=config.simulation.start_year,
            end_year=config.simulation.end_year,
            min_seeds=min_seeds,
            attribution=attribution,
            attribution_seed_count=attribution_seeds,
            thresholds=configured_thresholds + cli_thresholds,
            discard_seed_dbs=discard_seed_dbs,
            config_path=config_path,
        )
        plan = plan_ensemble(
            spec,
            output_root=batch_runner.batch_output_dir / name / "ensembles",
        )
        print_ensemble_plan(console, plan, resolve_worker_count(parallel, seed_count))
        result = run_ensemble(
            plan,
            parallel=parallel,
            config=config,
            on_event=EnsembleProgressReporter(console, total_seeds=seed_count),
        )
        print_distribution_tables(console, result.distributions, min_seeds=min_seeds)
        print_attribution_tables(console, result.attribution)
        export_path = None
        if export_format.lower() == "excel" and any(
            outcome.succeeded for outcome in result.outcomes
        ):
            export_path = _export_ensemble_workbook(
                batch_runner=batch_runner,
                scenario_name=name,
                config=config,
                result=result,
            )
        results[name] = {
            "status": (
                STATUS_COMPLETED if _ensemble_exit_code(result) == 0 else STATUS_FAILED
            ),
            "database_path": str(result.plan.ensemble_db_path),
            "ensemble_id": result.plan.ensemble_id,
            "export_path": str(export_path) if export_path is not None else None,
            "seed_failures": [
                {"seed": item.seed, "error": item.error}
                for item in result.outcomes
                if not item.succeeded
            ],
        }
    return results


def _export_ensemble_workbook(
    *, batch_runner, scenario_name: str, config, result
) -> Path:
    """Write the aggregate-only workbook without reopening a seed database."""
    from planalign_orchestrator.excel_exporter import ExcelExporter
    from planalign_orchestrator.utils import DatabaseConnectionManager

    manager = DatabaseConnectionManager(
        result.plan.ensemble_db_path,
        read_only=True,
    )
    try:
        return ExcelExporter(manager).export_scenario_results(
            scenario_name=scenario_name,
            output_dir=batch_runner.batch_output_dir / scenario_name,
            config=config,
            seed=config.simulation.random_seed,
            ensemble_db_path=result.plan.ensemble_db_path,
        )
    finally:
        manager.close_all()


def _validate_requested_scenarios(batch_runner, requested, discovered) -> None:
    """Match normal batch's clear missing-scenario error before any seed runs."""
    if not requested:
        return
    missing = sorted(set(requested) - set(discovered))
    if missing:
        available = ", ".join(sorted(batch_runner._discover_scenarios())) or "(none)"
        raise ValueError(
            f"Scenario(s) not found in {batch_runner.scenarios_dir}: "
            f"{', '.join(missing)}. Available: {available}"
        )
