"""Render ``fit_report.md`` — the human-readable half of a parameter pack.

The report exists so nobody has to take a fitted number on faith. Every value
shows the prior it moved from, the exposure behind it, and how much weight the
data actually carried; anything the snapshots could not speak to is listed
separately, with the default that was kept instead.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Iterable, Optional, Sequence

from planalign_fit.models import (
    CellObservation,
    FittedValue,
    HazardFit,
    PromotionBasis,
    PromotionClassification,
)

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
        _promotion_section(run),
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
        ("Promotion basis", _basis_label(result.promotion_classification)),
    ]
    moved = _moved_thresholds(run)
    if moved:
        rows.append(("Non-default thresholds", moved))
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
years and {_event_count(fit.total_events)} events; the multiplicative fit {convergence}.
Level factor held fixed at {constants} — see "Not fitted" below.

### Fitted values

{_fitted_table(fit.values())}

### Cell evidence

{_cell_table(cells)}
"""


def _event_count(events: float) -> str:
    """Render an event count, keeping a decimal when the count is expected.

    Promotion events are a sum of per-employee probabilities when promotions
    were inferred rather than observed (#511), so rounding 412.7 to "413" would
    present an estimate as an exact tally.
    """
    if abs(events - round(events)) < 1e-9:
        return f"{events:,.0f}"
    return f"{events:,.1f}"


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
        f"{cell.exposure:,.0f} | {_event_count(cell.events)} | "
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

Fitted as the **promotion-weighted** median year-over-year compensation growth
of employees who stayed, net of the configured COLA. Each employee is weighted
by how likely their raise was an ordinary one, so a certain promotion
contributes nothing and a certain non-promotion contributes fully — their
promotion raise is modelled separately. Exposure below is that summed weight,
not a headcount.
{_merit_caveat(run)}
{_fitted_table(values)}
"""


def _merit_caveat(run: "FitRun") -> str:
    """FR-008b: say when the weighting rests on an unresolved classification."""
    classification = run.result.promotion_classification
    if classification is None or classification.basis is not PromotionBasis.NOT_FITTED:
        return ""
    return (
        "\n⚠️ Promotions could not be distinguished from ordinary raises in this\n"
        "census, so the merit weighting **could not be sharpened** by a usable\n"
        "promotion classification. Some promotion raises may remain in the pool,\n"
        "biasing merit upward.\n"
    )


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

**Promotion classification.** A promotion is a move to a higher job level.
Where the census carries a job level for at least
{run.options.level_coverage_threshold:.0%} of linked employees, promotions are
measured directly from those moves. Otherwise level is derived from
compensation banding, which makes *any* band-crossing raise look like a
promotion — so instead the year-over-year raise distribution is fitted per level
as two components: ordinary raises near COLA plus merit, and promotion raises
near the configured promotion increase. Each employee's probability of belonging
to the promotion component becomes their weight in the promotion hazard, and its
complement their weight in the merit fit, so the two estimates are identified
together rather than off each other. A level contributes a fitted rate only
where the components are genuinely distinguishable — at least two pooled
standard deviations apart, with a two-component model preferred on BIC — and
where too little of the population separates, no promotion hazard is published
at all.

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


def _basis_label(classification: Optional[PromotionClassification]) -> str:
    """One line an analyst can read without opening the rest of the report."""
    if classification is None:
        return "not recorded"
    if classification.basis is PromotionBasis.MEASURED:
        return (
            f"measured from `level_id` (coverage {classification.level_coverage:.0%})"
        )
    if classification.basis is PromotionBasis.ESTIMATED:
        separated = sum(1 for level in classification.levels if level.separated)
        share = classification.separated_exposure_share or 0.0
        return (
            f"estimated from the raise distribution ({separated} of "
            f"{len(classification.levels)} levels, {share:.0%} of exposure)"
        )
    return "**not fitted — configured default retained**"


def _moved_thresholds(run: "FitRun") -> str:
    """FR-017: a moved dial must be visible without the command that set it."""
    from planalign_fit.promotion import (
        DEFAULT_LEVEL_COVERAGE_THRESHOLD,
        DEFAULT_SEPARATION_EXPOSURE_GATE,
    )

    moved = []
    if run.options.level_coverage_threshold != DEFAULT_LEVEL_COVERAGE_THRESHOLD:
        moved.append(
            f"level-coverage {run.options.level_coverage_threshold:.2f} "
            f"(default {DEFAULT_LEVEL_COVERAGE_THRESHOLD:.2f})"
        )
    if run.options.separation_exposure_gate != DEFAULT_SEPARATION_EXPOSURE_GATE:
        moved.append(
            f"separation-exposure-gate {run.options.separation_exposure_gate:.2f} "
            f"(default {DEFAULT_SEPARATION_EXPOSURE_GATE:.2f})"
        )
    return "; ".join(moved)


def _promotion_section(run: "FitRun") -> str:
    """The promotion hazard, prefaced by how its rate was arrived at."""
    classification = run.result.promotion_classification
    fit = run.result.promotion

    if classification is not None and classification.basis is PromotionBasis.NOT_FITTED:
        return f"""## Promotion hazard — not fitted

