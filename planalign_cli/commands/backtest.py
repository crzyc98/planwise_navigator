"""``planalign backtest`` command."""

from __future__ import annotations

from pathlib import Path
from typing import Optional
import json

import typer
from click.core import ParameterSource
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from planalign_backtest import BacktestError, BacktestOptions, MetricThresholds
from planalign_backtest.errors import SimulationFailure
from planalign_backtest.models import Threshold
from planalign_backtest.report import write_scorecard
from planalign_backtest.runner import run_backtest
from planalign_fit import FitOptions, PackError, SnapshotError, write_pack
from planalign_fit.promotion import (
    DEFAULT_LEVEL_COVERAGE_THRESHOLD,
    DEFAULT_SEPARATION_EXPOSURE_GATE,
)
from planalign_fit.smoothing import DEFAULT_CREDIBILITY_K, DEFAULT_MIN_EXPOSURE

console = Console()
EXIT_BAD_INPUT = 2
EXIT_REJECTED = 3
EXIT_SIMULATION = 4


def _pair(raw: str, name: str) -> Threshold:
    try:
        values = tuple(float(value.strip()) for value in raw.split(","))
        if len(values) != 2:
            raise ValueError
        return Threshold(warn=values[0], fail=values[1])
    except (ValueError, ValidationError) as exc:
        raise ValueError(f"{name} must be WARN,FAIL with 0 < WARN < FAIL") from exc


def _seed_values(count: int, raw: Optional[str]) -> tuple[int, ...]:
    if raw is None:
        if not 1 <= count <= 5:
            raise ValueError(f"--seeds must be between 1 and 5; got {count}.")
        return tuple(range(42, 42 + count))
    try:
        values = tuple(int(value.strip()) for value in raw.split(",") if value.strip())
        if not 1 <= len(values) <= 5:
            raise ValueError("--seed-list must contain between 1 and 5 seeds")
        if len(set(values)) != len(values):
            duplicate = next(value for value in values if values.count(value) > 1)
            raise ValueError(
                f"--seed-list contains duplicate seed {duplicate}; duplicate runs "
                "would narrow the reported spread without adding information."
            )
        return values
    except ValueError as exc:
        raise ValueError("--seed-list must contain comma-separated integers") from exc


def _render(run, destination: Path) -> None:
    table = Table("Metric", "Period", "Predicted", "Actual", "% error", "Status")
    for item in run.scorecard.comparisons:
        table.add_row(
            item.metric,
            str(item.period),
            "—" if item.predicted is None else f"{item.predicted:,.4f}",
            "—" if item.actual is None else f"{item.actual:,.4f}",
            "—" if item.percent_error is None else f"{item.percent_error:+.2%}",
            item.status,
        )
    console.print(table)
    console.print(
        f"[bold]Verdict: {run.scorecard.verdict.upper()}[/bold] — {run.scorecard.verdict_summary}"
    )
    if len(run.scorecard.seeds) == 1:
        console.print("[dim]no seed spread computed (1 seed)[/dim]")
    console.print(
        f"[green]Scorecard:[/green] {destination / 'backtest' / 'scorecard.md'}"
    )


