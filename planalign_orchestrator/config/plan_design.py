"""Per-employee plan-design assignment configuration."""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import BaseModel, Field, RootModel, field_validator, model_validator

MatchFormulaFamily = Literal[
    "deferral_based", "graded_by_service", "tenure_graded", "points_based"
]
CoreFormulaFamily = Literal["flat", "graded_by_service", "points_based", "age_banded"]


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
    """Formula selector and numeric inputs for one design's match."""

    family: MatchFormulaFamily | None = None
    match_template: str | None = Field(default=None, min_length=1)
    cap_percent: float = Field(ge=0.0, le=1.0)
    tiers: list[MatchTier] = Field(default_factory=list)
    graded_schedule: list[ServiceMatchBand] = Field(default_factory=list)
    tenure_graded_bands: list[TenureGradedBand] = Field(default_factory=list)
    points_tiers: list[ServiceMatchBand] = Field(default_factory=list)

    @field_validator("family", mode="before")
    @classmethod
    def normalize_legacy_family(cls, value: object) -> object:
        """Keep the supported pre-Feature-099 alias readable."""
        return "tenure_graded" if value == "tenure_based" else value

    @model_validator(mode="after")
    def validate_schedules(self) -> "MatchParameterSet":
        _validate_nonoverlapping_match_tiers(self.tiers, "match tiers")
        # Cross-band gaps and overlaps are valid diagnostic fixtures at load time.
        # The calculation guard validates exactly-one resolution against the
        # employees actually in scope, avoiding false rejection of unused ranges.
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


class CoreAgeBand(BaseModel):
    """One half-open age band with a percentage-valued rate."""

    min_age: int = Field(ge=0)
    max_age: int | None = Field(default=None, ge=0)
    rate: float = Field(ge=0.0, le=100.0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "CoreAgeBand":
        if self.max_age is not None and self.max_age <= self.min_age:
            raise ValueError("core age band max_age must exceed min_age")
        return self


class CorePointsBand(BaseModel):
    """One half-open age-plus-service points band with a percentage rate."""

    min_points: int = Field(ge=0)
    max_points: int | None = Field(default=None, ge=0)
    rate: float = Field(ge=0.0, le=100.0)

    @model_validator(mode="after")
    def validate_bounds(self) -> "CorePointsBand":
        if self.max_points is not None and self.max_points <= self.min_points:
            raise ValueError("core points band max_points must exceed min_points")
        return self


class CoreParameterSet(BaseModel):
    """Formula selector, schedules, and integration inputs for one design."""

    family: CoreFormulaFamily | None = None
    contribution_rate: float = Field(ge=0.0, le=1.0)
    graded_schedule: list[CoreServiceBand] = Field(default_factory=list)
    age_schedule: list[CoreAgeBand] = Field(default_factory=list)
    points_schedule: list[CorePointsBand] = Field(default_factory=list)
    integration_enabled: bool | None = None
    integration_level_mode: Literal[
        "ss_wage_base", "explicit", "percent_of_ss_wage_base", "fixed_dollar"
    ] | None = None
    integration_level_value: int | None = Field(default=None, ge=0)
    integration_disparity_rate: float | None = Field(default=None, ge=0.0, le=1.0)

    @model_validator(mode="after")
    def validate_schedule(self) -> "CoreParameterSet":
        if (
            self.integration_level_mode
            in {"explicit", "percent_of_ss_wage_base", "fixed_dollar"}
            and self.integration_level_value is None
        ):
            raise ValueError(
                "integration_level_value is required for an explicit, percent, or fixed integration level"
            )
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
        for design_id in self.root:
            if not design_id or design_id != design_id.strip():
                raise ValueError(
                    "plan design parameter ids must be nonblank and trimmed"
                )
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
