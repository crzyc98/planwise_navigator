"""Symmetric aggregate decomposition across two independent scenarios."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Callable, Mapping

from planalign_ensemble.models import METRIC_REGISTRY

from .cross_models import (
    CROSS_DRIVER_IDS,
    CrossCitation,
    CrossScenarioDriverContribution,
    CrossScenarioFigure,
    CrossScenarioMetricChange,
    CrossScenarioPopulationEvidence,
    CrossScenarioResidual,
)
from .decompose import canonical_decimal
from .models import PackWarning, reconciliation_quantum


@dataclass(frozen=True)
class CrossDriverDef:
    id: str
    label: str
    description: str
    population_label: str
    column: str = "value"


CROSS_DRIVER_REGISTRY: dict[str, tuple[CrossDriverDef, ...]] = {
    "active_headcount": (
        CrossDriverDef(
            "population_difference",
            "Population difference",
            "Active headcount difference between the two scenarios at the selected year.",
            "active records",
        ),
    ),
    "total_compensation": (
        CrossDriverDef(
            "population_effect",
            "Population size effect",
            "Effect of the two scenarios having different total record counts, holding the average value fixed.",
            "all records",
        ),
        CrossDriverDef(
            "average_value_effect",
            "Average value effect",
            "Effect of the two scenarios having different average compensation, holding population size fixed.",
            "all records",
        ),
    ),
    "employer_match_cost": (
        CrossDriverDef(
            "compensation_exposure_effect",
            "Compensation exposure effect",
            "Effect of the two scenarios having different total compensation exposure, holding the effective match rate fixed.",
            "all records",
        ),
        CrossDriverDef(
            "effective_payout_rate_effect",
            "Effective match payout rate effect",
            "Effect of the two scenarios having a different realized match-to-compensation rate, holding compensation exposure fixed.",
            "all records",
        ),
    ),
    "total_employer_plan_cost": (
        CrossDriverDef(
            "employer_match_difference",
            "Employer match",
            "Difference in total employer match contributions between the two scenarios.",
            "all records",
            "match_value",
        ),
        CrossDriverDef(
            "employer_core_difference",
            "Employer core contribution",
            "Difference in total employer core (non-elective) contributions between the two scenarios.",
            "all records",
            "core_value",
        ),
    ),
    "participation_rate": (
        CrossDriverDef(
            "rate_difference",
            "Participation rate difference",
            "Participation rate difference between the two scenarios at the selected year.",
            "all records",
        ),
    ),
    "avg_deferral_rate": (
        CrossDriverDef(
            "rate_difference",
            "Average deferral rate difference",
            "Average deferral rate difference between the two scenarios at the selected year, among records with a non-null deferral rate.",
            "records with a non-null deferral rate",
        ),
    ),
}
assert {
    key: tuple(d.id for d in definitions)
    for key, definitions in CROSS_DRIVER_REGISTRY.items()
} == CROSS_DRIVER_IDS


def _citation(store: str, query: str, query_id: str, column: str) -> CrossCitation:
    return CrossCitation(
        result_store=store, query=query, query_id=query_id, result_column=column
    )


def _figure(
    value: Decimal | None,
    unit: str,
    citations: tuple[CrossCitation, ...],
    reason: str | None = None,
    status: str = "defined",
) -> CrossScenarioFigure:
    return CrossScenarioFigure(
        value=canonical_decimal(value) if value is not None else None,
        unit=unit,
        status=status,
        reason=reason,
        citations=citations,
    )


def _share(
    value: Decimal | None,
    total: Decimal,
    citations: tuple[CrossCitation, ...],
    suppression: str | None,
    undefined: str | None = None,
) -> CrossScenarioFigure:
    if undefined:
        return _figure(None, "percent_of_change", citations, undefined, "undefined")
    if suppression:
        return _figure(None, "percent_of_change", citations, suppression, "suppressed")
    assert value is not None
    return _figure(value * 100 / total, "percent_of_change", citations)


def _factor_values(
    metric: str, a: Mapping[str, object], b: Mapping[str, object], total: Decimal
) -> tuple[tuple[Decimal | None, ...], str | None, tuple[Decimal, Decimal] | None]:
    if metric in {"active_headcount", "participation_rate", "avg_deferral_rate"}:
        return (total,), None, None
    if metric == "total_compensation":
        n0, n1 = Decimal(str(a["population"])), Decimal(str(b["population"]))
        if n0 == 0 or n1 == 0:
            return (
                (None, None),
                "One or both scenarios have zero records at this year, so the population and average-value factors are undefined.",
                None,
            )
        avg0, avg1 = Decimal(str(a["value"])) / n0, Decimal(str(b["value"])) / n1
        return (
            ((n1 - n0) * (avg0 + avg1) / 2, (avg1 - avg0) * (n0 + n1) / 2),
            None,
            None,
        )
    if metric == "total_employer_plan_cost":
        return _component_values(a, b)
    c0, c1 = Decimal(str(a["compensation_base"])), Decimal(str(b["compensation_base"]))
    if c0 == 0 or c1 == 0:
        return (
            (None, None),
            "Compensation exposure is zero in one or both scenarios, so the effective payout-rate factors are undefined.",
            None,
        )
    rate0, rate1 = Decimal(str(a["value"])) / c0, Decimal(str(b["value"])) / c1
    return (
        ((c1 - c0) * (rate0 + rate1) / 2, (rate1 - rate0) * (c0 + c1) / 2),
        None,
        (rate0, rate1),
    )


def _component_values(
    a: Mapping[str, object], b: Mapping[str, object]
) -> tuple[tuple[Decimal | None, ...], str | None, None]:
    """Split plan cost into its match and core contribution components."""
    parts = (a["match_value"], b["match_value"], a["core_value"], b["core_value"])
    if any(part is None for part in parts):
        return (
            (None, None),
            "Employer match or core amounts are unavailable in one or both results, so the plan cost cannot be split by component.",
            None,
        )
    match_a, match_b, core_a, core_b = (Decimal(str(part)) for part in parts)
    return (match_b - match_a, core_b - core_a), None, None


def _suppression(base: Decimal, target: Decimal, unit: str) -> str | None:
    if base * target < 0:
        return "Shares are suppressed because the two scenario endpoints cross zero."
    if abs(target - base) <= reconciliation_quantum(unit):
        return "Shares are suppressed because the total change is zero or near zero."
    return None


def _warnings(
    suppression: str | None, material: bool, largest: bool
) -> tuple[PackWarning, ...]:
    warnings = []
    if suppression:
        warnings.append(
            PackWarning(code="shares_suppressed", severity="info", message=suppression)
        )
    if material:
        warnings.append(
            PackWarning(
                code="material_residual",
                severity="caution",
                message="Caution: a material portion of the movement is unexplained.",
            )
        )
    if largest:
        warnings.append(
            PackWarning(
                code="residual_dominates",
                severity="critical",
                message="The named drivers do not explain this movement.",
            )
        )
    return tuple(warnings)


def decompose_cross_scenario(
    metric: str,
    year: int,
    scenario_a_id: str,
    scenario_b_id: str,
    row_a: Mapping[str, object],
    row_b: Mapping[str, object],
    *,
    query_a: str,
    query_b: str,
    result_store_a: str,
    result_store_b: str,
) -> tuple[
    CrossScenarioMetricChange,
    tuple[CrossScenarioDriverContribution, ...],
    CrossScenarioResidual,
    tuple[PackWarning, ...],
]:
    unit = METRIC_REGISTRY[metric].unit
    qa = (_citation(result_store_a, query_a, "QA", "value"),)
    qb = (_citation(result_store_b, query_b, "QB", "value"),)
    both = qa + qb
    a, b = Decimal(str(row_a["value"])), Decimal(str(row_b["value"]))
    total = b - a
    suppression = _suppression(a, b, unit)
    count_a = _figure(
        Decimal(str(row_a["population"])),
        "count",
        (_citation(result_store_a, query_a, "QA", "population"),),
    )
    count_b = _figure(
        Decimal(str(row_b["population"])),
        "count",
        (_citation(result_store_b, query_b, "QB", "population"),),
    )
    change = CrossScenarioMetricChange(
        metric=metric,
        label=METRIC_REGISTRY[metric].label,
        year=year,
        scenario_a_id=scenario_a_id,
        scenario_b_id=scenario_b_id,
        value_a=_figure(a, unit, qa),
        value_b=_figure(b, unit, qb),
        total_change=_figure(total, unit, both),
        population_a=count_a,
        population_b=count_b,
        shares_suppressed_reason=suppression,
    )
    values, undefined, rates = _factor_values(metric, row_a, row_b, total)
    context = _DriverContext(
        unit=unit,
        total=total,
        cite=lambda column: (
            _citation(result_store_a, query_a, "QA", column),
            _citation(result_store_b, query_b, "QB", column),
        ),
        count_a=count_a,
        count_b=count_b,
        suppression=suppression,
        undefined=undefined,
        rates=rates,
        rate_citations=(
            (qa[0], _citation(result_store_a, query_a, "QA", "compensation_base")),
            (qb[0], _citation(result_store_b, query_b, "QB", "compensation_base")),
        ),
    )
    drivers = tuple(
        _make_driver(definition, value, context)
        for definition, value in zip(CROSS_DRIVER_REGISTRY[metric], values, strict=True)
    )
    residual_value = total - sum((v for v in values if v is not None), Decimal(0))
    material = abs(residual_value) > max(
        reconciliation_quantum(unit), abs(total) * Decimal("0.01")
    )
    named = [abs(v) for v in values if v is not None]
    largest = residual_value != 0 and abs(residual_value) >= max(
        named, default=Decimal(0)
    )
    residual = CrossScenarioResidual(
        contribution=_figure(residual_value, unit, both),
        share_of_change=_share(residual_value, total, both, suppression),
        material=material,
        largest_contribution=largest,
    )
    return change, drivers, residual, _warnings(suppression, material, largest)


@dataclass(frozen=True)
class _DriverContext:
    """Figures shared by every driver of one cross-scenario decomposition."""

    unit: str
    total: Decimal
    cite: Callable[[str], tuple[CrossCitation, CrossCitation]]
    count_a: CrossScenarioFigure
    count_b: CrossScenarioFigure
    suppression: str | None
    undefined: str | None
    rates: tuple[Decimal, Decimal] | None
    rate_citations: tuple[tuple[CrossCitation, ...], tuple[CrossCitation, ...]]


def _make_driver(
    definition: CrossDriverDef, value: Decimal | None, ctx: _DriverContext
) -> CrossScenarioDriverContribution:
    rate_pair = ctx.rates if definition.id == "effective_payout_rate_effect" else None
    status = "undefined" if ctx.undefined else "defined"
    citations = ctx.cite(definition.column)
    rate_a_cites, rate_b_cites = ctx.rate_citations
    return CrossScenarioDriverContribution(
        id=definition.id,
        label=definition.label,
        description=definition.description,
        contribution=_figure(value, ctx.unit, citations, ctx.undefined, status),
        share_of_change=_share(
            value, ctx.total, citations, ctx.suppression, ctx.undefined
        ),
        population=CrossScenarioPopulationEvidence(
            label=definition.population_label, count_a=ctx.count_a, count_b=ctx.count_b
        ),
        rate_a=_figure(rate_pair[0], "rate", rate_a_cites) if rate_pair else None,
        rate_b=_figure(rate_pair[1], "rate", rate_b_cites) if rate_pair else None,
    )


def _display(value: Decimal, unit: str, signed: bool = False) -> str:
    sign = "+" if signed and value > 0 else ""
    if unit == "currency":
        return f"{sign}${value:,.2f}" if value >= 0 else f"-${abs(value):,.2f}"
    if unit == "rate":
        return f"{sign}{value*100:,.2f}%"
    return f"{sign}{value:,.0f}"


def build_cross_executive_summary(
    change: CrossScenarioMetricChange,
    drivers: tuple[CrossScenarioDriverContribution, ...],
    name_a: str,
    name_b: str,
) -> tuple[str, ...]:
    a = Decimal(change.value_a.value or "0")
    b = Decimal(change.value_b.value or "0")
    delta = Decimal(change.total_change.value or "0")
    unit = change.total_change.unit
    values = (
        f"{change.label}: {name_a} (A) {_display(a, change.value_a.unit)}, "
        f"{name_b} (B) {_display(b, change.value_b.unit)}."
    )
    if delta == 0:
        comparison = " The scenarios are equal."
    else:
        direction = "higher" if delta > 0 else "lower"
        percent = f" ({abs(delta / a * 100):.2f}%)" if a else ""
        comparison = (
            f" {name_b} is {direction} by {_display(abs(delta), unit)}{percent}."
        )
    sentences = [values + comparison]
    sentences.extend(
        f"{driver.label}: {_display(Decimal(driver.contribution.value), change.total_change.unit, True)}."
        for driver in drivers
        if driver.contribution.value is not None
    )
    return tuple(sentences)


__all__ = [
    "CROSS_DRIVER_REGISTRY",
    "CrossDriverDef",
    "build_cross_executive_summary",
    "decompose_cross_scenario",
]
