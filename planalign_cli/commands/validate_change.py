"""``planalign validate-change`` — prove an uncommitted change is output-neutral.

Builds the committed baseline (HEAD) and the candidate (working tree) into isolated
DuckDB files and compares them: all-mart parity, dbt invocation count, peak RSS, wall
time, and a shared-dev-DB guard. Exits non-zero if parity fails or the shared DB
changed, so it doubles as a gate for humans and agents (Claude/Codex).
"""

from __future__ import annotations

import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from planalign_orchestrator.change_validation import (
    ChangeValidationError,
    FrozenValidationResult,
    ScaleResult,
    ValidationResult,
    run_frozen_validation,
    run_validation_campaign,
)

console = Console()


def _repo_root() -> Path:
    res = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"], capture_output=True, text=True
    )
    if res.returncode != 0:
        raise typer.BadParameter("Not inside a git repository.")
    return Path(res.stdout.strip())


def _fmt_rss(mb: Optional[float]) -> str:
    return f"{mb:,.0f} MiB" if mb is not None else "n/a"


def _delta_pct(base: Optional[float], cand: Optional[float]) -> str:
    if not base or cand is None:
        return "—"
    return f"{(cand - base) / base * 100:+.1f}%"


def _render_scale(result: ScaleResult) -> Table:
    rows_label = (
        f"{result.census_rows:,} rows"
        if result.census_rows is not None
        else "config census"
    )
    title = f"[bold]{result.census_label}[/bold]  ({rows_label})"
    if result.small_census_warning:
        title += (
            "  [yellow]⚠ small census — scale-dependent bugs may not surface[/yellow]"
        )

    t = Table(title=title, title_justify="left", expand=False)
    t.add_column("Metric")
    t.add_column("Baseline", justify="right")
    t.add_column("Candidate", justify="right")
    t.add_column("Δ / Verdict")

    if not (result.baseline.ok and result.candidate.ok):
        which = "baseline" if not result.baseline.ok else "candidate"
        t.add_row("[red]build[/red]", "", "", f"[red]{which} build FAILED[/red]")
        return t

    bi, ci = result.baseline.invocation_count, result.candidate.invocation_count
    inv_delta = f"{ci - bi:+d}" if (bi is not None and ci is not None) else "—"
    t.add_row(
        "dbt invocations",
        str(bi if bi is not None else "?"),
        str(ci if ci is not None else "?"),
        inv_delta,
    )

    parity = (
        "[green]0/0 identical ✅[/green]"
        if result.parity_ok
        else "[red]MISMATCH ❌[/red]"
    )
    t.add_row("all-mart parity", f"{result.marts_compared} marts", "", parity)

    t.add_row(
        "peak RSS",
        _fmt_rss(result.baseline.peak_rss_mb),
        _fmt_rss(result.candidate.peak_rss_mb),
        _delta_pct(result.baseline.peak_rss_mb, result.candidate.peak_rss_mb),
    )
    t.add_row(
        "wall time",
        f"{result.baseline.wall_s:.1f}s",
        f"{result.candidate.wall_s:.1f}s",
        _delta_pct(result.baseline.wall_s, result.candidate.wall_s),
    )
    return t


def _render(result: ValidationResult) -> None:
    for scale in result.scales:
        console.print(_render_scale(scale))
        for mart, diff in scale.parity_offenders.items():
            console.print(
                f"    [red]DIFF[/red] {mart}: (baseline-candidate, candidate-baseline) = {diff}"
            )
        console.print()

    guard = (
        "[green]unchanged ✅[/green]"
        if result.shared_db_unchanged
        else "[red]CHANGED ❌ — a build wrote to the shared dev DB![/red]"
    )
    console.print(f"Shared dev DB (dbt/simulation.duckdb): {guard}")

    if result.passed:
        console.print(
            Panel.fit(
                "[bold green]PASS[/bold green] — change is output-neutral "
                "(byte-identical marts, shared DB untouched).",
                border_style="green",
            )
        )
    else:
        console.print(
            Panel.fit(
                "[bold red]FAIL[/bold red] — the change is NOT output-neutral. "
                "Do not ship; inspect the mismatches above.",
                border_style="red",
            )
        )
    if all(s.small_census_warning for s in result.scales):
        console.print(
            "[yellow]Note:[/yellow] only small censuses were validated. Re-run with "
            "[bold]--census <~60k parquet>[/bold] — scale-dependent bugs (e.g. feature 121 "
            "Tier C) pass at dev scale and fail at 60k."
        )


