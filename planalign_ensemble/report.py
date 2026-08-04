"""Rich CLI presentation for plans, distributions, risks, and attribution."""

from __future__ import annotations

from collections import defaultdict

from rich.console import Console
from rich.table import Table

from planalign_orchestrator.run_pool import EventKind, PoolEvent, WorkerBudget

from .models import (
    AttributionShare,
    MetricDistribution,
    RiskStatement,
    SeedPlan,
    Subsystem,
)


_METRIC_LABELS = {
    "active_headcount": "Active headcount",
    "total_compensation": "Total compensation",
    "employer_match_cost": "Employer match cost",
    "total_employer_plan_cost": "Total employer plan cost",
    "participation_rate": "Plan participation rate",
    "avg_deferral_rate": "Average deferral rate",
}
_CURRENCY_METRICS = {
    "total_compensation",
    "employer_match_cost",
    "total_employer_plan_cost",
}
_RATE_METRICS = {"participation_rate", "avg_deferral_rate"}


def print_ensemble_plan(console: Console, plan: SeedPlan, budget: WorkerBudget) -> None:
    """Disclose the resolved cost and location before the first worker starts."""
    horizon = plan.spec.end_year - plan.spec.start_year + 1
    console.print(
        f"[bold]Ensemble:[/bold] {len(plan.seeds)} seeds × {horizon} years "
        f"({plan.spec.start_year}-{plan.spec.end_year})"
    )
    console.print(f"  Seeds:         {_format_seeds(plan.seeds)}")
    console.print(f"  Worker budget: {budget.describe()}")
    _print_run_count(console, plan)
    console.print(f"  Est. disk:     ~{plan.estimated_disk_mib / 1024:.1f} GiB")
    console.print(f"  Output:        {plan.ensemble_db_path.parent}")
    if plan.spec.discard_seed_dbs:
        console.print(
            "  [yellow]Per-seed databases will be discarded after aggregation; "
            "later attribution cannot reuse them.[/yellow]"
        )


def _print_run_count(console: Console, plan: SeedPlan) -> None:
    """Make attribution's additional run multiplier visible before execution."""
    headline_runs = len(plan.seeds)
    if not plan.spec.attribution:
        console.print(f"  Runs:          {headline_runs} simulation runs")
        return
    attribution_runs = plan.total_run_count - headline_runs
    subsystem_count = sum(item.is_seed_variant for item in Subsystem)
    seed_count = plan.spec.resolved_attribution_seed_count
    anchor_count = plan.spec.resolved_attribution_anchor_count
    console.print(
        f"  Runs:          {headline_runs} headline + {attribution_runs} attribution "
        f"({subsystem_count} subsystems × {anchor_count} anchors × {seed_count} seeds) "
        f"= {plan.total_run_count} total"
    )
    console.print(
        f"                 baseline runs reused from headline: {seed_count} of {seed_count}"
    )


class EnsembleProgressReporter:
    """Render parent-process pool events without interleaving worker output."""

    def __init__(self, console: Console, *, total_seeds: int) -> None:
        self.console = console
        self.total_seeds = total_seeds
        self.completed = 0
        self.running: set[str] = set()

    def __call__(self, event: PoolEvent) -> None:
        """Print one concise update for each start or terminal pool event."""
        if event.kind is EventKind.JOB_STARTED:
            self.running.add(event.job_name)
            self.console.print(f"  ▶ {event.job_name} started")
            return
        self.running.discard(event.job_name)
        self.completed += 1
        icon = "✓" if event.kind is EventKind.JOB_COMPLETED else "✗"
        status = "completed" if event.kind is EventKind.JOB_COMPLETED else "failed"
        detail = f" ({event.duration_seconds or 0:.1f}s)"
        if event.error:
            detail = f"{detail}: {event.error}"
        self.console.print(
            f"  {icon} {event.job_name} {status}{detail}\n"
            f"  Ensemble progress: {self.completed}/{self.total_seeds}"
        )


def print_distribution_tables(
    console: Console,
    distributions: list[MetricDistribution] | tuple[MetricDistribution, ...],
    *,
    min_seeds: int,
) -> None:
    """Render metric bands, calling out insufficient samples rather than faking data."""
    grouped: dict[str, list[MetricDistribution]] = defaultdict(list)
    for distribution in distributions:
        grouped[distribution.metric].append(distribution)
    for metric in sorted(grouped):
        _print_metric_distribution(console, metric, grouped[metric], min_seeds)


