"""Deterministic self-contained Markdown renderer for evidence packs."""

from __future__ import annotations

import re
from decimal import Decimal

from .models import EvidenceFigure, EvidencePack, EvidencePackEnvelope


def render_evidence_pack(pack: EvidencePack) -> str:
    """Render canonical UTF-8/LF Markdown with one deduplicated SQL query."""
    provenance = pack.provenance
    change = pack.change
    lines = [
        f"# Evidence Pack: {change.label}, {change.base_year} to {change.target_year}",
        "",
        "## Provenance",
        "",
        f"- Scenario: {provenance.scenario_name or provenance.scenario_id} (`{provenance.scenario_id}`)",
        f"- Run ID: `{provenance.run_id}`",
        f"- Run timestamp: {provenance.run_timestamp.isoformat() if provenance.run_timestamp else 'Unavailable'}",
        f"- Random seed: {provenance.random_seed if provenance.random_seed is not None else 'Unavailable'}",
        f"- Configuration fingerprint: `{provenance.config_fingerprint or 'Unavailable'}`",
        f"- Result store: `{provenance.result_store}`",
        f"- Verification: {provenance.verification_disposition}",
        "",
        "## Warnings",
        "",
    ]
    lines.extend(
        [
            f"- **{warning.severity.title()} — {warning.code}:** {warning.message}"
            for warning in pack.warnings
        ]
        or ["None"]
    )
    lines.extend(["", "## Executive interpretation", ""])
    lines.extend(f"- {item}" for item in pack.executive_summary)
    lines.extend(
        [
            "",
            "## Movement",
            "",
            f"- Base ({change.base_year}): {_figure(change.base_value)}",
            f"- Target ({change.target_year}): {_figure(change.target_value)}",
            f"- Total change: {_figure(change.total_change)}",
            f"- Base population: **{_human(change.base_population)}** (`Q1.base_population`)",
            f"- Target population: **{_human(change.target_population)}** (`Q1.target_population`)",
        ]
    )
    if change.shares_suppressed_reason:
        lines.append(f"- Share treatment: {change.shares_suppressed_reason}")
    lines.extend(
        [
            "",
            "## Driver decomposition",
            "",
            "| Driver | Contribution | Share of change | Population | Citation |",
            "| --- | ---: | ---: | --- | --- |",
        ]
    )
    for driver in pack.drivers:
        rate_context = ""
        if driver.base_rate is not None and driver.target_rate is not None:
            rate_context = (
                f"<br>Effective retained payout rate: {_figure(driver.base_rate)} → "
                f"{_figure(driver.target_rate)}"
            )
        lines.append(
            f"| {driver.label}{rate_context} | {_figure(driver.contribution)} | {_figure(driver.share_of_change)} | "
            f"{_figure(driver.population.count)} {driver.population.label} | `Q1.{driver.contribution.citation.result_column}` |"
        )
    lines.extend(
        [
            "",
            "## Residual",
            "",
            f"- Amount: {_figure(pack.residual.contribution)}",
            f"- Share: {_figure(pack.residual.share_of_change)}",
        ]
    )
    if pack.residual.material:
        lines.append("- Caution: a material portion of the movement is unexplained.")
    if pack.residual.largest_contribution:
        lines.append("- The named drivers do not explain this movement.")
    lines.extend(
        [
            "",
            "## Population treatment",
            "",
            pack.population_note,
            "",
            "## Citations",
            "",
            f"Result store: `{provenance.result_store}`",
            "",
            "```sql",
            pack.change.base_value.citation.query,
            "```",
            "",
            "Figure mappings:",
        ]
    )
    for label, figure in _figure_mappings(pack):
        lines.append(f"- {label}: `Q1.{figure.citation.result_column}`")
    return "\n".join(lines) + "\n"


def build_envelope(pack: EvidencePack) -> EvidencePackEnvelope:
    slug = (
        re.sub(r"[^A-Za-z0-9._-]+", "-", pack.provenance.scenario_id).strip("-")
        or "scenario"
    )
    filename = f"evidence-pack-{slug}-{pack.change.metric}-{pack.change.base_year}-{pack.change.target_year}.md"
    return EvidencePackEnvelope(
        pack=pack, text_export=render_evidence_pack(pack), filename=filename
    )


def _figure(figure: EvidenceFigure) -> str:
    if figure.status == "defined":
        human = _human(figure)
        canonical = str(figure.value)
        return (
            human if human == canonical else f"**{human}** (canonical: `{canonical}`)"
        )
    return f"{figure.status.title()} — {figure.reason}"


def _human(figure: EvidenceFigure) -> str:
    if figure.value is None:
        return figure.status.title()
    value = Decimal(figure.value)
    if figure.unit == "currency":
        return f"-${abs(value):,.2f}" if value < 0 else f"${value:,.2f}"
    if figure.unit == "count":
        return f"{value:,.0f}"
    if figure.unit == "rate":
        return f"{value * 100:,.2f}%"
    return f"{value:,.2f}%"


def _figure_mappings(pack: EvidencePack):
    yield "Base value", pack.change.base_value
    yield "Target value", pack.change.target_value
    yield "Total change", pack.change.total_change
    yield "Base population", pack.change.base_population
    yield "Target population", pack.change.target_population
    for driver in pack.drivers:
        yield f"{driver.label} contribution", driver.contribution
        yield f"{driver.label} share", driver.share_of_change
        yield f"{driver.label} population", driver.population.count
        if driver.base_rate is not None and driver.target_rate is not None:
            yield f"{driver.label} base effective rate", driver.base_rate
            yield f"{driver.label} target effective rate", driver.target_rate
    yield "Residual contribution", pack.residual.contribution
    yield "Residual share", pack.residual.share_of_change


__all__ = ["build_envelope", "render_evidence_pack"]
