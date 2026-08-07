"""Load and validate optimizer YAML specifications."""

from __future__ import annotations

from pathlib import Path
from typing import Mapping

import yaml
from pydantic import ValidationError

from .design_space import LEVER_REGISTRY
from .metrics import OBJECTIVE_METRICS, SUPPORTED_METRICS
from .models import OptimizerSpec

MAX_LEVERS = 8


class OptimizerSpecError(ValueError):
    """A specific user-correctable optimizer specification error."""


def load_spec(path: Path | str) -> OptimizerSpec:
    """Parse and fully validate one optimizer YAML file before any run starts."""
    spec_path = Path(path)
    if not spec_path.exists():
        raise OptimizerSpecError(f"optimizer spec not found: {spec_path}")
    try:
        raw = yaml.safe_load(spec_path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise OptimizerSpecError(
            f"invalid YAML in optimizer spec {spec_path}: {exc}"
        ) from exc
    if not isinstance(raw, Mapping):
        raise OptimizerSpecError("optimizer spec root must be a mapping")
    try:
        spec = OptimizerSpec.model_validate(dict(raw))
    except ValidationError as exc:
        raise OptimizerSpecError(f"invalid optimizer spec: {exc}") from exc
    return validate_spec(spec)


def validate_spec(spec: OptimizerSpec) -> OptimizerSpec:
    """Validate registered levers and the shared metric vocabulary."""
    if len(spec.design_space.levers) > MAX_LEVERS:
        raise OptimizerSpecError(
            f"design_space declares {len(spec.design_space.levers)} levers; v1 supports at most {MAX_LEVERS}"
        )
    for lever in spec.design_space.levers:
        if lever.name not in LEVER_REGISTRY:
            raise OptimizerSpecError(f"unknown optimizer lever '{lever.name}'")
    for objective in spec.objective.objectives:
        if objective.metric not in OBJECTIVE_METRICS:
            raise OptimizerSpecError(_unknown_metric_message(objective.metric))
    for constraint in spec.objective.constraints:
        if constraint.metric not in SUPPORTED_METRICS:
            raise OptimizerSpecError(_unknown_metric_message(constraint.metric))
    return spec


def dump_resolved_spec(spec: OptimizerSpec, path: Path) -> None:
    """Write the validated, baseline-resolved request as YAML."""
    path.write_text(
        yaml.safe_dump(spec.model_dump(mode="json"), sort_keys=False),
        encoding="utf-8",
    )


def _unknown_metric_message(metric: str) -> str:
    supported = ", ".join(SUPPORTED_METRICS)
    return f"unknown optimizer metric '{metric}'; supported metrics: {supported}"