def print_risk_statements(
    console: Console,
    statements: list[RiskStatement] | tuple[RiskStatement, ...],
) -> None:
    """Render threshold probabilities and unavailable metrics without ambiguity."""
    console.print("[bold]Risk — thresholds[/bold]")
    if not statements:
        console.print("  No thresholds configured.")
        return
    evaluable: dict[tuple[str, float], list[RiskStatement]] = defaultdict(list)
    for statement in statements:
        if statement.is_evaluable:
            evaluable[(statement.metric, statement.threshold_value)].append(statement)
        else:
            console.print(
                f"  {statement.metric}: not evaluable — {statement.reason or 'unavailable'}"
            )
    for (metric, threshold), values in sorted(evaluable.items()):
        label = _METRIC_LABELS.get(metric, metric.replace("_", " ").title())
        years = "   ".join(
            _format_risk_year(metric, value)
            for value in sorted(values, key=lambda item: item.simulation_year or 0)
        )
        console.print(
            f"  P({label.lower()} > {_format_metric_value(metric, threshold)}): {years}"
        )


def print_attribution_tables(
    console: Console,
    shares: list[AttributionShare] | tuple[AttributionShare, ...],
) -> None:
    """Render ranked, anchor-averaged variance shares and structural absences."""
    grouped: dict[tuple[str, int], list[AttributionShare]] = defaultdict(list)
    for share in shares:
        grouped[(share.metric, share.simulation_year)].append(share)
    for (metric, year), values in sorted(grouped.items()):
        _print_attribution_group(console, metric, year, values)


def _print_metric_distribution(
    console: Console,
    metric: str,
    distributions: list[MetricDistribution],
    min_seeds: int,
) -> None:
    """Write one metric's sufficient table and any year-specific warnings."""
    label = _METRIC_LABELS.get(metric, metric.replace("_", " ").title())
    sufficient = [item for item in distributions if item.is_sufficient]
    if sufficient and _is_deterministic(sufficient):
        _print_deterministic_metric(console, metric, label, sufficient)
    elif sufficient:
        seed_count = min(item.n_seeds for item in sufficient)
        table = Table(
            title=f"{label} — n={seed_count} seeds, linear percentiles",
            show_header=True,
        )
        for heading in ("Year", "P10", "P25", "P50", "P75", "P90"):
            table.add_column(heading, justify="right")
        for item in sorted(sufficient, key=lambda value: value.simulation_year):
            table.add_row(
                str(item.simulation_year),
                _format_metric_value(metric, item.p10),
                _format_metric_value(metric, item.p25),
                _format_metric_value(metric, item.p50),
                _format_metric_value(metric, item.p75),
                _format_metric_value(metric, item.p90),
            )
        console.print(table)
    for item in sorted(
        (item for item in distributions if not item.is_sufficient),
        key=lambda value: value.simulation_year,
    ):
        console.print(
            f"{label} — INSUFFICIENT SAMPLE (n={item.n_seeds}, minimum {min_seeds})"
        )
        console.print("  Percentiles withheld. Per-seed values were written.")


def _is_deterministic(distributions: list[MetricDistribution]) -> bool:
    """Report zero observed spread in every year as determinism, not a band."""
    return all(item.stddev == 0.0 for item in distributions)


def _print_deterministic_metric(
    console: Console,
    metric: str,
    label: str,
    distributions: list[MetricDistribution],
) -> None:
    """Show one solved value per year so identical percentiles cannot read as spread."""
    seed_count = min(item.n_seeds for item in distributions)
    table = Table(
        title=f"{label} — deterministic, identical across all {seed_count} seeds",
        show_header=True,
    )
    table.add_column("Year", justify="right")
    table.add_column("Value", justify="right")
    for item in sorted(distributions, key=lambda value: value.simulation_year):
        table.add_row(str(item.simulation_year), _format_metric_value(metric, item.p50))
    console.print(table)
    console.print(
        "  [dim]Not stochastic under this configuration; no band shown.[/dim]"
    )