def _render_frozen(result: FrozenValidationResult) -> None:
    table = Table(title=f"Frozen baseline {result.baseline_id}")
    table.add_column("Mart")
    table.add_column("Status")
    table.add_column("Baseline − candidate", justify="right")
    table.add_column("Candidate − baseline", justify="right")
    for relation, comparison in sorted(result.comparisons.items()):
        style = "green" if comparison.passed else "red"
        table.add_row(
            relation,
            f"[{style}]{comparison.status}[/{style}]",
            str(comparison.baseline_minus_candidate),
            str(comparison.candidate_minus_baseline),
        )
    console.print(table)
    label = result.phase + (f"/{result.checkpoint}" if result.checkpoint else "")
    if result.passed:
        console.print(
            Panel.fit(
                f"[bold green]PASS[/bold green] — {label} matches the frozen baseline.",
                border_style="green",
            )
        )
    else:
        for failure in result.failures:
            console.print(f"[red]{failure}[/red]")
        console.print(
            Panel.fit(
                f"[bold red]FAIL[/bold red] — {label} does not satisfy the frozen gate.",
                border_style="red",
            )
        )


def run_validate_change(
    census: Optional[List[Path]] = None,
    config: Optional[Path] = None,
    years: str = "2025-2027",
    keep_dbs: bool = False,
    workdir: Optional[Path] = None,
    baseline_db: Optional[Path] = None,
    candidate_db: Optional[Path] = None,
    characterization: Optional[Path] = None,
    exclusions: Optional[Path] = None,
    phase: Optional[str] = None,
    checkpoint: Optional[str] = None,
) -> None:
    """Validate the current uncommitted change is output-neutral (see module doc)."""
    repo_root = _repo_root()
    frozen_values = (
        baseline_db,
        candidate_db,
        characterization,
        exclusions,
        phase,
    )
    if any(value is not None for value in frozen_values):
        if not all(value is not None for value in frozen_values):
            raise typer.BadParameter(
                "frozen mode requires --baseline-db, --candidate-db, "
                "--characterization, --exclusions, and --phase"
            )
        try:
            frozen_result = run_frozen_validation(
                repo_root=repo_root,
                baseline_db=baseline_db.resolve(),  # type: ignore[union-attr]
                candidate_db=candidate_db.resolve(),  # type: ignore[union-attr]
                characterization_path=characterization.resolve(),  # type: ignore[union-attr]
                exclusions_path=exclusions.resolve(),  # type: ignore[union-attr]
                phase=phase or "",
                checkpoint=checkpoint,
            )
        except ChangeValidationError as exc:
            console.print(f"[red]validate-change: {exc}[/red]")
            raise typer.Exit(2)
        _render_frozen(frozen_result)
        raise typer.Exit(0 if frozen_result.passed else 1)

    config_path = (
        config or (repo_root / "config" / "simulation_config.yaml")
    ).resolve()
    if not config_path.exists():
        raise typer.BadParameter(f"Config not found: {config_path}")

    censuses: List[Optional[Path]] = [c.resolve() for c in census] if census else [None]
    for c in censuses:
        if c is not None and not c.exists():
            raise typer.BadParameter(f"Census not found: {c}")

    work = (workdir or Path(tempfile.mkdtemp(prefix="planalign-validate-"))).resolve()

    console.print(
        Panel.fit(
            "[bold]validate-change[/bold]: baseline = HEAD (change stashed), "
            "candidate = working tree.\n"
            f"config: {config_path.name}   horizon: {years}   "
            f"censuses: {', '.join(c.name if c else 'config-default' for c in censuses)}\n"
            f"[dim]isolated DBs in {work} — the shared dev DB is never built into.[/dim]",
            border_style="blue",
        )
    )

    def log(msg: str) -> None:
        console.print(f"[dim]  {msg}[/dim]")

    try:
        result = run_validation_campaign(
            repo_root=repo_root,
            config_path=config_path,
            censuses=censuses,
            years=years,
            workdir=work,
            keep_dbs=keep_dbs,
            log=log,
        )
    except ChangeValidationError as exc:
        console.print(f"[red]validate-change: {exc}[/red]")
        raise typer.Exit(2)

    _render(result)
    if keep_dbs:
        console.print(f"[dim]Isolated DBs kept in {work}[/dim]")
    raise typer.Exit(0 if result.passed else 1)
