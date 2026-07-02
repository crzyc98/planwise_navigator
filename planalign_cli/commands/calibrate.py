"""
Calibrate command for Fidelity PlanAlign Engine CLI (Feature 105).

Fast Compensation Calibration Mode: rebuild only the compensation/workforce
subgraph per year, reuse the validated comp math (E077 solver, proration, S051
growth mart), skip the DC-plan stack, and return per-year avg-comp / growth-vs-
target / headcount in ~2-4 min instead of ~11 min -- exact on the comp columns.
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.table import Table

from planalign_orchestrator.calibration_runner import (
    CalibrationParameterSet,
    CalibrationRun,
    CalibrationRunner,
    PerYearCompensationResult,
)
from planalign_orchestrator.exceptions import ConfigurationError

from ..ui.progress import show_error_message, show_success_message
from ..utils.config_helpers import find_default_config, parse_years, validate_year_range

console = Console()

# Exit codes (see contracts/cli-calibrate.md)
EXIT_BAD_ARGS = 2
EXIT_GUARD_FAILURE = 3


def run_calibration(
    years: str = typer.Argument(..., help="Year range (e.g., '2025-2029' or '2025')"),
    config: Optional[str] = typer.Option(
        None, "--config", "-c", help="Path to simulation config YAML"
    ),
    database: Optional[str] = typer.Option(
        None,
        "--database",
        help="Target DuckDB path (default: isolated calibration DB)",
    ),
    target_growth: Optional[float] = typer.Option(
        None, "--target-growth", help="Target avg-comp YoY growth (e.g. 0.035)"
    ),
    cola: Optional[float] = typer.Option(None, "--cola", help="Override COLA rate"),
    merit: Optional[float] = typer.Option(
        None, "--merit", help="Override merit budget"
    ),
    interactive: bool = typer.Option(
        False, "--interactive", help="Re-tune parameters between iterations"
    ),
    threads: int = typer.Option(1, "--threads", help="Number of dbt threads"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Detailed output"),
) -> None:
    """⚡ Fast compensation calibration -- tune comp growth without a full sim."""
    try:
        start_year, end_year = parse_years(years)
        validate_year_range(start_year, end_year)
    except Exception as e:
        show_error_message(f"Invalid year range: {e}")
        raise typer.Exit(EXIT_BAD_ARGS)

    config_path = Path(config) if config else find_default_config()

    try:
        params = CalibrationParameterSet(
            target_growth_pct=target_growth,
            cola_rate=cola,
            merit_budget=merit,
        )
        run = CalibrationRun(
            start_year=start_year,
            end_year=end_year,
            config_path=config_path,
            database_path=Path(database) if database else None,
            interactive=interactive,
            params=params,
        )
    except Exception as e:  # pydantic validation (params out of range, etc.)
        show_error_message(f"Invalid calibration parameters: {e}")
        raise typer.Exit(EXIT_BAD_ARGS)

    runner = CalibrationRunner(run, threads=threads, verbose=verbose)
    console.print(
        f"⚡ [bold blue]Calibrating {start_year}-{end_year}[/bold blue] "
        f"against [dim]{runner.database_path}[/dim]"
    )

    try:
        results = runner.run_calibration()
    except ConfigurationError as e:
        show_error_message(str(e))
        raise typer.Exit(EXIT_GUARD_FAILURE)
    except Exception as e:
        show_error_message(f"Calibration failed: {e}")
        if verbose:
            import traceback

            console.print(f"[dim]{traceback.format_exc()}[/dim]")
        raise typer.Exit(1)

    _render_results(results)

    if interactive:
        _interactive_loop(runner)

    show_success_message("Calibration complete")


def _render_results(results: List[PerYearCompensationResult]) -> None:
    """Render the per-year calibration table (contracts/cli-calibrate.md)."""
    table = Table(title="Compensation Calibration", show_lines=False)
    table.add_column("Year", justify="right")
    table.add_column("Avg Comp", justify="right")
    table.add_column("YoY Growth", justify="right")
    table.add_column("Δ vs Target", justify="right")
    table.add_column("Headcount", justify="right")
    table.add_column("HC Growth", justify="right")
    table.add_column("Total Comp", justify="right")
    table.add_column("Total Growth", justify="right")
    table.add_column("NH Rate Gap", justify="right")

    for r in results:
        table.add_row(
            str(r.simulation_year),
            f"${r.avg_compensation:,.0f}",
            _pct(r.yoy_growth_pct),
            _signed_pct(r.growth_delta_pct),
            f"{r.headcount:,}",
            _pct(r.headcount_growth_pct),
            _compact_money(r.total_compensation),
            _pct(r.total_comp_growth_pct),
            _signed_money(r.new_hire_gap),
        )
    console.print(table)


def _compact_money(value: float) -> str:
    if value >= 1_000_000_000:
        return f"${value / 1_000_000_000:.2f}B"
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f}M"
    return f"${value:,.0f}"


def _pct(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:.1f}%"


def _signed_pct(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:+.1f}%"


def _signed_money(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:+,.0f}"


def _interactive_loop(runner: CalibrationRunner) -> None:
    """Re-tune loop (US2): adjust params and re-run without restarting.

    Tuning is cumulative -- each iteration starts from the currently-applied
    parameters and overrides only the fields the analyst changes, so a value
    set in one round carries into the next unless explicitly changed.
    """
    while True:
        console.print(
            "\n[dim]Adjust parameters (blank to keep current, 'q' to quit).[/dim]"
        )
        next_params = _prompt_params(runner.run.params)
        if next_params is None:
            break
        _render_results(runner.rerun_with_params(next_params))


def _prompt_params(
    current: CalibrationParameterSet,
) -> Optional[CalibrationParameterSet]:
    """Prompt for COLA/merit, layering changes onto the current params.

    Returns the updated params, or ``None`` if the analyst quits ('q').
    """
    merged = current.model_dump()
    for field, label in (("cola_rate", "COLA rate"), ("merit_budget", "Merit budget")):
        raw = typer.prompt(label, default="", show_default=False).strip()
        if raw.lower() == "q":
            return None
        if raw:
            merged[field] = float(raw)
    try:
        # Re-construct so pydantic validates the merged values (e.g. range checks).
        return CalibrationParameterSet(**merged)
    except Exception as e:
        show_error_message(f"Invalid input: {e}")
        return current
