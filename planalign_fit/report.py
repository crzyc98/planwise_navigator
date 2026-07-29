"""Render ``fit_report.md`` — the human-readable half of a parameter pack.

The report exists so nobody has to take a fitted number on faith. Every value
shows the prior it moved from, the exposure behind it, and how much weight the
data actually carried; anything the snapshots could not speak to is listed
separately, with the default that was kept instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional, Sequence

from planalign_fit.models import CellObservation, FittedValue, HazardFit

if TYPE_CHECKING:  # pragma: no cover - typing only
    from planalign_fit.runner import FitRun

THIN_BASES = ("pooled", "prior")


def render_fit_report(run: "FitRun") -> str:
    """Full Markdown report for one fit."""
    sections = [
        _header(run),
        _summary(run),
        _warnings(run),
        _hazard_section(
            "Termination hazard", run.result.termination, run.result.termination_cells
        ),
        _hazard_section(
            "Promotion hazard", run.result.promotion, run.result.promotion_cells
        ),
        _merit_section(run),
        _config_section(run),
        _deferral_section(run),
        _unfittable_section(run),
        _method_section(run),
    ]
    return "\n".join(section for section in sections if section).rstrip() + "\n"


def _header(run: "FitRun") -> str:
    manifest = run.pack.manifest
    sources = "\n".join(
        f"| {source.year} | `{source.filename}` | {source.row_count:,} | "
        f"`{source.sha256[:16]}…` |"
        for source in manifest.sources
    )
    return f"""# Fitted parameter pack — `{manifest.pack_id}`

Fitted **{manifest.fit_date}** with PlanAlign {manifest.planalign_version}.
Pack fingerprint `{manifest.fingerprint}`.

Every parameter below was estimated from the client's own census history. Runs
that use this pack stamp the fingerprint above into `run_metadata`, so any
result can be traced back to these exact source files.

## Source snapshots

| Year | File | Rows | SHA-256 |
|---|---|---:|---|
{sources}

Combined source digest: `{manifest.source_digest}`
"""


def _summary(run: "FitRun") -> str:
    result = run.result
    fitted = result.all_fitted()
    thin = [value for value in fitted if value.basis in THIN_BASES]
    diagnostics = result.diagnostics
    rows = [
        ("Snapshot years", ", ".join(str(y) for y in run.snapshot_set.years)),
        ("Employees linked across years", f"{diagnostics.get('linked_pairs', 0):,}"),
        ("Parameters fitted", f"{len(fitted)}"),
        ("Backed by a thin cell or the prior", f"{len(thin)}"),
        ("Parameters that could not be fitted", f"{len(result.unfittable)}"),
        ("Credibility constant `k`", f"{run.options.credibility_k:,.0f}"),
        ("Minimum exposure per cell", f"{run.options.min_exposure:,.0f}"),
    ]
    body = "\n".join(f"| {label} | {value} |" for label, value in rows)
    return f"""## Summary

| | |
|---|---|
{body}
"""


def _warnings(run: "FitRun") -> str:
    if not run.result.warnings:
        return ""
    items = "\n".join(f"- ⚠️ {warning}" for warning in run.result.warnings)
    return f"## Data warnings\n\n{items}\n"


def _hazard_section(
    title: str, fit: Optional[HazardFit], cells: Sequence[CellObservation]
) -> str:
    if fit is None:
        return ""

    observed = fit.observed_overall_rate
    observed_text = "n/a" if observed is None else f"{observed:.4f}"
    convergence = (
        f"converged in {fit.iterations} iterations"
        if fit.converged
        else f"**did not converge** within {fit.iterations} iterations"
    )
    constants = ", ".join(
        f"`{name}` = {value:g}" for name, value in sorted(fit.level_constants.items())
    )

    return f"""## {title}

Observed overall rate **{observed_text}** over {fit.total_exposure:,.0f} exposure
years and {fit.total_events:,.0f} events; the multiplicative fit {convergence}.
Level factor held fixed at {constants} — see "Not fitted" below.

### Fitted values

{_fitted_table(fit.values())}

### Cell evidence