{classification.reason.capitalize()}.

The configured promotion hazard is retained unchanged; see "Not fitted" below.
Supplying a `level_id` column in the census would let promotions be measured
directly rather than inferred from the size of a raise.

{_separation_table(classification)}
"""

    if fit is None:
        return ""

    section = _hazard_section("Promotion hazard", fit, run.result.promotion_cells)
    if classification is None:
        return section

    if classification.basis is PromotionBasis.MEASURED:
        preamble = (
            f"Job level supplied by the census for "
            f"{classification.level_coverage:.0%} of linked employees, so "
            "promotions were measured directly from level moves.\n"
        )
        return section.replace(
            "## Promotion hazard\n", f"## Promotion hazard\n\n{preamble}"
        )

    share = classification.separated_exposure_share or 0.0
    preamble = (
        f"No usable `level_id` column (coverage "
        f"{classification.level_coverage:.0%}, threshold "
        f"{classification.level_coverage_threshold:.0%}), so promotions were "
        "separated from ordinary raises by their size. A level contributes to "
        "the fit only where the two are genuinely distinguishable.\n\n"
        f"Levels that separated hold **{share:.0%}** of experienced exposure "
        f"(gate: {classification.exposure_gate:.0%}).\n\n"
        f"{_separation_table(classification)}\n"
    )
    return section.replace(
        "## Promotion hazard\n", f"## Promotion hazard\n\n{preamble}"
    )


def _distance(value: Optional[float]) -> str:
    return "—" if value is None else f"{value:.1f}\u03c3"


def _separation_table(classification: PromotionClassification) -> str:
    """Per-level verdicts — the evidence behind an inferred promotion rate."""
    if not classification.levels:
        return ""

    header = (
        "| Level | Exposure | Verdict | Est. rate | Ordinary raise | "
        "Promotion raise | Separation | BIC gain |\n"
        "|---:|---:|---|---:|---:|---:|---:|---:|"
    )

    def cell(value: Optional[float], fmt: str) -> str:
        return "—" if value is None else format(value, fmt)

    rows = []
    for level in classification.levels:
        verdict = "separated" if level.separated else "**not separated**"
        rows.append(
            f"| {level.level_id} | {level.exposure:,.0f} | {verdict} | "
            f"{cell(level.estimated_rate, '.4f')} | "
            f"{cell(level.ordinary_location, '.1%')} | "
            f"{cell(level.promotion_location, '.1%')} | "
            f"{_distance(level.standardized_distance)} | "
            f"{cell(level.bic_improvement, '+,.0f')} |"
        )

    notes = "\n".join(
        f"- Level {level.level_id}: {level.reason}."
        for level in classification.levels
        if not level.separated
    )
    table = "\n".join([header, *rows])
    return (
        f"### Level-by-level separation\n\n{table}\n\n{notes}\n"
        if notes
        else (f"### Level-by-level separation\n\n{table}\n")
    )
