"""Per-employee plan-design assignment configuration."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, RootModel, model_validator


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


class MatchTier(BaseModel):
    """One cumulative deferral-rate match tier."""

    employee_min: float = Field(ge=0.0, le=1.0)
    employee_max: float = Field(gt=0.0, le=1.0)
    match_rate: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "MatchTier":
        if self.employee_max <= self.employee_min:
            raise ValueError("match tier employee_max must exceed employee_min")
        return self


class ServiceMatchBand(BaseModel):
    """One service- or points-based match band."""

    min_value: int = Field(ge=0)
    max_value: int | None = Field(default=None, ge=0)
    match_rate: float = Field(ge=0.0, le=1.0)
    max_deferral_pct: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "ServiceMatchBand":
        if self.max_value is not None and self.max_value <= self.min_value:
            raise ValueError("match band max_value must exceed min_value")
        return self


class TenureGradedBand(BaseModel):
    """One tenure band carrying cumulative deferral match tiers."""

    min_years: int = Field(ge=0)
    max_years: int | None = Field(default=None, ge=0)
    tiers: list[MatchTier] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_band(self) -> "TenureGradedBand":
        if self.max_years is not None and self.max_years <= self.min_years:
            raise ValueError("tenure band max_years must exceed min_years")
        _validate_nonoverlapping_match_tiers(self.tiers, "tenure-graded match tiers")
        return self


class MatchParameterSet(BaseModel):
    """Numeric inputs for the run-global match formula family."""

    cap_percent: float = Field(ge=0.0, le=1.0)
    tiers: list[MatchTier] = Field(default_factory=list)
    graded_schedule: list[ServiceMatchBand] = Field(default_factory=list)
    tenure_graded_bands: list[TenureGradedBand] = Field(default_factory=list)
    points_tiers: list[ServiceMatchBand] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_schedules(self) -> "MatchParameterSet":
        _validate_nonoverlapping_match_tiers(self.tiers, "match tiers")
        _validate_nonoverlapping_bands(self.graded_schedule, "graded match schedule")
        _validate_nonoverlapping_bands(self.points_tiers, "points match schedule")
        _validate_tenure_bands(self.tenure_graded_bands)
        return self


class CoreServiceBand(BaseModel):
    """One service band for a graded core contribution."""

    min_years: int = Field(ge=0)
    max_years: int | None = Field(default=None, ge=0)
    rate: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "CoreServiceBand":
        if self.max_years is not None and self.max_years <= self.min_years:
            raise ValueError("core band max_years must exceed min_years")
        return self


class CoreParameterSet(BaseModel):
    """Numeric flat and service-graded core inputs."""

    contribution_rate: float = Field(ge=0.0, le=1.0)
    graded_schedule: list[CoreServiceBand] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_schedule(self) -> "CoreParameterSet":
        ordered = sorted(self.graded_schedule, key=lambda band: band.min_years)
        for previous, current in zip(ordered, ordered[1:]):
            if previous.max_years is None or current.min_years < previous.max_years:
                raise ValueError("core graded schedule bands overlap")
        return self


class AutoEnrollmentParameterSet(BaseModel):
    """Per-design automatic enrollment terms."""

    default_deferral_rate: float = Field(ge=0.0, le=1.0)
    window_days: int = Field(ge=0)
    scope: Literal["all_eligible_employees", "new_hires_only"]


class EscalationParameterSet(BaseModel):
    """Per-design automatic escalation numeric terms."""

    increment: float = Field(ge=0.0, le=1.0)
    cap: float = Field(ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_increment(self) -> "EscalationParameterSet":
        if self.increment > self.cap:
            raise ValueError("deferral escalation increment cannot exceed cap")
        return self


class EligibilityParameterSet(BaseModel):
    """Per-design plan eligibility waiting-period terms."""

    waiting_period_days: int = Field(ge=0)


class PlanDesignParameters(BaseModel):
    """Complete Tier 1 parameter definition for one design."""

    match: MatchParameterSet
    employer_core: CoreParameterSet
    auto_enrollment: AutoEnrollmentParameterSet
    deferral_escalation: EscalationParameterSet
    eligibility: EligibilityParameterSet


class PlanDesignParametersMap(RootModel[dict[str, PlanDesignParameters]]):
    """Strict map of design identifiers to Tier 1 parameter definitions."""

    @model_validator(mode="after")
    def validate_designs(self) -> "PlanDesignParametersMap":
        for design_id, parameters in self.root.items():
            if not design_id or design_id != design_id.strip():
                raise ValueError(
                    "plan design parameter ids must be nonblank and trimmed"
                )
            try:
                parameters.match.validate_schedules()
            except ValueError as exc:
                raise ValueError(f"{design_id} {exc}") from exc
        return self

    def design_ids(self) -> list[str]:
        """Return deterministic configured identifiers."""
        return sorted(self.root)

    def to_dbt_payload(self) -> dict[str, object]:
        """Return a JSON-compatible payload ordered by design identifier."""
        return {
            design_id: self.root[design_id].model_dump(mode="json")
            for design_id in self.design_ids()
        }


def _validate_nonoverlapping_match_tiers(tiers: list[MatchTier], label: str) -> None:
    ordered = sorted(tiers, key=lambda tier: tier.employee_min)
    for previous, current in zip(ordered, ordered[1:]):
        if current.employee_min < previous.employee_max:
            raise ValueError(f"{label} overlap")


def _validate_nonoverlapping_bands(bands: list[ServiceMatchBand], label: str) -> None:
    ordered = sorted(bands, key=lambda band: band.min_value)
    for previous, current in zip(ordered, ordered[1:]):
        if previous.max_value is None or current.min_value < previous.max_value:
            raise ValueError(f"{label} bands overlap")


def _validate_tenure_bands(bands: list[TenureGradedBand]) -> None:
    ordered = sorted(bands, key=lambda band: band.min_years)
    for previous, current in zip(ordered, ordered[1:]):
        if previous.max_years is None or current.min_years < previous.max_years:
            raise ValueError("tenure-graded match bands overlap")
