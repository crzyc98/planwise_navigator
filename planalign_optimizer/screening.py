"""Experimental screening policy for paired benchmarks, not production search."""

from __future__ import annotations

import hashlib
import math
from collections.abc import Sequence

from pydantic import BaseModel, ConfigDict, Field

from .models import Candidate, ObjectiveConstraintSpec


class ScreeningPolicy(BaseModel):
    """Conservative constraint filter with deterministic rejected-point audits."""

    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    relative_margin: float = Field(default=0.05, ge=0, le=1)
    audit_fraction: float = Field(default=0.10, gt=0, le=1)


def select_for_validation(
    candidates: Sequence[Candidate],
    spec: ObjectiveConstraintSpec,
    policy: ScreeningPolicy,
    *,
    seed: int,
) -> dict[str, str]:
    """Return retained IDs and reasons independent of completion/input order.

    Feasible, unknown, and near-boundary results always proceed. A violation
    is only a screening signal, never proof of full-horizon infeasibility.
    """
    selected: dict[str, str] = {}
    rejected: list[str] = []
    for candidate in candidates:
        if candidate.is_duplicate_of is not None:
            continue
        reason = _retention_reason(candidate, spec, policy)
        if reason is None:
            rejected.append(candidate.candidate_id)
        else:
            selected[candidate.candidate_id] = reason
    audit_count = math.ceil(len(rejected) * policy.audit_fraction)
    rejected.sort(key=lambda identifier: _audit_key(identifier, seed))
    selected.update(
        {identifier: "audit_sample" for identifier in rejected[:audit_count]}
    )
    return dict(sorted(selected.items()))


def _retention_reason(
    candidate: Candidate, spec: ObjectiveConstraintSpec, policy: ScreeningPolicy
) -> str | None:
    if candidate.status in {"failed", "non_evaluable"}:
        return "uncertain_evidence"
    if candidate.status == "feasible":
        return "screen_feasible"
    if len(candidate.constraint_results) != len(spec.constraints):
        return "uncertain_evidence"
    for constraint, result in zip(spec.constraints, candidate.constraint_results):
        value = result.evaluated_value
        if (
            value is None
            or not math.isfinite(value)
            or not math.isfinite(constraint.threshold)
            or result.satisfied is None
            or result.metric != constraint.metric
        ):
            return "uncertain_evidence"
        if (
            constraint.percentile is not None
            or constraint.metric == "irs_compliance_pass"
        ):
            return "unsupported_screen_constraint"
        if not result.satisfied and abs(value - constraint.threshold) <= (
            abs(constraint.threshold) * policy.relative_margin
        ):
            return "near_constraint_boundary"
    return None


def _audit_key(identifier: str, seed: int) -> str:
    return hashlib.sha256(f"{seed}:{identifier}".encode()).hexdigest()
