"""Map one aggregate query row into strict cited evidence entities."""

from __future__ import annotations

from decimal import Decimal
from typing import Mapping

from planalign_ensemble.models import METRIC_REGISTRY

from .models import (
    Citation,
    DriverContribution,
    EvidenceFigure,
    MetricChange,
    PackWarning,
    PopulationEvidence,
    Residual,
    reconciliation_quantum,
)
from .queries import DRIVER_REGISTRY

_UNDEFINED_FACTOR = "Retained compensation is zero at one or both endpoints, so the effective payout-rate factors are undefined."


def canonical_decimal(value: object) -> str:
    """Return a finite, non-exponent decimal string without insignificant zeros."""
    decimal = value if isinstance(value, Decimal) else Decimal(str(value))
    rendered = format(decimal, "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return "0" if rendered in {"-0", ""} else rendered


def decompose_row(
    metric: str,
    base_year: int,
    target_year: int,
    row: Mapping[str, object],
    *,
    query: str,
    result_store: str,
) -> tuple[
    MetricChange, tuple[DriverContribution, ...], Residual, tuple[PackWarning, ...]
]:
    """Construct ordered figures while preserving SQL NULL/undefined semantics."""
    unit = METRIC_REGISTRY[metric].unit
    suppression_reason = _suppression_reason(row)
    change = MetricChange(
        metric=metric,
        label=METRIC_REGISTRY[metric].label,
        base_year=base_year,
        target_year=target_year,
        base_value=_defined(row["base_value"], unit, "base_value", query, result_store),
        target_value=_defined(
            row["target_value"], unit, "target_value", query, result_store
        ),
        total_change=_defined(
            row["total_change"], unit, "total_change", query, result_store
        ),
        base_population=_defined(
            row["base_population"],
            "count",
            "base_population",
            query,
            result_store,
        ),
        target_population=_defined(
            row["target_population"],
            "count",
            "target_population",
            query,
            result_store,
        ),
        shares_suppressed_reason=suppression_reason,
    )
    drivers = tuple(
        _driver(metric, definition, row, unit, suppression_reason, query, result_store)
        for definition in DRIVER_REGISTRY[metric]
    )
    residual_value = Decimal(str(row["residual_contribution"]))
    total_change = Decimal(str(row["total_change"]))
    quantum = reconciliation_quantum(unit)
    material = abs(residual_value) > max(quantum, abs(total_change) * Decimal("0.01"))
    named = [
        abs(Decimal(driver.contribution.value or "0"))
        for driver in drivers
        if driver.contribution.status == "defined"
    ]
    largest = residual_value != 0 and abs(residual_value) >= max(
        named, default=Decimal(0)
    )
    residual = Residual(
        contribution=_defined(
            residual_value, unit, "residual_contribution", query, result_store
        ),
        share_of_change=_share(
            row["residual_share"],
            "residual_share",
            suppression_reason,
            query,
            result_store,
        ),
        material=material,
        largest_contribution=largest,
    )
    warnings: list[PackWarning] = []
    if suppression_reason:
        warnings.append(
            PackWarning(
                code="shares_suppressed", severity="info", message=suppression_reason
            )
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
    return change, drivers, residual, tuple(warnings)


def _driver(metric, definition, row, unit, suppression_reason, query, result_store):
    contribution_column = f"{definition.id}_contribution"
    share_column = f"{definition.id}_share"
    population_column = f"{definition.id}_population"
    contribution = row[contribution_column]
    if contribution is None:
        contribution_figure = _unavailable(
            unit, contribution_column, _UNDEFINED_FACTOR, query, result_store
        )
        share = _unavailable(
            "percent_of_change", share_column, _UNDEFINED_FACTOR, query, result_store
        )
    else:
        contribution_figure = _defined(
            contribution, unit, contribution_column, query, result_store
        )
        share = _share(
            row[share_column], share_column, suppression_reason, query, result_store
        )
    rate_driver = "effective_" in definition.id and "payout_rate" in definition.id
    return DriverContribution(
        id=definition.id,
        label=definition.label,
        description=definition.description,
        contribution=contribution_figure,
        share_of_change=share,
        population=PopulationEvidence(
            label=definition.population_label,
            count=_defined(
                row[population_column], "count", population_column, query, result_store
            ),
        ),
        base_rate=(
            _defined(
                row["base_effective_rate"],
                "rate",
                "base_effective_rate",
                query,
                result_store,
            )
            if rate_driver
            else None
        ),
        target_rate=(
            _defined(
                row["target_effective_rate"],
                "rate",
                "target_effective_rate",
                query,
                result_store,
            )
            if rate_driver
            else None
        ),
    )


def build_executive_summary(
    change: MetricChange, drivers: tuple[DriverContribution, ...]
) -> tuple[str, ...]:
    """Explain the cited decomposition in concise, deterministic business terms."""
    base = Decimal(change.base_value.value or "0")
    target = Decimal(change.target_value.value or "0")
    delta = Decimal(change.total_change.value or "0")
    direction = (
        "increased" if delta > 0 else "decreased" if delta < 0 else "did not change"
    )
    percent = None if base == 0 else abs(delta / base * Decimal(100))
    movement = (
        f"{change.label} {direction} from {_display(base, change.base_value.unit)} "
        f"to {_display(target, change.target_value.unit)}, a change of "
        f"{_display(delta, change.total_change.unit, signed=True)}"
        + (f" ({percent.quantize(Decimal('0.01'))}%)." if percent is not None else ".")
    )
    base_population = Decimal(change.base_population.value or "0")
    target_population = Decimal(change.target_population.value or "0")
    population = (
        f"The endpoint population changed from {_display(base_population, 'count')} "
        f"to {_display(target_population, 'count')} "
        f"({_display(target_population - base_population, 'count', signed=True)})."
    )
    summary = [movement, population]
    entering = next((item for item in drivers if item.id.startswith("entered_")), None)
    leaving = next((item for item in drivers if item.id.startswith("left_")), None)
    if (
        entering
        and leaving
        and entering.contribution.value
        and leaving.contribution.value
    ):
        net = Decimal(entering.contribution.value) + Decimal(leaving.contribution.value)
        summary.append(
            "Net entering/leaving population effect: "
            f"{_display(net, change.total_change.unit, signed=True)}."
        )
    rate_driver = next((item for item in drivers if item.base_rate is not None), None)
    exposure = next(
        (item for item in drivers if item.id == "retained_compensation_exposure"),
        None,
    )
    if (
        rate_driver
        and exposure
        and rate_driver.contribution.value
        and exposure.contribution.value
        and rate_driver.base_rate
        and rate_driver.target_rate
        and rate_driver.base_rate.value
        and rate_driver.target_rate.value
    ):
        summary.append(
            "For retained records, compensation exposure contributed "
            f"{_display(Decimal(exposure.contribution.value), change.total_change.unit, signed=True)}; "
            "the effective payout-rate change contributed "
            f"{_display(Decimal(rate_driver.contribution.value), change.total_change.unit, signed=True)}. "
            "The effective retained payout rate changed from "
            f"{_display(Decimal(rate_driver.base_rate.value), 'rate')} to "
            f"{_display(Decimal(rate_driver.target_rate.value), 'rate')}."
        )
    if any(
        item.share_of_change.value is not None
        and abs(Decimal(item.share_of_change.value)) > 100
        for item in drivers
    ):
        summary.append(
            "Shares above 100% indicate a gross driver that was offset by one or more negative drivers; signed shares still reconcile to 100%."
        )
    return tuple(summary)


def _display(value: Decimal, unit: str, *, signed: bool = False) -> str:
    sign = "+" if signed and value > 0 else ""
    if unit == "currency":
        return f"{sign}${value:,.2f}" if value >= 0 else f"-${abs(value):,.2f}"
    if unit == "rate":
        percent = value * 100
        return f"{sign}{percent:,.2f}%"
    if unit == "count":
        return f"{sign}{value:,.0f}"
    return f"{sign}{value:,.2f}%"


def _citation(result_store: str, query: str, column: str) -> Citation:
    return Citation(result_store=result_store, query=query, result_column=column)


def _defined(value, unit, column, query, result_store):
    if value is None:
        return _unavailable(
            unit,
            column,
            "The canonical endpoint has no supported population.",
            query,
            result_store,
        )
    return EvidenceFigure(
        value=canonical_decimal(value),
        unit=unit,
        status="defined",
        reason=None,
        citation=_citation(result_store, query, column),
    )


def _unavailable(unit, column, reason, query, result_store):
    return EvidenceFigure(
        value=None,
        unit=unit,
        status="undefined",
        reason=reason,
        citation=_citation(result_store, query, column),
    )


def _share(value, column, suppression_reason, query, result_store):
    if suppression_reason:
        return EvidenceFigure(
            value=None,
            unit="percent_of_change",
            status="suppressed",
            reason=suppression_reason,
            citation=_citation(result_store, query, column),
        )
    return _defined(value, "percent_of_change", column, query, result_store)


def _suppression_reason(row: Mapping[str, object]) -> str | None:
    base = Decimal(str(row["base_value"]))
    target = Decimal(str(row["target_value"]))
    if base * target < 0:
        return "Shares are suppressed because the endpoints cross zero."
    if row[next(key for key in row if key.endswith("_share"))] is None:
        return "Shares are suppressed because the total change is zero or near zero."
    return None


__all__ = ["build_executive_summary", "canonical_decimal", "decompose_row"]
