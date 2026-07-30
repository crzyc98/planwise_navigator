"""``planalign fit`` — fit hazards and behavioural parameters from census history.

Turns 2-5 consecutive annual census snapshots into a parameter pack: the exact
seed CSVs and config fragment the simulator already consumes, plus a report
that shows the evidence behind every number and names everything the data could
not speak to.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from planalign_fit import (
    FitOptions,
    FitRun,
    PackError,
    SnapshotError,
    TransitionError,
    fit_parameter_pack,
    render_fit_report,
    write_pack,
)
from planalign_fit.bands import BandDefinitionError
from planalign_fit.priors import PriorsError
from planalign_fit.smoothing import DEFAULT_CREDIBILITY_K, DEFAULT_MIN_EXPOSURE

console = Console()

EXIT_BAD_INPUT = 2
EXIT_UNREADABLE_SNAPSHOTS = 3
EXIT_OUTPUT_REFUSED = 4

THIN_BASES = ("pooled", "prior")


def run_fit(
    snapshots_dir: Path = typer.Argument(
        ...,
        help="Directory of 2-5 consecutive annual census snapshots (.parquet or .csv)",
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Where to write the parameter pack (default: var/param_packs/<pack_id>)",
    ),
    config: Optional[Path] = typer.Option(
        None,
        "--config",
        "-c",
        help="Base config supplying the priors thin cells fall back to "
        "(default: config/simulation_config.yaml)",
    ),
    seeds_dir: Optional[Path] = typer.Option(
        None,
        "--seeds-dir",
        help="Seed directory supplying band definitions and priors (default: dbt/seeds)",
    ),
    credibility_k: float = typer.Option(
        DEFAULT_CREDIBILITY_K,
        "--credibility-k",
        help="Exposure at which observed data and the prior carry equal weight. "
        "Lower trusts the data sooner.",
    ),
    min_exposure: float = typer.Option(
        DEFAULT_MIN_EXPOSURE,
        "--min-exposure",
        help="Cells below this exposure are flagged as thin and lean on the prior",
    ),
    pack_id: Optional[str] = typer.Option(
        None, "--pack-id", help="Name for the pack (default: fit-<years>-<timestamp>)"
    ),
    notes: str = typer.Option(
        "", "--notes", help="Free-text note recorded in the pack manifest"
    ),
    force: bool = typer.Option(
        False, "--force", help="Replace an existing pack directory"
    ),
) -> None:
    """📐 Fit simulation parameters from historical census snapshots."""
    options = FitOptions(
        credibility_k=credibility_k,
        min_exposure=min_exposure,
        seeds_dir=seeds_dir,
        config_path=config,
        pack_id=pack_id,
        notes=notes,
    )

    if credibility_k < 0 or min_exposure < 0:
        console.print("[red]--credibility-k and --min-exposure must be >= 0[/red]")
        raise typer.Exit(EXIT_BAD_INPUT)

    try:
        run = fit_parameter_pack(snapshots_dir, options)
    except (SnapshotError, TransitionError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_UNREADABLE_SNAPSHOTS) from exc
    except (BandDefinitionError, PriorsError) as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_BAD_INPUT) from exc

    destination = Path(output) if output else _default_output(run)
    try:
        write_pack(run.pack, destination, report=render_fit_report(run), force=force)
    except PackError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(EXIT_OUTPUT_REFUSED) from exc

    _render_summary(run, destination)


def _default_output(run: FitRun) -> Path:
    from planalign_fit.apply import DEFAULT_WORKDIR

    return DEFAULT_WORKDIR / run.pack.manifest.pack_id


def _render_summary(run: FitRun, destination: Path) -> None:
    result = run.result
    fitted = result.all_fitted()
    thin = [value for value in fitted if value.basis in THIN_BASES]

    table = Table(show_header=False, box=None, padding=(0, 2, 0, 0))
    table.add_row("Snapshot years", ", ".join(str(y) for y in run.snapshot_set.years))
    table.add_row("Employees linked", f"{result.diagnostics.get('linked_pairs', 0):,}")
    table.add_row("Parameters fitted", f"{len(fitted)}")
    table.add_row(
        "Thin / prior-backed",
        f"[yellow]{len(thin)}[/yellow]" if thin else "0",
    )
    table.add_row(
        "Could not be fitted",
        f"[yellow]{len(result.unfittable)}[/yellow]" if result.unfittable else "0",
    )
    table.add_row("Pack fingerprint", run.pack.manifest.fingerprint[:16] + "…")

    console.print(
        Panel(
            table,
            title=f"📐 Fitted [bold]{run.pack.manifest.pack_id}[/bold]",
            border_style="green",
        )
    )

    for warning in result.warnings:
        console.print(f"[yellow]⚠️  {warning}[/yellow]")

    if result.unfittable:
        console.print(
            f"\n[yellow]{len(result.unfittable)} parameter group(s) could not be "
            "fitted from this data and kept their defaults:[/yellow]"
        )
        for item in result.unfittable:
            console.print(f"  [yellow]•[/yellow] {item.name}")

    console.print(f"\n[green]Pack written to[/green] {destination}")
    console.print(f"[dim]Report:[/dim] {destination / 'fit_report.md'}")
    next_year = run.snapshot_set.years[-1] + 1
    console.print(
        f"\n[dim]Apply it:[/dim] planalign simulate {next_year}-{next_year + 2} "
        f"--params {destination} --database iso.duckdb"
    )
