"""Deterministic self-contained Markdown renderer for cross-scenario evidence packs."""

from __future__ import annotations

import re
from collections.abc import Iterator

from .cross_models import (
    ConfigDifference,
    CrossScenarioEvidencePack,
    CrossScenarioEvidencePackEnvelope,
    CrossScenarioFigure,
)
from .models import PackProvenance
from .render import format_figure, human_value

_STATUS_LABELS = {"changed": "Changed", "only_a": "Only in A", "only_b": "Only in B"}


def _cite(figure: CrossScenarioFigure) -> str:
    return ", ".join(f"`{c.query_id}.{c.result_column}`" for c in figure.citations)


def _provenance(label: str, provenance: PackProvenance) -> list[str]:
    timestamp = provenance.run_timestamp
    seed = provenance.random_seed
    return [
        f"### {label}: {provenance.scenario_name or provenance.scenario_id} (`{provenance.scenario_id}`)",
        "",
        f"- Run ID: `{provenance.run_id}`",
        f"- Run timestamp: {timestamp.isoformat() if timestamp else 'Unavailable'}",
        f"- Random seed: {seed if seed is not None else 'Unavailable'}",
        f"- Configuration fingerprint: `{provenance.config_fingerprint or 'Unavailable'}`",
        f"- Result store: `{provenance.result_store}`",
        f"- Verification: {provenance.verification_disposition}",
        "",
    ]


def _config_rows(differences: tuple[ConfigDifference, ...]) -> list[str]:
    if not differences:
        return ["No effective configuration differences between the selected runs."]
    rows = ["| Path | Scenario A | Scenario B | Status |", "| --- | --- | --- | --- |"]
    for item in differences:
        value_a = "—" if item.value_a is None else f"`{item.value_a}`"
        value_b = "—" if item.value_b is None else f"`{item.value_b}`"
        rows.append(
            f"| `{item.path}` | {value_a} | {value_b} | {_STATUS_LABELS[item.status]} |"
        )
    return rows


def _driver_rows(pack: CrossScenarioEvidencePack) -> list[str]:
    rows = [
        "| Driver | Contribution | Share of difference | Population (A / B) | Citation |",
        "| --- | ---: | ---: | --- | --- |",
    ]
    for driver in pack.drivers:
        rate_context = ""
        if driver.rate_a is not None and driver.rate_b is not None:
            rate_context = (
                f"<br>Effective payout rate: {format_figure(driver.rate_a)} (A) vs "
                f"{format_figure(driver.rate_b)} (B)"
            )
        population = driver.population
        rows.append(
            f"| {driver.label}{rate_context} | {format_figure(driver.contribution)} | "
            f"{format_figure(driver.share_of_change)} | {human_value(population.count_a)} / "
            f"{human_value(population.count_b)} {population.label} | {_cite(driver.contribution)} |"
        )
    return rows


def _figure_mappings(
    pack: CrossScenarioEvidencePack,
) -> Iterator[tuple[str, CrossScenarioFigure]]:
    change = pack.change
    yield "Scenario A value", change.value_a
    yield "Scenario B value", change.value_b
    yield "Difference", change.total_change
    yield "Scenario A population", change.population_a
    yield "Scenario B population", change.population_b
    for driver in pack.drivers:
        yield f"{driver.label} contribution", driver.contribution
        if driver.rate_a is not None and driver.rate_b is not None:
            yield f"{driver.label} scenario A effective rate", driver.rate_a
            yield f"{driver.label} scenario B effective rate", driver.rate_b
    yield "Residual contribution", pack.residual.contribution


def _difference_lines(pack: CrossScenarioEvidencePack) -> list[str]:
    change = pack.change
    lines = [
        "## Difference",
        "",
        f"- Scenario A: {format_figure(change.value_a)}",
        f"- Scenario B: {format_figure(change.value_b)}",
        f"- Difference (B − A): {format_figure(change.total_change)}",
        f"- Scenario A population: **{human_value(change.population_a)}** (`QA.population`)",
        f"- Scenario B population: **{human_value(change.population_b)}** (`QB.population`)",
    ]
    if change.shares_suppressed_reason:
        lines.append(f"- Share treatment: {change.shares_suppressed_reason}")
    return lines


def _residual_lines(pack: CrossScenarioEvidencePack) -> list[str]:
    lines = [
        "## Residual",
        "",
        f"- Amount: {format_figure(pack.residual.contribution)}",
        f"- Share: {format_figure(pack.residual.share_of_change)}",
    ]
    if pack.residual.material:
        lines.append("- Caution: a material portion of the difference is unexplained.")
    if pack.residual.largest_contribution:
        lines.append("- The named drivers do not explain this difference.")
    return lines


def _citation_lines(pack: CrossScenarioEvidencePack) -> list[str]:
    lines = ["## Citations", ""]
    for query_id, label, provenance, figure in (
        ("QA", "Scenario A", pack.provenance_a, pack.change.value_a),
        ("QB", "Scenario B", pack.provenance_b, pack.change.value_b),
    ):
        lines.extend(
            [
                f"{query_id} ({label}) — result store `{provenance.result_store}`:",
                "",
                "```sql",
                figure.citations[0].query,
                "```",
                "",
            ]
        )
    lines.append("Figure mappings:")
    lines.extend(
        f"- {label}: {_cite(figure)}" for label, figure in _figure_mappings(pack)
    )
    return lines


def render_cross_evidence_pack(pack: CrossScenarioEvidencePack) -> str:
    """Render canonical UTF-8/LF Markdown citing one query per scenario."""
    warnings = [
        f"- **{w.severity.title()} — {w.code}:** {w.message}" for w in pack.warnings
    ] or ["None"]
    sections = [
        [f"# Cross-Scenario Evidence Pack: {pack.change.label}, {pack.change.year}"],
        [
            "## Provenance",
            "",
            *_provenance("Scenario A", pack.provenance_a),
            *_provenance("Scenario B", pack.provenance_b),
        ][:-1],
        ["## Warnings", "", *warnings],
        [
            "## Executive interpretation",
            "",
            *(f"- {s}" for s in pack.executive_summary),
        ],
        ["## Configuration differences", "", *_config_rows(pack.config_differences)],
        _difference_lines(pack),
        ["## Driver decomposition", "", *_driver_rows(pack)],
        _residual_lines(pack),
        ["## Population treatment", "", pack.population_note],
        _citation_lines(pack),
    ]
    return "\n\n".join("\n".join(section) for section in sections).rstrip("\n") + "\n"


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")[:60].strip("-")
    return slug or "scenario"


def build_cross_envelope(
    pack: CrossScenarioEvidencePack,
) -> CrossScenarioEvidencePackEnvelope:
    change = pack.change
    name_a = pack.provenance_a.scenario_name or change.scenario_a_id
    name_b = pack.provenance_b.scenario_name or change.scenario_b_id
    filename = (
        f"evidence-pack-{_slug(name_a)}-vs-{_slug(name_b)}"
        f"-{change.metric}-{change.year}.md"
    )
    return CrossScenarioEvidencePackEnvelope(
        pack=pack, text_export=render_cross_evidence_pack(pack), filename=filename
    )


__all__ = ["build_cross_envelope", "render_cross_evidence_pack"]
