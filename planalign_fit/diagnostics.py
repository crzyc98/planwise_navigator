"""Machine-readable fit diagnostics — the ``diagnostics.json`` twin of the report.

``fit_report.md`` is written for a reader; Studio needs the same evidence as
data (#588): every fitted value with its prior, exposure, credibility, and
basis, grouped the way the report groups them, plus the summary the CLI prints.
The record rides alongside the pack but is not part of its fingerprint — it
describes the fit, it does not change what a run consumes.
"""

from __future__ import annotations

import math
from typing import Any, Optional

from planalign_fit.models import (
    FitResult,
    FittedValue,
    PromotionBasis,
    PromotionClassification,
)
from planalign_fit.runner import FitRun

DIAGNOSTICS_VERSION = 1
THIN_BASES = frozenset({"pooled", "prior"})


def build_diagnostics(run: FitRun) -> dict[str, Any]:
    """Everything Studio shows about a fit, as JSON-safe data."""
    result = run.result
    groups = _grouped_values(result)
    rows = [row for values in groups.values() for row in values]
    classification = result.promotion_classification
    return _json_safe(
        {
            "version": DIAGNOSTICS_VERSION,
            "summary": {
                "snapshot_years": list(run.snapshot_set.years),
                "linked_employees": int(result.diagnostics.get("linked_pairs", 0)),
                "fitted_count": len(rows),
                "thin_count": sum(1 for row in rows if row["thin"]),
                "promotion_basis": _basis_value(classification),
                "promotion_basis_label": promotion_basis_label(classification),
                "unfittable_count": len(result.unfittable),
                "warning_count": len(result.warnings),
            },
            "groups": groups,
            "unfittable": [item.to_dict() for item in result.unfittable],
            "warnings": list(result.warnings),
            "promotion_classification": (
                classification.to_dict() if classification is not None else None
            ),
            "counts": dict(result.diagnostics),
        }
    )


def promotion_basis_label(classification: Optional[PromotionClassification]) -> str:
    """How this fit learned its promotion rate, in one line (#511)."""
    if classification is None or classification.basis is PromotionBasis.NOT_FITTED:
        return "not fitted — default retained"
    if classification.basis is PromotionBasis.MEASURED:
        return f"measured from level_id (coverage {classification.level_coverage:.0%})"
    separated = sum(1 for level in classification.levels if level.separated)
    share = classification.separated_exposure_share or 0.0
    return (
        f"estimated from raise distribution ({separated} of "
        f"{len(classification.levels)} levels, {share:.0%} of exposure)"
    )


def _basis_value(classification: Optional[PromotionClassification]) -> str:
    if classification is None:
        return PromotionBasis.NOT_FITTED.value
    return classification.basis.value


def _grouped_values(result: FitResult) -> dict[str, list[dict[str, Any]]]:
    candidates: dict[str, list[FittedValue]] = {
        "termination": result.termination.values() if result.termination else [],
        "promotion": result.promotion.values() if result.promotion else [],
        "merit": list(result.merit_by_level.values()),
        "deferral": list(result.deferral_rates.values()),
        "config": list(result.config_overrides.values()),
    }
    return {
        group: [_row(value) for value in values]
        for group, values in candidates.items()
        if values
    }


def _row(value: FittedValue) -> dict[str, Any]:
    row = value.to_dict()
    row["thin"] = value.basis in THIN_BASES
    row["moved_pct"] = value.moved_pct
    return row


def _json_safe(value: Any) -> Any:
    """Replace NaN/inf with ``None`` so the record is strict JSON."""
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
