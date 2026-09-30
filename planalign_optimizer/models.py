"""Validated optimizer specifications and immutable run results."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

LeverValue = str | int | float | bool


class LeverSpec(BaseModel):
    """One declared configuration lever and its allowed values."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(min_length=1)
    kind: Literal["discrete", "continuous"]
    choices: tuple[LeverValue, ...] | None = None
    bounds: tuple[float, float] | None = None

    @model_validator(mode="after")
    def validate_value_domain(self) -> "LeverSpec":
        if self.kind == "discrete":
            if not self.choices or self.bounds is not None:
                raise ValueError(
                    f"discrete lever '{self.name}' requires non-empty choices and no bounds"
                )
        elif self.bounds is None or self.choices is not None:
            raise ValueError(
                f"continuous lever '{self.name}' requires bounds and no choices"
            )
        elif self.bounds[0] >= self.bounds[1]:
            raise ValueError(
                f"continuous lever '{self.name}' requires bounds min < max"
            )
        return self


class DesignSpaceSpec(BaseModel):
    """The complete set of levers the optimizer may mutate."""

    model_config = ConfigDict(frozen=True)
    levers: tuple[LeverSpec, ...] = Field(default_factory=tuple)

    @model_validator(mode="after")
    def reject_duplicate_names(self) -> "DesignSpaceSpec":
        names = [lever.name for lever in self.levers]
        duplicates = sorted({name for name in names if names.count(name) > 1})
        if duplicates:
            raise ValueError(f"duplicate lever name(s): {', '.join(duplicates)}")
        return self


class ObjectiveTerm(BaseModel):
    """One metric optimization direction."""

    model_config = ConfigDict(frozen=True)
    metric: str = Field(min_length=1)
    direction: Literal["minimize", "maximize"]


class ConstraintSpec(BaseModel):
    """One hard metric guardrail."""

    model_config = ConfigDict(frozen=True)
    metric: str = Field(min_length=1)
    operator: Literal["<=", ">=", "<", ">", "=="]
    threshold: float
    percentile: int | None = Field(
        default=None,
        ge=1,
        le=99,
        description=(
            "Evaluate the metric at this ensemble percentile. Only takes effect "
            "when baseline.ensemble_database is also set."
        ),
    )


class ObjectiveConstraintSpec(BaseModel):
    """The objectives and hard constraints for a search."""

    model_config = ConfigDict(frozen=True)
    objectives: tuple[ObjectiveTerm, ...] = Field(
        min_length=1,
        max_length=2,
        description="1 entry ranks candidates; 2 entries unlock the Pareto frontier.",
    )
    constraints: tuple[ConstraintSpec, ...] = Field(default_factory=tuple)


class BaselineSpec(BaseModel):
    """Location of the baseline simulation configuration."""

    model_config = ConfigDict(frozen=True)
    config_path: Path
    ensemble_database: Path | None = None


class OptimizerSpec(BaseModel):
    """Top-level user-authored optimizer request."""

    model_config = ConfigDict(frozen=True)
    design_space: DesignSpaceSpec
    objective: ObjectiveConstraintSpec
    baseline: BaselineSpec


class ConstraintResult(BaseModel):
    """Evaluated outcome for one declared constraint."""

    model_config = ConfigDict(
        frozen=True, json_schema_serialization_defaults_required=True
    )
    metric: str
    evaluation_mode: Literal["point_estimate", "percentile"]
    evaluated_value: float | None = None
    satisfied: bool | None = None


class Candidate(BaseModel):
    """One evaluated or exactly deduplicated design point."""

    model_config = ConfigDict(
        frozen=True, json_schema_serialization_defaults_required=True
    )
    candidate_id: str
    lever_values: dict[str, LeverValue]
    db_path: Path | None = None
    status: Literal["feasible", "infeasible", "non_evaluable", "failed"]
    objective_values: dict[str, float | None] = Field(default_factory=dict)
    constraint_results: tuple[ConstraintResult, ...] = Field(default_factory=tuple)
    is_duplicate_of: str | None = None
    duration_seconds: float = Field(default=0.0, ge=0)


class OptimizerRun(BaseModel):
    """Immutable output of one bounded optimizer invocation."""

    model_config = ConfigDict(
        frozen=True, json_schema_serialization_defaults_required=True
    )
    run_id: str
    design_space: DesignSpaceSpec
    objective_constraint_spec: ObjectiveConstraintSpec
    max_runs: int = Field(ge=1)
    search_seed: int
    baseline_config_fingerprint: str
    candidates: tuple[Candidate, ...] = Field(default_factory=tuple)
    ranked_feasible: tuple[str, ...] = Field(
        default_factory=tuple,
        description="Populated only for single-objective runs, best first.",
    )
    pareto_frontier: tuple[str, ...] | None = Field(
        default=None,
        description="Populated only for 2-objective runs; null otherwise.",
    )
    binding_infeasible_constraints: tuple[str, ...] | None = Field(
        default=None,
        description=(
            "Set only when no candidate was ranked or on the frontier: names the "
            "constraint(s) nobody satisfied. Surface this prominently."
        ),
    )
