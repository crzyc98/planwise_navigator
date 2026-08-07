"""Resolve, execute, and classify isolated optimizer candidates."""

from __future__ import annotations

import operator
from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path
from typing import Callable

from planalign_orchestrator.config import SimulationConfig, to_dbt_vars
from planalign_orchestrator.run_pool import JobResult

from .design_space import LEVER_REGISTRY
from .metrics import evaluate_constraint_metric, extract_point_metrics
from .models import (
    Candidate,
    ConstraintResult,
    ConstraintSpec,
    LeverSpec,
    LeverValue,
    ObjectiveConstraintSpec,
)

_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    "<=": operator.le,
    ">=": operator.ge,
    "<": operator.lt,
    ">": operator.gt,
    "==": operator.eq,
}


def resolve_candidate_config(
    baseline: SimulationConfig, lever_values: dict[str, LeverValue]
) -> tuple[SimulationConfig, dict[str, object]]:
    """Overlay declared levers on a deep copy and return the exported dbt delta."""
    payload = deepcopy(baseline.model_dump(mode="python"))
    for name, value in lever_values.items():
        try:
            path = LEVER_REGISTRY[name]
        except KeyError as exc:
            raise ValueError(f"unknown optimizer lever '{name}'") from exc
        _set_path(payload, path, value)
    candidate = SimulationConfig.model_validate(payload)
    before = to_dbt_vars(baseline)
    after = to_dbt_vars(candidate)
    delta = {
        key: after.get(key)
        for key in before.keys() | after.keys()
        if before.get(key) != after.get(key)
    }
    return candidate, delta


def validate_levers_against_baseline(
    baseline: SimulationConfig, levers: Sequence[LeverSpec]
) -> None:
    """Fail loudly, before any candidate run, if a declared lever cannot resolve.

    ``spec_io.validate_spec`` only checks that a lever name is registered; it
    cannot know whether the *resolved baseline* actually has the shape that
    name assumes (e.g. a tiered lever against a baseline whose active match
    formula has no ``tiers`` list). Probing every lever here, once, up front
    turns that into a clear spec-validation error instead of a mid-search
    crash that discards already-completed candidates.
    """
    payload = deepcopy(baseline.model_dump(mode="python"))
    errors: list[str] = []
    for lever in levers:
        try:
            path = LEVER_REGISTRY[lever.name]
        except KeyError:
            errors.append(f"unknown optimizer lever '{lever.name}'")
            continue
        probe_value = lever.choices[0] if lever.kind == "discrete" else lever.bounds[0]  # type: ignore[index]
        try:
            _set_path(deepcopy(payload), path, probe_value)
        except ValueError as exc:
            errors.append(
                f"lever '{lever.name}' cannot be resolved against the baseline "
                f"configuration: {exc}"
            )
    if errors:
        raise ValueError("; ".join(errors))


def classify_candidate(
    candidate_id: str,
    lever_values: dict[str, LeverValue],
    db_path: Path | None,
    spec: ObjectiveConstraintSpec,
    point_metrics: dict[str, float | None],
    *,
    ensemble_database: Path | None = None,
    failed: bool = False,
    duration_seconds: float = 0.0,
) -> Candidate:
    """Classify one terminal scenario outcome without fabricating missing values."""
    if failed:
        return Candidate(
            candidate_id=candidate_id,
            lever_values=lever_values,
            db_path=db_path,
            status="failed",
            duration_seconds=duration_seconds,
        )
    objective_values = {
        objective.metric: point_metrics.get(objective.metric)
        for objective in spec.objectives
    }
    constraint_results = tuple(
        _constraint_result(constraint, point_metrics, ensemble_database)
        for constraint in spec.constraints
    )
    missing = any(value is None for value in objective_values.values()) or any(
        result.satisfied is None for result in constraint_results
    )
    status = (
        "non_evaluable"
        if missing
        else "feasible"
        if all(result.satisfied for result in constraint_results)
        else "infeasible"
    )
    return Candidate(
        candidate_id=candidate_id,
        lever_values=lever_values,
        db_path=db_path,
        status=status,
        objective_values=objective_values,
        constraint_results=constraint_results,
        duration_seconds=duration_seconds,
    )


