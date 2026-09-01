"""Per-employee plan-design assignment configuration."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, model_validator


class HireDateCutoffRule(BaseModel):
    """Assign employees hired on or after a cutoff to a design."""

    type: Literal["hire_date_cutoff"] = "hire_date_cutoff"
    cutoff: date
    plan_design_id: str = Field(min_length=1)


class PlanDesignAssignmentSettings(BaseModel):
    """Ordered assignment rules plus the fallback design."""

    default_plan_design_id: str = Field(min_length=1)
    rules: list[HireDateCutoffRule] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_design_ids(self) -> "PlanDesignAssignmentSettings":
        """Reject whitespace identifiers and ambiguous duplicate cutoffs."""
        design_ids = [
            self.default_plan_design_id,
            *(r.plan_design_id for r in self.rules),
        ]
        if any(design_id != design_id.strip() for design_id in design_ids):
            raise ValueError(
                "plan design ids must not have leading or trailing whitespace"
            )
        cutoffs = [rule.cutoff for rule in self.rules]
        if len(cutoffs) != len(set(cutoffs)):
            raise ValueError("hire-date cutoff rules must use distinct cutoff dates")
        return self

    def design_set(self) -> list[str]:
        """Return the deterministic set of designs represented by this config."""
        return sorted(
            {self.default_plan_design_id, *(r.plan_design_id for r in self.rules)}
        )
