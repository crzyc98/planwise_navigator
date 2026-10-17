"""Versioned, explicit assumptions for elective-deferral source reporting."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class EmployerWageEvidence(BaseModel):
    """Section 3121(a) wages, never inferred from simulation compensation."""

    model_config = ConfigDict(extra="forbid")
    employee_id: str = Field(min_length=1)
    employer_id: str = Field(min_length=1)
    wage_year: int = Field(ge=2024)
    wages: Decimal = Field(ge=0, max_digits=14, decimal_places=2)
    basis: Literal["confirmed", "forecast"]
    provenance: str = Field(min_length=1)


class ProjectedRothThreshold(BaseModel):
    model_config = ConfigDict(extra="forbid")
    year: int = Field(ge=2027)
    threshold: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    provenance: str = Field(min_length=1)


class ContributionSourceSettings(BaseModel):
    """Reporting allocation only; does not change deferral or match events."""

    model_config = ConfigDict(extra="forbid")
    policy: Literal["legacy_estimate", "assumed_split"] = "legacy_estimate"
    roth_fraction: Decimal = Field(
        default=Decimal("0.15"), ge=0, le=1, decimal_places=8
    )
    roth_available: bool = True
    mandatory_roth_enabled: bool = False
    applicability: Literal["single_employer_401k", "unsupported"] = "unsupported"
    employer_id: str | None = Field(default=None, min_length=1)
    wage_evidence: list[EmployerWageEvidence] = Field(default_factory=list)
    projected_thresholds: list[ProjectedRothThreshold] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_policy(self) -> "ContributionSourceSettings":
        if self.policy == "legacy_estimate" and self.roth_fraction != Decimal("0.15"):
            raise ValueError("Use assumed_split for a non-legacy Roth fraction")
        if not self.roth_available and self.roth_fraction != 0:
            raise ValueError(
                "A plan without Roth requires assumed_split and roth_fraction: 0"
            )
        if self.mandatory_roth_enabled and not self.employer_id:
            raise ValueError("Mandatory Roth modeling requires employer_id")
        keys = [(w.employee_id, w.employer_id, w.wage_year) for w in self.wage_evidence]
        if len(keys) != len(set(keys)):
            raise ValueError("Duplicate employee/employer/wage-year evidence")
        years = [t.year for t in self.projected_thresholds]
        if len(years) != len(set(years)):
            raise ValueError("Duplicate projected threshold year")
        return self