def run_backtest_command(
    ctx: typer.Context,
    snapshots_dir: Path = typer.Argument(
        ..., help="Directory of consecutive annual census snapshots"
    ),
    holdout: int = typer.Option(1, "--holdout"),
    seeds: int = typer.Option(3, "--seeds"),
    seed_list: Optional[str] = typer.Option(None, "--seed-list"),
    output: Optional[Path] = typer.Option(None, "--output", "-o"),
    config: Path = typer.Option(
        Path("config/simulation_config.yaml"), "--config", "-c"
    ),
    seeds_dir: Optional[Path] = typer.Option(None, "--seeds-dir"),
    threshold_headcount: str = typer.Option("0.02,0.04", "--threshold-headcount"),
    threshold_compensation: str = typer.Option("0.03,0.06", "--threshold-compensation"),
    threshold_flows: str = typer.Option("0.10,0.20", "--threshold-flows"),
    threshold_plan: str = typer.Option("0.05,0.10", "--threshold-plan"),
    workdir: Optional[Path] = typer.Option(None, "--workdir"),
    notes: str = typer.Option("", "--notes"),
    keep_databases: bool = typer.Option(False, "--keep-databases"),
    force: bool = typer.Option(False, "--force"),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
    credibility_k: float = typer.Option(DEFAULT_CREDIBILITY_K, "--credibility-k"),
    min_exposure: float = typer.Option(DEFAULT_MIN_EXPOSURE, "--min-exposure"),
    level_coverage_threshold: float = typer.Option(
        DEFAULT_LEVEL_COVERAGE_THRESHOLD, "--level-coverage-threshold"
    ),
    separation_exposure_gate: float = typer.Option(
        DEFAULT_SEPARATION_EXPOSURE_GATE, "--separation-exposure-gate"
    ),
) -> None:
    """Fit on early snapshots and score simulations against held-out history."""
    try:
        if (
            seed_list is not None
            and ctx.get_parameter_source("seeds") is ParameterSource.COMMANDLINE
        ):
            raise ValueError("--seeds and --seed-list are mutually exclusive")
        if holdout not in (1, 2):
            raise ValueError(
                f"--holdout must be 1 or 2; got {holdout}. "
                "A longer holdout is not supported."
            )
        seed_values = _seed_values(seeds, seed_list)
        thresholds = MetricThresholds(
            headcount=_pair(threshold_headcount, "--threshold-headcount"),
            compensation=_pair(threshold_compensation, "--threshold-compensation"),
            flows=_pair(threshold_flows, "--threshold-flows"),
            plan=_pair(threshold_plan, "--threshold-plan"),
        )
        moved = tuple(
            name
            for name, raw, default in (
                ("headcount", threshold_headcount, "0.02,0.04"),
                ("compensation", threshold_compensation, "0.03,0.06"),
                ("flows", threshold_flows, "0.10,0.20"),
                ("plan", threshold_plan, "0.05,0.10"),
            )
            if raw != default
        )
        fit_options = FitOptions(
            credibility_k=credibility_k,
            min_exposure=min_exposure,
            level_coverage_threshold=level_coverage_threshold,
            separation_exposure_gate=separation_exposure_gate,
            seeds_dir=seeds_dir,
            config_path=config,
            notes=notes,
        )
        options = BacktestOptions(
            holdout_years=holdout,
            seeds=seed_values,
            thresholds=thresholds,
            output=output,
            base_config=config,
            workdir=workdir,
            fit_options=fit_options,
            force=force,
            keep_databases=keep_databases,
            overridden_thresholds=moved,
            notes=notes,
            verbose=verbose,
        )
    except (ValueError, ValidationError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_BAD_INPUT) from exc
    try:
        if output is not None and not force:
            score_path = output / "backtest" / "scorecard.json"
            if score_path.exists():
                payload = json.loads(score_path.read_text(encoding="utf-8"))
                scored_on = (payload.get("provenance") or {}).get(
                    "backtest_date", "an earlier date"
                )
                raise BacktestError(
                    f"{score_path} already exists, scored on {scored_on}. "
                    "Pass --force to replace it."
                )
        console.print(
            f"[blue]Backtesting {snapshots_dir} across seeds "
            f"{', '.join(str(seed) for seed in options.seeds)}[/blue]"
        )
        run = run_backtest(snapshots_dir, options)
        destination = output or Path("var/param_packs") / run.pack.manifest.pack_id
        write_pack(run.pack, destination, force=force)
        write_scorecard(run.scorecard, destination, force=force)
    except SimulationFailure as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_SIMULATION) from exc
    except (BacktestError, SnapshotError, PackError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_REJECTED) from exc
    _render(run, destination)
