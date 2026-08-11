"""``planalign optimize`` command."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Optional

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from planalign_optimizer.baseline import load_baseline, stale_baseline_warning
from planalign_optimizer.design_space import sample_candidates
from planalign_optimizer.evaluate import validate_levers_against_baseline
from planalign_optimizer.export import write_exports
from planalign_optimizer.paths import require_fresh_directory, resolve_output_paths
from planalign_optimizer.report import write_report
from planalign_optimizer.search import run_optimizer, seed_phase_count
from planalign_optimizer.models import OptimizerRun, OptimizerSpec
from planalign_optimizer.spec_io import (
    OptimizerSpecError,
    dump_resolved_spec,
    load_spec,
)

console = Console()
EXIT_BAD_INPUT = 2


def run_optimize(
    spec_path: Path = typer.Argument(..., exists=True, readable=True),
    max_runs: int = typer.Option(
        ..., "--max-runs", min=1, help="Mandatory hard cap on scenario evaluations"
    ),
    seed: Optional[int] = typer.Option(
        None, "--seed", help="Deterministic search seed"
    ),
    baseline: Optional[Path] = typer.Option(
        None, "--baseline", exists=True, readable=True, help="Override baseline config"
    ),
    database: Optional[Path] = typer.Option(
        None, "--database", help="Fresh directory for isolated candidate databases"
    ),
    output: Optional[Path] = typer.Option(None, "--output", help="Export directory"),
    parallel: Optional[int] = typer.Option(
        None, "--parallel", min=1, help="Scenario worker processes"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Validate and print candidates without evaluation"
    ),
    compare_baseline_to: Optional[Path] = typer.Option(
        None,
        "--compare-baseline-to",
        exists=True,
        readable=True,
        help="Warn if the resolved baseline drifted from a prior run's optimizer_results.json",
    ),
) -> None:
    """Search a bounded plan-design space and retain every candidate result."""
    try:
        spec = load_spec(spec_path)
        if baseline is not None:
            spec = spec.model_copy(
                update={
                    "baseline": spec.baseline.model_copy(
                        update={"config_path": baseline}
                    )
                }
            )
        resolved_baseline = load_baseline(spec.baseline.config_path)
        validate_levers_against_baseline(resolved_baseline, spec.design_space.levers)
        if compare_baseline_to is not None:
            drift = stale_baseline_warning(resolved_baseline, compare_baseline_to)
            if drift is not None:
                console.print(f"[yellow]{drift}[/yellow]")
        search_seed = seed if seed is not None else secrets.randbits(31)
        if dry_run:
            _render_dry_run(spec, max_runs, search_seed)
            return
        database_dir, output_dir = resolve_output_paths(database, output)
        require_fresh_directory(database_dir, "candidate database")
        if output_dir != database_dir:
            require_fresh_directory(output_dir, "export")
        run, budget = run_optimizer(
            spec,
            resolved_baseline,
            max_runs=max_runs,
            search_seed=search_seed,
            database_dir=database_dir,
            parallel=parallel,
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        dump_resolved_spec(spec, output_dir / "spec.yaml")
        write_exports(run, output_dir)
        report_path = write_report(run, output_dir)
    except (OptimizerSpecError, ValidationError, ValueError, OSError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_BAD_INPUT) from exc
    _render_summary(run, budget.describe(), report_path)


def _render_dry_run(spec: OptimizerSpec, max_runs: int, seed: int) -> None:
    seed_count = seed_phase_count(max_runs)
    candidates = sample_candidates(spec.design_space, seed_count, seed=seed)
    console.print(f"[blue]Search seed:[/blue] {seed}")
    console.print(
        f"[blue]Planned seed-phase candidates:[/blue] {len(candidates)} / {max_runs} budget"
    )
    for index, values in enumerate(candidates):
        console.print(f"candidate-{index:04d}: {values}")
    remaining = max_runs - len(candidates)
    if remaining > 0:
        console.print(
            f"[dim]Up to {remaining} additional refinement candidate(s) will be "
            "chosen after evaluating the seed phase and are not previewable here.[/dim]"
        )


def _render_summary(run: OptimizerRun, budget: str, report_path: Path) -> None:
    console.print(f"[blue]Search seed:[/blue] {run.search_seed}")
    console.print(f"[blue]Worker budget:[/blue] {budget}")
    executed = sum(item.is_duplicate_of is None for item in run.candidates)
    console.print(f"[blue]Runs executed:[/blue] {executed} / {run.max_runs}")
    if run.pareto_frontier is not None:
        console.print(
            f"[blue]Pareto frontier:[/blue] {len(run.pareto_frontier)} candidate(s)"
        )
    table = Table("Candidate", "Status", "Objectives", "Config delta")
    for candidate in run.candidates:
        table.add_row(
            candidate.candidate_id,
            candidate.status,
            str(candidate.objective_values),
            str(candidate.lever_values),
        )
    console.print(table)
    if run.binding_infeasible_constraints:
        console.print(
            "[yellow]Zero feasible candidates; constraints never satisfied: "
            + ", ".join(run.binding_infeasible_constraints)
            + "[/yellow]"
        )
    console.print(f"[green]Report:[/green] {report_path}")
