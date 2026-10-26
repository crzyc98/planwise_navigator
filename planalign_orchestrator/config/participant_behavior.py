"""Run-global participant behavior configuration (epic #986, D5)."""

from __future__ import annotations

from datetime import date, datetime
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

Rate = Annotated[float, Field(ge=0, le=1)]
AIPMode = Literal["automatic", "participant_elected"]


def validate_weights(weights: list[float]) -> None:
    """Require a probability distribution, within the documented tolerance."""
    if abs(sum(weights) - 1.0) > 1e-6:
        raise ValueError("weights/shares must sum to 1 (tolerance 1e-6)")


class EasyEnrollPackage(BaseModel):
    rate: float = Field(
        gt=0, le=1, description="Decimal 0–1 (0.06 = 6%) of pay deferred."
    )
    share: Rate = Field(
        description="Package share, decimal 0–1; package shares must sum to 1 (±1e-6)."
    )


class EasyEnrollSettings(BaseModel):
    enabled: bool = False
    channel_share: Rate = 0.35
    packages: list[EasyEnrollPackage] = Field(
        default_factory=lambda: [
            EasyEnrollPackage(rate=0.06, share=0.30),
            EasyEnrollPackage(rate=0.08, share=0.50),
            EasyEnrollPackage(rate=0.10, share=0.20),
        ],
        min_length=1,
    )
    escalation_cap: Rate = 0.10

    @field_validator("packages")
    @classmethod
    def check_packages(
        cls, packages: list[EasyEnrollPackage]
    ) -> list[EasyEnrollPackage]:
        validate_weights([package.share for package in packages])
        return packages


class BelowDefaultTier(BaseModel):
    max_auto_enroll_default_rate: Rate | None = Field(
        description="Inclusive auto-enrollment default rate ceiling, decimal 0–1 (0.06 = 6%); null is the final open-ended tier."
    )
    share: Rate = Field(
        description="Share of enrollees choosing a rate below the default in this tier, decimal 0–1; tier shares are independent and need not sum to 1."
    )


class DeferralChangeStep(BaseModel):
    pp: int = Field(
        gt=0,
        strict=True,
        description="Whole percentage points; 1 means a one-percentage-point change.",
    )
    weight: Rate = Field(
        description="Step probability weight, decimal 0–1; list weights must sum to 1 (±1e-6)."
    )


class BelowDefaultSettings(BaseModel):
    share_tiers: list[BelowDefaultTier] = Field(
        default_factory=lambda: [
            BelowDefaultTier(max_auto_enroll_default_rate=None, share=0.0)
        ],
        min_length=1,
    )
    steps: list[DeferralChangeStep] = Field(
        default_factory=lambda: [
            DeferralChangeStep(pp=pp, weight=weight)
            for pp, weight in [(1, 0.50), (2, 0.30), (3, 0.20)]
        ]
    )

    @field_validator("share_tiers")
    @classmethod
    def check_tiers(cls, tiers: list[BelowDefaultTier]) -> list[BelowDefaultTier]:
        bounds = [tier.max_auto_enroll_default_rate for tier in tiers]
        if bounds.count(None) != 1 or bounds[-1] is not None:
            raise ValueError(
                "share_tiers must have exactly one open-ended (null) tier, last"
            )
        closed = [bound for bound in bounds if bound is not None]
        if any(left >= right for left, right in zip(closed, closed[1:])):
            raise ValueError(
                "share_tiers must be ordered by max_auto_enroll_default_rate ascending"
            )
        return tiers

    @field_validator("steps")
    @classmethod
    def check_steps(cls, steps: list[DeferralChangeStep]) -> list[DeferralChangeStep]:
        validate_weights([step.weight for step in steps])
        return steps


class DeferralChangeRates(BaseModel):
    increase_probability: Rate
    decrease_probability: Rate


class DeferralRateChangesSettings(BaseModel):
    enabled: bool = False
    with_escalation: DeferralChangeRates = Field(
        default_factory=lambda: DeferralChangeRates(
            increase_probability=0.03, decrease_probability=0.15
        )
    )
    without_escalation: DeferralChangeRates = Field(
        default_factory=lambda: DeferralChangeRates(
            increase_probability=0.25, decrease_probability=0.075
        )
    )
    increase_steps: list[DeferralChangeStep] = Field(
        default_factory=lambda: [
            DeferralChangeStep(pp=pp, weight=weight)
            for pp, weight in [
                (1, 0.15),
                (2, 0.20),
                (3, 0.15),
                (5, 0.20),
                (7, 0.15),
                (10, 0.15),
            ]
        ]
    )
    decrease_steps: list[DeferralChangeStep] = Field(
        default_factory=lambda: [
            DeferralChangeStep(pp=pp, weight=weight)
            for pp, weight in [(1, 0.15), (2, 0.25), (3, 0.20), (5, 0.20), (8, 0.20)]
        ]
    )
    post_escalation_decrease_window_days: int = Field(default=90, ge=0, strict=True)
    post_escalation_decrease_leaves_escalation: bool = False
    stop_probability: Rate = 0.015
    restart_probability: Rate = 0.0

    @field_validator("increase_steps", "decrease_steps")
    @classmethod
    def check_steps(cls, steps: list[DeferralChangeStep]) -> list[DeferralChangeStep]:
        validate_weights([step.weight for step in steps])
        return steps


class DeferralAutoEscalationSettings(BaseModel):
    """Typed legacy fields; only explicitly supplied legacy keys are exported."""

    model_config = ConfigDict(validate_assignment=True)

    enabled: bool = True
    mode: AIPMode = "automatic"
    participant_elected_signup_probability: Rate = 0.0
    effective_day: str | None = None
    increment_amount: Rate | None = None
    maximum_rate: Rate | None = None
    hire_date_cutoff: str | None = None
    require_active_enrollment: bool = True
    first_escalation_delay_years: int | None = Field(default=None, ge=0)

    @field_validator("effective_day", "hire_date_cutoff", mode="before")
    @classmethod
    def normalize_dates(cls, value: Any) -> Any:
        """Preserve ISO strings for YAML's unquoted date/timestamp values."""
        return value.isoformat() if isinstance(value, (date, datetime)) else value


def escalation_settings(value: Any) -> DeferralAutoEscalationSettings:
    """Accept legacy callers that assign dictionaries after config loading."""
    return DeferralAutoEscalationSettings.model_validate(value)
