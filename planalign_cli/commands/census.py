"""``planalign census``: census tools (#1078)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

import typer
from rich.console import Console

console = Console()

census_app = typer.Typer(help="Census tools", no_args_is_help=True)


@census_app.command("roll-forward")
def roll_forward(
    config: Path = typer.Option(
        ...,
        "--config",
        "-c",
        help="Simulation config YAML (its settings drive the bridge)",
    ),
    census: Optional[Path] = typer.Option(
        None, "--census", help="Census to roll forward (default: the config's census)"
    ),
    to_year: Optional[int] = typer.Option(
        None, "--to-year", help="Year to roll forward to (default: start_year - 1)"
    ),
    output: Optional[Path] = typer.Option(
        None,
        "--output",
        "-o",
        help="Bridge census to write (default: next to the census)",
    ),
    database: Optional[Path] = typer.Option(
        None, "--database", help="Database for the bridge simulation"
    ),
) -> None:
    """Simulate the years a census is missing and save a bridge census."""
    import duckdb

    from planalign_orchestrator.census_rollforward import roll_forward_census
    from planalign_orchestrator.config import load_simulation_config, to_dbt_vars

    cfg = load_simulation_config(config)
    # to_dbt_vars resolves a relative census path the way simulations do.
    configured = to_dbt_vars(cfg).get("census_parquet_path")
    census_path = census or (Path(str(configured)) if configured else None)
    if census_path is None:
        raise typer.BadParameter("Pass --census or set setup.census_parquet_path")
    year = to_year or cfg.simulation.start_year - 1
    output_path = output or census_path.with_name(f"census_bridge_{year}.parquet")
    database_path = database or output_path.with_suffix(".duckdb")

    try:
        result = roll_forward_census(cfg, census_path, year, output_path, database_path)
    except (ValueError, duckdb.Error) as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)

    console.print(
        f"Rolled the {result.census_year} census forward to {result.bridge_year}: "
        f"{result.hires:,} hires, {result.terminations:,} terminations, "
        f"{result.ending_headcount:,} employees at year-end "
        f"({result.simulated_employees:,} simulated)."
    )
    console.print(f"Bridge census: {result.census_path}")
    console.print(
        "To use it, set setup.census_parquet_path to the bridge census. If the "
        "config sets setup.plan_year_start_date/plan_year_end_date, move them "
        f"to {year}."
    )
