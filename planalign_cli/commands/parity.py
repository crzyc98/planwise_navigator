"""Exact isolated parity command for standard and compiled execution."""

from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from planalign_cli.utils.config_helpers import parse_years, validate_year_range
from planalign_orchestrator.tools.parity import ParityReport, run_parity

console = Console()


def run_parity_command(
    years: str,
    config: Path,
    census: Path,
    seed: int,
    json_output: bool,
) -> None:
    """Run both engines in fresh databases and report exact parity."""
    try:
        start_year, end_year = parse_years(years)
        validate_year_range(start_year, end_year)
        _require_file(config, "configuration")
        _require_file(census, "census")
        report = run_parity(
            start_year=start_year,
            end_year=end_year,
            config_path=config,
            census_path=census,
            seed=seed,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        console.print(f"[bold red]Parity failed:[/bold red] {exc}")
        raise typer.Exit(2) from exc

    if json_output:
        typer.echo(report.to_json())
    else:
        _render_report(report)
    if report.verdict != "IDENTICAL":
        raise typer.Exit(1)


def _require_file(path: Path, label: str) -> None:
    if not path.is_file():
        raise ValueError(f"{label} file not found: {path}")


def _render_report(report: ParityReport) -> None:
    style = "green" if report.verdict == "IDENTICAL" else "red"
    console.print(f"[{style} bold]{report.verdict}[/{style} bold]")
    if report.error:
        console.print(report.error)
        return
    table = Table("Table", "Schema", "Rows (dbt/compiled)", "Differences")
    for result in report.tables:
        schema = "equal" if not result.schema_mismatch else "different"
        differences = f"{result.a_only_all}/{result.b_only_all}"
        table.add_row(
            result.table,
            schema,
            f"{result.rows_a}/{result.rows_b}",
            differences,
        )
    console.print(table)
    console.print(
        f"Unexpected fallbacks: {report.unexpected_fallback_count}",
        style="green" if report.unexpected_fallback_count == 0 else "red",
    )