def candidate_from_job_result(
    candidate_id: str,
    lever_values: dict[str, LeverValue],
    db_path: Path,
    spec: ObjectiveConstraintSpec,
    result: JobResult,
    *,
    ensemble_database: Path | None = None,
) -> Candidate:
    """Translate a pool outcome into the optimizer's exhaustive status model."""
    if not result.succeeded or not db_path.exists():
        return classify_candidate(
            candidate_id,
            lever_values,
            db_path if db_path.exists() else None,
            spec,
            {},
            failed=True,
            duration_seconds=result.duration_seconds,
        )
    metrics = extract_point_metrics(db_path)
    return classify_candidate(
        candidate_id,
        lever_values,
        db_path,
        spec,
        metrics,
        ensemble_database=ensemble_database,
        duration_seconds=result.duration_seconds,
    )


def _constraint_result(
    constraint: ConstraintSpec,
    point_metrics: dict[str, float | None],
    ensemble_database: Path | None,
) -> ConstraintResult:
    value, mode = evaluate_constraint_metric(
        constraint, point_metrics, ensemble_database=ensemble_database
    )
    satisfied = (
        None
        if value is None
        else _OPERATORS[constraint.operator](value, constraint.threshold)
    )
    return ConstraintResult(
        metric=constraint.metric,
        evaluation_mode=mode,
        evaluated_value=value,
        satisfied=satisfied,
    )


def _set_path(
    payload: dict[str, object], path: tuple[str | int, ...], value: LeverValue
) -> None:
    if _set_simple_match_tier(payload, path, value):
        return
    cursor: object = payload
    for index, segment in enumerate(path[:-1]):
        if segment == "*":
            employer_match = payload.get("employer_match")
            if not isinstance(employer_match, dict):
                raise ValueError("baseline has no employer_match configuration")
            segment = str(employer_match.get("active_formula", ""))
        next_segment = path[index + 1]
        if isinstance(segment, int):
            if not isinstance(cursor, list) or segment >= len(cursor):
                raise ValueError(f"baseline cannot resolve optimizer path {path}")
            cursor = cursor[segment]
        else:
            if not isinstance(cursor, dict) or segment not in cursor:
                raise ValueError(f"baseline cannot resolve optimizer path {path}")
            cursor = cursor[segment]
        if isinstance(next_segment, int) and not isinstance(cursor, list):
            raise ValueError(f"baseline cannot resolve optimizer path {path}")
    leaf = path[-1]
    if isinstance(leaf, int):
        if not isinstance(cursor, list) or leaf >= len(cursor):
            raise ValueError(f"baseline cannot resolve optimizer path {path}")
        cursor[leaf] = value
    elif isinstance(cursor, dict):
        cursor[leaf] = value
    else:
        raise ValueError(f"baseline cannot resolve optimizer path {path}")


def _set_simple_match_tier(
    payload: dict[str, object], path: tuple[str | int, ...], value: LeverValue
) -> bool:
    """Treat tier one as the flat active formula when it has no tiers array."""
    if "tiers" not in path:
        return False
    employer_match = payload.get("employer_match")
    if not isinstance(employer_match, dict):
        return False
    formulas = employer_match.get("formulas")
    active = employer_match.get("active_formula")
    formula = formulas.get(active) if isinstance(formulas, dict) else None
    tier_position = path.index("tiers") + 1
    if not isinstance(formula, dict) or "tiers" in formula or path[tier_position] != 0:
        return False
    leaf = path[-1]
    target = "max_match_percentage" if leaf == "employee_max" else leaf
    if not isinstance(target, str):
        return False
    formula[target] = value
    return True