def _print_attribution_group(
    console: Console,
    metric: str,
    year: int,
    shares: list[AttributionShare],
) -> None:
    """Show one metric/year ranking without treating a missing draw as zero."""
    label = _METRIC_LABELS.get(metric, metric.replace("_", " ").title())
    sample_size = max((share.n_seeds for share in shares), default=0)
    anchor_count = max((share.n_anchors for share in shares), default=0)
    console.print(
        f"[bold]Variance share (main effect) — {label.lower()}, {year} "
        f"(n={sample_size} paired seeds × {anchor_count} anchors)[/bold]"
    )
    stochastic = sorted(
        (share for share in shares if share.stochastic_status == "stochastic"),
        key=lambda share: (
            share.variance_share if share.variance_share is not None else float("-inf")
        ),
        reverse=True,
    )
    for share in stochastic:
        console.print(f"     {_format_attribution_share(share)}")
    for share in sorted(
        (share for share in shares if share.stochastic_status == "not_stochastic"),
        key=lambda item: item.subsystem.value,
    ):
        console.print(
            f"     {share.subsystem.value:<13} not stochastic — "
            f"{_not_stochastic_reason(share)} (n={share.n_seeds})"
        )
    representative = shares[0]
    console.print(
        f"  Method: conditional-variance reduction averaged across {anchor_count} "
        "independently pinned anchor seeds per subsystem — approximates the "
        "subsystem's first-order Sobol index. 95% CI from a paired bootstrap "
        "resampled within each anchor."
    )
    console.print(
        "  [yellow]Main effect only: pinning one subsystem's seed also fixes the "
        "population later subsystems draw from, so interaction effects are not "
        "decomposed and shares across subsystems need not sum to 1. Not a full "
        "variance decomposition or causal attribution.[/yellow]"
    )
    console.print(
        "  Baselines: "
        f"{representative.baselines_reused} reused from headline ensemble, "
        f"{representative.baselines_executed} executed."
    )


def _format_attribution_share(share: AttributionShare) -> str:
    """Show the raw variances and interval behind a share, not just the point estimate."""
    if share.variance_share is None:
        return (
            f"{share.subsystem.value:<13} not estimable — no anchor had two paired "
            f"values with nonzero baseline variance (n={share.n_seeds})"
        )
    direction = "lower" if share.variance_share > 0 else "higher"
    interval = (
        f", 95% CI [{share.ci_low:.0%}, {share.ci_high:.0%}]"
        if share.ci_low is not None and share.ci_high is not None
        else ", CI not estimable"
    )
    return (
        f"{share.subsystem.value:<13} variance {abs(share.variance_share):.0%} "
        f"{direction} when pinned{interval} "
        f"(unpinned {share.baseline_variance:.4g}, pinned {share.frozen_variance:.4g}, "
        f"n={share.n_seeds})"
    )


def _not_stochastic_reason(share: AttributionShare) -> str:
    """Explain the design finding rather than make it look like a low share."""
    if share.subsystem.value == "enrollment":
        return "draws do not vary with seed"
    if share.subsystem.value == "merit":
        return "no random draws"
    return "no independently seedable draws"


def _format_seeds(seeds: tuple[int, ...]) -> str:
    """Keep large seed lists legible while preserving their resolved order."""
    rendered = ", ".join(str(seed) for seed in seeds[:8])
    suffix = ", ..." if len(seeds) > 8 else ""
    return rendered + suffix


def _format_metric_value(metric: str, value: float | None) -> str:
    """Format a real statistic; absent values are intentionally left blank."""
    if value is None:
        return ""
    if metric in _CURRENCY_METRICS:
        return f"${value:,.0f}"
    if metric in _RATE_METRICS:
        return f"{value:.1%}"
    return f"{value:,.0f}"


def _format_risk_year(metric: str, statement: RiskStatement) -> str:
    """Show the exact numerator and denominator behind one risk probability."""
    probability = statement.exceedance_probability or 0.0
    count = round(probability * statement.n_seeds)
    return (
        f"{statement.simulation_year} {probability:.1%} "
        f"({count}/{statement.n_seeds})"
    )


__all__ = [
    "EnsembleProgressReporter",
    "print_attribution_tables",
    "print_distribution_tables",
    "print_ensemble_plan",
    "print_risk_statements",
]