{_cell_table(cells)}
"""


def _fitted_table(values: Iterable[FittedValue]) -> str:
    header = (
        "| Parameter | Fitted | Prior | Change | Exposure | Credibility | Basis |\n"
        "|---|---:|---:|---:|---:|---:|---|"
    )
    rows = []
    for value in values:
        moved = value.moved_pct
        moved_text = "n/a" if moved is None else f"{moved:+.1%}"
        flag = " ⚠️" if value.basis in THIN_BASES else ""
        rows.append(
            f"| `{value.name}` | {value.value:.4f} | {value.prior:.4f} | "
            f"{moved_text} | {value.exposure:,.0f} | {value.credibility:.0%} | "
            f"{value.basis}{flag} |"
        )
    return "\n".join([header, *rows])


def _cell_table(cells: Sequence[CellObservation], limit: int = 40) -> str:
    populated = sorted(
        (cell for cell in cells if cell.exposure > 0),
        key=lambda cell: cell.exposure,
        reverse=True,
    )
    header = (
        "| Age band | Tenure band | Level | Exposure | Events | Observed rate |\n"
        "|---|---|---:|---:|---:|---:|"
    )
    rows = [
        f"| {cell.age_band} | {cell.tenure_band} | {cell.level_id} | "
        f"{cell.exposure:,.0f} | {cell.events:,.0f} | "
        f"{(cell.observed_rate or 0.0):.4f} |"
        for cell in populated[:limit]
    ]
    table = "\n".join([header, *rows])
    if len(populated) > limit:
        table += (
            f"\n\n_{len(populated) - limit} further cell(s) omitted; "
            "the fit uses all of them._"
        )
    return table


def _merit_section(run: "FitRun") -> str:
    if not run.result.merit_by_level:
        return ""
    values = [
        run.result.merit_by_level[level] for level in sorted(run.result.merit_by_level)
    ]
    return f"""## Merit by job level

Fitted as the median year-over-year compensation growth of employees who stayed
and were not promoted, net of the configured COLA. Promotions are excluded —
their raise is modelled separately.

{_fitted_table(values)}
"""


def _config_section(run: "FitRun") -> str:
    overrides = run.result.config_overrides
    if not overrides:
        return ""
    values = [overrides[name] for name in sorted(overrides)]
    return f"""## Config parameters

Written to `parameters.yaml` and deep-merged over the base config.

{_fitted_table(values)}
"""


def _deferral_section(run: "FitRun") -> str:
    if not run.result.deferral_rates:
        return ""
    values = [
        run.result.deferral_rates[key] for key in sorted(run.result.deferral_rates)
    ]
    adoption = run.result.diagnostics.get("escalation_adoption_rate")
    adoption_note = ""
    if adoption is not None:
        exposure = run.result.diagnostics.get("escalation_exposure", 0)
        adoption_note = (
            f"\nObserved escalation adoption: **{adoption:.1%}** of "
            f"{exposure:,.0f} participants enrolled in consecutive years raised "
            "their deferral rate. `deferral_auto_escalation.enabled` is a switch "
            "rather than a rate, so this is evidence for how to set it, not a "
            "fitted value.\n"
        )
    return f"""## Deferral rates

Starting deferral rate of newly enrolled employees, by age and income segment.

{_fitted_table(values)}
{adoption_note}"""


def _unfittable_section(run: "FitRun") -> str:
    if not run.result.unfittable:
        return ""
    rows = "\n".join(
        f"| `{item.name}` | {item.reason} | `{item.default_used}` |"
        for item in run.result.unfittable
    )
    return f"""## Not fitted — defaults retained

**These parameters were NOT estimated from your data.** Each kept its existing
value, so any projection that depends on them still rests on an assumption.

| Parameter | Why it could not be fitted | Default kept |
|---|---|---|
{rows}
"""


def _method_section(run: "FitRun") -> str:
    return f"""## Method

**Cohort linking.** Employees are matched across consecutive snapshots by
`employee_id`. Exposure for a year-`t` rate is the population active at the end
of year `t-1`, placed in its year `t-1` age, tenure, and level band — the band
is known before the event resolves, exactly as the simulator applies a hazard.

**Hazard fitting.** Termination and promotion share the simulator's functional
form, `base x age_multiplier x tenure_multiplier x level_factor`. Both are fitted
with an exposure-weighted iterative proportional fit (equivalently, a Poisson
log-linear model with the level factor as a fixed offset). Age multipliers are
rescaled to an exposure-weighted mean of 1.0 so base and multipliers are
identified.

**Credibility smoothing.** Every fitted value is blended toward its prior — the
current seed or config value — with weight `Z = exposure / (exposure + k)`, at
`k = {run.options.credibility_k:,.0f}`. Cells below
{run.options.min_exposure:,.0f} exposure are labelled `pooled` and flagged, so a
handful of observations can never become a parameter on their own.

**Base config.** `{run.pack.manifest.base_config}`
**Base seeds.** `{run.pack.manifest.base_seeds}`

## Applying this pack

```bash
planalign simulate {run.snapshot_set.years[-1] + 1}-{run.snapshot_set.years[-1] + 3} \\
  --params <this directory> --database iso.duckdb
```

The run stamps `{run.pack.manifest.pack_id}` and fingerprint
`{run.pack.manifest.fingerprint[:16]}…` into `run_metadata`.
"""
