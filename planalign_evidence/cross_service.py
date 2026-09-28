"""Read two independent result stores and assemble a cross-scenario pack."""

from __future__ import annotations

from typing import Sequence

from planalign_ensemble.models import METRIC_REGISTRY

from .cross_decompose import build_cross_executive_summary, decompose_cross_scenario
from .cross_models import ConfigDifference, CrossScenarioEvidencePack
from .cross_queries import build_scenario_aggregate_query
from .models import PackProvenance, PackWarning
from .service import (
    EvidenceConflictError,
    EvidenceNotFoundError,
    EvidenceTarget,
    TargetSupport,
    UnsupportedEvidenceError,
    _read_provenance,
)


def _inspect_side(
    target: EvidenceTarget, metric: str, year: int, side: str
) -> tuple[tuple[int, int], TargetSupport]:
    before = target.signature()
    support = target.inspect()
    missing = tuple(
        column
        for column in METRIC_REGISTRY[metric].required_columns
        if column not in support.columns
    )
    if missing:
        raise UnsupportedEvidenceError(
            f"Metric {metric} is unavailable for {side}; missing columns: {', '.join(missing)}",
            available_years=support.available_years,
            missing_columns=missing,
        )
    if year not in support.available_years:
        available = ", ".join(map(str, support.available_years)) or "none"
        raise UnsupportedEvidenceError(
            f"Requested year {year} is unavailable for {side}; available years: {available}",
            available_years=support.available_years,
        )
    return before, support


def _run_side_query(
    target: EvidenceTarget, query: str, provenance: PackProvenance | None
) -> tuple[dict[str, object], PackProvenance]:
    with target.connect() as connection:
        cursor = connection.execute(query)
        values = cursor.fetchone()
        assert values is not None
        description = cursor.description
        assert description is not None
        row = dict(zip((item[0] for item in description), values, strict=True))
        resolved = provenance or _read_provenance(connection, target)
    return row, resolved


def _comparability_warnings(
    a: PackProvenance, b: PackProvenance
) -> tuple[PackWarning, ...]:
    """Flag differences that stochastic simulation noise, not config, may explain."""
    if a.random_seed is None or b.random_seed is None:
        return (
            PackWarning(
                code="scenario_seed_mismatch",
                severity="info",
                message="A random seed is not recorded for one or both scenarios, so part of the "
                "difference may be simulation noise rather than configuration.",
            ),
        )
    if a.random_seed != b.random_seed:
        return (
            PackWarning(
                code="scenario_seed_mismatch",
                severity="caution",
                message=f"The scenarios ran with different random seeds ({a.random_seed} vs "
                f"{b.random_seed}), so part of the difference is simulation noise "
                "rather than configuration.",
            ),
        )
    return ()


def _warning_key(warning: PackWarning) -> tuple[int, str]:
    severity = {"critical": 0, "caution": 1, "info": 2}
    return severity[warning.severity], warning.code


def build_cross_scenario_evidence_pack(
    target_a: EvidenceTarget,
    target_b: EvidenceTarget,
    metric: str,
    year: int,
    *,
    config_differences: Sequence[ConfigDifference] = (),
    provenance_a: PackProvenance | None = None,
    provenance_b: PackProvenance | None = None,
    warnings: Sequence[PackWarning] = (),
) -> CrossScenarioEvidencePack:
    """Read each scenario on its own connection and reconcile aggregate totals."""
    if metric not in METRIC_REGISTRY:
        raise UnsupportedEvidenceError(
            f"Unsupported metric {metric}; available metrics: {', '.join(METRIC_REGISTRY)}"
        )
    if target_a.scenario_id == target_b.scenario_id:
        raise UnsupportedEvidenceError("Select two distinct scenarios")
    before_a, support_a = _inspect_side(target_a, metric, year, "scenario_a")
    before_b, support_b = _inspect_side(target_b, metric, year, "scenario_b")
    query_a = build_scenario_aggregate_query(metric, year, support_a.columns)
    query_b = build_scenario_aggregate_query(metric, year, support_b.columns)
    row_a, resolved_a = _run_side_query(target_a, query_a, provenance_a)
    row_b, resolved_b = _run_side_query(target_b, query_b, provenance_b)
    if target_a.signature() != before_a or target_b.signature() != before_b:
        raise EvidenceConflictError(
            "Result store changed during the read-only evidence request"
        )
    if row_a["value"] is None or row_b["value"] is None:
        raise UnsupportedEvidenceError(
            f"Metric {metric} has an undefined population for scenario_a or scenario_b at {year}",
            available_years=support_a.available_years,
        )
    change, drivers, residual, arithmetic_warnings = decompose_cross_scenario(
        metric,
        year,
        target_a.scenario_id,
        target_b.scenario_id,
        row_a,
        row_b,
        query_a=query_a,
        query_b=query_b,
        result_store_a=target_a.result_store,
        result_store_b=target_b.result_store,
    )
    return CrossScenarioEvidencePack(
        provenance_a=resolved_a,
        provenance_b=resolved_b,
        config_differences=tuple(config_differences),
        change=change,
        drivers=drivers,
        residual=residual,
        warnings=tuple(
            sorted(
                (
                    *warnings,
                    *_comparability_warnings(resolved_a, resolved_b),
                    *arithmetic_warnings,
                ),
                key=_warning_key,
            )
        ),
        executive_summary=build_cross_executive_summary(
            change,
            drivers,
            resolved_a.scenario_name or resolved_a.scenario_id,
            resolved_b.scenario_name or resolved_b.scenario_id,
        ),
        population_note="Canonical snapshot populations include all rows for compensation, employer cost, and participation; average deferral rate excludes null-deferral rows; only active headcount filters employment status. Each scenario's aggregate is computed independently from its own result store — no employee-level record is matched or compared across scenarios.",
    )


__all__ = ["EvidenceNotFoundError", "build_cross_scenario_evidence_pack"]
